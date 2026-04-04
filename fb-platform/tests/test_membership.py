# -*- coding: utf-8 -*-
"""会员系统单元测试（设计书逻辑）。"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import app.membership as membership_mod
from app.membership import (
    MEMBERSHIP_DURATION_DAYS,
    _is_historical_assessment,
    _parse_yyyymmdd_to_beijing_day,
    _compute_expires_at,
    is_match_under_evaluation,
    non_member_may_view_curve,
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


def test_membership_fixed_duration_days():
    """周 7、月 30、季 120、年 365：均为 effective_at + N 天，保留时分秒。"""
    assert MEMBERSHIP_DURATION_DAYS == {
        "week": 7,
        "month": 30,
        "quarter": 120,
        "year": 365,
    }
    base = datetime(2026, 3, 21, 10, 19, 33)
    assert _compute_expires_at(base, "week") == datetime(2026, 3, 28, 10, 19, 33)
    assert _compute_expires_at(base, "month") == datetime(2026, 4, 20, 10, 19, 33)
    assert _compute_expires_at(base, "quarter") == datetime(2026, 7, 19, 10, 19, 33)
    assert _compute_expires_at(base, "year") == datetime(2027, 3, 21, 10, 19, 33)
    # 1 月跨月仍按天数，不踩自然月边界
    jan = datetime(2025, 1, 31, 0, 0, 0)
    assert _compute_expires_at(jan, "month") == datetime(2025, 3, 2, 0, 0, 0)


@patch.object(membership_mod, "EvaluationMatch")
def test_is_match_under_evaluation_true_when_row_exists(mock_em):
    q = MagicMock()
    q.first.return_value = MagicMock()
    mock_em.query.filter_by.return_value = q
    assert is_match_under_evaluation("20250101", "主队", "客队") is True


@patch.object(membership_mod, "EvaluationMatch")
def test_is_match_under_evaluation_false_when_no_row(mock_em):
    q = MagicMock()
    q.first.return_value = None
    q.all.return_value = []
    mock_em.query.filter_by.return_value = q
    assert is_match_under_evaluation("20250101", "主队", "客队") is False


@patch.object(membership_mod, "EvaluationMatch")
def test_is_match_under_evaluation_invalid_date(mock_em):
    assert is_match_under_evaluation("", "a", "b") is False
    assert is_match_under_evaluation("202501", "a", "b") is False
    mock_em.query.filter_by.assert_not_called()


def test_is_member_strict_expires_at_boundary():
    """expires_at 当秒起即过期：now=expires_at 与 now=expires_at+1s 均非会员。"""
    eff = datetime(2026, 3, 8, 10, 0, 0)
    exp = datetime(2026, 3, 21, 0, 0, 0)
    row = SimpleNamespace(effective_at=eff, expires_at=exp)

    q = MagicMock()
    q.all.return_value = [row]
    with patch.object(membership_mod, "MembershipRecord") as mock_mr:
        mock_mr.query.filter_by.return_value = q
        with patch.object(
            membership_mod,
            "_membership_now_naive",
            return_value=datetime(2026, 3, 21, 0, 0, 0),
        ):
            assert membership_mod.is_member(1) is False
        with patch.object(
            membership_mod,
            "_membership_now_naive",
            return_value=datetime(2026, 3, 21, 0, 0, 1),
        ):
            assert membership_mod.is_member(1) is False
        with patch.object(
            membership_mod,
            "_membership_now_naive",
            return_value=datetime(2026, 3, 20, 23, 59, 59),
        ):
            assert membership_mod.is_member(1) is True
        # 库中 expires 3/21 0 点，系统时间 08:51 同一天 → 已过期
        with patch.object(
            membership_mod,
            "_membership_now_naive",
            return_value=datetime(2026, 3, 21, 8, 51, 0),
        ):
            assert membership_mod.is_member(1) is False


@patch.object(membership_mod, "EvaluationMatch")
def test_non_member_may_view_curve(mock_em):
    # 第一次 is_match：精确查询无行 + 按日扫描为空 → 不在评估中
    q_exact_empty = MagicMock()
    q_exact_empty.first.return_value = None
    q_date_scan = MagicMock()
    q_date_scan.all.return_value = []
    # 第二次 is_match：精确查询命中 → 在评估中
    q_hit = MagicMock()
    q_hit.first.return_value = MagicMock()
    mock_em.query.filter_by.side_effect = [q_exact_empty, q_date_scan, q_hit]
    assert non_member_may_view_curve("20250101", "H", "A") is True
    assert non_member_may_view_curve("20250101", "H", "A") is False
