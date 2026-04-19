# -*- coding: utf-8 -*-
"""
微信支付 API v3：小程序 JSAPI 下单、调起支付 RSA 签名、HTTP 应答/回调验签、通知 resource 解密。
文档：JSAPI/小程序下单 https://pay.weixin.qq.com/doc/v3/merchant/4012791855
"""
from __future__ import annotations

import base64
import json
import logging
import secrets
import time
from typing import Any

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

MCH_HOST = "https://api.mch.weixin.qq.com"
JSAPI_PREPAY_PATH = "/v3/pay/transactions/jsapi"


def _header(headers: Any, name: str) -> str | None:
    if not headers:
        return None
    lower = {str(k).lower(): v for k, v in dict(headers).items()}
    return lower.get(name.lower())


def load_private_key_from_pem(pem: str) -> Any:
    if not (pem or "").strip():
        raise ValueError("商户 API 证书私钥 PEM 为空")
    return serialization.load_pem_private_key(
        pem.strip().encode("utf-8"),
        password=None,
    )


def load_public_key_from_pem(pem: str) -> Any:
    if not (pem or "").strip():
        raise ValueError("微信支付平台公钥 PEM 为空")
    return serialization.load_pem_public_key(pem.strip().encode("utf-8"))


def build_authorization(
    *,
    mchid: str,
    cert_serial_no: str,
    private_key: Any,
    method: str,
    url_path: str,
    body: str,
) -> str:
    """构造请求头 Authorization: WECHATPAY2-SHA256-RSA2048 ..."""
    ts = str(int(time.time()))
    nonce = secrets.token_hex(16)
    message = f"{method.upper()}\n{url_path}\n{ts}\n{nonce}\n{body}\n"
    signature = private_key.sign(
        message.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    sig_b64 = base64.b64encode(signature).decode("ascii")
    parts = [
        f'mchid="{mchid}"',
        f'nonce_str="{nonce}"',
        f'timestamp="{ts}"',
        f'serial_no="{cert_serial_no}"',
        f'signature="{sig_b64}"',
    ]
    return "WECHATPAY2-SHA256-RSA2048 " + ",".join(parts)


def verify_wechatpay_signature(
    *,
    body: str,
    timestamp: str,
    nonce: str,
    signature_b64: str,
    public_key: Any,
) -> bool:
    """校验微信侧 RSA-SHA256 签名（应答或回调）。"""
    if not signature_b64:
        return False
    message = f"{timestamp}\n{nonce}\n{body}\n"
    try:
        sig = base64.b64decode(signature_b64)
        public_key.verify(
            sig,
            message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def decrypt_notify_resource(
    *,
    api_v3_key: str,
    associated_data: str,
    nonce: str,
    ciphertext_b64: str,
) -> dict[str, Any]:
    """
    解密支付通知 resource（AEAD_AES_256_GCM）。
    api_v3_key：商户平台「APIv3 密钥」，UTF-8 编码须为 32 字节。
    """
    key = api_v3_key.encode("utf-8")
    if len(key) != 32:
        raise ValueError("WECHAT_API_V3_KEY 须为 UTF-8 长度 32 字节（商户平台 APIv3 密钥）")
    raw = base64.b64decode(ciphertext_b64)
    aes = AESGCM(key)
    plain = aes.decrypt(nonce.encode("utf-8"), raw, associated_data.encode("utf-8"))
    return json.loads(plain.decode("utf-8"))


def build_miniprogram_request_payment_params_v3(
    *,
    app_id: str,
    prepay_id: str,
    private_key: Any,
) -> dict[str, str]:
    """
    小程序 wx.requestPayment 五元组（signType=RSA，paySign 为商户私钥签名）。
    签名串：appId\\ntimeStamp\\nnonceStr\\npackage\\n
    """
    time_stamp = str(int(time.time()))
    nonce_str = secrets.token_hex(16)
    package = f"prepay_id={prepay_id}"
    message = f"{app_id}\n{time_stamp}\n{nonce_str}\n{package}\n"
    signature = private_key.sign(
        message.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    pay_sign = base64.b64encode(signature).decode("ascii")
    return {
        "timeStamp": time_stamp,
        "nonceStr": nonce_str,
        "package": package,
        "signType": "RSA",
        "paySign": pay_sign,
    }


def _verify_response_signature(resp: requests.Response, public_key: Any) -> None:
    ts = _header(resp.headers, "Wechatpay-Timestamp") or ""
    nonce = _header(resp.headers, "Wechatpay-Nonce") or ""
    sig = _header(resp.headers, "Wechatpay-Signature") or ""
    body = resp.text or ""
    if not verify_wechatpay_signature(
        body=body, timestamp=ts, nonce=nonce, signature_b64=sig, public_key=public_key
    ):
        raise ValueError("微信支付应答验签失败")


def jsapi_prepay(
    *,
    app_id: str,
    mch_id: str,
    mch_cert_serial: str,
    merchant_private_key: Any,
    platform_public_key: Any,
    platform_public_key_id: str,
    openid: str,
    out_trade_no: str,
    description: str,
    notify_url: str,
    total_fen: int,
    client_ip: str | None = None,
    timeout_sec: int = 15,
) -> tuple[str | None, str | None]:
    """
    POST /v3/pay/transactions/jsapi，成功返回 (prepay_id, None)。
    """
    if len(out_trade_no) > 32:
        return None, "out_trade_no 超过微信 32 字节限制"
    if total_fen <= 0:
        return None, "订单金额无效"
    notify_url = (notify_url or "").strip()
    body_obj: dict[str, Any] = {
        "appid": app_id,
        "mchid": mch_id,
        "description": (description or "订单")[:127],
        "out_trade_no": out_trade_no,
        "notify_url": notify_url[:255],
        "amount": {"total": int(total_fen), "currency": "CNY"},
        "payer": {"openid": (openid or "")[:128]},
    }
    if client_ip and client_ip.strip():
        body_obj["scene_info"] = {
            "payer_client_ip": (client_ip.strip())[:45],
        }
    body = json.dumps(body_obj, separators=(",", ":"), ensure_ascii=False)
    auth = build_authorization(
        mchid=mch_id,
        cert_serial_no=mch_cert_serial,
        private_key=merchant_private_key,
        method="POST",
        url_path=JSAPI_PREPAY_PATH,
        body=body,
    )
    url = MCH_HOST + JSAPI_PREPAY_PATH
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": auth,
        "User-Agent": "fb-platform-wechatpay-v3",
    }
    if platform_public_key_id:
        headers["Wechatpay-Serial"] = platform_public_key_id
    try:
        resp = requests.post(
            url,
            data=body.encode("utf-8"),
            headers=headers,
            timeout=timeout_sec,
        )
    except requests.RequestException as e:
        logger.exception("wechat v3 jsapi prepay request failed: %s", e)
        return None, str(e)

    text = resp.text or ""
    if 200 <= resp.status_code < 300:
        try:
            _verify_response_signature(resp, platform_public_key)
        except ValueError as e:
            logger.warning("%s", e)
            return None, str(e)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None, "应答非 JSON"
        prepay_id = (data.get("prepay_id") or "").strip()
        if not prepay_id:
            return None, "无 prepay_id"
        return prepay_id, None

    try:
        err = json.loads(text)
        msg = err.get("message") or err.get("detail") or text
        code = err.get("code", "")
        return None, f"{code} {msg}".strip() if code else (msg or f"HTTP {resp.status_code}")
    except json.JSONDecodeError:
        return None, text[:500] or f"HTTP {resp.status_code}"
