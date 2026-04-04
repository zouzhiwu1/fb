# -*- coding: utf-8 -*-
"""会员相关 API：当前会员状态。支付开通会员由支付系统回调 add_membership，不在此暴露。"""
from flask import Blueprint, jsonify, request

from app.membership import get_membership_status

membership_bp = Blueprint("membership", __name__)


def _get_user_id():
    from app.auth import get_user_id_from_authorization

    return get_user_id_from_authorization(request)


@membership_bp.route("/status", methods=["GET"])
def status():
    """当前登录用户的会员状态。Header: Authorization: Bearer <token>"""
    user_id = _get_user_id()
    if user_id is None:
        return jsonify(
            {"ok": False, "message": "账号已在其他设备登录或登录已过期，请重新登录"}
        ), 401
    data = get_membership_status(user_id)
    return jsonify({"ok": True, **data})
