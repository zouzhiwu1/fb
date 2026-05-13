# -*- coding: utf-8 -*-
"""管理员 platform users 表：单测在 SQLite 中建 users 表。"""
import pytest
from sqlalchemy import text
from werkzeug.security import generate_password_hash

_BOOT = {"X-Partner-Bootstrap-Key": "unit-test-bootstrap-key", "Content-Type": "application/json"}


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv(
        "PARTNER_JWT_SECRET_KEY",
        "unit-test-partner-jwt-secret-key-32bytes!",
    )
    monkeypatch.setenv("PARTNER_BOOTSTRAP_KEY", "unit-test-bootstrap-key")
    monkeypatch.setenv("PARTNER_ROOT_PASSWORD", "unit-test-root-pw")
    monkeypatch.setenv("PARTNER_ROOT_SESSION_VERSION", "1")
    monkeypatch.delenv("PARTNER_INITIAL_ADMINS_JSON", raising=False)
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _admin_auth(client):
    client.post(
        "/api/partner/auth/bootstrap-admin",
        json={"login_name": "adm_pu", "password": "Adm1!platusers"},
        headers=_BOOT,
    )
    r = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "adm_pu", "password": "Adm1!platusers"},
    )
    assert r.status_code == 200
    tok = r.get_json()["token"]
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _init_users_table(app):
    import app.admin_api as admin_api_mod
    from app import db
    from app.models import Agent

    admin_api_mod._platform_user_select_cols = None
    with app.app_context():
        db.session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(64) UNIQUE,
                    gender VARCHAR(10),
                    phone VARCHAR(20) NOT NULL UNIQUE,
                    email VARCHAR(128),
                    password_hash VARCHAR(255),
                    session_version INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME,
                    updated_at DATETIME,
                    free_week_granted_at DATETIME,
                    agent_id INTEGER,
                    wechat_mp_openid VARCHAR(64)
                )
                """
            )
        )
        ag = Agent(
            agent_code="__tmp_init",
            login_name="pu_agent@test.local",
            password_hash=generate_password_hash("x"),
            display_name="PU",
            status="active",
        )
        db.session.add(ag)
        db.session.flush()
        aid = ag.id
        ag.agent_code = str(aid)
        db.session.execute(
            text(
                """
                INSERT INTO users (username, gender, phone, email, password_hash, session_version, agent_id)
                VALUES ('u_find', '男', '13900008888', 'finduser@test.local', 'h', 2, :aid)
                """
            ),
            {"aid": aid},
        )
        db.session.commit()
        return aid


def test_admin_users_html(client):
    r = client.get("/admin/users")
    assert r.status_code == 200
    t = r.get_data(as_text=True)
    assert "用户信息" in t and "platform-users" in t


def test_platform_users_search_get_put(client, app):
    auth = _admin_auth(client)
    aid = _init_users_table(app)

    r0 = client.get("/api/partner/admin/platform-users/search?q=13900008888", headers=auth)
    assert r0.status_code == 200
    j0 = r0.get_json()
    assert j0.get("ok") is True
    assert len(j0.get("users") or []) == 1
    uid = j0["users"][0]["id"]

    r1 = client.get(f"/api/partner/admin/platform-users/{uid}", headers=auth)
    assert r1.status_code == 200
    assert r1.get_json()["user"]["phone"] == "13900008888"

    r2 = client.put(
        f"/api/partner/admin/platform-users/{uid}",
        json={
            "username": "u_renamed",
            "gender": "女",
            "phone": "13900008888",
            "email": "finduser@test.local",
            "agent_id": None,
        },
        headers=auth,
    )
    assert r2.status_code == 200
    u2 = r2.get_json()["user"]
    assert u2["username"] == "u_renamed"
    assert u2["gender"] == "女"
    assert u2["agent_id"] is None

    r3 = client.put(
        f"/api/partner/admin/platform-users/{uid}",
        json={"phone": "13900008888", "agent_id": aid},
        headers=auth,
    )
    assert r3.status_code == 200
    assert r3.get_json()["user"]["agent_id"] == aid


def test_root_can_search_platform_users(client, app):
    """根账号也可查 users（与代理商 API 403 区分）。"""
    _init_users_table(app)
    r = client.post(
        "/api/partner/auth/admin/login",
        json={"login_name": "root", "password": "unit-test-root-pw"},
    )
    assert r.status_code == 200
    tok = r.get_json()["token"]
    auth = {"Authorization": f"Bearer {tok}"}
    r2 = client.get("/api/partner/admin/platform-users/search?q=finduser@test.local", headers=auth)
    assert r2.status_code == 200
    assert r2.get_json().get("count") == 1
