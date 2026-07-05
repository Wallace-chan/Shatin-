"""GitHub Actions 排程与手动 Run 共用逻辑。

手动 workflow_dispatch 只生成 artifact，不写回 data/*_state.json，
也不占用 morning/noon/evening 排程 slot，确保每天三次定时任务不受影响。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, Tuple

from zoneinfo import ZoneInfo

HK_TZ = ZoneInfo("Asia/Hong_Kong")

SCHEDULE_SLOT_TIMES: Dict[str, Dict[str, Tuple[int, int]]] = {
    "social": {"morning": (8, 0), "noon": (12, 0), "evening": (18, 0)},
    "cantonese": {"morning": (8, 5), "noon": (12, 5), "evening": (18, 5)},
    "multilang": {"morning": (8, 10), "noon": (12, 10), "evening": (18, 10)},
}


def github_event_name() -> str:
    return os.environ.get("GITHUB_EVENT_NAME", "local")


def should_persist_state() -> bool:
    """手动 Run 不写回仓库 state（与 workflow 中 schedule-only commit 一致）。"""
    return github_event_name() != "workflow_dispatch"


def run_slot(now: datetime) -> str:
    """定时：morning/noon/evening；手动 Run：manual（不占用排程 slot）。"""
    if github_event_name() == "workflow_dispatch":
        return "manual"
    hour = now.hour
    if hour < 11:
        return "morning"
    if hour < 17:
        return "noon"
    return "evening"


def slot_record_time(now: datetime, slot: str, *, workflow: str) -> datetime:
    """排程任务用设定的 HKT 发布时间；手动 Run 用实际时间。"""
    if slot == "manual":
        return now
    hour, minute = SCHEDULE_SLOT_TIMES[workflow][slot]
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def slot_key(now: datetime, slot: str) -> str:
    return f"{now:%Y-%m-%d}_{slot}"


def output_stamp(now: datetime, slot: str, *, workflow: str) -> str:
    record = slot_record_time(now, slot, workflow=workflow)
    return record.strftime("%Y-%m-%d_%H%M")
