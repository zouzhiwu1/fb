# -*- coding: utf-8 -*-
"""
支付成功后「开通会员」的统一履约层。
各支付渠道（支付宝、微信等）验签、解析后，构造 VerifiedPayment 调用此处，避免重复业务逻辑。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Protocol

from app import db
from app.membership import SOURCE_PURCHASE, add_membership
from app.models import PaymentOrder

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerifiedPayment:
    """与支付渠道无关的「已确认收款」信息（由渠道适配器填入）。"""

    merchant_order_id: str
    """本系统商户订单号，对应 payment_orders.out_trade_no。"""
    provider_trade_id: str
    """第三方支付单号（支付宝 trade_no、微信 transaction_id 等），可空字符串。"""
    paid_amount: str
    """实付金额，与库中 total_amount 同一格式（如 "29.90"）。"""


class FulfillResult(Enum):
    """履约结果（供路由决定返回 success / fail）。"""

    OK_ALREADY_FULFILLED = "ok_already"  # 已支付过，幂等
    OK_FULFILLED = "ok_new"  # 本次完成开通
    ERR_UNKNOWN_ORDER = "unknown_order"
    ERR_AMOUNT_MISMATCH = "amount_mismatch"
    ERR_BAD_ORDER_STATE = "bad_state"
    ERR_EXCEPTION = "exception"


@dataclass(frozen=True)
class FulfillOutcome:
    result: FulfillResult


class MembershipFulfillmentPort(Protocol):
    """扩展新支付渠道时，回调里只负责解析并调用 fulfill。"""

    def fulfill(self, payment: VerifiedPayment) -> FulfillOutcome:
        ...


class DefaultMembershipFulfillment:
    """根据商户订单开通会员并更新 payment_orders（幂等）。"""

    def fulfill(self, payment: VerifiedPayment) -> FulfillOutcome:
        out_no = payment.merchant_order_id.strip()
        if not out_no:
            return FulfillOutcome(FulfillResult.ERR_UNKNOWN_ORDER)

        order = PaymentOrder.query.filter_by(out_trade_no=out_no).first()
        if not order:
            logger.warning("fulfill unknown order %s", out_no)
            return FulfillOutcome(FulfillResult.ERR_UNKNOWN_ORDER)

        try:
            if Decimal(str(payment.paid_amount)) != Decimal(str(order.total_amount)):
                logger.warning(
                    "fulfill amount mismatch order=%s expect=%s got=%s",
                    out_no,
                    order.total_amount,
                    payment.paid_amount,
                )
                return FulfillOutcome(FulfillResult.ERR_AMOUNT_MISMATCH)
        except InvalidOperation:
            return FulfillOutcome(FulfillResult.ERR_AMOUNT_MISMATCH)

        if order.status == "paid":
            return FulfillOutcome(FulfillResult.OK_ALREADY_FULFILLED)

        if order.status != "pending":
            logger.warning("fulfill bad order state %s status=%s", out_no, order.status)
            return FulfillOutcome(FulfillResult.ERR_BAD_ORDER_STATE)

        try:
            add_membership(
                order.user_id,
                order.membership_type,
                source=SOURCE_PURCHASE,
                order_id=out_no,
            )
            order.status = "paid"
            if payment.provider_trade_id:
                order.trade_no = payment.provider_trade_id
            order.paid_at = datetime.now()
            db.session.commit()
            logger.info("fulfill paid out_trade_no=%s user=%s", out_no, order.user_id)
            return FulfillOutcome(FulfillResult.OK_FULFILLED)
        except Exception:
            logger.exception("fulfill exception out_trade_no=%s", out_no)
            db.session.rollback()
            return FulfillOutcome(FulfillResult.ERR_EXCEPTION)


# 默认实例；测试可 patch 模块级变量或传入子类
default_membership_fulfillment: MembershipFulfillmentPort = DefaultMembershipFulfillment()
