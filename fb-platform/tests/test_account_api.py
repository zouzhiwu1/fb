# -*- coding: utf-8 -*-
"""账户资料 API：修改密码、邮箱、手机号。"""
import secrets
from datetime import datetime, timedelta

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.auth import _create_token
from app.models import User, VerificationCode


def _add_user(
    *,
    phone: str,
    password: str | None = "Secret12!",
    email: str | None = None,
    username: str | None = None,
    gender: str = "男",
) -> int:
    if username is None:
        username = f"u_{secrets.token_hex(4)}"
    if email is None:
        email = f"{secrets.token_hex(6)}@acct.test"
    h = generate_password_hash(password, method="pbkdf2:sha256") if password else None
    u = User(
        phone=phone,
        password_hash=h,
        email=email,
        username=username,
        gender=gender,
    )
    db.session.add(u)
    db.session.commit()
    return u.id


def _auth(uid: int) -> dict:
    return {"Authorization": f"Bearer {_create_token(uid)}"}


@pytest.fixture
def user_with_password(platform_app):
    with platform_app.app_context():
        phone = f"138{secrets.randbelow(10**8):08d}"
        uid = _add_user(phone=phone, password="Oldpass12!")
        return uid, phone


@pytest.fixture
def user_no_password(platform_app):
    with platform_app.app_context():
        phone = f"137{secrets.randbelow(10**8):08d}"
        uid = _add_user(phone=phone, password=None)
        return uid, phone


def test_change_password_unauthorized(platform_client):
    r = platform_client.post("/api/auth/change-password", json={"new_password": "abcdef12"})
    assert r.status_code == 401


def test_change_password_wrong_current(platform_client, user_with_password):
    uid, _ = user_with_password
    r = platform_client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong", "new_password": "Newpass12!"},
        headers=_auth(uid),
    )
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_change_password_success(platform_app, platform_client, user_with_password):
    uid, phone = user_with_password
    r = platform_client.post(
        "/api/auth/change-password",
        json={"current_password": "Oldpass12!", "new_password": "Newpass99!"},
        headers=_auth(uid),
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    with platform_app.app_context():
        u = db.session.get(User, uid)
        assert check_password_hash(u.password_hash, "Newpass99!")
    login = platform_client.post(
        "/api/auth/login",
        json={"phone": phone, "password": "Newpass99!"},
    )
    assert login.status_code == 200


def test_change_password_first_time_no_current(platform_app, platform_client, user_no_password):
    uid, phone = user_no_password
    r = platform_client.post(
        "/api/auth/change-password",
        json={"new_password": "Firstpass1!"},
        headers=_auth(uid),
    )
    assert r.status_code == 200
    with platform_app.app_context():
        u = db.session.get(User, uid)
        assert u.password_hash
        assert check_password_hash(u.password_hash, "Firstpass1!")


def test_me_includes_password_set(platform_client, user_with_password):
    uid, _ = user_with_password
    r = platform_client.get("/api/auth/me", headers=_auth(uid))
    assert r.status_code == 200
    body = r.get_json()
    assert body["user"]["password_set"] is True


def test_me_password_set_false(platform_client, user_no_password):
    uid, _ = user_no_password
    r = platform_client.get("/api/auth/me", headers=_auth(uid))
    assert r.get_json()["user"]["password_set"] is False


def test_change_email_success(platform_client, user_with_password):
    uid, _ = user_with_password
    new_mail = f"changed_{secrets.token_hex(4)}@Example.COM"
    r = platform_client.post(
        "/api/auth/change-email",
        json={"email": new_mail},
        headers={**_auth(uid), "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["user"]["email"] == new_mail.strip().lower()


def test_change_email_duplicate_other_user(platform_app, platform_client, user_with_password):
    uid_a, _ = user_with_password
    taken = f"taken_{secrets.token_hex(4)}@example.com"
    with platform_app.app_context():
        phone_b = f"136{secrets.randbelow(10**8):08d}"
        _add_user(phone=phone_b, email=taken, password="Aa1!xxxxxx")

    r = platform_client.post(
        "/api/auth/change-email",
        json={"email": taken},
        headers={**_auth(uid_a), "Content-Type": "application/json"},
    )
    assert r.status_code == 409


def test_change_phone_success(platform_app, platform_client, user_with_password):
    uid, old_phone = user_with_password
    new_phone = f"159{secrets.randbelow(10**8):08d}"
    assert new_phone != old_phone

    with platform_app.app_context():
        rec = VerificationCode(
            phone=new_phone,
            code="654321",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        db.session.add(rec)
        db.session.commit()

    r = platform_client.post(
        "/api/auth/change-phone",
        json={"new_phone": new_phone, "code": "654321"},
        headers={**_auth(uid), "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["user"]["phone"] == new_phone

    with platform_app.app_context():
        u = db.session.get(User, uid)
        assert u.phone == new_phone


def test_change_phone_same_number(platform_client, user_with_password):
    uid, phone = user_with_password
    r = platform_client.post(
        "/api/auth/change-phone",
        json={"new_phone": phone, "code": "111111"},
        headers={**_auth(uid), "Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_change_phone_taken(platform_app, platform_client, user_with_password):
    uid_a, phone_a = user_with_password
    with platform_app.app_context():
        phone_b = f"135{secrets.randbelow(10**8):08d}"
        _add_user(phone=phone_b, password="Bb2!yyyyyy")
        rec = VerificationCode(
            phone=phone_b,
            code="888888",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        db.session.add(rec)
        db.session.commit()

    r = platform_client.post(
        "/api/auth/change-phone",
        json={"new_phone": phone_b, "code": "888888"},
        headers={**_auth(uid_a), "Content-Type": "application/json"},
    )
    assert r.status_code == 409


def test_account_page_renders(platform_client):
    r = platform_client.get("/account")
    assert r.status_code == 200
    assert "账户资料".encode("utf-8") in r.data
