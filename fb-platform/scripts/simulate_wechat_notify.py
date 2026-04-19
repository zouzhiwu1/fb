#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟微信支付结果通知 POST（WECHAT_PAY_MODE=mock 联调）。

默认发 JSON（与 curl 一致）；生产环境 V2 多为 XML，本服务亦支持。
WECHAT_PAY_MODE=v3 时真实回调为微信签名的加密 JSON，本脚本无法模拟；请用 mock 联调或 tests/test_wechat_pay_v3.py。

用法：
  python3 scripts/simulate_wechat_notify.py \\
    --base-url http://127.0.0.1:5001 \\
    --out-trade-no FB... \\
    --total-amount 29.90

或使用微信规范的「分」：
  --total-fee 2990

环境变量 WECHAT_NOTIFY_URL 可覆盖完整回调 URL。
"""
from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urljoin

import requests


def main() -> int:
    p = argparse.ArgumentParser(description="模拟微信支付 notify POST")
    p.add_argument("--base-url", default=os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:5001"))
    p.add_argument("--out-trade-no", required=True)
    p.add_argument("--transaction-id", default="4200000000202603210000123456")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--total-amount", help="元，两位小数，与订单一致（mock 便捷）")
    group.add_argument("--total-fee", help="分，整数字符串（微信 V2 规范）")
    p.add_argument("--mock-secret", default=os.environ.get("WECHAT_MOCK_SECRET", ""))
    p.add_argument("--xml", action="store_true", help="以 XML 发送（更接近生产）")
    args = p.parse_args()

    notify = os.environ.get("WECHAT_NOTIFY_URL")
    if not notify:
        notify = urljoin(args.base_url.rstrip("/") + "/", "api/pay/wechat/notify")

    if args.xml:
        if args.total_amount:
            # 元转分
            from decimal import Decimal

            fen = int((Decimal(args.total_amount) * 100).quantize(Decimal("1")))
            fee_str = str(fen)
        else:
            fee_str = str(args.total_fee)
        body = f"""<xml>
<return_code><![CDATA[SUCCESS]]></return_code>
<result_code><![CDATA[SUCCESS]]></result_code>
<out_trade_no><![CDATA[{args.out_trade_no}]]></out_trade_no>
<transaction_id><![CDATA[{args.transaction_id}]]></transaction_id>
<total_fee><![CDATA[{fee_str}]]></total_fee>
</xml>"""
        headers = {"Content-Type": "application/xml; charset=utf-8"}
        if args.mock_secret:
            headers["X-Wechat-Mock-Secret"] = args.mock_secret
        r = requests.post(notify, data=body.encode("utf-8"), headers=headers, timeout=30)
    else:
        payload = {
            "return_code": "SUCCESS",
            "result_code": "SUCCESS",
            "out_trade_no": args.out_trade_no,
            "transaction_id": args.transaction_id,
        }
        if args.total_amount:
            payload["total_amount"] = args.total_amount
        else:
            payload["total_fee"] = str(args.total_fee)
        headers = {"Content-Type": "application/json"}
        if args.mock_secret:
            headers["X-Wechat-Mock-Secret"] = args.mock_secret
        r = requests.post(notify, json=payload, headers=headers, timeout=30)

    print("POST", notify)
    print("status", r.status_code)
    print("body", r.text[:500])
    if r.status_code != 200:
        return 1
    compact = r.text.replace("\n", "").replace(" ", "")
    if "<![CDATA[SUCCESS]]></return_code>" in compact or "<return_code>SUCCESS</return_code>" in compact.lower():
        return 0
    try:
        j = r.json()
        if isinstance(j, dict) and str(j.get("code", "")).upper() == "SUCCESS":
            return 0
    except Exception:
        pass
    return 1


if __name__ == "__main__":
    sys.exit(main())
