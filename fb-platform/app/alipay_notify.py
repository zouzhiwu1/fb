# -*- coding: utf-8 -*-
"""
支付宝异步通知验签（RSA2 / SHA256）。
文档：https://opendocs.alipay.com/common/02mse9
"""
import base64
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def build_alipay_sign_content(params: dict[str, Any]) -> str:
    """待验签串：除 sign、sign_type 外，按键名 ASCII 升序，& 连接 k=v，空值不参与。"""
    parts: list[str] = []
    for key in sorted(params.keys()):
        if key in ("sign", "sign_type"):
            continue
        val = params[key]
        if val is None or val == "":
            continue
        parts.append(f"{key}={val}")
    return "&".join(parts)


def verify_alipay_rsa256(sign_content: str, sign_b64: str, alipay_public_key_pem: str) -> bool:
    """
    使用支付宝公钥验证 RSA2 签名。public_key_pem 为 PEM 格式（含 BEGIN/END）。
    """
    if not alipay_public_key_pem or not sign_b64:
        return False
    pem = alipay_public_key_pem.strip()
    if not pem.startswith("-----"):
        # 兼容仅一行 Base64 的公钥：包装为 PEM
        pem = (
            "-----BEGIN PUBLIC KEY-----\n"
            + "\n".join(pem[i : i + 64] for i in range(0, len(pem), 64))
            + "\n-----END PUBLIC KEY-----"
        )
    try:
        pub = serialization.load_pem_public_key(pem.encode("utf-8"), backend=default_backend())
        sig = base64.b64decode(sign_b64)
        pub.verify(
            sig,
            sign_content.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


def verify_notify_params(
    params: dict[str, Any],
    *,
    alipay_public_key_pem: str | None,
    sign_type: str | None = None,
) -> bool:
    """验签；sign_type 须为 RSA2（生产环境）。"""
    sign = params.get("sign")
    st = (sign_type or params.get("sign_type") or "").upper()
    if not sign:
        return False
    if st and st != "RSA2":
        return False
    content = build_alipay_sign_content(params)
    if not alipay_public_key_pem:
        return False
    return verify_alipay_rsa256(content, str(sign), alipay_public_key_pem)
