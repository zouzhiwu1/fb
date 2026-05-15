# -*- coding: utf-8 -*-
"""
微信小程序「米大师」虚拟支付：wx.requestVirtualPayment 所需签名，及 xpay/query_order 查单。

签名规则见微信文档《签名详解》：
- 客户端拉起：paySig = HMAC-SHA256(appKey, "requestVirtualPayment&" + signData)
- 用户态：signature = HMAC-SHA256(sessionKey, signData)
- 服务端 xpay/*：pay_sig = HMAC-SHA256(appKey, uri + "&" + post_body)，uri 如 /xpay/query_order
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import requests

logger = logging.getLogger(__name__)

# 客户端 wx.requestVirtualPayment 固定 uri 片段（无前后斜杠）
WX_VIRTUAL_PAY_URI = "requestVirtualPayment"
XPAY_QUERY_ORDER_URI = "/xpay/query_order"

_access_token_cache: dict[str, Any] = {"token": "", "exp": 0.0}


def hmac_sha256_hex(key: str, message: str) -> str:
    return hmac.new(
        key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def compact_json(obj: dict) -> str:
    """与参与签名的 HTTP body 完全一致：无空格、UTF-8。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def virtual_payment_client_signatures(
    session_key: str, app_key: str, sign_data: dict
) -> tuple[str, str, str]:
    """
    返回 (signData 字符串, paySig, signature)，供小程序 wx.requestVirtualPayment 使用。
    """
    sign_data_str = compact_json(sign_data)
    pay_sig = hmac_sha256_hex(app_key, f"{WX_VIRTUAL_PAY_URI}&{sign_data_str}")
    signature = hmac_sha256_hex(session_key, sign_data_str)
    return sign_data_str, pay_sig, signature


def xpay_pay_sig(app_key: str, uri_path: str, post_body: str) -> str:
    """服务端 xpay 接口的 query 参数 pay_sig。"""
    return hmac_sha256_hex(app_key, f"{uri_path}&{post_body}")


def fetch_cgi_access_token(app_id: str, app_secret: str) -> tuple[str | None, str | None]:
    """client_credential access_token，进程内简单缓存。"""
    now = time.time()
    if _access_token_cache["token"] and now < float(_access_token_cache["exp"]) - 120:
        return _access_token_cache["token"], None
    try:
        r = requests.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": app_id,
                "secret": app_secret,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.exception("fetch_cgi_access_token failed: %s", e)
        return None, str(e)
    if data.get("errcode"):
        return None, data.get("errmsg") or str(data)
    tok = (data.get("access_token") or "").strip()
    if not tok:
        return None, "access_token 为空"
    exp_in = int(data.get("expires_in") or 7200)
    _access_token_cache["token"] = tok
    _access_token_cache["exp"] = now + exp_in
    return tok, None


def xpay_query_order(
    app_key: str,
    access_token: str,
    openid: str,
    env: int,
    order_id: str,
) -> tuple[dict | None, str | None]:
    """
    POST https://api.weixin.qq.com/xpay/query_order?access_token=...&pay_sig=...
    返回 (json_dict, error_message)。
    """
    body_obj = {"openid": openid, "env": int(env), "order_id": order_id}
    post_body = compact_json(body_obj)
    pay_sig = xpay_pay_sig(app_key, XPAY_QUERY_ORDER_URI, post_body)
    url = f"https://api.weixin.qq.com{XPAY_QUERY_ORDER_URI}"
    try:
        r = requests.post(
            url,
            params={"access_token": access_token, "pay_sig": pay_sig},
            data=post_body.encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.exception("xpay_query_order http failed: %s", e)
        return None, str(e)
    if data.get("errcode") not in (None, 0):
        return None, data.get("errmsg") or f"errcode={data.get('errcode')}"
    return data, None


def fen_to_price_str(fen: int) -> str:
    """分 -> 与 payment_orders.total_amount 一致的两位小数字符串。"""
    q = (Decimal(fen) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(q, "f")
