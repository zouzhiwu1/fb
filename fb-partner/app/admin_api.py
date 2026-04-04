# -*- coding: utf-8 -*-
import logging
import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.security import generate_password_hash

from fb_common import validate_password_strength

from app import db
from app.auth_partner import require_db_admin_token, require_root_only
from app.contact_format import (
    normalize_email,
    validate_agent_login_email,
    validate_cn_mobile,
    validate_payout_account,
    validate_payout_channel,
    validate_payout_holder_name,
)
from app.dashboard import _parse_month_param, build_monthly_board_dict
from app.models import (
    Agent,
    AgentCommissionLine,
    AgentCommissionSettlement,
    PartnerAdmin,
    PayoutOrder,
)

partner_admin_bp = Blueprint("partner_admin_api", __name__, url_prefix="/api/partner/admin")

_MIGRATE_MSG = (
    "请先在 MySQL 执行 scripts/migrate_agent_payout_profile.sql "
    "（或完整 add_partner_tables.sql / init_database.sql），"
    "确保 agents 表含 payout_channel、payout_account、payout_holder_name，且 login_name 可为 VARCHAR(128)。"
)

_SETTLE_MIGRATE_MSG = (
    "请先在 MySQL 执行 scripts/extend_commission_settlement_payment.sql，"
    "确保 agent_commission_settlements 含 payment_channel、payment_reference、payment_note。"
)

_SETTLEMENT_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _agent_code_taken(agent_code: str, exclude_agent_id: int | None) -> bool:
    """推广码全局唯一，比较时不区分大小写（与库唯一约束互补，避免 D001 / d001 并存）。"""
    raw = (agent_code or "").strip()
    if not raw:
        return False
    lc = raw.lower()
    q = Agent.query.filter(func.lower(Agent.agent_code) == lc)
    if exclude_agent_id is not None:
        q = q.filter(Agent.id != exclude_agent_id)
    return q.first() is not None


def _owed_paid_pending_commission_yuan(
    agent: Agent, ym: str
) -> tuple[Decimal, Decimal, Decimal]:
    """按月度看板核算：本月应计佣金、本月已结算流水合计、待付（应计−已结，不低于 0）。"""
    board = build_monthly_board_dict(agent, ym)
    raw_owed = (board.get("summary") or {}).get("commission_yuan")
    owed = Decimal(str(raw_owed if raw_owed is not None else 0)).quantize(
        Decimal("0.01")
    )
    paid = db.session.query(
        func.coalesce(func.sum(AgentCommissionSettlement.amount_yuan), 0)
    ).filter(
        AgentCommissionSettlement.agent_id == agent.id,
        AgentCommissionSettlement.settlement_month == ym,
    ).scalar()
    paid_dec = Decimal(str(paid if paid is not None else 0)).quantize(Decimal("0.01"))
    pending = (owed - paid_dec).quantize(Decimal("0.01"))
    if pending < 0:
        pending = Decimal("0")
    return owed, paid_dec, pending


def _month_start_end(ym: str) -> tuple[datetime, datetime]:
    y, m = map(int, ym.split("-"))
    start = datetime(y, m, 1)
    if m == 12:
        end = datetime(y + 1, 1, 1)
    else:
        end = datetime(y, m + 1, 1)
    return start, end


def _mask_phone(phone: object | None) -> str:
    if phone is None:
        return "—"
    p = str(phone).strip()
    if len(p) >= 11:
        return f"{p[:3]}****{p[-4:]}"
    if len(p) >= 7:
        return f"{p[:2]}****{p[-2:]}"
    return "****"


def _sync_agent_commission_lines(agent: Agent, ym: str) -> None:
    """
    将指定月份的注册/充值事件增量写入 agent_commission_lines（幂等）。
    """
    import config as _cfg

    start, end = _month_start_end(ym)
    aid = agent.id
    reg_factor = Decimal(str(_cfg.PARTNER_REG_FACTOR)).quantize(Decimal("0.0001"))
    rebate_rate = Decimal(str(agent.current_rate or 0)).quantize(Decimal("0.0001"))
    commission_per_point = Decimal(str(_cfg.PARTNER_COMMISSION_PER_POINT)).quantize(
        Decimal("0.0001")
    )

    # 拉新事件：按 (agent_id, user_id, commission_type=registration) 幂等
    reg_rows = db.session.execute(
        text(
            """
            SELECT u.id AS user_id, u.phone AS phone, u.created_at AS created_at
            FROM users u
            WHERE u.agent_id = :aid
              AND u.created_at >= :start AND u.created_at < :end
            """
        ),
        {"aid": aid, "start": start, "end": end},
    ).mappings().all()
    for r in reg_rows:
        uid = int(r["user_id"])
        exists = AgentCommissionLine.query.filter_by(
            agent_id=aid,
            user_id=uid,
            commission_type="registration",
        ).first()
        if exists:
            continue
        c = AgentCommissionLine(
            agent_id=aid,
            user_id=uid,
            username=_mask_phone(r.get("phone")),
            commission_type="registration",
            created_at=r.get("created_at") or datetime.utcnow(),
            reg_factor=reg_factor,
            commission_amount=Decimal(str(reg_factor)).quantize(Decimal("0.01")),
            payment_status="pending",
        )
        db.session.add(c)

    # 充值事件：按 (agent_id, payment_order_id) 幂等
    recharge_rows = db.session.execute(
        text(
            """
            SELECT po.id AS payment_order_id, po.user_id AS user_id, po.total_amount AS total_amount, po.paid_at AS paid_at, u.phone AS phone
            FROM payment_orders po
            INNER JOIN users u ON u.id = po.user_id
            WHERE u.agent_id = :aid
              AND po.status = 'paid'
              AND po.paid_at IS NOT NULL
              AND po.paid_at >= :start AND po.paid_at < :end
            """
        ),
        {"aid": aid, "start": start, "end": end},
    ).mappings().all()
    for r in recharge_rows:
        payment_order_id = str(r["payment_order_id"])
        exists = AgentCommissionLine.query.filter_by(
            agent_id=aid,
            payment_order_id=payment_order_id,
            commission_type="recharge",
        ).first()
        if exists:
            continue
        recharge_amount = Decimal(str(r.get("total_amount") or 0)).quantize(
            Decimal("0.01")
        )
        commission_amount = (recharge_amount * rebate_rate * commission_per_point).quantize(
            Decimal("0.01")
        )
        c = AgentCommissionLine(
            agent_id=aid,
            user_id=int(r["user_id"]),
            username=_mask_phone(r.get("phone")),
            commission_type="recharge",
            created_at=r.get("paid_at") or datetime.utcnow(),
            payment_order_id=payment_order_id,
            recharge_amount=recharge_amount,
            rebate_rate=rebate_rate,
            commission_amount=commission_amount,
            payment_status="pending",
        )
        db.session.add(c)


def _agent_public_row(a: Agent) -> dict:
    return {
        "id": a.id,
        "agent_code": a.agent_code,
        "login_name": a.login_name,
        "display_name": a.display_name,
        "real_name": a.real_name,
        "age": a.age,
        "phone": a.phone,
        "bank_account": a.bank_account,
        "bank_info": a.bank_info,
        "payout_channel": a.payout_channel,
        "payout_account": a.payout_account,
        "payout_holder_name": a.payout_holder_name,
        "current_rate": float(a.current_rate or 0),
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "settled_commission_yuan": round(float(a.settled_commission_yuan or 0), 2),
    }


def _partner_admin_public_row(a: PartnerAdmin) -> dict:
    return {
        "id": a.id,
        "login_name": a.login_name,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@partner_admin_bp.route("/admins", methods=["GET"])
def list_partner_admins():
    er = require_root_only()
    if er is not None:
        return er
    admins = PartnerAdmin.query.order_by(PartnerAdmin.id.asc()).all()
    return jsonify(
        {"ok": True, "admins": [_partner_admin_public_row(a) for a in admins]}
    )


@partner_admin_bp.route("/admins", methods=["POST"])
def create_partner_admin():
    er = require_root_only()
    if er is not None:
        return er
    data = request.get_json(silent=True) or {}
    login_name = (data.get("login_name") or "").strip()
    password = data.get("password") or ""
    if not login_name or not str(password).strip():
        return jsonify({"ok": False, "message": "请填写登录名与密码"}), 400
    if login_name.lower() == "root":
        return jsonify(
            {
                "ok": False,
                "message": "登录名不可为 root（保留给部署根账号，与库内管理员区分）。",
            }
        ), 400
    np = str(password).strip()
    ok_pw, pw_msg = validate_password_strength(np)
    if not ok_pw:
        return jsonify({"ok": False, "message": pw_msg}), 400
    if PartnerAdmin.query.filter_by(login_name=login_name).first():
        return jsonify({"ok": False, "message": "该登录名已存在"}), 400
    try:
        admin = PartnerAdmin(
            login_name=login_name,
            password_hash=generate_password_hash(np),
        )
        db.session.add(admin)
        db.session.commit()
        return jsonify({"ok": True, "admin": _partner_admin_public_row(admin)})
    except IntegrityError:
        db.session.rollback()
        return jsonify({"ok": False, "message": "登录名冲突"}), 400


@partner_admin_bp.route("/admins/<int:admin_id>", methods=["PUT"])
def update_partner_admin(admin_id: int):
    """根账号：修改登录名、状态；可选新密码（留空不改）。"""
    er = require_root_only()
    if er is not None:
        return er
    admin = db.session.get(PartnerAdmin, admin_id)
    if not admin:
        return jsonify({"ok": False, "message": "管理员不存在"}), 404

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"ok": False, "message": "无效的 JSON"}), 400

    bump_sv = False

    if "login_name" in data:
        new_ln = (data.get("login_name") or "").strip()
        if not new_ln:
            return jsonify({"ok": False, "message": "登录名不能为空"}), 400
        if new_ln.lower() == "root":
            return jsonify(
                {"ok": False, "message": "登录名不可为 root（保留给部署根账号）。"}
            ), 400
        if new_ln != admin.login_name:
            if PartnerAdmin.query.filter(
                PartnerAdmin.login_name == new_ln, PartnerAdmin.id != admin_id
            ).first():
                return jsonify({"ok": False, "message": "该登录名已存在"}), 400
            admin.login_name = new_ln
            bump_sv = True

    if "status" in data:
        st = (data.get("status") or "").strip().lower()
        if st not in ("active", "disabled"):
            return jsonify(
                {"ok": False, "message": "状态须为 active 或 disabled"}
            ), 400
        if admin.status != st:
            admin.status = st
            bump_sv = True

    np = str(data.get("new_password") or "").strip()
    if np:
        ok_pw, pw_msg = validate_password_strength(np)
        if not ok_pw:
            return jsonify({"ok": False, "message": pw_msg}), 400
        admin.password_hash = generate_password_hash(np)
        bump_sv = True

    if bump_sv:
        admin.session_version = int(admin.session_version or 1) + 1

    try:
        db.session.commit()
        return jsonify({"ok": True, "admin": _partner_admin_public_row(admin)})
    except IntegrityError:
        db.session.rollback()
        return jsonify({"ok": False, "message": "登录名冲突"}), 400


@partner_admin_bp.route("/admins/<int:admin_id>/password", methods=["PUT"])
def reset_partner_admin_password(admin_id: int):
    """兼容旧前端：仅改密（等价于 PUT /admins/<id> 只传 new_password）。"""
    er = require_root_only()
    if er is not None:
        return er
    admin = db.session.get(PartnerAdmin, admin_id)
    if not admin:
        return jsonify({"ok": False, "message": "管理员不存在"}), 404
    data = request.get_json(silent=True) or {}
    np = str(data.get("new_password") or "").strip()
    ok_pw, pw_msg = validate_password_strength(np)
    if not ok_pw:
        return jsonify({"ok": False, "message": pw_msg}), 400
    admin.password_hash = generate_password_hash(np)
    admin.session_version = int(admin.session_version or 1) + 1
    db.session.commit()
    return jsonify({"ok": True})


@partner_admin_bp.route("/admins/<int:admin_id>", methods=["DELETE"])
def delete_partner_admin(admin_id: int):
    er = require_root_only()
    if er is not None:
        return er
    admin = db.session.get(PartnerAdmin, admin_id)
    if not admin:
        return jsonify({"ok": False, "message": "管理员不存在"}), 404
    if PartnerAdmin.query.count() <= 1:
        return jsonify(
            {"ok": False, "message": "至少保留一名库内管理员，无法删除。"}
        ), 400
    try:
        AgentCommissionSettlement.query.filter_by(
            partner_admin_id=admin_id
        ).update(
            {AgentCommissionSettlement.partner_admin_id: None},
            synchronize_session=False,
        )
        db.session.delete(admin)
        db.session.commit()
        return jsonify({"ok": True})
    except Exception:
        db.session.rollback()
        logging.exception("delete_partner_admin")
        return jsonify({"ok": False, "message": "删除失败"}), 500


@partner_admin_bp.route("/agents/check-agent-code", methods=["GET"])
def check_agent_code_available():
    """注册/修改推广码前校验是否可用（不区分大小写）。"""
    _, err = require_db_admin_token()
    if err:
        return err
    code = (request.args.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "message": "请提供推广码参数 code"}), 400
    exclude_id = request.args.get("exclude_id", type=int)
    taken = _agent_code_taken(code, exclude_id)
    return jsonify(
        {
            "ok": True,
            "available": not taken,
            "message": ("该推广码已被使用，请更换。" if taken else "该推广码可以使用。"),
        }
    )


@partner_admin_bp.route("/agents", methods=["GET"])
def list_agents():
    _, err = require_db_admin_token()
    if err:
        return err
    try:
        agents = Agent.query.order_by(Agent.id.desc()).limit(500).all()
        return jsonify({"ok": True, "agents": [_agent_public_row(a) for a in agents]})
    except Exception:
        logging.exception("list_agents")
        return jsonify(
            {
                "ok": False,
                "message": "读取代理商列表失败，请确认已执行 scripts 中的库迁移（agents 表含 real_name 等字段）。",
            }
        ), 500


@partner_admin_bp.route("/agents", methods=["POST"])
def create_agent():
    _, err = require_db_admin_token()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    login_name = normalize_email(data.get("login_name"))
    password = data.get("password") or ""
    agent_code = (data.get("agent_code") or "").strip()
    real_name = (data.get("real_name") or "").strip()
    phone = (data.get("phone") or "").strip()
    pch = (data.get("payout_channel") or "").strip().lower()
    pacct = (data.get("payout_account") or "").strip()
    pholder = (data.get("payout_holder_name") or "").strip()
    age_raw = data.get("age")

    if not login_name or not password or not agent_code:
        return jsonify({"ok": False, "message": "请填写登录名、初始密码、推广码"}), 400
    ok_ln, ln_msg = validate_agent_login_email(login_name)
    if not ok_ln:
        return jsonify({"ok": False, "message": ln_msg}), 400
    ok_pw, pw_msg = validate_password_strength(str(password).strip())
    if not ok_pw:
        return jsonify({"ok": False, "message": pw_msg}), 400
    ok_ph, ph_msg = validate_cn_mobile(phone)
    if not ok_ph:
        return jsonify({"ok": False, "message": ph_msg}), 400
    if not real_name:
        return jsonify({"ok": False, "message": "请填写用户姓名"}), 400
    ok_pc, pc_msg = validate_payout_channel(pch)
    if not ok_pc:
        return jsonify({"ok": False, "message": pc_msg}), 400
    ok_pa, pa_msg = validate_payout_account(pacct)
    if not ok_pa:
        return jsonify({"ok": False, "message": pa_msg}), 400
    ok_h, h_msg = validate_payout_holder_name(pholder)
    if not ok_h:
        return jsonify({"ok": False, "message": h_msg}), 400

    try:
        age = int(age_raw)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "请填写有效年龄（数字）"}), 400
    if age < 1 or age > 120:
        return jsonify({"ok": False, "message": "年龄应在 1～120 之间"}), 400

    display_name = (data.get("display_name") or real_name).strip()
    cr = data.get("current_rate", 0)
    try:
        current_rate = float(cr) if cr is not None and cr != "" else 0.0
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "返点率格式无效"}), 400

    try:
        if Agent.query.filter(func.lower(Agent.login_name) == login_name).first():
            return jsonify({"ok": False, "message": "该登录名已存在"}), 400
        if _agent_code_taken(agent_code, None):
            return jsonify(
                {
                    "ok": False,
                    "message": "推广码已存在，请更换（全局唯一，不区分大小写）。",
                }
            ), 400
        if Agent.query.filter_by(phone=phone).first():
            return jsonify({"ok": False, "message": "该电话号码已被使用"}), 400

        agent = Agent(
            agent_code=agent_code,
            login_name=login_name,
            password_hash=generate_password_hash(password),
            display_name=display_name,
            real_name=real_name,
            age=age,
            phone=phone,
            payout_channel=pch,
            payout_account=pacct,
            payout_holder_name=pholder,
            contact=phone,
            current_rate=current_rate,
        )
        db.session.add(agent)
        db.session.commit()
        return jsonify({"ok": True, "agent": _agent_public_row(agent)})
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            {
                "ok": False,
                "message": "数据冲突：登录名、推广码（须唯一）或电话可能已存在。",
            }
        ), 400
    except OperationalError:
        db.session.rollback()
        logging.exception("create_agent")
        return jsonify({"ok": False, "message": _MIGRATE_MSG}), 500
    except Exception:
        db.session.rollback()
        logging.exception("create_agent")
        return jsonify({"ok": False, "message": _MIGRATE_MSG}), 500


@partner_admin_bp.route("/agents/<int:agent_id>/commission/settle", methods=["POST"])
def settle_agent_commission(agent_id: int):
    """管理员线下打款后，按勾选佣金明细批量结算。"""
    admin, err = require_db_admin_token()
    if err:
        return err
    assert admin is not None
    agent = db.session.get(Agent, agent_id)
    if not agent:
        return jsonify({"ok": False, "message": "代理商不存在"}), 404

    data = request.get_json(silent=True) or {}
    ym = (data.get("settlement_month") or "").strip()
    if not _SETTLEMENT_MONTH_RE.match(ym):
        return jsonify({"ok": False, "message": "请提供有效结算月份 settlement_month（YYYY-MM）"}), 400

    line_ids = data.get("line_ids") or []
    # 兼容旧版调用：仅传 amount_yuan + settlement_month（无 line_ids）
    if not isinstance(line_ids, list) or not line_ids:
        raw_old = data.get("amount_yuan")
        try:
            amt_old = Decimal(str(raw_old)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            return jsonify({"ok": False, "message": "结算金额格式无效"}), 400
        if amt_old <= 0:
            return jsonify({"ok": False, "message": "结算金额须大于 0"}), 400
        try:
            owed, paid_dec, pending = _owed_paid_pending_commission_yuan(agent, ym)
        except Exception:
            logging.exception("settle_agent_commission pending commission")
            return jsonify({"ok": False, "message": "无法核算该月待付佣金，请稍后重试"}), 500
        if amt_old > pending:
            return jsonify(
                {
                    "ok": False,
                    "message": (
                        "结算金额不能超过本月待付佣金。"
                        f"当月应计佣金 {owed} 元，本月已累计结算 {paid_dec} 元，待付 {pending} 元。"
                    ),
                    "commission_yuan_month": float(owed),
                    "settled_month_total_yuan": float(paid_dec),
                    "pending_commission_yuan": float(pending),
                }
            ), 400
        ch_old = (data.get("payment_channel") or "").strip().lower()
        if ch_old not in ("alipay", "wechat"):
            return jsonify({"ok": False, "message": "请提供有效支付渠道 payment_channel：alipay 或 wechat"}), 400
        ref_old = (data.get("payment_reference") or "").strip()
        if not ref_old:
            return jsonify({"ok": False, "message": "请填写线下打款订单号 payment_reference"}), 400
        note_old = (data.get("payment_note") or "").strip() or None
        prev_old = Decimal(str(agent.settled_commission_yuan or 0)).quantize(Decimal("0.01"))
        new_total_old = (prev_old + amt_old).quantize(Decimal("0.01"))
        agent.settled_commission_yuan = new_total_old
        row_old = AgentCommissionSettlement(
            partner_admin_id=admin.id,
            agent_id=agent_id,
            settlement_month=ym,
            payment_channel=ch_old,
            payment_reference=ref_old,
            payment_note=note_old,
            amount_yuan=amt_old,
        )
        db.session.add(row_old)
        db.session.commit()
        return jsonify(
            {
                "ok": True,
                "settled_commission_yuan": float(new_total_old),
                "amount_yuan": float(amt_old),
                "settlement_id": row_old.id,
                "settlement_month": ym,
                "payment_channel": ch_old,
                "payment_reference": ref_old,
            }
        )
    try:
        line_ids = [int(x) for x in line_ids]
    except Exception:
        return jsonify({"ok": False, "message": "line_ids 格式无效"}), 400

    raw = data.get("paid_amount")
    try:
        paid_amount = Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return jsonify({"ok": False, "message": "实付金额 paid_amount 格式无效"}), 400
    if paid_amount <= 0:
        return jsonify({"ok": False, "message": "实付金额须大于 0"}), 400

    ref = (data.get("payout_reference") or "").strip()
    if not ref:
        return jsonify({"ok": False, "message": "请填写线下打款凭证号 payout_reference"}), 400
    if len(ref) > 256:
        return jsonify({"ok": False, "message": "凭证号过长（最多 256 字符）"}), 400
    remark = (data.get("remark") or "").strip() or None

    try:
        _sync_agent_commission_lines(agent, ym)
        db.session.flush()

        rows = AgentCommissionLine.query.filter(
            AgentCommissionLine.id.in_(line_ids),
            AgentCommissionLine.agent_id == agent_id,
        ).with_for_update().all()
        if len(rows) != len(set(line_ids)):
            return jsonify({"ok": False, "message": "部分佣金明细不存在或不属于该代理商"}), 400
        if any((r.payment_status or "pending") != "pending" for r in rows):
            return jsonify({"ok": False, "message": "仅可结算待支付（pending）佣金明细"}), 400

        total = Decimal("0.00")
        for r in rows:
            total += Decimal(str(r.commission_amount or 0))
        total = total.quantize(Decimal("0.01"))
        if total != paid_amount:
            return jsonify(
                {
                    "ok": False,
                    "message": f"实付金额与勾选明细佣金合计不一致：合计 {total} 元，实付 {paid_amount} 元",
                    "selected_total": float(total),
                    "paid_amount": float(paid_amount),
                }
            ), 400

        now = datetime.utcnow()
        payout = PayoutOrder(
            order_id=f"PO{now.strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4().hex[:6]).upper()}",
            agent_id=agent_id,
            total_amount=paid_amount,
            paid_at=now,
            paid_by_admin_id=admin.id,
            payout_reference=ref,
            status="paid",
            remark=remark,
        )
        db.session.add(payout)
        db.session.flush()

        batch_id = uuid.uuid4().hex
        for r in rows:
            r.payment_status = "paid"
            r.paid_at = now
            r.paid_by_admin_id = admin.id
            r.payout_reference = ref
            r.payment_batch_id = batch_id
            r.payout_order_id = payout.id

        # 兼容旧字段：累计已结算
        prev = Decimal(str(agent.settled_commission_yuan or 0)).quantize(Decimal("0.01"))
        agent.settled_commission_yuan = (prev + paid_amount).quantize(Decimal("0.01"))

        # 兼容旧结算流水表：保留一条聚合记录
        legacy = AgentCommissionSettlement(
            partner_admin_id=admin.id,
            agent_id=agent_id,
            settlement_month=ym,
            payment_channel=None,
            payment_reference=ref,
            payment_note=remark,
            amount_yuan=paid_amount,
        )
        db.session.add(legacy)
        db.session.commit()
        return jsonify(
            {
                "ok": True,
                "payout_order_id": payout.id,
                "order_id": payout.order_id,
                "payment_batch_id": batch_id,
                "paid_amount": float(paid_amount),
                "line_count": len(rows),
                "settled_commission_yuan": float(agent.settled_commission_yuan or 0),
            }
        )
    except OperationalError:
        db.session.rollback()
        logging.exception("settle_agent_commission")
        return jsonify({"ok": False, "message": _SETTLE_MIGRATE_MSG}), 500
    except Exception:
        db.session.rollback()
        logging.exception("settle_agent_commission")
        return jsonify({"ok": False, "message": "结算失败"}), 500


@partner_admin_bp.route("/agents/<int:agent_id>/monthly-board", methods=["GET"])
def admin_agent_monthly_board(agent_id: int):
    """管理员代查某代理商月度业绩（与代理商本人 /api/partner/stats/monthly-board 一致）。"""
    _, err = require_db_admin_token()
    if err:
        return err
    agent = db.session.get(Agent, agent_id)
    if not agent:
        return jsonify({"ok": False, "message": "代理商不存在"}), 404
    ym = _parse_month_param(request.args.get("month"))
    try:
        return jsonify(build_monthly_board_dict(agent, ym))
    except Exception:
        logging.exception("admin_agent_monthly_board")
        return jsonify({"ok": False, "message": "查询失败"}), 500


@partner_admin_bp.route("/agents/<int:agent_id>/commission-lines", methods=["GET"])
def admin_agent_commission_lines(agent_id: int):
    """管理员查看代理商佣金明细（统一拉新/充值）。"""
    _, err = require_db_admin_token()
    if err:
        return err
    agent = db.session.get(Agent, agent_id)
    if not agent:
        return jsonify({"ok": False, "message": "代理商不存在"}), 404

    ym = _parse_month_param(request.args.get("month"))
    if not _SETTLEMENT_MONTH_RE.match(ym):
        return jsonify({"ok": False, "message": "month 参数格式错误，应为 YYYY-MM"}), 400
    try:
        _sync_agent_commission_lines(agent, ym)
        db.session.commit()
        start, end = _month_start_end(ym)
        rows = (
            AgentCommissionLine.query.filter(
                AgentCommissionLine.agent_id == agent_id,
                AgentCommissionLine.created_at >= start,
                AgentCommissionLine.created_at < end,
            )
            .order_by(AgentCommissionLine.created_at.desc(), AgentCommissionLine.id.desc())
            .all()
        )
        total = Decimal("0.00")
        pending = Decimal("0.00")
        items = []
        for r in rows:
            amt = Decimal(str(r.commission_amount or 0)).quantize(Decimal("0.01"))
            total += amt
            if (r.payment_status or "pending") == "pending":
                pending += amt
            if r.commission_type == "registration":
                remark = f"reg_factor={float(r.reg_factor or 0):g}"
            else:
                remark = (
                    f"充值金额={float(r.recharge_amount or 0):.2f}，"
                    f"返点率={float(r.rebate_rate or 0) * 100:.2f}%"
                )
            items.append(
                {
                    "id": int(r.id),
                    "user_id": int(r.user_id),
                    "username": r.username,
                    "commission_type": r.commission_type,
                    "commission_amount": float(amt),
                    "remark": remark,
                    "created_at": r.created_at.isoformat(sep=" ", timespec="seconds")
                    if r.created_at
                    else None,
                    "payment_status": r.payment_status,
                    "paid_at": r.paid_at.isoformat(sep=" ", timespec="seconds")
                    if r.paid_at
                    else None,
                    "payment_batch_id": r.payment_batch_id,
                }
            )
        return jsonify(
            {
                "ok": True,
                "month": ym,
                "items": items,
                "summary": {
                    "commission_total": float(total.quantize(Decimal("0.01"))),
                    "pending_total": float(pending.quantize(Decimal("0.01"))),
                    "line_count": len(items),
                },
            }
        )
    except Exception:
        db.session.rollback()
        logging.exception("admin_agent_commission_lines")
        return jsonify({"ok": False, "message": "佣金明细查询失败"}), 500


@partner_admin_bp.route("/agents/<int:agent_id>", methods=["GET"])
def get_agent(agent_id: int):
    _, err = require_db_admin_token()
    if err:
        return err
    try:
        agent = db.session.get(Agent, agent_id)
        if not agent:
            return jsonify({"ok": False, "message": "代理商不存在"}), 404
        return jsonify({"ok": True, "agent": _agent_public_row(agent)})
    except Exception:
        logging.exception("get_agent")
        return jsonify({"ok": False, "message": "读取失败"}), 500


@partner_admin_bp.route("/agents/<int:agent_id>", methods=["PUT"])
def update_agent(agent_id: int):
    _, err = require_db_admin_token()
    if err:
        return err
    agent = db.session.get(Agent, agent_id)
    if not agent:
        return jsonify({"ok": False, "message": "代理商不存在"}), 404

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"ok": False, "message": "无效的 JSON"}), 400

    try:
        if "login_name" in data:
            login_name = normalize_email(data.get("login_name"))
            ok_ln, ln_msg = validate_agent_login_email(login_name)
            if not ok_ln:
                return jsonify({"ok": False, "message": ln_msg}), 400
            other = Agent.query.filter(
                func.lower(Agent.login_name) == login_name, Agent.id != agent_id
            ).first()
            if other:
                return jsonify({"ok": False, "message": "该登录名已被使用"}), 400
            agent.login_name = login_name

        if "agent_code" in data:
            agent_code = (data.get("agent_code") or "").strip()
            if not agent_code:
                return jsonify({"ok": False, "message": "推广码不能为空"}), 400
            if _agent_code_taken(agent_code, agent_id):
                return jsonify(
                    {
                        "ok": False,
                        "message": "推广码已存在，请更换（全局唯一，不区分大小写）。",
                    }
                ), 400
            agent.agent_code = agent_code

        if "phone" in data:
            phone = (data.get("phone") or "").strip()
            ok_ph, ph_msg = validate_cn_mobile(phone)
            if not ok_ph:
                return jsonify({"ok": False, "message": ph_msg}), 400
            other = Agent.query.filter(Agent.phone == phone, Agent.id != agent_id).first()
            if other:
                return jsonify({"ok": False, "message": "该电话号码已被使用"}), 400
            agent.phone = phone
            agent.contact = phone

        if "real_name" in data:
            v = (data.get("real_name") or "").strip()
            agent.real_name = v or None

        if "display_name" in data:
            v = (data.get("display_name") or "").strip()
            agent.display_name = v or agent.display_name or ""

        if any(
            k in data
            for k in ("payout_channel", "payout_account", "payout_holder_name")
        ):
            pch = (
                data["payout_channel"]
                if "payout_channel" in data
                else agent.payout_channel
            )
            pch = (pch or "").strip().lower()
            pacct = (
                data["payout_account"]
                if "payout_account" in data
                else agent.payout_account
            )
            pacct = (pacct or "").strip()
            pho = (
                data["payout_holder_name"]
                if "payout_holder_name" in data
                else agent.payout_holder_name
            )
            pho = (pho or "").strip()
            ok_pc, pc_msg = validate_payout_channel(pch)
            if not ok_pc:
                return jsonify({"ok": False, "message": pc_msg}), 400
            ok_pa, pa_msg = validate_payout_account(pacct)
            if not ok_pa:
                return jsonify({"ok": False, "message": pa_msg}), 400
            ok_h, h_msg = validate_payout_holder_name(pho)
            if not ok_h:
                return jsonify({"ok": False, "message": h_msg}), 400
            agent.payout_channel = pch
            agent.payout_account = pacct
            agent.payout_holder_name = pho

        if "age" in data:
            try:
                age = int(data.get("age"))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "message": "年龄须为数字"}), 400
            if age < 1 or age > 120:
                return jsonify({"ok": False, "message": "年龄应在 1～120 之间"}), 400
            agent.age = age

        if "current_rate" in data:
            cr = data.get("current_rate")
            try:
                agent.current_rate = float(cr) if cr is not None and cr != "" else 0.0
            except (TypeError, ValueError):
                return jsonify({"ok": False, "message": "返点率格式无效"}), 400

        if "status" in data:
            st = (data.get("status") or "").strip().lower()
            if st not in ("active", "disabled"):
                return jsonify(
                    {"ok": False, "message": "状态须为 active 或 disabled"}
                ), 400
            agent.status = st

        pwd = data.get("password")
        if pwd is not None and str(pwd).strip() != "":
            pws = str(pwd).strip()
            ok_pw, pw_msg = validate_password_strength(pws)
            if not ok_pw:
                return jsonify({"ok": False, "message": pw_msg}), 400
            agent.password_hash = generate_password_hash(pws)
            agent.session_version = int(agent.session_version or 1) + 1

        db.session.commit()
        return jsonify({"ok": True, "agent": _agent_public_row(agent)})
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            {
                "ok": False,
                "message": "数据冲突：登录名、推广码（须唯一）或电话可能重复。",
            }
        ), 400
    except OperationalError:
        db.session.rollback()
        logging.exception("update_agent")
        return jsonify({"ok": False, "message": _MIGRATE_MSG}), 500
    except Exception:
        db.session.rollback()
        logging.exception("update_agent")
        return jsonify({"ok": False, "message": _MIGRATE_MSG}), 500
