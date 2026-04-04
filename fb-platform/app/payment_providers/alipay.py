# -*- coding: utf-8 -*-
"""
支付宝异步通知适配器。
仅负责：参数提取、验签、终态判断、组装 VerifiedPayment；开通会员交给 MembershipFulfillmentPort。
"""
from __future__ import annotations

import logging

from flask import Request

from app.alipay_notify import verify_notify_params
from app.payment_fulfillment import (
    FulfillOutcome,
    FulfillResult,
    MembershipFulfillmentPort,
    VerifiedPayment,
    default_membership_fulfillment,
)
from config import ALIPAY_MODE, ALIPAY_MOCK_SECRET, ALIPAY_PUBLIC_KEY_PEM

logger = logging.getLogger(__name__)

SUCCESS_BODY = "success"
FAIL_BODY = "fail"


def _params_from_request(req: Request) -> dict[str, str]:
    if req.is_json:
        return {
            k: str(v) if v is not None else ""
            for k, v in (req.get_json() or {}).items()
        }
    return req.form.to_dict()


def _mock_notify_allowed(req: Request) -> bool:
    if ALIPAY_MODE != "mock":
        return False
    if not ALIPAY_MOCK_SECRET:
        return True
    return req.headers.get("X-Alipay-Mock-Secret") == ALIPAY_MOCK_SECRET


def _verify_alipay_signature(params: dict[str, str], req: Request) -> bool:
    if ALIPAY_MODE == "mock":
        return _mock_notify_allowed(req)
    return verify_notify_params(params, alipay_public_key_pem=ALIPAY_PUBLIC_KEY_PEM or None)


def _outcome_to_http_body(outcome: FulfillOutcome) -> str:
    if outcome.result in (
        FulfillResult.OK_ALREADY_FULFILLED,
        FulfillResult.OK_FULFILLED,
    ):
        return SUCCESS_BODY
    return FAIL_BODY


def handle_alipay_notify(
    req: Request,
    fulfillment: MembershipFulfillmentPort | None = None,
) -> tuple[str, int, dict[str, str]]:
    """
    处理支付宝 POST 通知。
    返回 (body, status_code, headers) 供 Flask 直接 return。
    """
    fulfillment = fulfillment or default_membership_fulfillment
    params = _params_from_request(req)

    if not _verify_alipay_signature(params, req):
        logger.warning("alipay notify verify failed mode=%s", ALIPAY_MODE)
        return FAIL_BODY, 200, {"Content-Type": "text/plain; charset=utf-8"}

    trade_status = (params.get("trade_status") or "").upper()
    if trade_status not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        # 非支付成功终态：仍应答 success，避免支付宝重试风暴
        return SUCCESS_BODY, 200, {"Content-Type": "text/plain; charset=utf-8"}

    out_trade_no = (params.get("out_trade_no") or "").strip()
    trade_no = (params.get("trade_no") or "").strip()
    total_amount = (params.get("total_amount") or "").strip()

    if not out_trade_no:
        return FAIL_BODY, 200, {"Content-Type": "text/plain; charset=utf-8"}

    payment = VerifiedPayment(
        merchant_order_id=out_trade_no,
        provider_trade_id=trade_no,
        paid_amount=total_amount,
    )
    outcome = fulfillment.fulfill(payment)
    body = _outcome_to_http_body(outcome)
    return body, 200, {"Content-Type": "text/plain; charset=utf-8"}
