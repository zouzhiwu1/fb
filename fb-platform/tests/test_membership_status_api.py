# -*- coding: utf-8 -*-
"""会员状态 API 与会员信息页。"""
import secrets
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.auth import _create_token

from app import db
from app.models import MembershipRecord, User
from tests.conftest import make_test_user_and_token


def test_membership_status_401(platform_client):
    r = platform_client.get("/api/membership/status")
    assert r.status_code == 401


def test_membership_status_empty(platform_app, platform_client):
    _, token = make_test_user_and_token(platform_app)
    r = platform_client.get(
        "/api/membership/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["is_member"] is False
    assert data["expires_at"] is None
    assert data["active_records"] == []
    assert data.get("free_week_granted_at") is None


def test_membership_status_with_active_record(platform_app, platform_client):
    from werkzeug.security import generate_password_hash

    with platform_app.app_context():
        phone = f"138{secrets.randbelow(10**8):08d}"
        u = User(
            phone=phone,
            password_hash=generate_password_hash("Aa1!xxxxxx"),
            username=f"m_{secrets.token_hex(4)}",
            gender="男",
            email=f"{secrets.token_hex(4)}@m.test",
        )
        db.session.add(u)
        db.session.commit()
        uid = u.id
        now = datetime(2030, 6, 15, 12, 0, 0)
        db.session.add(
            MembershipRecord(
                user_id=uid,
                membership_type="month",
                effective_at=now,
                expires_at=now + timedelta(days=30),
                source="purchase",
                order_id="FBTEST123",
            )
        )
        db.session.commit()
        token = _create_token(uid, int(u.session_version or 1))

    mid = datetime(2030, 6, 16, 12, 0, 0)
    with patch("app.membership._membership_now_naive", return_value=mid):
        r = platform_client.get(
            "/api/membership/status",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["is_member"] is True
    assert data["expires_at"]
    assert len(data["active_records"]) == 1
    ar0 = data["active_records"][0]
    assert ar0["membership_type"] == "month"
    assert ar0["membership_type_label"] == "月会员"
    assert ar0["source"] == "purchase"
    assert ar0["source_label"] == "购买"
    assert ar0["order_id"] == "FBTEST123"


def test_membership_status_expires_at_includes_queued_records(platform_app, platform_client):
    """总到期日含待生效顺延记录（付月卡后立即显示最晚 expires_at）。"""
    with platform_app.app_context():
        uid, token = make_test_user_and_token(platform_app)
        gift_eff = datetime(2026, 5, 27, 5, 51, 27)
        gift_exp = datetime(2026, 6, 3, 5, 51, 27)
        month_eff = datetime(2026, 6, 3, 5, 51, 27)
        month_exp = datetime(2026, 7, 3, 5, 51, 27)
        db.session.add(
            MembershipRecord(
                user_id=uid,
                membership_type="week",
                effective_at=gift_eff,
                expires_at=gift_exp,
                source="gift",
                order_id=None,
            )
        )
        db.session.add(
            MembershipRecord(
                user_id=uid,
                membership_type="month",
                effective_at=month_eff,
                expires_at=month_exp,
                source="purchase",
                order_id="V000058TEST",
            )
        )
        db.session.commit()

    now = datetime(2026, 6, 1, 20, 30, 30)
    with patch("app.membership._membership_now_naive", return_value=now):
        r = platform_client.get(
            "/api/membership/status",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["is_member"] is True
    assert data["expires_at"].startswith("2026-07-03")
    assert data["days_remaining"] == 32
    assert data["active_expires_at"].startswith("2026-06-03")
    assert data["active_days_remaining"] == 2
    assert len(data["active_records"]) == 1
    assert data["active_records"][0]["membership_type"] == "week"
    assert len(data["pending_records"]) == 1
    assert data["pending_records"][0]["membership_type"] == "month"


def test_membership_page_renders(platform_client):
    r = platform_client.get("/membership")
    assert r.status_code == 200
    assert "会员信息".encode("utf-8") in r.data
