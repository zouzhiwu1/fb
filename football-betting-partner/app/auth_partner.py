# -*- coding: utf-8 -*-
import datetime
import logging
import secrets
from dataclasses import dataclass
from typing import Any, Optional, Tuple

import jwt
from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

import config as _cfg
from app import db
from app.models import Agent, PartnerAdmin

partner_auth_bp = Blueprint("partner_auth", __name__)

# JWT / whoami 中的根登录名；表单可输入 Root、ROOT，均视为 root
_ROOT_JWT_LOGIN_NAME = "root"


@dataclass
class AuthenticatedAdmin:
    """管理员 JWT 解析结果：根账号（.env）或库内管理员。"""

    is_root: bool
    admin: Optional[PartnerAdmin] = None


def _decode_jwt(token: str) -> Optional[dict[str, Any]]:
    if not token:
        return None
    try:
        return jwt.decode(
            token,
            _cfg.PARTNER_JWT_SECRET_KEY,
            algorithms=[_cfg.PARTNER_JWT_ALGORITHM],
        )
    except jwt.PyJWTError:
        return None


def _root_password_configured() -> bool:
    return bool(_cfg.PARTNER_ROOT_PASSWORD)


def require_partner_token() -> Tuple[
    Optional[Agent], Optional[Tuple[Any, int]]
]:
    auth = request.headers.get("Authorization", "")
    token = None
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
    if not token:
        return None, (jsonify({"ok": False, "message": "未登录"}), 401)
    payload = _decode_jwt(token)
    if not payload or payload.get("sub_type") != "partner":
        return None, (jsonify({"ok": False, "message": "登录已失效"}), 401)
    agent_id = payload.get("agent_id")
    sv = payload.get("session_version")
    if agent_id is None or sv is None:
        return None, (jsonify({"ok": False, "message": "登录已失效"}), 401)
    agent = db.session.get(Agent, int(agent_id))
    if not agent or agent.status != "active" or int(agent.session_version) != int(sv):
        return None, (jsonify({"ok": False, "message": "登录已失效"}), 401)
    return agent, None


def require_admin_auth() -> Tuple[
    Optional[AuthenticatedAdmin], Optional[Tuple[Any, int]]
]:
    auth = request.headers.get("Authorization", "")
    token = None
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
    if not token:
        return None, (jsonify({"ok": False, "message": "未登录"}), 401)
    payload = _decode_jwt(token)
    if not payload or payload.get("sub_type") != "partner_admin":
        return None, (jsonify({"ok": False, "message": "登录已失效"}), 401)

    if payload.get("admin_role") == "root":
        if not _root_password_configured():
            return None, (jsonify({"ok": False, "message": "登录已失效"}), 401)
        if (payload.get("login_name") or "").strip().lower() != _ROOT_JWT_LOGIN_NAME:
            return None, (jsonify({"ok": False, "message": "登录已失效"}), 401)
        if int(payload.get("session_version") or 0) != int(
            _cfg.PARTNER_ROOT_SESSION_VERSION
        ):
            return None, (jsonify({"ok": False, "message": "登录已失效"}), 401)
        return AuthenticatedAdmin(is_root=True), None

    admin_id = payload.get("admin_id")
    if admin_id is None:
        return None, (jsonify({"ok": False, "message": "登录已失效"}), 401)
    sv = payload.get("session_version")
    if sv is None:
        return None, (jsonify({"ok": False, "message": "登录已失效"}), 401)
    admin = db.session.get(PartnerAdmin, int(admin_id))
    if not admin or admin.status != "active" or int(admin.session_version) != int(sv):
        return None, (jsonify({"ok": False, "message": "登录已失效"}), 401)
    return AuthenticatedAdmin(is_root=False, admin=admin), None


def require_db_admin_token() -> Tuple[
    Optional[PartnerAdmin], Optional[Tuple[Any, int]]
]:
    """仅库内管理员（可操作代理商）；根账号会得到 403。"""
    auth, err = require_admin_auth()
    if err is not None:
        return None, err
    if auth.is_root:
        return None, (
            jsonify(
                {
                    "ok": False,
                    "message": "根账号仅可维护后台管理员账户，不能使用代理商管理功能。",
                }
            ),
            403,
        )
    return auth.admin, None


def require_root_only() -> Optional[Tuple[Any, int]]:
    """若返回非 None，应直接 return 该元组 (jsonify, status)。"""
    auth, err = require_admin_auth()
    if err is not None:
        return err
    if not auth.is_root:
        return jsonify({"ok": False, "message": "仅部署根账号可执行此操作。"}), 403
    return None


def issue_partner_token(agent: Agent) -> str:
    now = datetime.datetime.utcnow()
    exp = now + datetime.timedelta(hours=_cfg.PARTNER_JWT_EXPIRE_HOURS)
    payload = {
        "sub_type": "partner",
        "agent_id": agent.id,
        "login_name": agent.login_name,
        "session_version": agent.session_version,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(
        payload,
        _cfg.PARTNER_JWT_SECRET_KEY,
        algorithm=_cfg.PARTNER_JWT_ALGORITHM,
    )


def issue_admin_token(admin: PartnerAdmin) -> str:
    now = datetime.datetime.utcnow()
    exp = now + datetime.timedelta(hours=_cfg.PARTNER_JWT_EXPIRE_HOURS)
    payload = {
        "sub_type": "partner_admin",
        "admin_role": "admin",
        "admin_id": admin.id,
        "login_name": admin.login_name,
        "session_version": admin.session_version,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(
        payload,
        _cfg.PARTNER_JWT_SECRET_KEY,
        algorithm=_cfg.PARTNER_JWT_ALGORITHM,
    )


def issue_root_token() -> str:
    now = datetime.datetime.utcnow()
    exp = now + datetime.timedelta(hours=_cfg.PARTNER_JWT_EXPIRE_HOURS)
    payload = {
        "sub_type": "partner_admin",
        "admin_role": "root",
        "login_name": _ROOT_JWT_LOGIN_NAME,
        "session_version": _cfg.PARTNER_ROOT_SESSION_VERSION,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(
        payload,
        _cfg.PARTNER_JWT_SECRET_KEY,
        algorithm=_cfg.PARTNER_JWT_ALGORITHM,
    )


@partner_auth_bp.route("/login", methods=["POST"])
def partner_login():
    data = request.get_json(silent=True) or {}
    login_name = (data.get("login_name") or "").strip()
    password = data.get("password") or ""
    if not login_name or not password:
        return jsonify({"ok": False, "message": "请输入账号和密码"}), 400
    agent = Agent.query.filter_by(login_name=login_name).first()
    if not agent:
        return jsonify({"ok": False, "message": "账号或密码错误"}), 401
    if agent.status != "active":
        return jsonify({"ok": False, "message": "账号已禁用"}), 403
    if not check_password_hash(agent.password_hash, password):
        return jsonify({"ok": False, "message": "账号或密码错误"}), 401
    token = issue_partner_token(agent)
    logging.info("partner agent login ok agent_id=%s", agent.id)
    return jsonify(
        {
            "ok": True,
            "token": token,
            "agent": {
                "id": agent.id,
                "agent_code": agent.agent_code,
                "login_name": agent.login_name,
                "display_name": agent.display_name,
                "current_rate": float(agent.current_rate or 0),
            },
        }
    )


@partner_auth_bp.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    login_name = (data.get("login_name") or "").strip()
    password = data.get("password") or ""
    if not login_name or not password:
        return jsonify({"ok": False, "message": "请输入账号和密码"}), 400

    if login_name.strip().lower() == _ROOT_JWT_LOGIN_NAME:
        if not _root_password_configured():
            return jsonify({"ok": False, "message": "账号或密码错误"}), 401
        try:
            ok_pw = secrets.compare_digest(
                password.encode("utf-8"),
                _cfg.PARTNER_ROOT_PASSWORD.encode("utf-8"),
            )
        except Exception:
            ok_pw = False
        if not ok_pw:
            return jsonify({"ok": False, "message": "账号或密码错误"}), 401
        token = issue_root_token()
        logging.info("partner root admin login ok")
        return jsonify(
            {
                "ok": True,
                "token": token,
                "admin": {
                    "login_name": _ROOT_JWT_LOGIN_NAME,
                    "role": "root",
                },
            }
        )

    admin = PartnerAdmin.query.filter_by(login_name=login_name).first()
    if not admin:
        return jsonify({"ok": False, "message": "账号或密码错误"}), 401
    if admin.status != "active":
        return jsonify({"ok": False, "message": "账号已禁用"}), 403
    if not check_password_hash(admin.password_hash, password):
        return jsonify({"ok": False, "message": "账号或密码错误"}), 401
    token = issue_admin_token(admin)
    logging.info("partner admin login ok admin_id=%s", admin.id)
    return jsonify(
        {
            "ok": True,
            "token": token,
            "admin": {
                "id": admin.id,
                "login_name": admin.login_name,
                "role": "admin",
            },
        }
    )


@partner_auth_bp.route("/admin/whoami", methods=["GET"])
def admin_whoami():
    auth, err = require_admin_auth()
    if err is not None:
        return err
    if auth.is_root:
        return jsonify(
            {
                "ok": True,
                "role": "root",
                "login_name": _ROOT_JWT_LOGIN_NAME,
            }
        )
    a = auth.admin
    assert a is not None
    return jsonify(
        {
            "ok": True,
            "role": "admin",
            "id": a.id,
            "login_name": a.login_name,
        }
    )


def _agent_me_payload(agent: Agent) -> dict:
    return {
        "id": agent.id,
        "agent_code": agent.agent_code,
        "login_name": agent.login_name,
        "display_name": agent.display_name,
        "real_name": agent.real_name,
        "age": agent.age,
        "phone": agent.phone,
        "bank_account": agent.bank_account,
        "contact": agent.contact,
        "current_rate": float(agent.current_rate or 0),
        "bank_info": agent.bank_info,
    }


@partner_auth_bp.route("/me", methods=["GET", "PUT"])
def partner_me():
    agent, err = require_partner_token()
    if err:
        return err
    if request.method == "GET":
        return jsonify({"ok": True, "agent": _agent_me_payload(agent)})

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"ok": False, "message": "无效的 JSON"}), 400

    password_changed = False
    new_pw_raw = data.get("new_password")
    if new_pw_raw is not None and str(new_pw_raw).strip() != "":
        cur = data.get("current_password") or ""
        if not check_password_hash(agent.password_hash, cur):
            return jsonify({"ok": False, "message": "当前密码错误"}), 400
        np = str(new_pw_raw).strip()
        if len(np) < 6:
            return jsonify({"ok": False, "message": "新密码至少 6 位"}), 400
        agent.password_hash = generate_password_hash(np)
        agent.session_version = int(agent.session_version or 1) + 1
        password_changed = True

    if "display_name" in data:
        v = (data.get("display_name") or "").strip()
        if v:
            agent.display_name = v
    if "real_name" in data:
        agent.real_name = (data.get("real_name") or "").strip() or None
    if "age" in data:
        if data.get("age") is None or data.get("age") == "":
            agent.age = None
        else:
            try:
                age = int(data.get("age"))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "message": "年龄须为数字"}), 400
            if age < 1 or age > 120:
                return jsonify({"ok": False, "message": "年龄应在 1～120 之间"}), 400
            agent.age = age
    if "phone" in data:
        phone = (data.get("phone") or "").strip() or None
        if phone:
            other = Agent.query.filter(
                Agent.phone == phone, Agent.id != agent.id
            ).first()
            if other:
                return jsonify({"ok": False, "message": "该电话号码已被使用"}), 400
        agent.phone = phone
        if phone:
            agent.contact = phone
    if "bank_account" in data:
        v = (data.get("bank_account") or "").strip()
        agent.bank_account = v if v else None
    if "contact" in data:
        v = (data.get("contact") or "").strip()
        agent.contact = v if v else None
    if "bank_info" in data:
        v = (data.get("bank_info") or "").strip()
        agent.bank_info = v if v else None

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            {"ok": False, "message": "保存失败，电话号码等可能与已有数据冲突。"}
        ), 400

    body: dict = {"ok": True, "agent": _agent_me_payload(agent)}
    if password_changed:
        body["token"] = issue_partner_token(agent)
    return jsonify(body)


@partner_auth_bp.route("/bootstrap-agent", methods=["POST"])
def bootstrap_agent():
    bk = _cfg.PARTNER_BOOTSTRAP_KEY
    if not bk:
        return jsonify({"ok": False, "message": "未配置 PARTNER_BOOTSTRAP_KEY"}), 403
    if (request.headers.get("X-Partner-Bootstrap-Key") or "") != bk:
        return jsonify({"ok": False, "message": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    login_name = (data.get("login_name") or "").strip()
    password = data.get("password") or ""
    agent_code = (data.get("agent_code") or "").strip()
    display_name = (data.get("display_name") or login_name).strip()
    if not login_name or not password or not agent_code:
        return jsonify({"ok": False, "message": "缺少 login_name/password/agent_code"}), 400
    if Agent.query.filter(
        (Agent.login_name == login_name) | (Agent.agent_code == agent_code)
    ).first():
        return jsonify({"ok": False, "message": "账号或推广码已存在"}), 400
    phone = (data.get("phone") or "").strip() or None
    if phone and Agent.query.filter_by(phone=phone).first():
        return jsonify({"ok": False, "message": "该手机号已被使用"}), 400
    age = data.get("age")
    if age is not None and age != "":
        try:
            age = int(age)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "message": "年龄格式无效"}), 400
    else:
        age = None
    agent = Agent(
        agent_code=agent_code,
        login_name=login_name,
        password_hash=generate_password_hash(password),
        display_name=display_name,
        real_name=(data.get("real_name") or "").strip() or None,
        age=age,
        phone=phone,
        bank_account=(data.get("bank_account") or "").strip() or None,
        contact=phone or (data.get("contact") or "").strip() or None,
        current_rate=data.get("current_rate") or 0,
    )
    db.session.add(agent)
    db.session.commit()
    return jsonify({"ok": True, "agent_id": agent.id})


@partner_auth_bp.route("/bootstrap-admin", methods=["POST"])
def bootstrap_admin():
    bk = _cfg.PARTNER_BOOTSTRAP_KEY
    if not bk:
        return jsonify({"ok": False, "message": "未配置 PARTNER_BOOTSTRAP_KEY"}), 403
    if (request.headers.get("X-Partner-Bootstrap-Key") or "") != bk:
        return jsonify({"ok": False, "message": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    login_name = (data.get("login_name") or "").strip()
    password = data.get("password") or ""
    if not login_name or not password:
        return jsonify({"ok": False, "message": "缺少 login_name/password"}), 400
    if login_name.lower() == "root":
        return jsonify(
            {"ok": False, "message": "登录名 root 保留给部署根账号，请使用其它名称。"}
        ), 400
    if PartnerAdmin.query.filter_by(login_name=login_name).first():
        return jsonify({"ok": False, "message": "管理员登录名已存在"}), 400
    admin = PartnerAdmin(
        login_name=login_name,
        password_hash=generate_password_hash(password),
    )
    db.session.add(admin)
    db.session.commit()
    return jsonify({"ok": True, "admin_id": admin.id})
