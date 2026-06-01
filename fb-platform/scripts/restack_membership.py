#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按购买顺序重算 membership_records 的 effective_at / expires_at（顺延含待生效记录）。

用法（在 fb-platform 目录）:
  python3 scripts/restack_membership.py              # 全部用户
  python3 scripts/restack_membership.py --user-id 58 # 指定用户
"""
from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="重算会员记录顺延时间")
    parser.add_argument("--user-id", type=int, help="仅处理该 user_id")
    args = parser.parse_args()

    from app import create_app, db
    from app.membership import restack_membership_records_for_user
    from app.models import MembershipRecord

    app = create_app()
    with app.app_context():
        if args.user_id is not None:
            user_ids = [args.user_id]
        else:
            rows = db.session.query(MembershipRecord.user_id).distinct().all()
            user_ids = sorted({r[0] for r in rows})
        total = 0
        for uid in user_ids:
            n = restack_membership_records_for_user(uid)
            if n:
                print(f"user_id={uid} updated {n} record(s)")
                total += n
        print(f"done, {total} record(s) updated across {len(user_ids)} user(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
