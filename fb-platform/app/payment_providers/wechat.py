# -*- coding: utf-8 -*-
"""
微信支付结果通知适配器。
- mock：JSON/XML 等扁平字段，便于 curl / simulate 脚本
- v2：XML + MD5（商户 API 密钥）
- v3：JSON + 平台公钥验签 + APIv3 密钥解密 resource
履约统一走 MembershipFulfillmentPort。
"""
from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import Request, Response

from app.payment_fulfillment import (
    FulfillOutcome,
    FulfillResult,
    MembershipFulfillmentPort,
    VerifiedPayment,
    default_membership_fulfillment,
)
from app.wechat_notify import verify_v2_sign, xml_body_to_dict
from app.wechat_pay_v3 import (
    decrypt_notify_resource,
    load_public_key_from_pem,
    verify_wechatpay_signature,
)
from config import (
    WECHAT_API_KEY,
    WECHAT_API_V3_KEY,
    WECHAT_MOCK_SECRET,
    WECHAT_PAY_MODE,
    WECHAT_PLATFORM_PUBLIC_KEY_PEM,
)

logger = logging.getLogger(__name__)

WECHAT_ACK_SUCCESS_XML = (
    "<xml>"
    "<return_code><![CDATA[SUCCESS]]></return_code>"
    "<return_msg><![CDATA[OK]]></return_msg>"
    "</xml>"
)
WECHAT_ACK_FAIL_XML = (
    "<xml>"
    "<return_code><![CDATA[FAIL]]></return_code>"
    "<return_msg><![CDATA[ERROR]]></return_msg>"
    "</xml>"
)


def _xml_response(xml_str: str, status: int = 200) -> tuple[Response, int]:
    r = Response(
        xml_str,
        status=status,
        mimetype="application/xml; charset=utf-8",
    )
    return r, status


def _mock_notify_allowed(req: Request) -> bool:
    if WECHAT_PAY_MODE != "mock":
        return False
    if not WECHAT_MOCK_SECRET:
        return True
    return req.headers.get("X-Wechat-Mock-Secret") == WECHAT_MOCK_SECRET


def _verify_wechat_params(params: dict[str, str], req: Request) -> bool:
    if WECHAT_PAY_MODE == "mock":
        return _mock_notify_allowed(req)
    if WECHAT_PAY_MODE == "v2":
        return verify_v2_sign(params, WECHAT_API_KEY or "")
    return False


def _params_from_request(req: Request) -> dict[str, str]:
    ct = (req.content_type or "").lower()
    if "json" in ct:
        d = req.get_json(silent=True) or {}
        return {k: str(v) if v is not None else "" for k, v in d.items()}

    raw = (req.get_data(as_text=True) or "").strip()
    if raw.startswith("<"):
        try:
            return xml_body_to_dict(raw)
        except ET.ParseError:
            logger.warning("wechat notify invalid xml")
            return {}

    return req.form.to_dict()


def _total_fee_to_yuan_str(total_fee: str) -> str | None:
    """微信 total_fee 为分（整数字符串），转为与订单一致的元两位小数。"""
    try:
        fen = Decimal(str(total_fee.strip()))
        yuan = (fen / Decimal(100)).quantize(Decimal("0.01"))
        return format(yuan, "f")
    except (InvalidOperation, AttributeError):
        return None


def _paid_amount_yuan(params: dict[str, str]) -> str | None:
    """
    mock 可传 total_amount（元）与支付宝联调习惯一致；
    生产/规范用法传 total_fee（分）。
    """
    ta = (params.get("total_amount") or "").strip()
    if ta:
        try:
            return format(Decimal(ta).quantize(Decimal("0.01")), "f")
        except InvalidOperation:
            return None
    tf = (params.get("total_fee") or "").strip()
    if tf:
        return _total_fee_to_yuan_str(tf)
    return None


def _outcome_to_xml(outcome: FulfillOutcome) -> str:
    if outcome.result in (
        FulfillResult.OK_ALREADY_FULFILLED,
        FulfillResult.OK_FULFILLED,
    ):
        return WECHAT_ACK_SUCCESS_XML
    return WECHAT_ACK_FAIL_XML


def _json_v3_ack(ok: bool, message: str = "") -> tuple[Response, int]:
    body = {
        "code": "SUCCESS" if ok else "FAIL",
        "message": message or ("成功" if ok else "失败"),
    }
    r = Response(
        json.dumps(body, ensure_ascii=False),
        status=200,
        mimetype="application/json; charset=utf-8",
    )
    return r, 200


def _v3_amount_total_to_yuan_str(total: Any) -> str | None:
    try:
        fen = Decimal(str(int(total)))
        yuan = (fen / Decimal(100)).quantize(Decimal("0.01"))
        return format(yuan, "f")
    except (InvalidOperation, ValueError, TypeError):
        return None


def _handle_wechat_notify_v3(
    req: Request,
    fulfillment: MembershipFulfillmentPort,
) -> tuple[Response, int]:
    raw_body = req.get_data(as_text=True) or ""
    ts = (req.headers.get("Wechatpay-Timestamp") or "").strip()
    nonce = (req.headers.get("Wechatpay-Nonce") or "").strip()
    sig = (req.headers.get("Wechatpay-Signature") or "").strip()
    if not ts or not nonce or not sig:
        logger.warning("wechat v3 notify missing signature headers")
        return Response("missing headers", status=401, mimetype="text/plain"), 401

    try:
        pub = load_public_key_from_pem(WECHAT_PLATFORM_PUBLIC_KEY_PEM)
    except ValueError as e:
        logger.warning("wechat v3 platform key: %s", e)
        return Response("server misconfigured", status=500, mimetype="text/plain"), 500

    if not verify_wechatpay_signature(
        body=raw_body,
        timestamp=ts,
        nonce=nonce,
        signature_b64=sig,
        public_key=pub,
    ):
        logger.warning("wechat v3 notify signature verify failed")
        return Response("invalid signature", status=401, mimetype="text/plain"), 401

    try:
        outer = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("wechat v3 notify invalid json")
        return Response("bad json", status=400, mimetype="text/plain"), 400

    event_type = (outer.get("event_type") or "").strip()
    if event_type != "TRANSACTION.SUCCESS":
        return _json_v3_ack(True, "成功")

    resource = outer.get("resource") or {}
    if not isinstance(resource, dict):
        return _json_v3_ack(False, "无 resource")

    algorithm = (resource.get("algorithm") or "").strip()
    if algorithm != "AEAD_AES_256_GCM":
        logger.warning("wechat v3 notify unknown algorithm %s", algorithm)
        return _json_v3_ack(False, "不支持的通知算法")

    ciphertext = (resource.get("ciphertext") or "").strip()
    nonce_r = (resource.get("nonce") or "").strip()
    aad = (resource.get("associated_data") or "").strip()
    if not ciphertext or not nonce_r:
        return _json_v3_ack(False, "resource 不完整")

    try:
        trade = decrypt_notify_resource(
            api_v3_key=WECHAT_API_V3_KEY,
            associated_data=aad,
            nonce=nonce_r,
            ciphertext_b64=ciphertext,
        )
    except Exception as e:
        logger.warning("wechat v3 notify decrypt failed: %s", e)
        return Response("decrypt failed", status=500, mimetype="text/plain"), 500

    trade_state = (trade.get("trade_state") or "").strip()
    if trade_state != "SUCCESS":
        return _json_v3_ack(True, "成功")

    out_trade_no = (trade.get("out_trade_no") or "").strip()
    transaction_id = (trade.get("transaction_id") or "").strip()
    amount = trade.get("amount") or {}
    total = amount.get("total") if isinstance(amount, dict) else None
    paid_yuan = _v3_amount_total_to_yuan_str(total)
    if not out_trade_no or not paid_yuan:
        return _json_v3_ack(False, "订单字段缺失")

    payment = VerifiedPayment(
        merchant_order_id=out_trade_no,
        provider_trade_id=transaction_id,
        paid_amount=paid_yuan,
    )
    outcome = fulfillment.fulfill(payment)

    if outcome.result in (
        FulfillResult.OK_ALREADY_FULFILLED,
        FulfillResult.OK_FULFILLED,
    ):
        return _json_v3_ack(True, "成功")

    if outcome.result == FulfillResult.ERR_EXCEPTION:
        return Response("exception", status=500, mimetype="text/plain"), 500

    return _json_v3_ack(False, outcome.result.value)


def handle_wechat_notify(
    req: Request,
    fulfillment: MembershipFulfillmentPort | None = None,
) -> tuple[Response, int]:
    """
    处理微信支付异步通知。
    mock / v2：成功时返回 XML（return_code SUCCESS）；v3：返回 JSON（code SUCCESS）。
    """
    fulfillment = fulfillment or default_membership_fulfillment

    if WECHAT_PAY_MODE == "v3":
        return _handle_wechat_notify_v3(req, fulfillment)

    params = _params_from_request(req)

    if not _verify_wechat_params(params, req):
        logger.warning("wechat notify verify failed mode=%s", WECHAT_PAY_MODE)
        r, st = _xml_response(WECHAT_ACK_FAIL_XML)
        return r, st

    if (params.get("return_code") or "").upper() != "SUCCESS":
        r, st = _xml_response(WECHAT_ACK_SUCCESS_XML)
        return r, st

    if (params.get("result_code") or "").upper() != "SUCCESS":
        r, st = _xml_response(WECHAT_ACK_SUCCESS_XML)
        return r, st

    out_trade_no = (params.get("out_trade_no") or "").strip()
    transaction_id = (params.get("transaction_id") or "").strip()
    paid_yuan = _paid_amount_yuan(params)

    if not out_trade_no or not paid_yuan:
        r, st = _xml_response(WECHAT_ACK_FAIL_XML)
        return r, st

    payment = VerifiedPayment(
        merchant_order_id=out_trade_no,
        provider_trade_id=transaction_id,
        paid_amount=paid_yuan,
    )
    outcome = fulfillment.fulfill(payment)
    xml_body = _outcome_to_xml(outcome)
    r, st = _xml_response(xml_body)
    return r, st
