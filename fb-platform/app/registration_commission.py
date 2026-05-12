# -*- coding: utf-8 -*-
"""
注册归因成功后写入 agent_commission_lines（registration），与 fb-partner _sync 拉新行一致。
失败仅打日志，不影响注册主流程。
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Agent, AgentCommissionLine

logger = logging.getLogger(__name__)


def _mask_phone(phone: object | None) -> str:
    if phone is None:
        return "—"
    p = str(phone).strip()
    if len(p) >= 11:
        return f"{p[:3]}****{p[-4:]}"
    if len(p) >= 7:
        return f"{p[:2]}****{p[-2:]}"
    return "****"


def try_insert_registration_commission_line(
    agent_id: int,
    user_id: int,
    phone: str | None,
    created_at: datetime | None,
) -> None:
    """
    幂等插入一条 commission_type=registration。
    须在 users 行已提交后调用；内部单独 commit。
    """
    if agent_id is None or user_id is None:
        return
    try:
        if db.session.get(Agent, agent_id) is None:
            logger.warning(
                "registration commission skipped: agent not found agent_id=%s user_id=%s",
                agent_id,
                user_id,
            )
            return
        from config import PARTNER_REG_FACTOR

        reg_factor = Decimal(str(PARTNER_REG_FACTOR)).quantize(Decimal("0.0001"))
        amt = Decimal(str(reg_factor)).quantize(Decimal("0.01"))
        ts = created_at or datetime.now()
        row = AgentCommissionLine(
            agent_id=agent_id,
            user_id=user_id,
            username=_mask_phone(phone),
            commission_type="registration",
            created_at=ts,
            reg_factor=reg_factor,
            commission_amount=amt,
            payment_status="pending",
        )
        db.session.add(row)
        db.session.commit()
        logger.info(
            "registration commission line inserted agent_id=%s user_id=%s amount=%s",
            agent_id,
            user_id,
            amt,
        )
    except IntegrityError:
        db.session.rollback()
        logger.info(
            "registration commission line already exists (skip) agent_id=%s user_id=%s",
            agent_id,
            user_id,
        )
    except Exception:
        db.session.rollback()
        logger.exception(
            "registration commission line insert failed agent_id=%s user_id=%s",
            agent_id,
            user_id,
        )
