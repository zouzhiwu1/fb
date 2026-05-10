# -*- coding: utf-8 -*-
"""注册时写入 agent_id（推广归因）。"""
import secrets
from decimal import Decimal

import pytest
from werkzeug.security import generate_password_hash


@pytest.fixture
def _agent_for_register(platform_app):
    from app import db
    from app.models import Agent

    with platform_app.app_context():
        suf = secrets.token_hex(3)
        a = Agent(
            agent_code=f"RG{suf}",
            login_name=f"reg_{suf}@t.com",
            password_hash="x",
            display_name="R",
            current_rate=Decimal("0.0500"),
        )
        db.session.add(a)
        db.session.commit()
        return int(a.id)


def test_register_saves_agent_id(platform_app, platform_client, _agent_for_register):
    from app import db
    from app.models import User

    aid = _agent_for_register
    phone = f"136{secrets.randbelow(10**8):08d}"
    r = platform_client.post(
        "/api/auth/register",
        json={
            "username": f"u{secrets.token_hex(2)}",
            "gender": "男",
            "password": "Ab1!xxxx",
            "phone": phone,
            "email": f"{phone}@ex.com",
            "agent_id": aid,
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    with platform_app.app_context():
        u = User.query.filter_by(phone=phone).one()
        assert u.agent_id == aid


def test_register_rejects_inactive_or_missing_agent(platform_app, platform_client):
    r = platform_client.post(
        "/api/auth/register",
        json={
            "username": f"u{secrets.token_hex(2)}",
            "gender": "男",
            "password": "Ab1!xxxx",
            "phone": f"135{secrets.randbelow(10**8):08d}",
            "email": f"x{secrets.token_hex(2)}@ex.com",
            "agent_id": 99999999,
        },
    )
    assert r.status_code == 400
    assert "推广" in (r.get_json() or {}).get("message", "")
