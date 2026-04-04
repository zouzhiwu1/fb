# -*- coding: utf-8 -*-
"""
微信支付结果通知：V2 统一下单/支付结果通知常用 XML + MD5 签名（与商户平台 API 密钥）。
文档：https://pay.weixin.qq.com/wiki/doc/api/native.php?chapter=4_2
"""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from typing import Any


def xml_body_to_dict(xml_text: str) -> dict[str, str]:
    """解析支付结果通知 XML 为扁平 dict（子节点文本）。"""
    root = ET.fromstring(xml_text.strip())
    out: dict[str, str] = {}
    for child in root:
        out[child.tag] = (child.text or "").strip()
    return out


def build_v2_sign_string(params: dict[str, Any]) -> str:
    """待签名字符串：非空参数按 key ASCII 排序，k=v 用 & 连接（不含 sign）。"""
    parts: list[str] = []
    for key in sorted(params.keys()):
        if key == "sign":
            continue
        val = params[key]
        if val is None or val == "":
            continue
        parts.append(f"{key}={val}")
    return "&".join(parts)


def sign_v2_md5(params: dict[str, Any], api_key: str) -> str:
    """MD5 签名，大写 hex。"""
    astr = build_v2_sign_string(params) + f"&key={api_key}"
    return hashlib.md5(astr.encode("utf-8")).hexdigest().upper()


def verify_v2_sign(params: dict[str, Any], api_key: str) -> bool:
    """校验通知中的 sign 与本地重算是否一致。"""
    if not api_key:
        return False
    want = (params.get("sign") or "").upper()
    if not want:
        return False
    got = sign_v2_md5(params, api_key)
    return want == got
