# -*- coding: utf-8 -*-
"""
会员购买：创建订单（商户侧）+ 支付渠道回调入口。
支付成功后的开通会员逻辑见 payment_fulfillment；支付宝 / 微信见 payment_providers。
"""
from __future__ import annotations

import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, Request, jsonify, request

from app import db
from app.membership import MEMBERSHIP_TYPES, MEMBERSHIP_TYPE_LABELS
from app.models import PaymentOrder, User
from app.payment_fulfillment import (
    FulfillResult,
    VerifiedPayment,
    default_membership_fulfillment,
)
from app.payment_providers.alipay import handle_alipay_notify
from app.payment_providers.wechat import handle_wechat_notify
from app.wechat_mp_client import (
    build_miniprogram_request_payment_params,
    jscode2session,
    unifiedorder_jsapi,
    yuan_str_to_total_fee_fen,
)
from app.wechat_pay_v3 import (
    build_miniprogram_request_payment_params_v3,
    jsapi_prepay,
    load_private_key_from_pem,
    load_public_key_from_pem,
)
from app.wechat_virtual_pay import (
    fetch_cgi_access_token,
    fen_to_price_str,
    virtual_payment_client_signatures,
    xpay_query_order,
)
from config import (
    ALIPAY_APP_ID,
    ALIPAY_MODE,
    ALIPAY_MOCK_SECRET,
    MEMBERSHIP_PRICES,
    PUBLIC_BASE_URL,
    WECHAT_API_KEY,
    WECHAT_MCH_CERT_SERIAL,
    WECHAT_MCH_ID,
    WECHAT_MCH_PRIVATE_KEY_PEM,
    WECHAT_MOCK_SECRET,
    WECHAT_MP_APP_ID,
    WECHAT_MP_APP_SECRET,
    WECHAT_MP_VIRTUAL_APP_KEY,
    WECHAT_MP_VIRTUAL_APP_KEY_SANDBOX,
    WECHAT_MP_VIRTUAL_ENV,
    WECHAT_MP_VIRTUAL_GOODS,
    WECHAT_MP_VIRTUAL_OFFER_ID,
    WECHAT_PAY_MODE,
    WECHAT_PLATFORM_PUBLIC_KEY_ID,
    WECHAT_PLATFORM_PUBLIC_KEY_PEM,
    wechat_v3_config_ok,
    wechat_virtual_pay_config_ok,
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


def _client_ip(req: Request) -> str:
    xff = (req.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return (req.remote_addr or "127.0.0.1").strip()


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
    return jsonify({
        "ok": True,
        "options": options,
        "wechat_virtual_pay_ready": wechat_virtual_pay_config_ok(),
    })


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
    Body:
      - { "membership_type": "month" } 默认支付宝侧自行收银台（与历史行为一致）
      - { "membership_type": "month", "payment_channel": "wechat_mp" } 微信小程序 JSAPI 支付，
        成功时返回 wx_pay 供 wx.requestPayment；需用户已绑定 openid（POST /api/auth/wechat-mp/bind）。
      - { "membership_type": "month", "payment_channel": "wechat_mp_virtual", "login_code": "<wx.login>" }
        小程序虚拟支付：返回 virtual_pay 供 wx.requestVirtualPayment；支付成功后请调
        POST /api/pay/wechat-virtual/confirm 查单并开通会员。
    """
    user_id = _get_user_id()
    if user_id is None:
        return jsonify(
            {"ok": False, "message": "账号已在其他设备登录或登录已过期，请重新登录"}
        ), 401
    data = request.get_json() or {}
    mtype = (data.get("membership_type") or "").strip().lower()
    payment_channel = (data.get("payment_channel") or "alipay").strip().lower()
    if payment_channel not in ("alipay", "wechat_mp", "wechat_mp_virtual"):
        return jsonify({
            "ok": False,
            "message": "payment_channel 须为 alipay、wechat_mp 或 wechat_mp_virtual",
        }), 400
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

    user_row = db.session.get(User, user_id)
    virtual_session_key: str | None = None

    if payment_channel == "wechat_mp_virtual":
        if not wechat_virtual_pay_config_ok():
            return jsonify({
                "ok": False,
                "message": (
                    "服务端未配置小程序虚拟支付：需 WECHAT_MP_APP_ID/SECRET、"
                    "WECHAT_MP_VIRTUAL_OFFER_ID、WECHAT_MP_VIRTUAL_APP_KEY、"
                    "WECHAT_MP_VIRTUAL_GOODS_JSON（见 .env.example）"
                ),
            }), 503
        login_code = (data.get("login_code") or "").strip()
        if not login_code:
            return jsonify({
                "ok": False,
                "message": "缺少 login_code，请先在小程序内调用 wx.login",
            }), 400
        sess = jscode2session(WECHAT_MP_APP_ID, WECHAT_MP_APP_SECRET, login_code)
        if sess.get("errcode") not in (None, 0):
            return jsonify({
                "ok": False,
                "message": sess.get("errmsg") or "登录态无效，请重新 wx.login 后再试",
            }), 400
        virtual_session_key = (sess.get("session_key") or "").strip()
        v_openid = (sess.get("openid") or "").strip()
        if not virtual_session_key or not v_openid:
            return jsonify({"ok": False, "message": "未获取到 session_key/openid"}), 400
        spec = WECHAT_MP_VIRTUAL_GOODS.get(mtype)
        if not isinstance(spec, dict):
            return jsonify({
                "ok": False,
                "message": f"虚拟支付未配置档位 {mtype}（WECHAT_MP_VIRTUAL_GOODS_JSON）",
            }), 400
        pid = (spec.get("productId") or spec.get("product_id") or "").strip()
        raw_gpf = spec.get("goodsPrice") if "goodsPrice" in spec else spec.get("goods_price")
        if not pid or raw_gpf is None:
            return jsonify({
                "ok": False,
                "message": f"档位 {mtype} 须含 productId 与 goodsPrice（分）",
            }), 400
        try:
            goods_price_fen = int(raw_gpf)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "message": "goodsPrice 须为整数（分）"}), 400
        exp_fen = yuan_str_to_total_fee_fen(price)
        if exp_fen is None or exp_fen <= 0:
            return jsonify({"ok": False, "message": "金额换算分失败"}), 500
        if goods_price_fen != exp_fen:
            return jsonify({
                "ok": False,
                "message": (
                    f"虚拟道具标价（{goods_price_fen} 分）与会员价（{exp_fen} 分）不一致，"
                    "请同步修改 MEMBERSHIP_PRICES 与 WECHAT_MP_VIRTUAL_GOODS_JSON"
                ),
            }), 400
        if user_row:
            uo = (user_row.wechat_mp_openid or "").strip()
            if uo and uo != v_openid:
                return jsonify({
                    "ok": False,
                    "message": "当前账号已绑定其他支付用户，请使用原设备或联系客服",
                }), 400
            if not uo:
                user_row.wechat_mp_openid = v_openid
    elif payment_channel == "wechat_mp":
        if WECHAT_PAY_MODE != "mock":
            if not user_row or not (user_row.wechat_mp_openid or "").strip():
                return jsonify({
                    "ok": False,
                    "message": "请先在小程序内完成登录并绑定支付账号（登录后自动绑定，或重新进入小程序）",
                }), 400
            if WECHAT_PAY_MODE == "v3":
                if not wechat_v3_config_ok():
                    return jsonify({
                        "ok": False,
                        "message": (
                            "服务端未配置 V3 小程序支付：WECHAT_MP_APP_ID、WECHAT_MCH_ID、"
                            "WECHAT_MCH_CERT_SERIAL（或 WECHAT_MCH_CERT_PATH 从 apiclient_cert.pem 解析）、"
                            "WECHAT_MCH_PRIVATE_KEY_PATH（或 PEM）、"
                            "WECHAT_PLATFORM_PUBLIC_KEY_ID、WECHAT_PLATFORM_PUBLIC_KEY_PATH（或 PEM）、"
                            "WECHAT_API_V3_KEY（32 字节）"
                        ),
                    }), 503
            elif WECHAT_PAY_MODE == "v2":
                if not (WECHAT_MP_APP_ID and WECHAT_MCH_ID and WECHAT_API_KEY):
                    return jsonify({
                        "ok": False,
                        "message": "服务端未配置小程序支付：WECHAT_MP_APP_ID、WECHAT_MCH_ID、WECHAT_API_KEY（V2）",
                    }), 503
            else:
                return jsonify({
                    "ok": False,
                    "message": "WECHAT_PAY_MODE 须为 mock、v2 或 v3",
                }), 400

    labels = {"week": "周会员", "month": "月会员", "quarter": "季会员", "year": "年会员"}
    subject = f"足球数据会员-{labels.get(mtype, mtype)}"
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    rand = secrets.token_hex(3)
    if payment_channel == "wechat_mp_virtual":
        out_trade_no = f"V{user_id % 1000000:06d}{secrets.token_hex(10).upper()}"
    elif payment_channel == "wechat_mp":
        # 微信商户订单号最长 32 字节
        out_trade_no = f"W{user_id % 1000000:06d}{secrets.token_hex(10).upper()}"
    else:
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
    payload: dict = {
        "ok": True,
        "out_trade_no": out_trade_no,
        "total_amount": price,
        "subject": subject,
        "membership_type": mtype,
        "payment_channel": payment_channel,
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

    if payment_channel == "wechat_mp":
        payload["wx_pay"] = None
        if WECHAT_PAY_MODE == "mock":
            payload["wechat_mp_mock"] = True
            payload["simulate"]["hint"] = (
                "WECHAT_PAY_MODE=mock：无真实 wx.requestPayment。"
                "可 scripts/simulate_wechat_notify.py 模拟回调；"
                "生产请设 WECHAT_PAY_MODE=v2 或 v3。"
            )
        else:
            total_fen = yuan_str_to_total_fee_fen(price)
            if total_fen is None or total_fen <= 0:
                return jsonify({"ok": False, "message": "金额换算分失败"}), 500
            openid = (user_row.wechat_mp_openid or "").strip()
            if WECHAT_PAY_MODE == "v3":
                try:
                    merchant_priv = load_private_key_from_pem(WECHAT_MCH_PRIVATE_KEY_PEM)
                    platform_pub = load_public_key_from_pem(WECHAT_PLATFORM_PUBLIC_KEY_PEM)
                except ValueError as e:
                    return jsonify({
                        "ok": False,
                        "message": f"微信支付证书配置无效：{e}",
                    }), 503
                prepay_id, uerr = jsapi_prepay(
                    app_id=WECHAT_MP_APP_ID,
                    mch_id=WECHAT_MCH_ID,
                    mch_cert_serial=WECHAT_MCH_CERT_SERIAL,
                    merchant_private_key=merchant_priv,
                    platform_public_key=platform_pub,
                    platform_public_key_id=WECHAT_PLATFORM_PUBLIC_KEY_ID,
                    openid=openid,
                    out_trade_no=out_trade_no,
                    description=subject,
                    notify_url=wechat_notify_url,
                    total_fen=total_fen,
                    client_ip=_client_ip(request),
                )
                if not prepay_id:
                    return jsonify({
                        "ok": False,
                        "message": uerr or "微信 V3 下单失败",
                        "out_trade_no": out_trade_no,
                    }), 502
                payload["wx_pay"] = build_miniprogram_request_payment_params_v3(
                    app_id=WECHAT_MP_APP_ID,
                    prepay_id=prepay_id,
                    private_key=merchant_priv,
                )
            else:
                prepay_id, uerr = unifiedorder_jsapi(
                    app_id=WECHAT_MP_APP_ID,
                    mch_id=WECHAT_MCH_ID,
                    api_key=WECHAT_API_KEY or "",
                    openid=openid,
                    out_trade_no=out_trade_no,
                    body=subject,
                    total_fee_fen=total_fen,
                    notify_url=wechat_notify_url,
                    client_ip=_client_ip(request),
                )
                if not prepay_id:
                    return jsonify({
                        "ok": False,
                        "message": uerr or "微信统一下单失败",
                        "out_trade_no": out_trade_no,
                    }), 502
                payload["wx_pay"] = build_miniprogram_request_payment_params(
                    app_id=WECHAT_MP_APP_ID,
                    api_key=WECHAT_API_KEY or "",
                    prepay_id=prepay_id,
                )

    elif payment_channel == "wechat_mp_virtual":
        payload["wx_pay"] = None
        if not virtual_session_key:
            return jsonify({"ok": False, "message": "内部错误：缺少虚拟支付会话"}), 500
        app_key = (
            WECHAT_MP_VIRTUAL_APP_KEY_SANDBOX
            if WECHAT_MP_VIRTUAL_ENV == 1
            else WECHAT_MP_VIRTUAL_APP_KEY
        )
        spec = WECHAT_MP_VIRTUAL_GOODS.get(mtype)
        assert isinstance(spec, dict)
        pid = (spec.get("productId") or spec.get("product_id") or "").strip()
        raw_gpf = spec.get("goodsPrice") if "goodsPrice" in spec else spec.get("goods_price")
        goods_price_fen = int(raw_gpf)
        sign_data = {
            "offerId": WECHAT_MP_VIRTUAL_OFFER_ID,
            "buyQuantity": 1,
            "env": int(WECHAT_MP_VIRTUAL_ENV),
            "currencyType": "CNY",
            "productId": pid,
            "goodsPrice": goods_price_fen,
            "outTradeNo": out_trade_no,
            "attach": out_trade_no,
        }
        sign_data_str, pay_sig, signature = virtual_payment_client_signatures(
            virtual_session_key, app_key, sign_data
        )
        payload["virtual_pay"] = {
            "signData": sign_data_str,
            "paySig": pay_sig,
            "signature": signature,
            "mode": "short_series_goods",
        }

    return jsonify(payload)


def _virtual_pay_app_key() -> str:
    if WECHAT_MP_VIRTUAL_ENV == 1 and WECHAT_MP_VIRTUAL_APP_KEY_SANDBOX:
        return WECHAT_MP_VIRTUAL_APP_KEY_SANDBOX
    return WECHAT_MP_VIRTUAL_APP_KEY


@pay_bp.route("/wechat-virtual/confirm", methods=["POST"])
def wechat_virtual_confirm():
    """
    虚拟支付完成后查单并开通会员（需登录）。
    Body: { "out_trade_no": "...", "login_code": "<wx.login 新 code>" }
    """
    user_id = _get_user_id()
    if user_id is None:
        return jsonify(
            {"ok": False, "message": "账号已在其他设备登录或登录已过期，请重新登录"}
        ), 401
    if not wechat_virtual_pay_config_ok():
        return jsonify({"ok": False, "message": "服务端未配置小程序虚拟支付"}), 503

    body = request.get_json() or {}
    out_trade_no = (body.get("out_trade_no") or "").strip()
    login_code = (body.get("login_code") or "").strip()
    if not out_trade_no or not login_code:
        return jsonify({"ok": False, "message": "须提供 out_trade_no 与 login_code"}), 400

    order_row = PaymentOrder.query.filter_by(out_trade_no=out_trade_no).first()
    if not order_row or order_row.user_id != user_id:
        return jsonify({"ok": False, "message": "订单不存在"}), 404

    sess = jscode2session(WECHAT_MP_APP_ID, WECHAT_MP_APP_SECRET, login_code)
    if sess.get("errcode") not in (None, 0):
        return jsonify({
            "ok": False,
            "message": sess.get("errmsg") or "登录态无效，请重新 wx.login",
        }), 400
    openid = (sess.get("openid") or "").strip()
    if not openid:
        return jsonify({"ok": False, "message": "未获取到 openid"}), 400

    user_row = db.session.get(User, user_id)
    uo = (user_row.wechat_mp_openid or "").strip() if user_row else ""
    if uo and uo != openid:
        return jsonify({"ok": False, "message": "支付用户与当前账号不一致"}), 403

    access_token, terr = fetch_cgi_access_token(WECHAT_MP_APP_ID, WECHAT_MP_APP_SECRET)
    if not access_token:
        return jsonify({"ok": False, "message": terr or "获取 access_token 失败"}), 502

    qjson, qerr = xpay_query_order(
        _virtual_pay_app_key(),
        access_token,
        openid,
        int(WECHAT_MP_VIRTUAL_ENV),
        out_trade_no,
    )
    if not qjson:
        return jsonify({"ok": False, "message": qerr or "查单失败"}), 502

    wxo = qjson.get("order") or {}
    status = int(wxo.get("status") if wxo.get("status") is not None else -1)
    # 2=已支付待发货 3=发货中 4=已发货
    if status not in (2, 3, 4):
        return jsonify({
            "ok": False,
            "message": f"订单未支付完成（status={status}）",
            "wx_order": wxo,
        }), 400

    fee_fen = int(wxo.get("paid_fee") or wxo.get("order_fee") or 0)
    if fee_fen <= 0:
        return jsonify({"ok": False, "message": "查单返回金额异常"}), 502

    paid_str = fen_to_price_str(fee_fen)
    wx_oid = (wxo.get("wx_order_id") or wxo.get("wxpay_order_id") or "").strip()

    outcome = default_membership_fulfillment.fulfill(
        VerifiedPayment(
            merchant_order_id=out_trade_no,
            provider_trade_id=wx_oid,
            paid_amount=paid_str,
        )
    )
    if outcome.result == FulfillResult.ERR_AMOUNT_MISMATCH:
        return jsonify({"ok": False, "message": "支付金额与订单不一致"}), 400
    if outcome.result == FulfillResult.ERR_BAD_ORDER_STATE:
        return jsonify({"ok": True, "message": "订单已处理", "already": True})
    if outcome.result in (FulfillResult.OK_FULFILLED, FulfillResult.OK_ALREADY_FULFILLED):
        return jsonify({"ok": True, "fulfilled": outcome.result == FulfillResult.OK_FULFILLED})

    return jsonify({"ok": False, "message": "开通会员失败，请稍后重试或联系客服"}), 500


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
