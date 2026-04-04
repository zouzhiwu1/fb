# -*- coding: utf-8 -*-
"""
会员购买：创建订单（商户侧）+ 支付渠道回调入口。
支付成功后的开通会员逻辑见 payment_fulfillment；支付宝 / 微信见 payment_providers。
"""
from __future__ import annotations

import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request

from app import db
from app.membership import MEMBERSHIP_TYPES, MEMBERSHIP_TYPE_LABELS
from app.models import PaymentOrder
from app.payment_providers.alipay import handle_alipay_notify
from app.payment_providers.wechat import handle_wechat_notify
from config import (
    ALIPAY_APP_ID,
    ALIPAY_MODE,
    ALIPAY_MOCK_SECRET,
    MEMBERSHIP_PRICES,
    PUBLIC_BASE_URL,
    WECHAT_MOCK_SECRET,
    WECHAT_PAY_MODE,
)

pay_bp = Blueprint("pay", __name__)

_STATUS_LABELS = {
    "pending": "待支付",
    "paid": "已支付",
    "closed": "已关闭",
}


def _status_label_zh(status: str) -> str:
    return _STATUS_LABELS.get((status or "").strip().lower(), status or "—")


def _order_to_list_item(order: PaymentOrder) -> dict:
    """充值信息列表项（不含 user_id）。"""
    return {
        "id": order.id,
        "out_trade_no": order.out_trade_no,
        "membership_type": order.membership_type,
        "membership_type_label": MEMBERSHIP_TYPE_LABELS.get(
            order.membership_type or "", order.membership_type or "—"
        ),
        "total_amount": order.total_amount,
        "subject": order.subject,
        "status": order.status,
        "status_label": _status_label_zh(order.status),
        "trade_no": order.trade_no,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
    }


def _get_user_id() -> int | None:
    from app.auth import get_user_id_from_authorization

    return get_user_id_from_authorization(request)


@pay_bp.route("/membership-options", methods=["GET"])
def membership_options():
    """
    会员购买档位与标价（无需登录，供充值页展示）。
    """
    options = []
    for mtype in MEMBERSHIP_TYPES:
        price = MEMBERSHIP_PRICES.get(mtype)
        if not price:
            continue
        options.append(
            {
                "membership_type": mtype,
                "label": MEMBERSHIP_TYPE_LABELS.get(mtype, mtype),
                "price": price,
            }
        )
    return jsonify({"ok": True, "options": options})


@pay_bp.route("/orders", methods=["GET"])
def list_orders():
    """
    当前登录用户的充值（购买）订单列表，按创建时间倒序。
    Query: limit 默认 50，最大 100。
    """
    user_id = _get_user_id()
    if user_id is None:
        return jsonify(
            {"ok": False, "message": "账号已在其他设备登录或登录已过期，请重新登录"}
        ), 401
    try:
        limit = int(request.args.get("limit", "50"))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 100))
    rows = (
        PaymentOrder.query.filter_by(user_id=user_id)
        .order_by(PaymentOrder.created_at.desc())
        .limit(limit)
        .all()
    )
    return jsonify({"ok": True, "orders": [_order_to_list_item(o) for o in rows]})


@pay_bp.route("/orders", methods=["POST"])
def create_order():
    """
    创建会员购买订单（需登录）。
    Body: { "membership_type": "month" }
    返回 out_trade_no、金额、标题；真实环境需再用 app_id + 私钥调支付宝下单拿到 form / 二维码。
    """
    user_id = _get_user_id()
    if user_id is None:
        return jsonify(
            {"ok": False, "message": "账号已在其他设备登录或登录已过期，请重新登录"}
        ), 401
    data = request.get_json() or {}
    mtype = (data.get("membership_type") or "").strip().lower()
    if mtype not in MEMBERSHIP_TYPES:
        return jsonify({
            "ok": False,
            "message": f"membership_type 须为 {list(MEMBERSHIP_TYPES)}",
        }), 400
    price = MEMBERSHIP_PRICES.get(mtype)
    if not price:
        return jsonify({"ok": False, "message": "该类型未配置价格"}), 400
    try:
        Decimal(price)
    except InvalidOperation:
        return jsonify({"ok": False, "message": "价格配置无效"}), 500

    labels = {"week": "周会员", "month": "月会员", "quarter": "季会员", "year": "年会员"}
    subject = f"足球数据会员-{labels.get(mtype, mtype)}"
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    rand = secrets.token_hex(3)
    out_trade_no = f"FB{user_id}{ts}{rand}"[:64]

    order = PaymentOrder(
        out_trade_no=out_trade_no,
        user_id=user_id,
        membership_type=mtype,
        total_amount=price,
        subject=subject,
        status="pending",
    )
    db.session.add(order)
    db.session.commit()

    alipay_notify_url = f"{PUBLIC_BASE_URL}/api/pay/alipay/notify"
    wechat_notify_url = f"{PUBLIC_BASE_URL}/api/pay/wechat/notify"
    payload = {
        "ok": True,
        "out_trade_no": out_trade_no,
        "total_amount": price,
        "subject": subject,
        "membership_type": mtype,
        "notify_url": alipay_notify_url,
        "wechat_notify_url": wechat_notify_url,
        "app_id": ALIPAY_APP_ID or None,
        "mode": ALIPAY_MODE,
        "simulate": {
            "hint": "本地联调：用 scripts/simulate_alipay_notify.py 向 notify_url POST 表单",
            "needs_mock_header": bool(ALIPAY_MOCK_SECRET),
            "header_name": "X-Alipay-Mock-Secret",
        },
        "wechat": {
            "mode": WECHAT_PAY_MODE,
            "simulate": {
                "hint": "本地联调：scripts/simulate_wechat_notify.py 向 wechat_notify_url POST JSON",
                "needs_mock_header": bool(WECHAT_MOCK_SECRET),
                "header_name": "X-Wechat-Mock-Secret",
            },
        },
    }
    return jsonify(payload)


@pay_bp.route("/alipay/notify", methods=["POST"])
def alipay_notify():
    """支付宝异步通知：验签与解析在 payment_providers.alipay，履约在 payment_fulfillment。"""
    body, status, headers = handle_alipay_notify(request)
    return body, status, headers


@pay_bp.route("/wechat/notify", methods=["POST"])
def wechat_notify():
    """微信支付结果通知：解析在 payment_providers.wechat，履约在 payment_fulfillment。"""
    resp, status = handle_wechat_notify(request)
    return resp, status
