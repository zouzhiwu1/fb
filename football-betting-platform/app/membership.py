# -*- coding: utf-8 -*-
"""
会员系统：按《会员系统设计书》实现。
- 自然日/24:00/0 点以北京时间（东八区）为准。
- 有效期：到期当日 24:00 前有效，下一自然日 0 点起非会员。
- 多次购买/续费：在当前剩余有效期基础上顺延。
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app import db
from app.models import User, MembershipRecord

BEIJING = ZoneInfo("Asia/Shanghai")
MEMBERSHIP_TYPES = ("week", "month", "quarter", "year")
SOURCE_GIFT = "gift"
SOURCE_PURCHASE = "purchase"


def _beijing_now() -> datetime:
    """当前时刻（北京时间）。"""
    return datetime.now(BEIJING)


def _to_beijing(dt: datetime) -> datetime:
    """若 dt 无时区则视为 UTC，转为北京时间。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(BEIJING)
    else:
        dt = dt.astimezone(BEIJING)
    return dt


def _beijing_date_str(dt: datetime) -> str:
    """YYYYMMDD 字符串（北京日）。"""
    bj = _to_beijing(dt) if dt.tzinfo else dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(BEIJING)
    return bj.strftime("%Y%m%d")


def _parse_yyyymmdd_to_beijing_day(date_yyyymmdd: str):
    """将 YYYYMMDD 解析为北京时间的 date（用于比较）。"""
    if not date_yyyymmdd or len(date_yyyymmdd) != 8:
        return None
    try:
        y, m, d = int(date_yyyymmdd[:4]), int(date_yyyymmdd[4:6]), int(date_yyyymmdd[6:8])
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


def _is_historical_assessment(date_yyyymmdd: str) -> bool:
    """
    该日期（完场日）的综合评估是否属于「历史综合评估」。
    历史 = 早于昨日（自然日）完场；当前 = 昨日及当日。
    以北京日为准。
    """
    day = _parse_yyyymmdd_to_beijing_day(date_yyyymmdd)
    if day is None:
        return True
    today_bj = _beijing_now().date()
    yesterday_bj = today_bj - timedelta(days=1)
    return day < yesterday_bj


def _add_months(base: datetime, months: int) -> datetime:
    """
    在 base（北京时区）的日期上加 months 个月；若目标月无该日则取月末。
    设计：自然月 = 下月无该日取该月最后一日。到期当日 24:00 前有效 → 失效时刻 = 到期日次日 0:00。
    """
    from calendar import monthrange
    bj = _to_beijing(base) if base.tzinfo else base.replace(tzinfo=ZoneInfo("UTC")).astimezone(BEIJING)
    y, m, d = bj.year, bj.month, bj.day
    for _ in range(months):
        m += 1
        if m > 12:
            m -= 12
            y += 1
    last = monthrange(y, m)[1]
    day = min(d, last)
    # 到期日 = (y, m, day)，失效时刻 = 到期日 24:00 后 = 次日 0:00
    end_date = date(y, m, day)
    next_day = end_date + timedelta(days=1)
    result = datetime(next_day.year, next_day.month, next_day.day, 0, 0, 0, tzinfo=BEIJING)
    return result


def _expires_at_week(effective_at: datetime) -> datetime:
    """周会员：生效后第 7 个自然日 24:00 前有效 → 第 8 日 0:00 为失效时刻（北京）。"""
    bj = _to_beijing(effective_at) if effective_at.tzinfo else effective_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(BEIJING)
    end_day = bj.date() + timedelta(days=7)
    return datetime(end_day.year, end_day.month, end_day.day, 0, 0, 0, tzinfo=BEIJING)


def _expires_at_month(effective_at: datetime) -> datetime:
    """月会员：1 个自然月，下月无该日取月末。"""
    return _add_months(effective_at, 1)


def _expires_at_year(effective_at: datetime) -> datetime:
    """年会员：满 12 个月；2 月 29 日 → 次年 2 月 28 日。"""
    return _add_months(effective_at, 12)


def _compute_expires_at(effective_at: datetime, membership_type: str) -> datetime:
    """根据类型计算失效时刻（北京 0 点）。"""
    if membership_type == "week":
        return _expires_at_week(effective_at)
    if membership_type == "month":
        return _expires_at_month(effective_at)
    if membership_type == "quarter":
        return _add_months(effective_at, 3)
    if membership_type == "year":
        return _expires_at_year(effective_at)
    raise ValueError(f"unknown membership_type: {membership_type}")


def _effective_at_utc(effective_at_beijing: datetime) -> datetime:
    """北京时刻转 UTC 存库（设计书约定以北京为准，比较时再转回）。"""
    if effective_at_beijing.tzinfo is None:
        effective_at_beijing = effective_at_beijing.replace(tzinfo=BEIJING)
    return effective_at_beijing.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def is_member(user_id: int) -> bool:
    """
    当前时间是否落在任意一条未过期会员记录的有效期内。
    库内存 UTC，比较用 UTC。
    """
    now_utc = datetime.utcnow()
    records = (
        MembershipRecord.query.filter_by(user_id=user_id)
        .filter(MembershipRecord.expires_at > now_utc)
        .all()
    )
    for r in records:
        if r.effective_at <= now_utc:
            return True
    return False


def _get_current_expires_at_utc(user_id: int) -> datetime | None:
    """当前有效期内最晚的 expires_at（UTC，用于顺延）。若无有效记录则返回 None。"""
    now_utc = datetime.utcnow()
    records = (
        MembershipRecord.query.filter_by(user_id=user_id)
        .filter(MembershipRecord.expires_at > now_utc)
        .all()
    )
    if not records:
        return None
    return max(r.expires_at for r in records)


def _utc_to_beijing(dt: datetime) -> datetime:
    """无时区的 UTC 时间转北京。"""
    if dt.tzinfo:
        return dt.astimezone(BEIJING)
    return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(BEIJING)


def grant_free_week(user_id: int) -> bool:
    """
    为新用户赠送周会员。仅当该账号从未获得过赠送时发放。
    返回 True 表示已发放，False 表示已领取过不重复发放。
    """
    user = User.query.get(user_id)
    if not user:
        return False
    if user.free_week_granted_at is not None:
        return False
    now_bj = _beijing_now()
    effective_utc = _effective_at_utc(now_bj)
    expires_bj = _expires_at_week(now_bj)
    expires_utc = _effective_at_utc(expires_bj)
    rec = MembershipRecord(
        user_id=user_id,
        membership_type="week",
        effective_at=effective_utc,
        expires_at=expires_utc,
        source=SOURCE_GIFT,
        order_id=None,
    )
    db.session.add(rec)
    user.free_week_granted_at = datetime.utcnow()
    db.session.commit()
    return True


def add_membership(
    user_id: int,
    membership_type: str,
    source: str = SOURCE_PURCHASE,
    order_id: str | None = None,
) -> bool:
    """
    增加会员权益（支付成功回调等调用）。在当前剩余有效期基础上顺延。
    membership_type: week / month / quarter / year
    """
    if membership_type not in MEMBERSHIP_TYPES:
        return False
    now_bj = _beijing_now()
    now_utc = datetime.utcnow()
    base_expires_utc = _get_current_expires_at_utc(user_id)
    if base_expires_utc and base_expires_utc > now_utc:
        base_expires_bj = _utc_to_beijing(base_expires_utc)
        effective_at_bj = base_expires_bj
    else:
        effective_at_bj = now_bj
    expires_bj = _compute_expires_at(effective_at_bj, membership_type)
    effective_utc = _effective_at_utc(effective_at_bj)
    expires_utc = _effective_at_utc(expires_bj)
    rec = MembershipRecord(
        user_id=user_id,
        membership_type=membership_type,
        effective_at=effective_utc,
        expires_at=expires_utc,
        source=source,
        order_id=order_id,
    )
    db.session.add(rec)
    db.session.commit()
    return True


def get_membership_status(user_id: int) -> dict:
    """返回当前会员状态，供前端展示。"""
    member = is_member(user_id)
    now_utc = datetime.utcnow()
    records = (
        MembershipRecord.query.filter_by(user_id=user_id)
        .filter(MembershipRecord.expires_at > now_utc)
        .order_by(MembershipRecord.expires_at.desc())
        .all()
    )
    expires_at = None
    if records:
        expires_at = max(r.expires_at for r in records)
    return {
        "is_member": member,
        "expires_at": expires_at.isoformat() + "Z" if expires_at else None,
    }
