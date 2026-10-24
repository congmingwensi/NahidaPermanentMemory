"""Run with: python example.py"""
import asyncio

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from NahidaPermanentMemory import manager
else:
    from . import manager


async def main():
    result = await manager.run_memory("demo_user", "我喜欢喝茉莉花茶，请记住这个偏好。")
    print("记忆处理完成，大字段数：", len(result["history_memory"]))


if __name__ == "__main__":
    asyncio.run(main())
