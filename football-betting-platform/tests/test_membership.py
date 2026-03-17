# -*- coding: utf-8 -*-
"""会员系统单元测试（设计书逻辑）。"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.membership import (
    _is_historical_assessment,
    _parse_yyyymmdd_to_beijing_day,
    _expires_at_week,
    _add_months,
)


BEIJING = ZoneInfo("Asia/Shanghai")


def test_parse_yyyymmdd_to_beijing_day():
    assert _parse_yyyymmdd_to_beijing_day("20250101").year == 2025
    assert _parse_yyyymmdd_to_beijing_day("20250101").month == 1
    assert _parse_yyyymmdd_to_beijing_day("20250101").day == 1
    assert _parse_yyyymmdd_to_beijing_day("") is None
    assert _parse_yyyymmdd_to_beijing_day("202501") is None


def test_is_historical_assessment():
    # 设计书：历史 = 早于昨日（自然日）完场；当前 = 昨日和当日
    today = datetime.now(BEIJING).strftime("%Y%m%d")
    yesterday = (datetime.now(BEIJING) - timedelta(days=1)).strftime("%Y%m%d")
    day_before_yesterday = (datetime.now(BEIJING) - timedelta(days=2)).strftime("%Y%m%d")
    assert _is_historical_assessment(day_before_yesterday) is True
    assert _is_historical_assessment(yesterday) is False
    assert _is_historical_assessment(today) is False
    old = (datetime.now(BEIJING) - timedelta(days=10)).strftime("%Y%m%d")
    assert _is_historical_assessment(old) is True


def test_expires_at_week():
    # 1月1日 12:00 北京 → 第8日 0:00 北京
    base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=BEIJING)
    exp = _expires_at_week(base)
    assert exp.year == 2025 and exp.month == 1 and exp.day == 8
    assert exp.hour == 0 and exp.minute == 0


def test_add_months_one_month():
    # 1月31日 + 1月 → 2月无31日取月末，失效时刻 = 3月1日 0:00
    base = datetime(2025, 1, 31, 0, 0, 0, tzinfo=BEIJING)
    exp = _add_months(base, 1)
    assert exp.year == 2025 and exp.month == 3 and exp.day == 1
