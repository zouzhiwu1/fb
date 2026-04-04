# -*- coding: utf-8 -*-
"""
微信支付结果通知适配器（V2 XML 为主；mock 下支持 JSON/表单便于 curl）。
履约统一走 MembershipFulfillmentPort。
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from flask import Request, Response

from app.payment_fulfillment import (
    FulfillOutcome,
    FulfillResult,
    MembershipFulfillmentPort,
    VerifiedPayment,
    default_membership_fulfillment,
)
from app.wechat_notify import verify_v2_sign, xml_body_to_dict
from config import WECHAT_API_KEY, WECHAT_MOCK_SECRET, WECHAT_PAY_MODE

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


def handle_wechat_notify(
    req: Request,
    fulfillment: MembershipFulfillmentPort | None = None,
) -> tuple[Response, int]:
    """
    处理微信支付异步通知。
    成功处理须返回 XML（业务层 return_code SUCCESS），否则微信会重试。
    """
    fulfillment = fulfillment or default_membership_fulfillment
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
