# -*- coding: utf-8 -*-
"""单测默认 mock：避免创建代理商时请求微信。"""
import pytest


@pytest.fixture(autouse=True)
def _mock_agent_promo_qr_save(app, monkeypatch):
    """须在 app fixture 之后执行（与 test_smoke 中 setenv/create_app 顺序一致）。"""
    monkeypatch.setattr(
        "app.admin_api.save_agent_promo_miniprogram_qr",
        lambda agent_id: True,
    )
    monkeypatch.setattr(
        "app.auth_partner.save_agent_promo_miniprogram_qr",
        lambda agent_id: True,
    )
