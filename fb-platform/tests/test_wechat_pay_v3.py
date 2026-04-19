# -*- coding: utf-8 -*-
import base64
import json
import secrets
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import app.wechat_pay_v3 as wechat_pay_v3_mod

import pytest
from flask import Request
from werkzeug.test import EnvironBuilder
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.payment_fulfillment import FulfillOutcome, FulfillResult, VerifiedPayment
from app.wechat_pay_v3 import (
    build_authorization,
    build_miniprogram_request_payment_params_v3,
    decrypt_notify_resource,
    jsapi_prepay,
    load_private_key_from_pem,
    verify_wechatpay_signature,
)
def _rsa_pair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key()
    pem_priv = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pem_pub = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return priv, pub, pem_priv, pem_pub


def test_verify_wechatpay_signature_roundtrip():
    priv, pub, _, _ = _rsa_pair()
    body = '{"prepay_id":"wx"}'
    ts = "1600000000"
    nonce = secrets.token_hex(8)
    message = f"{ts}\n{nonce}\n{body}\n"
    sig_b64 = base64.b64encode(
        priv.sign(
            message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    ).decode("ascii")
    assert verify_wechatpay_signature(
        body=body,
        timestamp=ts,
        nonce=nonce,
        signature_b64=sig_b64,
        public_key=pub,
    )


def test_build_authorization_header_shape():
    priv, _, pem_priv, _ = _rsa_pair()
    pk = load_private_key_from_pem(pem_priv)
    auth = build_authorization(
        mchid="1900000001",
        cert_serial_no="7ABDE424BDABC5555",
        private_key=pk,
        method="POST",
        url_path="/v3/pay/transactions/jsapi",
        body="{}",
    )
    assert auth.startswith("WECHATPAY2-SHA256-RSA2048 ")
    assert "mchid=" in auth and "serial_no=" in auth and "signature=" in auth


def test_decrypt_notify_resource_roundtrip():
    key32 = "0123456789abcdef0123456789abcdef"
    payload = {"trade_state": "SUCCESS", "out_trade_no": "WX1", "amount": {"total": 100}}
    plain = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    aes = AESGCM(key32.encode("utf-8"))
    nonce_str = "abcdefghijkl"
    iv = nonce_str.encode("utf-8")
    ct = aes.encrypt(iv, plain, b"transaction")
    b64 = base64.b64encode(ct).decode("ascii")
    dec = decrypt_notify_resource(
        api_v3_key=key32,
        associated_data="transaction",
        nonce=nonce_str,
        ciphertext_b64=b64,
    )
    assert dec["out_trade_no"] == "WX1"
    assert dec["amount"]["total"] == 100


def test_jsapi_prepay_success_with_mock_http():
    """Mock 微信 HTTP 应答并验签（平台私钥在测中扮演微信）。"""
    mch_priv, _, _, _ = _rsa_pair()
    plat_priv, plat_pub, _, _ = _rsa_pair()
    resp_body = '{"prepay_id":"wxgoodprepayid"}'
    ts = "1700000000"
    nonce = "mocknonce1234567890"
    sign_msg = f"{ts}\n{nonce}\n{resp_body}\n"
    sig_b64 = base64.b64encode(
        plat_priv.sign(
            sign_msg.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    ).decode("ascii")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = resp_body
    mock_resp.headers = {
        "Wechatpay-Timestamp": ts,
        "Wechatpay-Nonce": nonce,
        "Wechatpay-Signature": sig_b64,
    }
    with patch.object(wechat_pay_v3_mod.requests, "post", return_value=mock_resp):
        prepay_id, err = jsapi_prepay(
            app_id="wxappidtest0000001",
            mch_id="1900000001",
            mch_cert_serial="7ABDE424BDABC5555",
            merchant_private_key=mch_priv,
            platform_public_key=plat_pub,
            platform_public_key_id="PUB_KEY_ID_TEST",
            openid="oUpF8uMuAJO_M2pxb1Q9zNjWeS6o",
            out_trade_no="W1234567890123456789012345678",
            description="会员",
            notify_url="https://example.com/api/pay/wechat/notify",
            total_fen=100,
            client_ip="127.0.0.1",
        )
    assert err is None
    assert prepay_id == "wxgoodprepayid"


def test_miniprogram_pay_sign_v3_verify_with_public():
    priv, pub, pem_priv, _ = _rsa_pair()
    pk = load_private_key_from_pem(pem_priv)
    d = build_miniprogram_request_payment_params_v3(
        app_id="wxtestapp",
        prepay_id="prepay_abc",
        private_key=pk,
    )
    assert d["signType"] == "RSA"
    assert d["package"] == "prepay_id=prepay_abc"
    msg = (
        f"wxtestapp\n{d['timeStamp']}\n{d['nonceStr']}\n{d['package']}\n"
    ).encode("utf-8")
    sig = base64.b64decode(d["paySign"])
    pub.verify(sig, msg, padding.PKCS1v15(), hashes.SHA256())


@pytest.fixture
def _v3_notify_patches():
    import app.payment_providers.wechat as wechat_mod

    plat_priv, plat_pub, _, plat_pub_pem = _rsa_pair()
    api_v3_key = "0123456789abcdef0123456789abcdef"
    with (
        patch.object(wechat_mod, "WECHAT_PAY_MODE", "v3"),
        patch.object(wechat_mod, "WECHAT_API_V3_KEY", api_v3_key),
        patch.object(wechat_mod, "WECHAT_PLATFORM_PUBLIC_KEY_PEM", plat_pub_pem),
    ):
        yield plat_priv, plat_pub, api_v3_key


def test_wechat_v3_notify_verify_decrypt_and_fulfill(_v3_notify_patches):
    """不依赖 MySQL 迁移：直接走 handle_wechat_notify + 注入履约。"""
    plat_priv, _, api_v3_key = _v3_notify_patches

    out_no = "W123TESTORDER00000001"
    fen = int((Decimal("29.90") * 100).quantize(Decimal("1")))
    trade = {
        "trade_state": "SUCCESS",
        "out_trade_no": out_no,
        "transaction_id": "4200000000V3TEST01",
        "amount": {"total": int(fen)},
    }
    plain = json.dumps(trade, separators=(",", ":")).encode("utf-8")
    aes = AESGCM(api_v3_key.encode("utf-8"))
    nonce_r = "123456789012"
    ct = aes.encrypt(nonce_r.encode("utf-8"), plain, b"transaction")
    outer = {
        "id": "evt-1",
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "algorithm": "AEAD_AES_256_GCM",
            "ciphertext": base64.b64encode(ct).decode("ascii"),
            "associated_data": "transaction",
            "nonce": nonce_r,
        },
    }
    body = json.dumps(outer, separators=(",", ":"), ensure_ascii=False)
    ts = str(int(time.time()))
    nonce = secrets.token_hex(16)
    sign_msg = f"{ts}\n{nonce}\n{body}\n"
    sig_b64 = base64.b64encode(
        plat_priv.sign(
            sign_msg.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    ).decode("ascii")

    builder = EnvironBuilder(
        method="POST",
        data=body.encode("utf-8"),
        content_type="application/json; charset=utf-8",
        headers={
            "Wechatpay-Timestamp": ts,
            "Wechatpay-Nonce": nonce,
            "Wechatpay-Signature": sig_b64,
            "Wechatpay-Serial": "PUB_KEY_ID_TEST",
        },
    )
    req = Request(builder.get_environ())

    mock_ff = MagicMock()
    mock_ff.fulfill.return_value = FulfillOutcome(FulfillResult.OK_FULFILLED)

    import app.payment_providers.wechat as wechat_mod

    resp, st = wechat_mod.handle_wechat_notify(req, fulfillment=mock_ff)
    assert st == 200
    assert resp.get_json().get("code") == "SUCCESS"
    mock_ff.fulfill.assert_called_once()
    arg = mock_ff.fulfill.call_args[0][0]
    assert isinstance(arg, VerifiedPayment)
    assert arg.merchant_order_id == out_no
    assert arg.paid_amount == "29.90"
    assert arg.provider_trade_id == "4200000000V3TEST01"
