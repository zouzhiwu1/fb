# -*- coding: utf-8 -*-
import logging
import re
from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import text

import config as _cfg
from app import db
from app.auth_partner import require_partner_token
from app.models import Agent, AgentCommissionLine

partner_ui_bp = Blueprint("partner_api", __name__, url_prefix="/api/partner")

_YM_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _parse_month_param(raw: str | None) -> str:
    if raw and isinstance(raw, str):
        s = raw.strip()
        if _YM_RE.match(s):
            return s
    now = datetime.now()
    return f"{now.year:04d}-{now.month:02d}"


def _month_start_end(ym: str) -> tuple[datetime, datetime]:
    y, m = map(int, ym.split("-"))
    start = datetime(y, m, 1)
    if m == 12:
        end = datetime(y + 1, 1, 1)
    else:
        end = datetime(y, m + 1, 1)
    return start, end


def mask_phone(phone: object | None) -> str:
    if phone is None:
        return "—"
    p = str(phone).strip()
    if len(p) >= 11:
        return f"{p[:3]}****{p[-4:]}"
    if len(p) >= 7:
        return f"{p[:2]}****{p[-2:]}"
    return "****"


def _exec_mappings(sql: str, params: dict) -> list:
    try:
        return list(db.session.execute(text(sql), params).mappings().all())
    except Exception:
        logging.exception("partner dashboard sql")
        return []


@partner_ui_bp.route("/stats/summary", methods=["GET"])
def partner_stats_summary():
    agent, err = require_partner_token()
    if err:
        return err
    referred_count = None
    ledger_sum = None
    try:
        row = db.session.execute(
            text(
                "SELECT COUNT(*) AS c FROM users WHERE agent_id = :aid"
            ),
            {"aid": agent.id},
        ).mappings().first()
        referred_count = int(row["c"]) if row else 0
    except Exception:
        referred_count = None
    try:
        row = db.session.execute(
            text(
                "SELECT COALESCE(SUM(points_delta), 0) AS s "
                "FROM points_ledger WHERE agent_id = :aid"
            ),
            {"aid": agent.id},
        ).mappings().first()
        if row and row["s"] is not None:
            ledger_sum = float(row["s"])
        else:
            ledger_sum = 0.0
    except Exception:
        ledger_sum = None
    return jsonify(
        {
            "ok": True,
            "agent": {
                "id": agent.id,
                "agent_code": agent.agent_code,
                "display_name": agent.display_name,
                "current_rate": float(agent.current_rate or 0),
            },
            "referred_user_count": referred_count,
            "points_ledger_total": ledger_sum,
            "hint": (
                "若 referred_user_count 为 null，请确认已执行 scripts/add_partner_tables.sql，"
                "为 users 表增加 agent_id。"
                if referred_count is None
                else None
            ),
        }
    )


@partner_ui_bp.route("/stats/promo-links", methods=["GET"])
def partner_promo_links():
    """代理商推广：小程序 / WEB / Android / iOS 二维码所用 URL 与 path、scene 提示。"""
    agent, err = require_partner_token()
    if err:
        return err
    bundle = _cfg.partner_promo_bundle(agent.id, agent.agent_code)
    return jsonify({"ok": True, **bundle})


def build_monthly_board_dict(agent: Agent, ym: str) -> dict:
    """文档 1.2：按月汇总与明细；供代理商接口与管理员代查共用。"""
    start, end = _month_start_end(ym)
    aid = agent.id
    bind = {"aid": aid, "start": start, "end": end, "ym": ym}

    reg_sql = """
    SELECT u.id AS user_id, u.phone AS phone, u.created_at AS created_at
    FROM users u
    WHERE u.agent_id = :aid
    AND u.created_at >= :start AND u.created_at < :end
    ORDER BY u.created_at DESC
    """
    reg_rows = _exec_mappings(reg_sql, bind)
    reg_count = len(reg_rows)

    types_reg = _cfg.PARTNER_LEDGER_EVENT_TYPES_REG
    reg_points_by_user: dict[int, float] = {}
    if types_reg:
        tkeys = [f"t{i}" for i in range(len(types_reg))]
        placeholders = ", ".join(f":{k}" for k in tkeys)
        tparams = {tkeys[i]: types_reg[i] for i in range(len(types_reg))}
        ledger_reg_sql = f"""
        SELECT user_id, COALESCE(SUM(points_delta), 0) AS pts
        FROM points_ledger
        WHERE agent_id = :aid
        AND created_at >= :start AND created_at < :end
        AND user_id IS NOT NULL
        AND event_type IN ({placeholders})
        GROUP BY user_id
        """
        for row in _exec_mappings(ledger_reg_sql, {**bind, **tparams}):
            uid = row.get("user_id")
            if uid is not None:
                reg_points_by_user[int(uid)] = float(row["pts"] or 0)

    referrals = []
    for r in reg_rows:
        uid = int(r["user_id"])
        pts = reg_points_by_user.get(uid, 0.0)
        created = r["created_at"]
        if hasattr(created, "isoformat"):
            created_iso = created.isoformat(sep=" ", timespec="seconds")
        else:
            created_iso = str(created)
        if pts > 0:
            reward_label = f"+{pts:.1f} 积分"
            status_label = "正常"
        else:
            reward_label = "0.0"
            status_label = "正常（奖励未入账）"
        referrals.append(
            {
                "user_mask": mask_phone(r.get("phone")),
                "registered_at": created_iso,
                "register_reward": reward_label,
                "status": status_label,
            }
        )

    recharge_sql = """
    SELECT u.phone AS phone, po.total_amount AS total_amount, po.paid_at AS paid_at
    FROM payment_orders po
    INNER JOIN users u ON u.id = po.user_id
    WHERE u.agent_id = :aid
    AND po.status = 'paid'
    AND po.paid_at IS NOT NULL
    AND po.paid_at >= :start AND po.paid_at < :end
    ORDER BY po.paid_at DESC
    """
    recharge_rows = _exec_mappings(recharge_sql, bind)
    recharge_list = []
    recharge_sum = 0.0
    for row in recharge_rows:
        raw_amt = row.get("total_amount")
        try:
            amt = float(raw_amt) if raw_amt is not None else 0.0
        except (TypeError, ValueError):
            amt = 0.0
        recharge_sum += amt
        paid = row.get("paid_at")
        if paid is not None and hasattr(paid, "isoformat"):
            paid_iso = paid.isoformat(sep=" ", timespec="seconds")
        else:
            paid_iso = str(paid) if paid is not None else "—"
        recharge_list.append(
            {
                "user_mask": mask_phone(row.get("phone")),
                "amount_yuan": round(amt, 2),
                "paid_at": paid_iso,
            }
        )

    yuan_per_reg = float(_cfg.PARTNER_YUAN_PER_VALID_REGISTRATION)
    performance_reg = float(reg_count) * yuan_per_reg
    performance_recharge = round(recharge_sum, 2)
    performance_total = round(performance_reg + performance_recharge, 2)
    rebate_rate = float(agent.current_rate or 0)
    points_computed = round(performance_total * rebate_rate, 4)

    ledger_month_sql = """
    SELECT COALESCE(SUM(points_delta), 0) AS s
    FROM points_ledger
    WHERE agent_id = :aid
    AND (
        settlement_month = :ym
        OR (settlement_month IS NULL AND created_at >= :start AND created_at < :end)
    )
    """
    ledger_month = 0.0
    lm_rows = _exec_mappings(ledger_month_sql, bind)
    if lm_rows:
        ledger_month = float(lm_rows[0].get("s") or 0)

    commission = round(
        points_computed * float(_cfg.PARTNER_COMMISSION_PER_POINT), 4
    )

    settled_total = round(float(agent.settled_commission_yuan or 0), 2)

    try:
        commission_rows = (
            AgentCommissionLine.query.filter(
                AgentCommissionLine.agent_id == aid,
                AgentCommissionLine.created_at >= start,
                AgentCommissionLine.created_at < end,
            )
            .order_by(AgentCommissionLine.created_at.desc(), AgentCommissionLine.id.desc())
            .all()
        )
    except Exception:
        logging.exception("partner dashboard commission_lines query")
        commission_rows = []
    commission_lines = []
    for row in commission_rows:
        created_at = row.created_at
        created_at_str = (
            created_at.isoformat(sep=" ", timespec="seconds")
            if hasattr(created_at, "isoformat")
            else str(created_at)
        )
        paid_at = row.paid_at
        paid_at_str = (
            paid_at.isoformat(sep=" ", timespec="seconds")
            if hasattr(paid_at, "isoformat")
            else ("—" if paid_at is None else str(paid_at))
        )
        ctype = "拉新" if row.commission_type == "registration" else "充值"
        if row.commission_type == "registration":
            remark = f"拉新系数 {float(row.reg_factor or 0):.4f}"
        else:
            recharge_amt = float(row.recharge_amount or 0)
            rebate_pct = float(row.rebate_rate or 0) * 100
            remark = f"充值金额 {recharge_amt:.2f} 元，分润率 {rebate_pct:.2f}%"
        commission_lines.append(
            {
                "id": int(row.id),
                "username": row.username or "—",
                "commission_type": ctype,
                "commission_amount": round(float(row.commission_amount or 0), 2),
                "remark": remark,
                "created_at": created_at_str,
                "payment_status": row.payment_status or "pending",
                "paid_at": paid_at_str,
            }
        )

    return {
        "ok": True,
        "month": ym,
        "summary": {
            "performance_total_yuan": performance_total,
            "performance_reg_yuan": round(performance_reg, 2),
            "performance_recharge_yuan": performance_recharge,
            "valid_reg_count": reg_count,
            "yuan_per_registration": yuan_per_reg,
            "rebate_rate": rebate_rate,
            "points": points_computed,
            "points_ledger_month": ledger_month,
            "commission_yuan": commission,
            "commission_per_point": float(_cfg.PARTNER_COMMISSION_PER_POINT),
            "settled_commission_yuan": settled_total,
        },
        "referrals": referrals,
        "recharges": recharge_list,
        "recharges_total_yuan": round(recharge_sum, 2),
        "commission_lines": commission_lines,
        "notes": {
            "formula": "总业绩=拉新业绩+充值业绩；积分=总业绩×本月分润率；服务费=积分×积分系数。",
            "ledger": "points_ledger_month 为当月流水汇总（settlement_month 或创建时间落在本月）。",
        },
    }


@partner_ui_bp.route("/stats/monthly-board", methods=["GET"])
def partner_monthly_board():
    """文档 1.2：按月汇总业绩/积分/服务费 + 拉新明细 + 充值明细（依赖 users / payment_orders / points_ledger）。"""
    agent, err = require_partner_token()
    if err:
        return err
    ym = _parse_month_param(request.args.get("month"))
    return jsonify(build_monthly_board_dict(agent, ym))
