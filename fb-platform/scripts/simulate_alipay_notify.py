#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟支付宝向本服务 POST 异步通知（用于 ALIPAY_MODE=mock 联调）。

用法示例：
  1) 启动平台后，用登录 token 创建订单：
     curl -s -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \\
       -d '{"membership_type":"month"}' http://127.0.0.1:5000/api/pay/orders
  2) 用返回的 out_trade_no、total_amount 执行本脚本：
     python scripts/simulate_alipay_notify.py \\
       --base-url http://127.0.0.1:5000 \\
       --out-trade-no FB... \\
       --total-amount 29.90 \\
       --mock-secret <与 .env 中 ALIPAY_MOCK_SECRET 一致，若未配置则可省略>

环境变量（可选）：
  ALIPAY_NOTIFY_URL  覆盖完整回调 URL
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from urllib.parse import urljoin

import requests


def main() -> int:
    p = argparse.ArgumentParser(description="模拟支付宝异步通知 POST")
    p.add_argument("--base-url", default=os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:5000"))
    p.add_argument("--out-trade-no", required=True)
    p.add_argument("--total-amount", required=True, help="须与订单金额一致，如 29.90")
    p.add_argument("--mock-secret", default=os.environ.get("ALIPAY_MOCK_SECRET", ""))
    p.add_argument("--subject", default="模拟-月会员")
    args = p.parse_args()

    notify = os.environ.get("ALIPAY_NOTIFY_URL")
    if not notify:
        notify = urljoin(args.base_url.rstrip("/") + "/", "api/pay/alipay/notify")

    # 贴近支付宝异步通知常见字段（mock 模式下仅验可选 header + 业务字段）
    form = {
        "notify_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "notify_type": "trade_status_sync",
        "notify_id": "mock-notify-id",
        "charset": "utf-8",
        "version": "1.0",
        "sign_type": "RSA2",
        "sign": "MOCK_NO_SIGN",
        "app_id": os.environ.get("ALIPAY_APP_ID", "mock_app_id"),
        "trade_no": f"2026{args.out_trade_no[-12:]}".ljust(28, "0")[:28],
        "out_trade_no": args.out_trade_no,
        "trade_status": "TRADE_SUCCESS",
        "total_amount": args.total_amount,
        "receipt_amount": args.total_amount,
        "buyer_pay_amount": args.total_amount,
        "subject": args.subject,
    }

    headers = {}
    if args.mock_secret:
        headers["X-Alipay-Mock-Secret"] = args.mock_secret

    r = requests.post(notify, data=form, headers=headers, timeout=30)
    print("POST", notify)
    print("status", r.status_code)
    print("body", repr(r.text))
    if r.status_code != 200 or (r.text or "").strip().lower() != "success":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
