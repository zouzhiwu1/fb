# -*- coding: utf-8 -*-
from datetime import timedelta
from unittest.mock import patch

import pytest

import app.membership as membership_mod
from app.models import MembershipRecord
from tests.conftest import make_test_user_and_token


@pytest.fixture(autouse=True)
def _pay_mock_mode():
    """支付测试固定为 mock，且不强制 mock secret。"""
    import app.payment_providers.alipay as alipay_mod

    with patch.object(alipay_mod, "ALIPAY_MODE", "mock"), patch.object(
        alipay_mod, "ALIPAY_MOCK_SECRET", ""
    ):
        yield


def test_pay_orders_401(platform_client):
    r = platform_client.post(
        "/api/pay/orders",
        json={"membership_type": "month"},
    )
    assert r.status_code == 401


def test_pay_membership_options_ok(platform_client):
    r = platform_client.get("/api/pay/membership-options")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    opts = data.get("options") or []
    assert len(opts) >= 1
    types = {o["membership_type"] for o in opts}
    assert "month" in types
    assert all("label" in o and "price" in o for o in opts)


def test_pay_list_orders_401(platform_client):
    assert platform_client.get("/api/pay/orders").status_code == 401


def test_pay_list_orders_after_create(platform_app, platform_client):
    _, token = make_test_user_and_token(platform_app)
    platform_client.post(
        "/api/pay/orders",
        json={"membership_type": "week"},
        headers={"Authorization": f"Bearer {token}"},
    )
    r = platform_client.get(
        "/api/pay/orders",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    orders = data.get("orders") or []
    assert len(orders) >= 1
    row = orders[0]
    assert row.get("out_trade_no")
    assert row.get("status") == "pending"
    assert row.get("status_label") == "待支付"
    assert row.get("membership_type_label")
    assert "user_id" not in row


def test_recharge_pages_render(platform_client):
    assert platform_client.get("/recharge").status_code == 200
    assert platform_client.get("/recharge-records").status_code == 200


def test_pay_orders_creates_order(platform_app, platform_client):
    _, token = make_test_user_and_token(platform_app)
    r = platform_client.post(
        "/api/pay/orders",
        json={"membership_type": "month"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert data.get("out_trade_no")
    assert data.get("total_amount")
    assert data.get("notify_url", "").endswith("/api/pay/alipay/notify")


def test_alipay_notify_mock_paid_then_member(platform_app, platform_client):
    from app.models import PaymentOrder

    _, token = make_test_user_and_token(platform_app)
    r = platform_client.post(
        "/api/pay/orders",
        json={"membership_type": "week"},
        headers={"Authorization": f"Bearer {token}"},
    )
    out_no = r.get_json()["out_trade_no"]
    amount = r.get_json()["total_amount"]

    nr = platform_client.post(
        "/api/pay/alipay/notify",
        data={
            "trade_status": "TRADE_SUCCESS",
            "out_trade_no": out_no,
            "trade_no": "2026032122001156789012345678",
            "total_amount": amount,
        },
    )
    assert nr.status_code == 200
    assert nr.data.decode("utf-8").strip().lower() == "success"

    with platform_app.app_context():
        o = PaymentOrder.query.filter_by(out_trade_no=out_no).one()
        assert o.status == "paid"
        uid = o.user_id
        m = MembershipRecord.query.filter_by(order_id=out_no).one()
        assert m.membership_type == "week"
        assert m.effective_at < m.expires_at
        # 共享 MySQL 时 add_membership 可能把 effective 顺延到未来，不依赖「当前时刻」断言 is_member
        mid = m.effective_at + timedelta(days=1)
        with patch.object(membership_mod, "_membership_now_naive", return_value=mid):
            assert membership_mod.is_member(uid) is True


def test_alipay_notify_idempotent(platform_app, platform_client):
    _, token = make_test_user_and_token(platform_app)
    r = platform_client.post(
        "/api/pay/orders",
        json={"membership_type": "month"},
        headers={"Authorization": f"Bearer {token}"},
    )
    out_no = r.get_json()["out_trade_no"]
    amount = r.get_json()["total_amount"]
    body = {
        "trade_status": "TRADE_SUCCESS",
        "out_trade_no": out_no,
        "trade_no": "2026032122001156789012345678",
        "total_amount": amount,
    }
    assert platform_client.post("/api/pay/alipay/notify", data=body).status_code == 200
    assert platform_client.post("/api/pay/alipay/notify", data=body).status_code == 200

    from app.models import MembershipRecord

    with platform_app.app_context():
        n = MembershipRecord.query.filter_by(order_id=out_no).count()
        assert n == 1


def test_alipay_notify_amount_mismatch(platform_app, platform_client):
    _, token = make_test_user_and_token(platform_app)
    r = platform_client.post(
        "/api/pay/orders",
        json={"membership_type": "month"},
        headers={"Authorization": f"Bearer {token}"},
    )
    out_no = r.get_json()["out_trade_no"]

    nr = platform_client.post(
        "/api/pay/alipay/notify",
        data={
            "trade_status": "TRADE_SUCCESS",
            "out_trade_no": out_no,
            "trade_no": "x",
            "total_amount": "0.01",
        },
    )
    assert nr.data.decode("utf-8").strip().lower() == "fail"
