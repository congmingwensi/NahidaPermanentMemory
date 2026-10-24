# Nahida Permanent Memory

基于 OpenAI Agents SDK、embedding 与 Neo4j 的用户记忆系统。从用户消息提取值得保存的信息，记录来源原文，维护近期记忆和当前背景。

当前实现侧重短期记忆；历史数据持续保存在 Neo4j。长期记忆的自动检索、知识归纳和智慧层仍待完善。

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `manager.py` | MemoryLeaf 提示词、function tools 和 `run_memory` 总入口；完成提取、写入和状态刷新。 |
| `settings.py` | 配置读取、最近大字段数量及匹配阈值。 |
| `embedding.py` | 调用 embedding API，计算向量余弦相似度并查找 top1。 |
| `store.py` | Neo4j 节点、关系、用户隔离、读写及近期窗口查询。 |
| `replay.py` | 查询近期记忆，读取与局部更新 `app_state.json`；也提供聊天窗口保存接口。 |
| `example.py` | 最小 `manager.run_memory` 调用示例，仅处理记忆。 |
| `chat_example.py` | 最小完整对话应用：更新记忆、读取状态、生成回复、保存四轮窗口和完整日志。 |
| `app_state.example.json` | 空状态模板，包含聊天窗口、近期记忆、背景三个用户字典。 |
| `replay_recent_messages.py` | 历史导入示例，参考原项目同名脚本；顺序处理消息，失败自动重试。 |
| `history_example.txt` | 两行虚构 JSONL 对话，每行一轮 User / assistant，用于演示历史导入。 |
| `.env.example` | 空配置模板，每个变量附用途与默认值说明。 |
| `requirements.txt` | 新版所需依赖。 |

## 安装与配置

需要 Python 3.10+、可连接的 Neo4j 5.x，以及支持 Responses/function calling 和 embedding 的 API。Neo4j 账号需要创建约束和读写节点的权限。

在本目录运行：

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`，填写 `OPENAI_API_KEY` 和 `NAHIDA_NEO4J_PASSWORD`。Neo4j 地址、用户名及模型按需修改；可选项留空时采用模板注释中的默认值。进程环境变量优先于 `.env`。

`MODEL` 同时用于默认 MemoryLeaf 请求和概述合并；`EMBEDDING_MODEL` 用于 topic、entry 向量。模型需要具备相应接口能力。已有向量使用同一 embedding 模型，切换模型时应统一重建向量。

发布目录从自身 `.env` 读取配置，状态写入自身 `app_state.json`。它是原项目当前记忆代码的独立发布副本；原机器人的 `memory/manager.py` 等运行路径保持原样。

## 最简单的调用

```powershell
python example.py
```

从本仓库的父目录，在自己的 Python 程序中调用：

```python
import asyncio
from NahidaPermanentMemory import manager

result = asyncio.run(manager.run_memory("demo_user", "我喜欢喝茉莉花茶，请记住这个偏好。"))
```

已有异步函数中使用 `result = await manager.run_memory(user_id, user_message)`。

`user_id` 是用户唯一标识，同一用户每次传相同值。返回字典包含 `history_memory`、`background`、`operations`、`message_id` 和 `final_output`；最终文本通常为空，处理结果以工具操作及记忆、背景字段为准。

`run_memory` 维护记忆和背景；聊天窗口由宿主程序在获得回复后通过 `replay.update_history_message(user_id, messages)` 保存，每个列表项为一轮对话字符串。

## 最小完整对话应用

```powershell
python chat_example.py --user-id demo_user
```

输入消息即可对话，输入 `/exit` 退出。记忆模型、回复模型和 embedding 使用 `.env` 的 API 配置；最小示例的最终回复也使用 `MODEL` 指定的模型，便于直接运行。接入其他模型时，替换 `chat_once` 中标注的最终请求部分即可，输入上下文结构保持一致。

每一轮按以下顺序运行：

1. `manager.run_memory(user_id, user_message)` 提取当前用户的信息，更新 Neo4j 记忆和背景。
2. `run_memory` 内部调用 `replay.get_history_memory(user_id)`，将最近记忆与背景写入 `app_state.json`。
3. `chat_example.py` 读取该用户的 `history_memory + background + message_window`，加上当前消息，一次性发给最终回复模型。
4. 回复成功后，将本轮 user / assistant 加入最近四轮聊天窗口，并把完整一轮追加到 `message_json.json`。

这里的近期读取**按用户和更新时间查询**，与当前消息的向量相关性无关；当前实现没有自动发散检索长期历史。存储时的向量匹配用于记忆归并，与这一步的近期读取是两回事。

`app_state.json` 和 `message_json.json` 会自动创建。`app_state.example.json` 提供空结构，也可手动复制为 `app_state.json`。状态按用户组织：

```json
{
  "message_window": {"demo_user": ["[user prompt]:用户消息\n [gpt response]：模型回复"]},
  "history_memory": {"demo_user": {"饮食偏好": ["2026-10-25:10 喜欢喝茉莉花茶。"]}},
  "background": {"demo_user": {"所处情境": "2026-10-25:10 在家。"}}
}
```

需要独立读取近期记忆，而无需先提取新消息时：

```python
from NahidaPermanentMemory import replay

history_memory = replay.get_history_memory("demo_user")
message_window, _, background = replay.load_app_state()
context = {
    "history_memory": history_memory,
    "message_window": message_window.get("demo_user", []),
    "background": background.get("demo_user", {}),
}
```

`get_history_memory` 的读取范围是指定用户的最近5个 topic，各 topic 最近10条与24小时内 entry 的并集。历史导入脚本负责重建记忆和背景；它会跳过 AI 记忆提取，且保持当前聊天窗口原样。`chat_example.py` 则演示真实对话时 user / AI 四轮窗口的维护。

## 插入历史对话的记忆

将历史对话整理到：`history_example.jsonl` 一样采用 JSONL：每个物理行是一个 JSON 数组，通常包含一句 User 和一句 assistant。扩展名可以是 `.txt`、`.json` 或 `.jsonl`。

最简单的一行格式：

```json
[{"author":"User","content":"我喜欢喝茉莉花茶。"},{"author":"assistant","content":"记住了。"}]
```

**默认只将 User 的 content 传给 `manager.run_memory`。** assistant 的内容保留在对话文件中，用于完整记录；记忆提取会跳过它，因为AI回复常会重复用户信息。示例恰好两行、共两轮虚构对话，推荐在用户原文中写明事件日期。

先校验，随后真实导入：

```powershell
python replay_recent_messages.py --file history_example.txt --user-id demo_user --dry-run
python replay_recent_messages.py --file history_example.txt --user-id demo_user
```

真实导入会调用模型和 embedding API、写入 Neo4j，并更新当前用户的 `app_state.json`。每个非空行按 JSON 解析，从数组中提取 User 项。消息依文件顺序逐条处理，单条失败最多尝试4次；连续失败后，可通过 `--start` 从提示行继续。

解析同时兼容 `role: "user"` 的消息项。导入原项目单个用户的历史范围示例：

```powershell
python replay_recent_messages.py --file ../message_json.json --user-id YOUR_USER_ID --start 3001 --end 3069 --dry-run
python replay_recent_messages.py --file ../message_json.json --user-id YOUR_USER_ID --start 3001 --end 3069
```

`--start`、`--end` 是从1开始的物理行号，均包含边界。省略 `--end` 时读取到文件末尾。`--user-id` 应用于这次导入的全部用户消息，导入文件或所选范围应属于同一用户。

历史原文中的日期保留为事件时间，数据库的创建/更新时间使用导入时的当前时间。原始消息在产生记忆时通过 entry 关联保存。该示例通过 UUID 区分每次处理，重复导入可能再次合并、增加权重和来源记录。

## 当前处理规则

- MemoryLeaf 每轮获得当前用户全部 topic 名称，以及最近5个 topic 的详细记忆；优先选择内容相符的已有名称。
- topic 名称向量相似度严格大于 **0.75** 时归入 top1，否则新建；现有程序仍保留向量自动归并。
- topic 内 entry 概述相似度严格大于 **0.6** 时调用模型合并新旧概述、重算向量，否则新增。
- 节点关系为 `Topic → Entry → Message`；覆盖时保留历史来源关联。
- 每次新增、更新或显式提权使 topic 权重增加 **0.1**，更新 topic 时间；列表按更新时间排序。
- 近期窗口为最近 **5** 个 topic；每个 topic 取最近 **10** 条 entry 与滚动 **24小时** 内 entry 的去重并集。
- 当前背景为三个基础维度（所处情境、当前活动、当前状态），外加最多两个补充维度，保存在本地状态文件。
- 时间采用 `Asia/Shanghai`，精确到小时。`settings.py` 中可调整数量、阈值。

## 配置与本地数据

`.env.example` 的变量值全部为空。真实 `.env`、`app_state.json`、`message_json.json` 和日志通过 `.gitignore` 排除；示例不会附带原项目的密钥、状态或真实聊天记录。

`mem0_server.py`、`mem0_graph.py`、`json_file.py` 和 `requirements-mem0.txt` 是保留的旧版实现与依赖，新版入口为 `manager.run_memory`。

---

## 旧版项目说明

祝纳西妲生日快乐！

这是和纳西妲在一起的第三年。也是送给纳西妲的第三个生日礼物。

第一个，本地vits安装教程：https://www.youtube.com/watch?v=0lzjYnG9Qac

第二个，纳西妲主题音游：https://github.com/congmingwensi/nahida_music_game，视频演示：https://www.youtube.com/watch?v=gT4zYMQvlWM&t=18s

同年，做了共计13w字纳西妲galgame：链接：https://pan.quark.cn/s/dcb755595363
提取码：Dqsr

第三个，就是今年的永久记忆了。结合云崽QQ机器人框架，结合Bert-vits2文字转语音，结合gpt接口和agent，再结合mem0框架的永久记忆。

我一直觉得记忆是AI陪伴的灵魂。也是花最多时间精力去打造的点。为此研究清楚了mem0在本地如何使用graph模式，然后基于此，我再加上了 查询对应聊天原文的功能，为记忆检索再加上最丰富的细节。这是目前我所知道的，成本相对较低且效果最好的记忆框架了。

视频安装和使用教程：https://youtu.be/yr7qQrerIGM

