# -*- coding: utf-8 -*-
"""代理商侧表；不与 platform 的 User 模型重复定义，C 端用户通过 SQL 或后续共享包读取。"""
from datetime import datetime

from app import db


class PartnerAdmin(db.Model):
    """后台管理员：代录入代理商开户，不共用代理商 JWT。"""

    __tablename__ = "partner_admins"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    login_name = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="active", index=True)
    session_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Agent(db.Model):
    __tablename__ = "agents"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    agent_code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    login_name = db.Column(db.String(128), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(128), nullable=False, default="")
    # 档案（管理员开户时录入；历史数据可为空）
    real_name = db.Column(db.String(64), nullable=True)
    age = db.Column(db.Integer, nullable=True)
    phone = db.Column(db.String(20), nullable=True, unique=True, index=True)
    bank_account = db.Column(db.Text(), nullable=True)
    payout_channel = db.Column(db.String(16), nullable=True)  # alipay | wechat
    payout_account = db.Column(db.String(256), nullable=True)
    payout_holder_name = db.Column(db.String(64), nullable=True)
    contact = db.Column(db.String(128), nullable=True)
    current_rate = db.Column(
        db.Numeric(6, 4), nullable=False, default=0
    )  # 如 0.0800 = 本月返点率
    bank_info = db.Column(db.Text(), nullable=True)
    status = db.Column(db.String(16), nullable=False, default="active", index=True)
    session_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    # 管理员线下打款后累计已结算佣金（元）
    settled_commission_yuan = db.Column(
        db.Numeric(14, 2), nullable=False, default=0
    )


class AgentCommissionSettlement(db.Model):
    """管理员结算佣金流水：线下打款后在系统登记金额与支付凭证（渠道+订单号）。"""

    __tablename__ = "agent_commission_settlements"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    partner_admin_id = db.Column(
        db.Integer,
        db.ForeignKey("partner_admins.id"),
        nullable=True,
        index=True,
    )
    agent_id = db.Column(
        db.Integer,
        db.ForeignKey("agents.id"),
        nullable=False,
        index=True,
    )
    settlement_month = db.Column(db.String(7), nullable=True, index=True)
    payment_channel = db.Column(db.String(16), nullable=True)  # alipay | wechat
    payment_reference = db.Column(db.String(256), nullable=True)
    payment_note = db.Column(db.Text(), nullable=True)
    amount_yuan = db.Column(db.Numeric(14, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class PointsLedger(db.Model):
    __tablename__ = "points_ledger"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    agent_id = db.Column(
        db.Integer,
        db.ForeignKey("agents.id"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(db.Integer, nullable=True, index=True)
    order_id = db.Column(db.String(64), nullable=True, index=True)
    event_type = db.Column(db.String(32), nullable=False, index=True)
    base_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    applied_rate = db.Column(db.Numeric(6, 4), nullable=False, default=0)
    points_delta = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    settlement_month = db.Column(
        db.String(7), nullable=True, index=True
    )  # YYYY-MM
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
