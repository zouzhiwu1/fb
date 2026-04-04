# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import pytest

from app.models import MembershipRecord
from app.payment_fulfillment import FulfillOutcome, FulfillResult, VerifiedPayment
from app.payment_providers.wechat import handle_wechat_notify
from tests.conftest import make_test_user_and_token


@pytest.fixture(autouse=True)
def _wechat_mock_mode():
    import app.payment_providers.wechat as wechat_mod

    with patch.object(wechat_mod, "WECHAT_PAY_MODE", "mock"), patch.object(
        wechat_mod, "WECHAT_MOCK_SECRET", ""
    ):
        yield


def test_create_order_includes_wechat_notify_url(platform_app, platform_client):
    _, token = make_test_user_and_token(platform_app)
    r = platform_client.post(
        "/api/pay/orders",
        json={"membership_type": "month"},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = r.get_json()
    assert data.get("wechat_notify_url", "").endswith("/api/pay/wechat/notify")
    assert "wechat" in data


def test_wechat_notify_mock_paid_then_member(platform_app, platform_client):
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
        "/api/pay/wechat/notify",
        json={
            "return_code": "SUCCESS",
            "result_code": "SUCCESS",
            "out_trade_no": out_no,
            "transaction_id": "4200000000123456789",
            "total_amount": amount,
        },
    )
    assert nr.status_code == 200
    assert b"SUCCESS" in nr.data
    assert b"return_code" in nr.data

    with platform_app.app_context():
        o = PaymentOrder.query.filter_by(out_trade_no=out_no).one()
        assert o.status == "paid"
        m = MembershipRecord.query.filter_by(order_id=out_no).one()
        assert m.membership_type == "week"


def test_wechat_notify_xml_total_fee(platform_app, platform_client):
    """生产形态：XML + total_fee（分）。"""
    _, token = make_test_user_and_token(platform_app)
    r = platform_client.post(
        "/api/pay/orders",
        json={"membership_type": "month"},
        headers={"Authorization": f"Bearer {token}"},
    )
    out_no = r.get_json()["out_trade_no"]
    # 29.90 -> 2990 分
    xml = f"""<xml>
<return_code><![CDATA[SUCCESS]]></return_code>
<result_code><![CDATA[SUCCESS]]></result_code>
<out_trade_no><![CDATA[{out_no}]]></out_trade_no>
<transaction_id><![CDATA[wx-txn-1]]></transaction_id>
<total_fee><![CDATA[2990]]></total_fee>
</xml>"""
    nr = platform_client.post(
        "/api/pay/wechat/notify",
        data=xml,
        content_type="application/xml",
    )
    assert nr.status_code == 200
    assert b"SUCCESS" in nr.data

    with platform_app.app_context():
        from app.models import PaymentOrder

        o = PaymentOrder.query.filter_by(out_trade_no=out_no).one()
        assert o.status == "paid"


def test_handle_wechat_notify_uses_injected_fulfillment():
    req = MagicMock()
    req.content_type = "application/json"
    req.get_json.return_value = {
        "return_code": "SUCCESS",
        "result_code": "SUCCESS",
        "out_trade_no": "FB_WX",
        "transaction_id": "T1",
        "total_amount": "9.90",
    }
    req.get_data.return_value = ""

    mock_ff = MagicMock()
    mock_ff.fulfill.return_value = FulfillOutcome(FulfillResult.OK_FULFILLED)

    import app.payment_providers.wechat as wechat_mod

    with (
        patch.object(wechat_mod, "WECHAT_PAY_MODE", "mock"),
        patch.object(wechat_mod, "WECHAT_MOCK_SECRET", ""),
    ):
        resp, st = handle_wechat_notify(req, fulfillment=mock_ff)

    assert st == 200
    mock_ff.fulfill.assert_called_once()
    arg = mock_ff.fulfill.call_args[0][0]
    assert isinstance(arg, VerifiedPayment)
    assert arg.merchant_order_id == "FB_WX"
    assert arg.paid_amount == "9.90"
