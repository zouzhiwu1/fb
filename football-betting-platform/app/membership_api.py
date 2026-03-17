# -*- coding: utf-8 -*-
"""会员相关 API：当前会员状态。支付开通会员由支付系统回调 add_membership，不在此暴露。"""
from flask import Blueprint, jsonify, request

from app.membership import get_membership_status

membership_bp = Blueprint("membership", __name__)


def _get_user_id():
    try:
        from app.auth import _verify_token
        auth = request.headers.get("Authorization") or ""
        if not auth.startswith("Bearer "):
            return None
        return _verify_token(auth[7:].strip())
    except Exception:
        return None


@membership_bp.route("/status", methods=["GET"])
def status():
    """当前登录用户的会员状态。Header: Authorization: Bearer <token>"""
    user_id = _get_user_id()
    if user_id is None:
        return jsonify({"ok": False, "message": "请先登录"}), 401
    data = get_membership_status(user_id)
    return jsonify({"ok": True, **data})
