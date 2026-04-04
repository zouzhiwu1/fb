# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

from app.payment_fulfillment import FulfillOutcome, FulfillResult, VerifiedPayment
from app.payment_providers.alipay import handle_alipay_notify


def test_handle_alipay_notify_uses_injected_fulfillment():
    """支付宝适配器应调用注入的 fulfillment，便于单测与扩展其他渠道。"""
    req = MagicMock()
    req.is_json = False
    req.form.to_dict.return_value = {
        "trade_status": "TRADE_SUCCESS",
        "out_trade_no": "FB_TEST_ORDER",
        "trade_no": "ALI123",
        "total_amount": "1.00",
    }
    req.headers = {}

    mock_ff = MagicMock()
    mock_ff.fulfill.return_value = FulfillOutcome(FulfillResult.OK_FULFILLED)

    import app.payment_providers.alipay as alipay_mod

    with (
        patch.object(alipay_mod, "ALIPAY_MODE", "mock"),
        patch.object(alipay_mod, "ALIPAY_MOCK_SECRET", ""),
    ):
        body, status, _ = handle_alipay_notify(req, fulfillment=mock_ff)

    assert status == 200
    assert body == "success"
    mock_ff.fulfill.assert_called_once()
    arg = mock_ff.fulfill.call_args[0][0]
    assert isinstance(arg, VerifiedPayment)
    assert arg.merchant_order_id == "FB_TEST_ORDER"
    assert arg.provider_trade_id == "ALI123"
    assert arg.paid_amount == "1.00"
