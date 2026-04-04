# -*- coding: utf-8 -*-
"""
认证相关 API：发送验证码、注册、登录。
"""
from datetime import datetime, timedelta

import jwt
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from app.models import User, VerificationCode
from app.sms import generate_code, send_sms
from app.membership import grant_free_week
from config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    JWT_EXPIRE_HOURS,
    SMS_CODE_EXPIRE,
    SMS_SEND_INTERVAL,
)
from fb_common import validate_password_strength

auth_bp = Blueprint("auth", __name__)


def _create_token(user_id: int, session_version: int) -> str:
    payload = {
        "sub": str(user_id),  # JWT 规范建议 sub 为字符串
        "sv": int(session_version),  # session version：用于踢掉旧登录
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token if isinstance(token, str) else token.decode("utf-8")


def _verify_token(token: str):
    try:
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        sub = payload.get("sub")
        sv = payload.get("sv")
        if sub is None or not str(sub).isdigit():
            return None
        if sv is None or not str(sv).isdigit():
            return None
        user_id = int(sub)
        token_sv = int(sv)
        user = db.session.get(User, user_id)
        if not user:
            return None
        current_sv = int(user.session_version or 1)
        if token_sv != current_sv:
            return None
        return user_id
    except Exception:
        return None


def get_user_id_from_authorization(request) -> int | None:
    """
    从 Authorization: Bearer <jwt> 解析用户 id。
    兼容 scheme 大小写（bearer / Bearer）、token 首尾引号；验签失败返回 None。
    """
    try:
        auth = (request.headers.get("Authorization") or "").strip()
        parts = auth.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        raw = parts[1].strip().strip('"').strip("'")
        uid = _verify_token(raw)
        if uid is None:
            return None
        return int(uid) if str(uid).isdigit() else None
    except (TypeError, ValueError):
        return None


def _normalize_phone(phone: str) -> str:
    """简单规范化：去空格、可去国家前缀。"""
    return (phone or "").strip().replace(" ", "").replace("-", "")


def _is_valid_phone(phone: str) -> bool:
    """中国大陆手机号：11 位数字。"""
    return bool(phone and len(phone) == 11 and phone.isdigit())


@auth_bp.route("/send-code", methods=["POST"])
def send_code():
    """发送短信验证码。请求体: { "phone": "13800138000" }"""
    data = request.get_json() or {}
    phone = _normalize_phone(data.get("phone") or "")
    if not _is_valid_phone(phone):
        return jsonify({"ok": False, "message": "请输入 11 位有效手机号"}), 400

    now = datetime.utcnow()
    last = (
        VerificationCode.query.filter_by(phone=phone)
        .order_by(VerificationCode.created_at.desc())
        .first()
    )
    if last and (now - last.created_at).total_seconds() < SMS_SEND_INTERVAL:
        return jsonify({
            "ok": False,
            "message": f"发送过于频繁，请 {SMS_SEND_INTERVAL} 秒后再试",
        }), 429

    code = generate_code()
    expires_at = now + timedelta(seconds=SMS_CODE_EXPIRE)
    rec = VerificationCode(phone=phone, code=code, expires_at=expires_at)
    db.session.add(rec)
    db.session.commit()

    if not send_sms(phone, code):
        return jsonify({"ok": False, "message": "验证码发送失败"}), 500
    return jsonify({"ok": True, "message": "验证码已发送"})


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


@auth_bp.route("/register", methods=["POST"])
def register():
    """
    注册：用户名、性别、密码、手机号、邮箱、验证码。
    请求体: { "username", "gender", "password", "phone", "email", "code" }
    """
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    gender = (data.get("gender") or "").strip()
    password = (data.get("password") or "").strip()
    phone = _normalize_phone(data.get("phone") or "")
    email = _normalize_email(data.get("email") or "")
    code = (data.get("code") or "").strip()

    if not username:
        return jsonify({"ok": False, "message": "请输入用户名"}), 400
    if not gender:
        return jsonify({"ok": False, "message": "请选择性别"}), 400
    ok_pw, pw_msg = validate_password_strength(password)
    if not ok_pw:
        return jsonify({"ok": False, "message": pw_msg}), 400
    if not _is_valid_phone(phone):
        return jsonify({"ok": False, "message": "请输入 11 位有效手机号"}), 400
    if not email or "@" not in email:
        return jsonify({"ok": False, "message": "请输入有效的邮箱地址"}), 400
    if not code:
        return jsonify({"ok": False, "message": "请输入验证码"}), 400

    now = datetime.utcnow()
    rec = (
        VerificationCode.query.filter_by(phone=phone, code=code)
        .filter(VerificationCode.used_at.is_(None))
        .filter(VerificationCode.expires_at > now)
        .order_by(VerificationCode.created_at.desc())
        .first()
    )
    if not rec:
        return jsonify({"ok": False, "message": "验证码错误或已过期"}), 400

    if User.query.filter_by(phone=phone).first():
        return jsonify({"ok": False, "message": "该手机号已注册"}), 409
    if User.query.filter_by(username=username).first():
        return jsonify({"ok": False, "message": "该用户名已被使用"}), 409
    if email and User.query.filter_by(email=email).first():
        return jsonify({"ok": False, "message": "该邮箱已被使用"}), 409

    try:
        password_hash = generate_password_hash(password, method="pbkdf2:sha256")
        user = User(
            username=username,
            gender=gender,
            phone=phone,
            email=email or None,
            password_hash=password_hash,
        )
        db.session.add(user)
        rec.used_at = now
        db.session.commit()

        # 新用户赠送周会员（设计书：仅限一次，账号维度）
        try:
            grant_free_week(user.id)
        except Exception as e:
            if hasattr(request, "app") and request.app.logger:
                request.app.logger.exception("注册时赠送周会员失败: %s", e)

        token = _create_token(user.id, int(user.session_version or 1))
        return jsonify({
            "ok": True,
            "message": "注册成功",
            "user": user.to_dict(),
            "token": token,
        })
    except Exception as e:
        if hasattr(request, "app") and request.app.logger:
            request.app.logger.exception("注册失败: %s", e)
        return jsonify({
            "ok": False,
            "message": "服务器错误，请稍后重试。若为首次部署，请执行 scripts/add_membership_tables.sql 并重启服务。",
        }), 500


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    登录：支持两种方式
    1) 手机号 + 验证码：{ "phone": "13800138000", "code": "123456" }
    2) 手机号 + 密码：{ "phone": "13800138000", "password": "xxx" }
    """
    data = request.get_json() or {}
    phone = _normalize_phone(data.get("phone") or "")
    code = (data.get("code") or "").strip()
    password = data.get("password") or ""

    if not _is_valid_phone(phone):
        return jsonify({"ok": False, "message": "请输入 11 位有效手机号"}), 400

    user = User.query.filter_by(phone=phone).first()
    if not user:
        return jsonify({"ok": False, "message": "该手机号未注册"}), 404

    now = datetime.utcnow()
    if code:
        rec = (
            VerificationCode.query.filter_by(phone=phone, code=code)
            .filter(VerificationCode.used_at.is_(None))
            .filter(VerificationCode.expires_at > now)
            .order_by(VerificationCode.created_at.desc())
            .first()
        )
        if not rec:
            return jsonify({"ok": False, "message": "验证码错误或已过期"}), 400
        rec.used_at = now
    elif password:
        if not user.password_hash or not check_password_hash(user.password_hash, password):
            return jsonify({"ok": False, "message": "密码错误"}), 401
    else:
        return jsonify({"ok": False, "message": "请提供验证码或密码"}), 400

    # 单设备登录：每次登录成功都提升会话版本，使旧 token 立即失效
    user.session_version = int(user.session_version or 1) + 1
    db.session.commit()

    token = _create_token(user.id, int(user.session_version))
    return jsonify({
        "ok": True,
        "user": user.to_dict(),
        "token": token,
    })


def _current_user_from_bearer() -> tuple[User | None, tuple | None]:
    """
    从 Authorization Bearer 解析当前用户。
    返回 (user, None) 或 (None, (jsonify 响应体, http_status))。
    """
    user_id = get_user_id_from_authorization(request)
    if user_id is None:
        return None, (
            jsonify(
                {
                    "ok": False,
                    "message": "账号已在其他设备登录或登录已过期，请重新登录",
                }
            ),
            401,
        )
    user = db.session.get(User, user_id)
    if not user:
        return None, (jsonify({"ok": False, "message": "用户不存在"}), 404)
    return user, None


@auth_bp.route("/me", methods=["GET"])
def me():
    """根据 token 返回当前用户信息。Header: Authorization: Bearer <token>"""
    user, err = _current_user_from_bearer()
    if err:
        body, status = err
        return body, status
    return jsonify({"ok": True, "user": user.to_dict()})


@auth_bp.route("/change-password", methods=["POST"])
def change_password():
    """
    修改密码。Header: Authorization: Bearer <token>
    Body: { "current_password": "...", "new_password": "..." }
    若账号从未设置过密码（仅验证码登录过），可不传 current_password，仅传 new_password 即可首次设置。
    """
    user, err = _current_user_from_bearer()
    if err:
        body, status = err
        return body, status
    data = request.get_json() or {}
    current_password = data.get("current_password") or ""
    new_password = (data.get("new_password") or "").strip()

    ok_pw, pw_msg = validate_password_strength(new_password)
    if not ok_pw:
        return jsonify({"ok": False, "message": pw_msg}), 400

    if user.password_hash:
        if not current_password or not check_password_hash(user.password_hash, current_password):
            return jsonify({"ok": False, "message": "当前密码错误"}), 400
    # 无 password_hash：允许首次设置，不校验 current_password

    user.password_hash = generate_password_hash(new_password, method="pbkdf2:sha256")
    db.session.commit()
    return jsonify({"ok": True, "message": "密码已更新"})


@auth_bp.route("/change-email", methods=["POST"])
def change_email():
    """
    修改邮箱。Header: Authorization: Bearer <token>
    Body: { "email": "new@example.com" }
    """
    user, err = _current_user_from_bearer()
    if err:
        body, status = err
        return body, status
    data = request.get_json() or {}
    email = _normalize_email(data.get("email") or "")
    if not email or "@" not in email:
        return jsonify({"ok": False, "message": "请输入有效的邮箱地址"}), 400

    if user.email and email == _normalize_email(user.email or ""):
        return jsonify({"ok": True, "message": "邮箱未变更", "user": user.to_dict()})

    existing = User.query.filter(User.email == email, User.id != user.id).first()
    if existing:
        return jsonify({"ok": False, "message": "该邮箱已被其他账号使用"}), 409

    user.email = email
    db.session.commit()
    return jsonify({"ok": True, "message": "邮箱已更新", "user": user.to_dict()})


@auth_bp.route("/change-phone", methods=["POST"])
def change_phone():
    """
    修改手机号（登录凭证）。需向新手机号发送验证码后提交校验。
    Header: Authorization: Bearer <token>
    Body: { "new_phone": "13800138000", "code": "123456" }
    """
    user, err = _current_user_from_bearer()
    if err:
        body, status = err
        return body, status
    data = request.get_json() or {}
    new_phone = _normalize_phone(data.get("new_phone") or "")
    code = (data.get("code") or "").strip()

    if not _is_valid_phone(new_phone):
        return jsonify({"ok": False, "message": "请输入 11 位有效手机号"}), 400
    if new_phone == user.phone:
        return jsonify({"ok": False, "message": "新手机号与当前相同"}), 400
    if not code:
        return jsonify({"ok": False, "message": "请输入验证码"}), 400

    if User.query.filter_by(phone=new_phone).first():
        return jsonify({"ok": False, "message": "该手机号已被其他账号使用"}), 409

    now = datetime.utcnow()
    rec = (
        VerificationCode.query.filter_by(phone=new_phone, code=code)
        .filter(VerificationCode.used_at.is_(None))
        .filter(VerificationCode.expires_at > now)
        .order_by(VerificationCode.created_at.desc())
        .first()
    )
    if not rec:
        return jsonify({"ok": False, "message": "验证码错误或已过期"}), 400

    rec.used_at = now
    user.phone = new_phone
    db.session.commit()
    return jsonify({
        "ok": True,
        "message": "手机号已更新，请使用新手机号登录",
        "user": user.to_dict(),
    })
