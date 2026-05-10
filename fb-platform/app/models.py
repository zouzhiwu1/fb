# -*- coding: utf-8 -*-
from datetime import datetime
from app import db


class User(db.Model):
    """用户表：用户名、性别、手机号、邮箱、密码。"""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), unique=True, nullable=True, index=True)  # 兼容旧数据
    gender = db.Column(db.String(10), nullable=True)  # 男 / 女 / 其他
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email = db.Column(db.String(128), nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=True)  # 新注册必填，兼容旧数据
    # 登录会话版本号：每次成功登录自增，旧 token 因版本不匹配而失效（单设备登录）
    session_version = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    # 会员系统：是否已赠送过周会员（仅一次）
    free_week_granted_at = db.Column(db.DateTime, nullable=True)
    # 微信小程序支付：jscode2session 得到的 openid（与账号绑定后用于 JSAPI 下单）
    wechat_mp_openid = db.Column(db.String(64), nullable=True, index=True)
    # 拉新归属代理商 agents.id（与 fb-partner / scripts 扩展列一致；未归因则为空）
    agent_id = db.Column(db.Integer, nullable=True, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "gender": self.gender,
            "phone": self.phone,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "password_set": bool(self.password_hash),
            "wechat_mp_bound": bool(self.wechat_mp_openid),
        }


class VerificationCode(db.Model):
    """短信验证码记录：用于注册/找回等场景。"""
    __tablename__ = "verification_codes"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    phone = db.Column(db.String(20), nullable=False, index=True)
    code = db.Column(db.String(10), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)


class EvaluationMatch(db.Model):
    """正在综合评估的比赛：联合主键为（比赛日 YYYYMMDD、主队、客队）。"""

    __tablename__ = "evaluation_matches"

    # 固定 8 位日期字符串，与 pipeline 目录 YYYYMMDD 一致；与主客队组成联合主键（即唯一）
    match_date = db.Column(db.String(8), primary_key=True)
    home_team = db.Column(db.String(128), primary_key=True)  # 主场球队名称
    away_team = db.Column(db.String(128), primary_key=True)  # 客场球队名称

    def to_dict(self):
        return {
            "match_date": self.match_date,
            "home_team": self.home_team,
            "away_team": self.away_team,
        }


class PaymentOrder(db.Model):
    """会员购买订单：商户订单号与支付宝异步通知对账、幂等发货。"""

    __tablename__ = "payment_orders"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    out_trade_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    membership_type = db.Column(db.String(20), nullable=False)
    total_amount = db.Column(db.String(16), nullable=False)  # 与支付宝 total_amount 一致，如 "1000.00"
    subject = db.Column(db.String(256), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending / paid / closed
    trade_no = db.Column(db.String(64), nullable=True)  # 支付宝交易号
    created_at = db.Column(db.DateTime, default=datetime.now)
    paid_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "out_trade_no": self.out_trade_no,
            "user_id": self.user_id,
            "membership_type": self.membership_type,
            "total_amount": self.total_amount,
            "subject": self.subject,
            "status": self.status,
            "trade_no": self.trade_no,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
        }


class MembershipRecord(db.Model):
    """会员记录：用户 ID、类型、生效/失效时间、来源、订单号（购买时）。"""
    __tablename__ = "membership_records"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    membership_type = db.Column(db.String(20), nullable=False)  # week / month / quarter / year
    effective_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    source = db.Column(db.String(20), nullable=False)  # gift / purchase
    order_id = db.Column(db.String(128), nullable=True)  # 购买时填

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "membership_type": self.membership_type,
            "effective_at": self.effective_at.isoformat() if self.effective_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "source": self.source,
            "order_id": self.order_id,
        }


class Agent(db.Model):
    """代理商档案（与 fb-partner 共用 MySQL 表 agents；用于读取 current_rate 等）。"""

    __tablename__ = "agents"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    agent_code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    login_name = db.Column(db.String(128), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(128), nullable=False, default="")
    real_name = db.Column(db.String(64), nullable=True)
    age = db.Column(db.Integer, nullable=True)
    phone = db.Column(db.String(20), nullable=True, unique=True, index=True)
    bank_account = db.Column(db.Text(), nullable=True)
    payout_channel = db.Column(db.String(16), nullable=True)
    payout_account = db.Column(db.String(256), nullable=True)
    payout_holder_name = db.Column(db.String(64), nullable=True)
    contact = db.Column(db.String(128), nullable=True)
    current_rate = db.Column(
        db.Numeric(6, 4), nullable=False, default=0
    )  # 本月充值分润率，如 0.0800 = 8%
    bank_info = db.Column(db.Text(), nullable=True)
    status = db.Column(db.String(16), nullable=False, default="active", index=True)
    session_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    settled_commission_yuan = db.Column(
        db.Numeric(14, 2), nullable=False, default=0
    )


class PointsLedger(db.Model):
    """代理商积分流水（与 fb-partner 共用表 points_ledger）。"""

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
    settlement_month = db.Column(db.String(7), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, index=True)
