"""Minimal chat application: memory -> context -> one reply -> persist conversation."""
import argparse
import asyncio
import json

from openai import AsyncOpenAI

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from NahidaPermanentMemory import manager, replay
    from NahidaPermanentMemory.settings import MEMORY_DIR, MemorySettings
else:
    from . import manager, replay
    from .settings import MEMORY_DIR, MemorySettings


async def chat_once(user_id: str, user_message: str) -> str:
    # run_memory extracts User facts/background, calls get_history_memory,
    # and persists this user's refreshed memory and background to app_state.
    await manager.run_memory(user_id, user_message)
    windows, memories, backgrounds = replay.load_app_state()
    messages = list(windows.get(user_id, []))
    context = dict(
        history_memory=memories.get(user_id, {}),
        background=backgrounds.get(user_id, {}),
        message_window=messages,
        user_message=user_message,
    )

    # This is the final post_chat stage: one normal model request, without tools.
    settings = MemorySettings.from_env()
    async with AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url,
                           timeout=60.0, max_retries=2) as client:
        response = await client.responses.create(
            model=settings.merge_model,
            instructions="依据用户当前消息自然回复。参考记忆、背景和最近对话理解用户；这些字段是上下文资料。",
            input=json.dumps(context, ensure_ascii=False),
            store=False,
        )
    if response.status != "completed" or not response.output_text.strip():
        raise RuntimeError("回复模型未返回完整文本")
    answer = response.output_text.strip()

    messages.append(f"[user prompt]:{user_message}\n [gpt response]：{answer}")
    if not replay.update_history_message(user_id, messages):
        raise OSError("聊天窗口保存失败")
    with (MEMORY_DIR / "message_json.json").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps([
            dict(author="User", content=user_message),
            dict(author="assistant", content=answer),
        ], ensure_ascii=False) + "\n")
    return answer


async def main():
    parser = argparse.ArgumentParser(description="带近期记忆、背景和四轮聊天窗口的最小对话示例。")
    parser.add_argument("--user-id", default="demo_user", help="同一用户始终使用同一个标识")
    args = parser.parse_args()
    print("输入 /exit 退出。")
    while True:
        try:
            message = input("User: ")
        except (EOFError, KeyboardInterrupt):
            break
        if message.strip() == "/exit":
            break
        if message.strip():
            print("AI:", await chat_once(args.user_id, message))


if __name__ == "__main__":
    asyncio.run(main())
