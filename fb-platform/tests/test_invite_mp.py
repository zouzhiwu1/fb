# -*- coding: utf-8 -*-
"""H5 /invite-mp 落地页（拉起小程序）。"""
import pytest


def test_invite_mp_503_when_no_app_id(platform_client, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg, "WECHAT_MP_APP_ID", "")
    r = platform_client.get("/invite-mp?agent_id=1")
    assert r.status_code == 503
    assert "WECHAT_MP_APP_ID".encode("utf-8") in r.data or "配置".encode("utf-8") in r.data


def test_invite_mp_200_contains_scheme(platform_client, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg, "WECHAT_MP_APP_ID", "wx1234567890abcdef")
    monkeypatch.setattr(cfg, "INVITE_MP_ENTRY_PAGE", "pages/register/register")
    monkeypatch.setattr(cfg, "INVITE_MP_ENV_VERSION", "trial")
    r = platform_client.get("/invite-mp?agent_id=1")
    assert r.status_code == 200
    assert b"weixin://dl/business/" in r.data
    assert b"agent_id%3D1" in r.data or b"agent_id=1" in r.data


def test_invite_mp_bad_agent_returns_400(platform_client, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg, "WECHAT_MP_APP_ID", "wx1234567890abcdef")
    r = platform_client.get("/invite-mp?agent_id=abc")
    assert r.status_code == 400
