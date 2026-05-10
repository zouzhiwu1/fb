# -*- coding: utf-8 -*-
import secrets
from decimal import Decimal
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


def test_wechat_notify_records_partner_recharge_points(platform_app, platform_client):
    """归因用户充值成功后写入 points_ledger（积分 = 金额 × current_rate）。"""
    from app import db
    from app.models import Agent, PointsLedger, User
    from werkzeug.security import generate_password_hash

    with platform_app.app_context():
        suf = secrets.token_hex(4)
        agent = Agent(
            agent_code=f"PT{suf}",
            login_name=f"pt_{suf}@example.com",
            password_hash="x",
            display_name="PT",
            current_rate=Decimal("0.0800"),
        )
        db.session.add(agent)
        db.session.commit()
        phone = f"137{secrets.randbelow(10**8):08d}"
        user = User(
            phone=phone,
            password_hash=generate_password_hash("TestPass1!"),
            agent_id=agent.id,
        )
        db.session.add(user)
        db.session.commit()
        from app.auth import _create_token

        token = _create_token(user.id, int(user.session_version or 1))
        expected_agent_id = int(agent.id)
        expected_user_id = int(user.id)

    r = platform_client.post(
        "/api/pay/orders",
        json={"membership_type": "week"},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = r.get_json()
    out_no = data["out_trade_no"]
    amount = data["total_amount"]

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

    with platform_app.app_context():
        row = PointsLedger.query.filter_by(
            order_id=out_no, event_type="recharge"
        ).one()
        assert row.agent_id == expected_agent_id
        assert row.user_id == expected_user_id
        expected = (Decimal(str(amount)) * Decimal("0.08")).quantize(Decimal("0.01"))
        assert Decimal(str(row.points_delta)) == expected


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
