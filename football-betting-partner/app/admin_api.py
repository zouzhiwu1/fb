# -*- coding: utf-8 -*-
import logging
import re
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.security import generate_password_hash

from app import db
from app.auth_partner import require_db_admin_token, require_root_only
from app.dashboard import _parse_month_param, build_monthly_board_dict
from app.models import Agent, AgentCommissionSettlement, PartnerAdmin

partner_admin_bp = Blueprint("partner_admin_api", __name__, url_prefix="/api/partner/admin")

_MIGRATE_MSG = (
    "请先在 MySQL 执行 scripts/migrate_partner_admin_and_agent_profile.sql "
    "（或完整 add_partner_tables.sql），确保 agents 表含 real_name、phone、bank_account 等字段。"
)

_SETTLE_MIGRATE_MSG = (
    "请先在 MySQL 执行 scripts/add_agent_settled_commission.sql 与 "
    "scripts/extend_commission_settlement_audit.sql，"
    "确保 agent_commission_settlements 含 partner_admin_id、settlement_month、agent_bank_account。"
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


def _agent_bank_snapshot(agent: Agent) -> str:
    a = (agent.bank_account or "").strip()
    b = (agent.bank_info or "").strip()
    if a and b:
        return f"{a}\n{b}"
    return a or b or ""


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
    if len(np) < 6:
        return jsonify({"ok": False, "message": "密码至少 6 位"}), 400
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
        if len(np) < 6:
            return jsonify({"ok": False, "message": "新密码至少 6 位"}), 400
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
    if len(np) < 6:
        return jsonify({"ok": False, "message": "新密码至少 6 位"}), 400
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
    login_name = (data.get("login_name") or "").strip()
    password = data.get("password") or ""
    agent_code = (data.get("agent_code") or "").strip()
    real_name = (data.get("real_name") or "").strip()
    phone = (data.get("phone") or "").strip()
    bank_account = (data.get("bank_account") or "").strip()
    age_raw = data.get("age")

    if not login_name or not password or not agent_code:
        return jsonify({"ok": False, "message": "请填写登录名、初始密码、推广码"}), 400
    if not real_name or not phone or not bank_account:
        return jsonify(
            {"ok": False, "message": "请填写用户姓名、电话号码、银行账户"}
        ), 400

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
        if Agent.query.filter_by(login_name=login_name).first():
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
            bank_account=bank_account,
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
    """管理员线下打款后登记本次结算金额，累加到代理商已结算总额。"""
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
        return jsonify(
            {"ok": False, "message": "请提供有效结算月份 settlement_month（格式 YYYY-MM）"}
        ), 400

    raw = data.get("amount_yuan")
    try:
        amt = Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return jsonify({"ok": False, "message": "结算金额格式无效"}), 400
    if amt <= 0:
        return jsonify({"ok": False, "message": "结算金额须大于 0"}), 400

    try:
        owed, paid_dec, pending = _owed_paid_pending_commission_yuan(agent, ym)
    except Exception:
        logging.exception("settle_agent_commission pending commission")
        return jsonify({"ok": False, "message": "无法核算该月待付佣金，请稍后重试"}), 500

    if amt > pending:
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

    bank_snap = _agent_bank_snapshot(agent)

    try:
        prev = Decimal(str(agent.settled_commission_yuan or 0)).quantize(
            Decimal("0.01")
        )
        new_total = prev + amt
        agent.settled_commission_yuan = new_total
        row = AgentCommissionSettlement(
            partner_admin_id=admin.id,
            agent_id=agent_id,
            settlement_month=ym,
            agent_bank_account=bank_snap or None,
            amount_yuan=amt,
        )
        db.session.add(row)
        db.session.commit()
        return jsonify(
            {
                "ok": True,
                "settled_commission_yuan": float(new_total),
                "amount_yuan": float(amt),
                "settlement_id": row.id,
                "settlement_month": ym,
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
            login_name = (data.get("login_name") or "").strip()
            if not login_name:
                return jsonify({"ok": False, "message": "登录名不能为空"}), 400
            other = Agent.query.filter(
                Agent.login_name == login_name, Agent.id != agent_id
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
            if not phone:
                return jsonify({"ok": False, "message": "电话号码不能为空"}), 400
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

        if "bank_account" in data:
            v = (data.get("bank_account") or "").strip()
            if not v:
                return jsonify({"ok": False, "message": "银行账户不能为空"}), 400
            agent.bank_account = v

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
            agent.password_hash = generate_password_hash(str(pwd).strip())
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
