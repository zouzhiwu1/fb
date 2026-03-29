#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读取项目根目录 .env 中的 DATABASE_URL，执行 init_full_stack.sql 初始化/重建库表。"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pymysql
from pymysql.constants import CLIENT


def _parse_database_url(url: str) -> dict:
    if not url or not url.strip():
        raise SystemExit("DATABASE_URL 为空，请在 football-betting-partner/.env 中配置。")
    u = url.strip()
    if u.startswith("mysql+pymysql://"):
        u = "mysql://" + u[len("mysql+pymysql://") :]
    parsed = urlparse(u)
    if parsed.scheme != "mysql":
        raise SystemExit(f"仅支持 MySQL 连接串，当前 scheme={parsed.scheme!r}")
    database = (parsed.path or "").lstrip("/").split("/")[0]
    if not database:
        raise SystemExit("DATABASE_URL 中未指定库名（路径部分）。")
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": database,
    }


def main() -> None:
    from config import DATABASE_URL

    kw = _parse_database_url(DATABASE_URL)
    sql_path = Path(__file__).with_name("init_full_stack.sql")
    if not sql_path.is_file():
        raise SystemExit(f"未找到 {sql_path}")

    sql = sql_path.read_text(encoding="utf-8")
    conn = pymysql.connect(
        charset="utf8mb4",
        client_flag=CLIENT.MULTI_STATEMENTS,
        **kw,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            while cur.nextset():
                pass
        conn.commit()
    finally:
        conn.close()

    print(
        f"已执行 {sql_path.name}，库 {kw['database']} @ {kw['host']}:{kw['port']} 表结构已就绪。"
    )
    print(
        "请重启 partner（及 platform）进程；在 .env 配置 PARTNER_ROOT_PASSWORD 后使用登录名 root "
        "进入根账号并添加库内管理员。"
    )


if __name__ == "__main__":
    main()
