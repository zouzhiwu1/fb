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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # 会员系统：是否已赠送过周会员（仅一次）
    free_week_granted_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "gender": self.gender,
            "phone": self.phone,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class VerificationCode(db.Model):
    """短信验证码记录：用于注册/找回等场景。"""
    __tablename__ = "verification_codes"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    phone = db.Column(db.String(20), nullable=False, index=True)
    code = db.Column(db.String(10), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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
