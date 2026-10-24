"""Import User messages in order; adapted from memory/replay_recent_messages.py."""
import argparse
import asyncio
import json
from pathlib import Path

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from NahidaPermanentMemory import manager
else:
    from . import manager


def read_messages(path: Path, start: int = 1, end: int | None = None) -> list[tuple[int, str]]:
    """Parse each line as JSON and return only User content, regardless of file extension."""
    if start < 1 or (end is not None and end < start):
        raise ValueError("行号需要满足 1 <= start <= end")
    messages = []
    last_line = 0
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            last_line = line_number
            if line_number < start:
                continue
            if line.strip():
                row = json.loads(line)
                for item in row if isinstance(row, list) else [row]:
                    if str(item.get("author", item.get("role", ""))).lower() == "user":
                        content = item["content"]
                        if not isinstance(content, str) or not content.strip():
                            raise ValueError(f"第 {line_number} 行用户内容需要为非空文本")
                        messages.append((line_number, content))
            if line_number == end:
                break
    if start > last_line or (end is not None and end > last_line):
        raise ValueError(f"文件只有 {last_line} 行，所选范围超出文件")
    return messages


async def replay_messages(user_id: str, messages: list[tuple[int, str]]) -> None:
    for index, (line_number, content) in enumerate(messages, 1):
        print(f"[{index}/{len(messages)}] line={line_number} user_id={user_id}", flush=True)
        for attempt in range(1, 5):
            try:
                await manager.run_memory(user_id, content)
                break
            except Exception as exc:
                if attempt == 4:
                    raise SystemExit(f"第 {line_number} 行连续失败4次：{type(exc).__name__}；使用 --start {line_number} 继续。") from None
                print(f"第 {line_number} 行失败：{type(exc).__name__}；2秒后重试。", flush=True)
                await asyncio.sleep(2)
    print(f"导入完成：{len(messages)} 条用户消息。")


def main():
    parser = argparse.ArgumentParser(description="将单个用户的历史消息依次导入记忆。")
    parser.add_argument("--file", type=Path, default=Path(__file__).with_name("history_example.jsonl"))
    parser.add_argument("--user-id", required=True, help="本次导入全部消息所属用户的唯一标识")
    parser.add_argument("--start", type=int, default=1, help="起始行，从1开始，包含该行")
    parser.add_argument("--end", type=int, help="结束行，包含该行；省略时读取到文件末尾")
    parser.add_argument("--dry-run", action="store_true", help="解析并显示数量，省略模型调用和数据库写入")
    args = parser.parse_args()
    if not args.user_id.strip():
        parser.error("--user-id 需要为非空字符串")
    messages = read_messages(args.file, args.start, args.end)
    print(f"待导入用户消息：{len(messages)} 条。")
    if args.dry_run:
        for line_number, _ in messages:
            print(f"line={line_number} user_id={args.user_id}")
    else:
        asyncio.run(replay_messages(args.user_id, messages))


if __name__ == "__main__":
    main()
