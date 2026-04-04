from types import SimpleNamespace

from app.auth import (
    _normalize_phone,
    _is_valid_phone,
    _normalize_email,
    _create_token,
    _verify_token,
    get_user_id_from_authorization,
)


def test_normalize_phone_removes_spaces_and_dashes():
    assert _normalize_phone(" 138-0013 8000 ") == "13800138000"


def test_is_valid_phone():
    assert _is_valid_phone("13800138000")
    assert not _is_valid_phone("1380013800")  # 10 位
    assert not _is_valid_phone("bad-number")


def test_normalize_email_lower_and_strip():
    assert _normalize_email("  USER@Example.COM ") == "user@example.com"


def test_create_and_verify_token_roundtrip():
    token = _create_token(123)
    user_id = _verify_token(token)
    assert user_id == 123


def test_verify_token_invalid_returns_none():
    assert _verify_token("invalid-token") is None
    assert _verify_token("") is None


def test_get_user_id_from_authorization_bearer_case_insensitive():
    tok = _create_token(42)
    req = SimpleNamespace(headers={"Authorization": f"bearer {tok}"})
    assert get_user_id_from_authorization(req) == 42
    req2 = SimpleNamespace(headers={"Authorization": f'Bearer "{tok}"'})
    assert get_user_id_from_authorization(req2) == 42


def test_get_user_id_from_authorization_invalid():
    assert get_user_id_from_authorization(SimpleNamespace(headers={})) is None
    assert get_user_id_from_authorization(SimpleNamespace(headers={"Authorization": "Basic x"})) is None

