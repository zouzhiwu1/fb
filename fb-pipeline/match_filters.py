# -*- coding: utf-8 -*-
"""
即时比分列表过滤规则（与 config 中的 MATCH_* 配置对应）。
"""
from config import MATCH_STATUS_MODES

# 日志用中文说明
_STATUS_MODE_LABELS = {
    "not_started": "未开场",
    "live": "进行中",
    "finished": "完场",
}


def describe_status_filter_for_log() -> str:
    modes = MATCH_STATUS_MODES or ["not_started"]
    return "、".join(_STATUS_MODE_LABELS.get(m, m) for m in modes)


def match_status_allowed(status_text: str) -> bool:
    """
    状态列是否通过过滤。MATCH_STATUS_MODES 为允许类别的并集：
    - not_started: 空白或「-」（未开赛）
    - live: 非空且非完场，视为进行中（含分钟数、半场等）
    - finished: 含「完」等完场标识
    """
    modes = {m.lower() for m in (MATCH_STATUS_MODES or ["not_started"])}
    if not modes:
        modes = {"not_started"}

    s = " ".join((status_text or "").split())
    is_empty = s == "" or s == "-"
    is_finished = "完" in s
    is_live = (not is_empty) and (not is_finished)

    if "not_started" in modes and is_empty:
        return True
    if "finished" in modes and is_finished:
        return True
    if "live" in modes and is_live:
        return True
    return False
