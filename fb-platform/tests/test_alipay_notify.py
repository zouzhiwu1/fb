# -*- coding: utf-8 -*-
from app.alipay_notify import build_alipay_sign_content


def test_build_alipay_sign_content_sorts_and_skips_sign():
    params = {
        "b": "2",
        "a": "1",
        "sign": "xxx",
        "sign_type": "RSA2",
        "empty": "",
    }
    s = build_alipay_sign_content(params)
    assert s == "a=1&b=2"
