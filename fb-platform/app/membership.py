# -*- coding: utf-8 -*-
"""
会员系统：按《会员系统设计书》实现。
- membership_records.effective_at / expires_at：MySQL DATETIME 无时区；不做时区换算，与运行环境的
  「当前系统时间」使用同一套墙上时钟数字直接比较（datetime.now() 的 naive 本地时刻 ↔ 库中列值）。
- 是否仍为会员：effective_at <= now < expires_at（左闭右开，精确到 datetime 精度）。
- 多次购买/续费：在当前剩余有效期基础上顺延。
- 各档时长为**固定天数**（自 effective_at 起）：周 7、月 30、季 120、年 365；到期时刻与生效同一时分秒（+N 天）。
- 历史/当前综合评估等仍按设计书使用「北京自然日」（见 _is_historical_assessment）。
"""
import re
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app import db
from app.models import User, MembershipRecord, EvaluationMatch

BEIJING = ZoneInfo("Asia/Shanghai")
MEMBERSHIP_TYPES = ("week", "month", "quarter", "year")
# 前端展示用中文档名
MEMBERSHIP_TYPE_LABELS: dict[str, str] = {
    "week": "周会员",
    "month": "月会员",
    "quarter": "季会员",
    "year": "年会员",
}
# 固定天数（非自然月/年），避免日历边界歧义
MEMBERSHIP_DURATION_DAYS: dict[str, int] = {
    "week": 7,
    "month": 30,
    "quarter": 120,
    "year": 365,
}
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


def _norm_team_name(s: str) -> str:
    """与文件名 / 入库队名在 Unicode 上等价时视为同一队（NFKC、空白规范化）。"""
    t = unicodedata.normalize("NFKC", (s or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_match_under_evaluation(match_date: str, home_team: str, away_team: str) -> bool:
    """
    《会员系统设计书》§3.3：该场是否仍在「正在综合评估」中。
    优先用原生 SQL 读 evaluation_matches，避免 ORM/会话与库实际数据不一致导致误判。
    """
    if not match_date or len(match_date) != 8 or not match_date.isdigit():
        return False
    h0 = (home_team or "").strip()
    a0 = (away_team or "").strip()
    hn, an = _norm_team_name(h0), _norm_team_name(a0)

    sql_ok = False
    sql_rows: list | None = None
    try:
        from sqlalchemy import text

        from app import db

        sql_rows = db.session.execute(
            text(
                "SELECT home_team, away_team FROM evaluation_matches WHERE match_date = :md"
            ),
            {"md": match_date},
        ).fetchall()
        sql_ok = True
    except Exception:
        sql_rows = None

    if sql_ok and sql_rows is not None:
        if not sql_rows:
            return False
        for home_db, away_db in sql_rows:
            if home_db == h0 and away_db == a0:
                return True
            rh, ra = _norm_team_name(home_db), _norm_team_name(away_db)
            if rh == hn and ra == an:
                return True
            if rh == an and ra == hn:
                return True
        return False

    # 无应用上下文等导致 SQL 不可用时回退 ORM（供单元测试 mock）
    row = EvaluationMatch.query.filter_by(
        match_date=match_date,
        home_team=h0,
        away_team=a0,
    ).first()
    if row is not None:
        return True
    for r in EvaluationMatch.query.filter_by(match_date=match_date).all():
        rh, ra = _norm_team_name(r.home_team), _norm_team_name(r.away_team)
        if (rh == hn and ra == an) or (rh == an and ra == hn):
            return True
    return False


def non_member_may_view_curve(match_date: str, home_team: str, away_team: str) -> bool:
    """非会员是否允许查看该场曲线：仅当该场不在 evaluation_matches 中时为 True。"""
    return not is_match_under_evaluation(match_date, home_team, away_team)


def _membership_now_naive() -> datetime:
    """与库中 DATETIME 同一标尺：当前系统本地时刻（naive）。"""
    return datetime.now()


def _row_membership_dt_naive(dt: datetime | None) -> datetime | None:
    """库中读出：已为 naive 则原样；若 ORM 带 tz 则先转到本地再抹掉 tz，便于与 datetime.now() 直接比。"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def _compute_expires_at(effective_at: datetime, membership_type: str) -> datetime:
    """
    自 effective_at 起加固定天数（MEMBERSHIP_DURATION_DAYS），保留原时分秒（naive 本地）。
    周 7、月 30、季 120、年 365。
    """
    if membership_type not in MEMBERSHIP_DURATION_DAYS:
        raise ValueError(f"unknown membership_type: {membership_type}")
    b = _row_membership_dt_naive(effective_at)
    if b is None:
        raise TypeError("effective_at required")
    days = MEMBERSHIP_DURATION_DAYS[membership_type]
    return b + timedelta(days=days)


def is_member(user_id: int) -> bool:
    """
    库中列值与 datetime.now() 直接比较（同一 naive 墙上时钟标尺）。
    当且仅当存在一条记录满足：effective_at <= now < expires_at（左闭右开）。
    """
    now = _membership_now_naive()
    records = MembershipRecord.query.filter_by(user_id=user_id).all()
    for r in records:
        eff = _row_membership_dt_naive(r.effective_at)
        exp = _row_membership_dt_naive(r.expires_at)
        if eff is None or exp is None:
            continue
        if eff <= now < exp:
            return True
    return False


def _get_current_expires_at_naive(user_id: int) -> datetime | None:
    """当前有效期内最晚的 expires_at（naive，与库一致，用于顺延）。若无则 None。"""
    now = _membership_now_naive()
    records = MembershipRecord.query.filter_by(user_id=user_id).all()
    valid: list[datetime] = []
    for r in records:
        eff = _row_membership_dt_naive(r.effective_at)
        exp = _row_membership_dt_naive(r.expires_at)
        if eff is None or exp is None:
            continue
        if eff <= now < exp:
            valid.append(exp)
    if not valid:
        return None
    return max(valid)


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
    now = _membership_now_naive()
    effective_naive = now
    expires_naive = _compute_expires_at(now, "week")
    rec = MembershipRecord(
        user_id=user_id,
        membership_type="week",
        effective_at=effective_naive,
        expires_at=expires_naive,
        source=SOURCE_GIFT,
        order_id=None,
    )
    db.session.add(rec)
    user.free_week_granted_at = datetime.now()
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
    now = _membership_now_naive()
    base_expires = _get_current_expires_at_naive(user_id)
    if base_expires:
        effective_at = base_expires if base_expires > now else now
    else:
        effective_at = now
    expires_naive = _compute_expires_at(effective_at, membership_type)
    effective_naive = effective_at
    rec = MembershipRecord(
        user_id=user_id,
        membership_type=membership_type,
        effective_at=effective_naive,
        expires_at=expires_naive,
        source=source,
        order_id=order_id,
    )
    db.session.add(rec)
    db.session.commit()
    return True


def _membership_source_label(source: str) -> str:
    if source == SOURCE_GIFT:
        return "赠送"
    if source == SOURCE_PURCHASE:
        return "购买"
    return source or "—"


def get_membership_status(user_id: int) -> dict:
    """
    返回当前会员状态，供前端展示。
    兼容旧字段：is_member、expires_at（所有当前有效权益中最晚的到期时间）。
    扩展：active_records（当前生效中的明细）、free_week_granted_at（是否曾领取注册周会员）。
    """
    member = is_member(user_id)
    now = _membership_now_naive()
    records = (
        MembershipRecord.query.filter_by(user_id=user_id)
        .order_by(MembershipRecord.expires_at.desc())
        .all()
    )
    valid_expires: list[datetime] = []
    active_records: list[dict] = []
    for r in records:
        eff = _row_membership_dt_naive(r.effective_at)
        exp = _row_membership_dt_naive(r.expires_at)
        if eff is None or exp is None:
            continue
        if eff <= now < exp:
            valid_expires.append(exp)
            mtype = r.membership_type or ""
            active_records.append(
                {
                    "membership_type": mtype,
                    "membership_type_label": MEMBERSHIP_TYPE_LABELS.get(
                        mtype, mtype or "—"
                    ),
                    "effective_at": eff.isoformat(),
                    "expires_at": exp.isoformat(),
                    "source": r.source,
                    "source_label": _membership_source_label(r.source or ""),
                    "order_id": r.order_id,
                }
            )
    expires_at = max(valid_expires) if valid_expires else None

    user = db.session.get(User, user_id)
    free_week_iso = None
    if user and user.free_week_granted_at:
        free_week_iso = user.free_week_granted_at.isoformat()

    return {
        "is_member": member,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "active_records": active_records,
        "free_week_granted_at": free_week_iso,
    }
