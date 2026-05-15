# -*- coding: utf-8 -*-
import json
from unittest.mock import patch

import pytest

from app.wechat_virtual_pay import (
    compact_json,
    virtual_payment_client_signatures,
    xpay_pay_sig,
)
from tests.conftest import make_test_user_and_token


@pytest.fixture(autouse=True)
def _virtual_pay_env():
    goods = {
        "week": {"productId": "test_week", "goodsPrice": 990},
        "month": {"productId": "test_month", "goodsPrice": 2990},
    }
    with patch("config.WECHAT_MP_APP_ID", "wx_test"), patch(
        "config.WECHAT_MP_APP_SECRET", "secret"
    ), patch("config.WECHAT_MP_VIRTUAL_OFFER_ID", "offer1"), patch(
        "config.WECHAT_MP_VIRTUAL_APP_KEY", "appkey_prod"
    ), patch("config.WECHAT_MP_VIRTUAL_APP_KEY_SANDBOX", ""), patch(
        "config.WECHAT_MP_VIRTUAL_ENV", 0
    ), patch("config.WECHAT_MP_VIRTUAL_GOODS", goods), patch(
        "app.pay_api.WECHAT_MP_APP_ID", "wx_test"
    ), patch("app.pay_api.WECHAT_MP_APP_SECRET", "secret"), patch(
        "app.pay_api.WECHAT_MP_VIRTUAL_OFFER_ID", "offer1"
    ), patch("app.pay_api.WECHAT_MP_VIRTUAL_APP_KEY", "appkey_prod"), patch(
        "app.pay_api.WECHAT_MP_VIRTUAL_APP_KEY_SANDBOX", ""
    ), patch("app.pay_api.WECHAT_MP_VIRTUAL_ENV", 0), patch(
        "app.pay_api.WECHAT_MP_VIRTUAL_GOODS", goods
    ):
        yield


def test_xpay_pay_sig_matches_wechat_doc_example():
    uri = "/xpay/query_user_balance"
    post_body = '{"openid": "xxx", "user_ip": "127.0.0.1", "env": 0}'
    appkey = "12345"
    assert (
        xpay_pay_sig(appkey, uri, post_body)
        == "c37809f27c6d7fd1837ad2500a04512b66b34fd793a39a385fade56dca89a4b5"
    )


def test_virtual_payment_client_signatures():
    sign_data = {
        "offerId": "123",
        "buyQuantity": 1,
        "env": 0,
        "currencyType": "CNY",
        "productId": "p1",
        "goodsPrice": 990,
        "outTradeNo": "V000001ABCDEF",
        "attach": "V000001ABCDEF",
    }
    s, pay_sig, sig = virtual_payment_client_signatures(
        "session_key_abc", "appkey", sign_data
    )
    assert s == compact_json(sign_data)
    assert len(pay_sig) == 64
    assert len(sig) == 64


def test_create_order_wechat_mp_virtual(platform_app, platform_client):
    _, token = make_test_user_and_token(platform_app)
    with patch(
        "app.pay_api.jscode2session",
        return_value={
            "openid": "o_test_openid",
            "session_key": "sk_test",
        },
    ):
        r = platform_client.post(
            "/api/pay/orders",
            json={
                "membership_type": "week",
                "payment_channel": "wechat_mp_virtual",
                "login_code": "lc123",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert data.get("payment_channel") == "wechat_mp_virtual"
    vp = data.get("virtual_pay") or {}
    assert vp.get("mode") == "short_series_goods"
    assert vp.get("paySig")
    assert vp.get("signature")
    sd = json.loads(vp["signData"])
    assert sd["productId"] == "test_week"
    assert sd["goodsPrice"] == 990
    assert data.get("wx_pay") is None


def test_wechat_virtual_confirm_fulfills(platform_app, platform_client):
    from app.models import PaymentOrder

    _, token = make_test_user_and_token(platform_app)
    with patch(
        "app.pay_api.jscode2session",
        return_value={
            "openid": "o_test_openid",
            "session_key": "sk_test",
        },
    ):
        cr = platform_client.post(
            "/api/pay/orders",
            json={
                "membership_type": "week",
                "payment_channel": "wechat_mp_virtual",
                "login_code": "lc1",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    out_no = cr.get_json()["out_trade_no"]

    with patch(
        "app.pay_api.jscode2session",
        return_value={"openid": "o_test_openid", "session_key": "sk2"},
    ), patch(
        "app.pay_api.fetch_cgi_access_token",
        return_value=("at_test", None),
    ), patch(
        "app.pay_api.xpay_query_order",
        return_value=(
            {
                "errcode": 0,
                "order": {
                    "status": 4,
                    "paid_fee": 990,
                    "wx_order_id": "wxoid1",
                },
            },
            None,
        ),
    ):
        r = platform_client.post(
            "/api/pay/wechat-virtual/confirm",
            json={"out_trade_no": out_no, "login_code": "lc2"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    assert r.get_json().get("ok") is True
    assert r.get_json().get("fulfilled") is True

    with platform_app.app_context():
        o = PaymentOrder.query.filter_by(out_trade_no=out_no).one()
        assert o.status == "paid"
