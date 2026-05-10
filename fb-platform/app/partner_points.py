# -*- coding: utf-8 -*-
"""
代理商积分流水：用户充值成功后写入 points_ledger。
文档：充值业绩(元) × 本月充值分润率 = 该笔贡献的积分（与月度汇总公式一致）。
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app import db
from app.models import Agent, PaymentOrder, PointsLedger, User

logger = logging.getLogger(__name__)

EVENT_RECHARGE = "recharge"


def record_recharge_points_ledger(order: PaymentOrder, paid_at: datetime | None) -> None:
    """
    幂等：同一商户订单号 out_trade_no 仅一条 event_type=recharge 流水。
    用户未绑定 agent_id 或分润率为 0 时不记账。
    """
    ts = paid_at or datetime.now()
    user = db.session.get(User, order.user_id)
    if user is None or user.agent_id is None:
        return

    exists = (
        PointsLedger.query.filter_by(
            order_id=order.out_trade_no,
            event_type=EVENT_RECHARGE,
        ).first()
    )
    if exists is not None:
        return

    agent = db.session.get(Agent, user.agent_id)
    if agent is None:
        logger.warning(
            "partner points skipped: no agent row agent_id=%s order=%s",
            user.agent_id,
            order.out_trade_no,
        )
        return

    try:
        rate = Decimal(str(agent.current_rate or 0))
        base = Decimal(str(order.total_amount))
    except (InvalidOperation, TypeError, ValueError):
        logger.warning(
            "partner points skipped: invalid amount or rate order=%s",
            order.out_trade_no,
        )
        return

    points_delta = (base * rate).quantize(Decimal("0.01"))
    if points_delta <= 0:
        return

    ym = f"{ts.year:04d}-{ts.month:02d}"
    ledger = PointsLedger(
        agent_id=agent.id,
        user_id=user.id,
        order_id=order.out_trade_no,
        event_type=EVENT_RECHARGE,
        base_amount=base,
        applied_rate=rate,
        points_delta=points_delta,
        settlement_month=ym,
        created_at=ts,
    )
    db.session.add(ledger)
