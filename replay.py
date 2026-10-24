"""Recent memory queries and local application state persistence."""
import json
from contextlib import closing
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from threading import RLock

from .settings import HISTORY_TOPIC_LIMIT, MEMORY_DIR, MemorySettings
from .store import Neo4jMemoryStore

APP_STATE_PATH = MEMORY_DIR / "app_state.json"
STATE_LOCK = RLock()


def get_history_memory(user_id: str) -> dict[str, list[str]]:
    """按配置读取用户近期大字段，每个字段取最近十条与24小时内小字段的并集。"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    cutoff = (now - timedelta(hours=24)).strftime("%Y-%m-%d:%H")
    with closing(Neo4jMemoryStore(MemorySettings.from_env())) as store:
        topics = store.get_recent_topics(user_id, HISTORY_TOPIC_LIMIT, cutoff)
    return {
        topic["name"]: [f'{entry["updatetime"]} {entry["summary"]}' for entry in topic["entries"]]
        for topic in topics
    }


def load_app_state() -> tuple[dict, dict, dict]:
    """从 app_state.json 返回 message_window、history_memory、background。"""
    with STATE_LOCK:
        if APP_STATE_PATH.exists():
            try:
                with APP_STATE_PATH.open("r", encoding="utf-8") as handle:
                    state = json.load(handle)
                return (
                    state.get("message_window", {}),
                    state.get("history_memory", {}),
                    state.get("background", {}),
                )
            except Exception as exc:
                print(f"读取状态失败: {exc}")
        return {}, {}, {}


def _save_app_state(message_window: dict, history_memory: dict, background: dict) -> bool:
    try:
        state = {"message_window": message_window, "history_memory": history_memory, "background": background}
        with APP_STATE_PATH.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=4)
        return True
    except Exception as exc:
        print(f"保存状态失败: {exc}")
        return False


def update_history_memory(user_id: str, history_memory: dict | None = None,
                          background: dict | None = None) -> bool:
    """更新指定用户的记忆和背景；省略的参数保留文件中的已有值。"""
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("用户 ID 需要为非空字符串")
    with STATE_LOCK:
        mw, hm, bg = load_app_state()
        if history_memory is not None:
            hm[user_id] = history_memory
        if background is not None:
            bg[user_id] = background
        return _save_app_state(mw, hm, bg)


def update_history_message(user_id: str, messages: list[str]) -> bool:
    """保存指定用户最近四轮 user/AI 对话，保留文件中的记忆、背景和其他用户。"""
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("用户 ID 需要为非空字符串")
    with STATE_LOCK:
        mw, hm, bg = load_app_state()
        mw[user_id] = list(messages[-4:])
        return _save_app_state(mw, hm, bg)
