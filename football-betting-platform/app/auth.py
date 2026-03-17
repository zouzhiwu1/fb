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

auth_bp = Blueprint("auth", __name__)


def _create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),  # JWT 规范建议 sub 为字符串
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
        return int(sub) if sub is not None and str(sub).isdigit() else sub
    except Exception:
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
    if not password or len(password) < 6:
        return jsonify({"ok": False, "message": "密码至少 6 位"}), 400
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

        token = _create_token(user.id)
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

    if code:
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
        rec.used_at = now
        db.session.commit()
    elif password:
        if not user.password_hash or not check_password_hash(user.password_hash, password):
            return jsonify({"ok": False, "message": "密码错误"}), 401
    else:
        return jsonify({"ok": False, "message": "请提供验证码或密码"}), 400

    token = _create_token(user.id)
    return jsonify({
        "ok": True,
        "user": user.to_dict(),
        "token": token,
    })


@auth_bp.route("/me", methods=["GET"])
def me():
    """根据 token 返回当前用户信息。Header: Authorization: Bearer <token>"""
    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        return jsonify({"ok": False, "message": "未登录"}), 401
    token = auth[7:].strip()
    user_id = _verify_token(token)
    if not user_id:
        return jsonify({"ok": False, "message": "登录已过期"}), 401
    user = User.query.get(user_id)
    if not user:
        return jsonify({"ok": False, "message": "用户不存在"}), 404
    return jsonify({"ok": True, "user": user.to_dict()})
