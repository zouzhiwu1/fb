# -*- coding: utf-8 -*-
"""
微信小程序：code2Session、微信支付 V2 统一下单（trade_type=JSAPI）、调起支付 paySign。
V3 JSAPI 见 app.wechat_pay_v3（/v3/pay/transactions/jsapi + RSA paySign）。
文档：V2 https://pay.weixin.qq.com/wiki/doc/api/jsapi.php?chapter=9_1
"""
from __future__ import annotations

import logging
import secrets
import time
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from app.wechat_notify import sign_v2_md5, xml_body_to_dict

logger = logging.getLogger(__name__)

CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"
UNIFIEDORDER_URL = "https://api.mch.weixin.qq.com/pay/unifiedorder"


def _dict_to_xml(d: dict[str, str]) -> str:
    parts = ["<xml>"]
    for k, v in d.items():
        parts.append(f"<{k}><![CDATA[{v}]]></{k}>")
    parts.append("</xml>")
    return "".join(parts)


def jscode2session(app_id: str, app_secret: str, js_code: str) -> dict[str, Any]:
    """
    用 wx.login 的 code 换取 openid / session_key。
    成功返回 JSON dict（含 openid）；失败含 errcode。
    """
    try:
        r = requests.get(
            CODE2SESSION_URL,
            params={
                "appid": app_id,
                "secret": app_secret,
                "js_code": js_code,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.exception("jscode2session request failed: %s", e)
        return {"errcode": -1, "errmsg": str(e)}


def yuan_str_to_total_fee_fen(yuan_str: str) -> int | None:
    try:
        return int((Decimal(str(yuan_str).strip()) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None


def unifiedorder_jsapi(
    *,
    app_id: str,
    mch_id: str,
    api_key: str,
    openid: str,
    out_trade_no: str,
    body: str,
    total_fee_fen: int,
    notify_url: str,
    client_ip: str,
) -> tuple[str | None, str | None]:
    """
    统一下单 JSAPI。成功返回 (prepay_id, None)，失败返回 (None, err_msg)。
    """
    if len(out_trade_no) > 32:
        return None, "out_trade_no 超过微信 32 字节限制"
    nonce_str = secrets.token_hex(16)
    params: dict[str, str] = {
        "appid": app_id,
        "mch_id": mch_id,
        "nonce_str": nonce_str,
        "body": (body or "会员")[:127],
        "out_trade_no": out_trade_no,
        "total_fee": str(int(total_fee_fen)),
        "spbill_create_ip": (client_ip or "127.0.0.1").strip()[:45],
        "notify_url": notify_url[:255],
        "trade_type": "JSAPI",
        "openid": openid[:128],
    }
    params["sign"] = sign_v2_md5(params, api_key)
    xml_body = _dict_to_xml(params)
    try:
        resp = requests.post(
            UNIFIEDORDER_URL,
            data=xml_body.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8"},
            timeout=15,
        )
        resp.raise_for_status()
        data = xml_body_to_dict(resp.text)
    except Exception as e:
        logger.exception("unifiedorder failed: %s", e)
        return None, str(e)

    if (data.get("return_code") or "").upper() != "SUCCESS":
        return None, data.get("return_msg") or "通信失败"
    if (data.get("result_code") or "").upper() != "SUCCESS":
        return None, data.get("err_code_des") or data.get("err_code") or "业务失败"
    prepay_id = (data.get("prepay_id") or "").strip()
    if not prepay_id:
        return None, "无 prepay_id"
    return prepay_id, None


def build_miniprogram_request_payment_params(
    *,
    app_id: str,
    api_key: str,
    prepay_id: str,
) -> dict[str, str]:
    """
    生成小程序 wx.requestPayment 所需五元组（V2 MD5）。
    """
    time_stamp = str(int(time.time()))
    nonce_str = secrets.token_hex(8)
    package = f"prepay_id={prepay_id}"
    sign_type = "MD5"
    sign_params = {
        "appId": app_id,
        "timeStamp": time_stamp,
        "nonceStr": nonce_str,
        "package": package,
        "signType": sign_type,
    }
    pay_sign = sign_v2_md5(sign_params, api_key)
    return {
        "timeStamp": time_stamp,
        "nonceStr": nonce_str,
        "package": package,
        "signType": sign_type,
        "paySign": pay_sign,
    }
