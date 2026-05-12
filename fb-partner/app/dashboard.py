# -*- coding: utf-8 -*-
import logging
import re
from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

import config as _cfg
from app import db
from app.auth_partner import require_partner_token
from app.models import Agent, AgentCommissionLine
from app.promo_miniprogram_qr import load_agent_promo_miniprogram_qr_data_url

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


def _payment_status_zh(raw: object | None) -> str:
    """与管理员佣金页一致：月度看板 API 返回中文支付状态。"""
    if raw is None:
        return "待支付"
    s = str(raw).strip().lower()
    if not s:
        return "待支付"
    if s == "paid":
        return "已支付"
    if s == "pending":
        return "待支付"
    return str(raw).strip()


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
    mp_qr_image = load_agent_promo_miniprogram_qr_data_url(agent.id)
    if mp_qr_image:
        for ch in bundle.get("channels") or []:
            if ch.get("id") == "miniprogram":
                ch["qr_image_data_url"] = mp_qr_image
                ch["configured"] = True
                break
    return jsonify({"ok": True, **bundle})


def build_monthly_board_dict(agent: Agent, ym: str) -> dict:
    """文档 1.2：按月汇总与明细；供代理商接口与管理员代查共用。"""
    # 与管理员 commission-lines 一致：查表前把当月注册/充值增量写入 agent_commission_lines（幂等）。
    # 否则代理商只看 monthly-board 时会出现「业绩有数、服务费明细为空」。
    try:
        from app.admin_api import _sync_agent_commission_lines

        _sync_agent_commission_lines(agent, ym)
        db.session.commit()
    except OperationalError:
        db.session.rollback()
        logging.warning(
            "partner commission_lines sync skipped (users/payment_orders 等表不可用或库未就绪)"
        )
    except Exception:
        db.session.rollback()
        logging.exception("partner commission_lines sync before monthly board")

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

    referrals = []
    for r in reg_rows:
        created = r["created_at"]
        if hasattr(created, "isoformat"):
            created_iso = created.isoformat(sep=" ", timespec="seconds")
        else:
            created_iso = str(created)
        referrals.append(
            {
                "user_mask": mask_phone(r.get("phone")),
                "registered_at": created_iso,
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

    rebate_rate = float(agent.current_rate or 0)
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
    sum_reg_lines = 0.0
    sum_rec_lines = 0.0
    for row in commission_rows:
        line_amt = round(float(row.commission_amount or 0), 2)
        if row.commission_type == "registration":
            sum_reg_lines += line_amt
        else:
            sum_rec_lines += line_amt
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
                "commission_amount": line_amt,
                "remark": remark,
                "created_at": created_at_str,
                "payment_status": _payment_status_zh(row.payment_status),
                "paid_at": paid_at_str,
            }
        )

    commission_yuan = round(sum_reg_lines + sum_rec_lines, 2)

    return {
        "ok": True,
        "month": ym,
        "summary": {
            "service_fee_reg_yuan": round(sum_reg_lines, 2),
            "service_fee_recharge_yuan": round(sum_rec_lines, 2),
            "commission_yuan": commission_yuan,
            "valid_reg_count": reg_count,
            "recharge_total_yuan": round(recharge_sum, 2),
            "reg_factor": float(_cfg.PARTNER_REG_FACTOR),
            "rebate_rate": rebate_rate,
            "settled_commission_yuan": settled_total,
        },
        "referrals": referrals,
        "recharges": recharge_list,
        "recharges_total_yuan": round(recharge_sum, 2),
        "commission_lines": commission_lines,
        "notes": {
            "formula": "服务费=拉新服务费+充值服务费；展示金额与当月服务费明细各行之和一致；入账时拉新系数、充值分润率均为快照。",
        },
    }


@partner_ui_bp.route("/stats/monthly-board", methods=["GET"])
def partner_monthly_board():
    """按月汇总服务费（与 agent_commission_lines 明细一致）+ 拉新/充值列表（依赖 users / payment_orders）。"""
    agent, err = require_partner_token()
    if err:
        return err
    ym = _parse_month_param(request.args.get("month"))
    return jsonify(build_monthly_board_dict(agent, ym))
