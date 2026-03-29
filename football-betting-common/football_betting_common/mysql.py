# -*- coding: utf-8 -*-
from urllib.parse import urlparse, unquote

MYSQL_USER_PLACEHOLDERS = ("用户", "密码", "YOUR_MYSQL_USER", "YOUR_MYSQL_PASSWORD")


def ensure_mysql_user_not_placeholder(
    database_url: str,
    *,
    error_message: str,
) -> None:
    parsed = urlparse(database_url)
    db_user = unquote(parsed.username or "")
    if db_user in MYSQL_USER_PLACEHOLDERS:
        raise ValueError(error_message)


def pymysql_connect_from_url(database_url: str):
    """
    PyMySQL 默认用 latin-1 编码密码，中文等非 ASCII 会报错。
    将密码用 UTF-8 字节经 latin-1 还原，使线上握手为正确 UTF-8 密码。
    """
    import pymysql

    parsed = urlparse(database_url)
    password = unquote(parsed.password) if parsed.password else ""
    if password:
        password = password.encode("utf-8").decode("latin-1")
    return pymysql.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        user=unquote(parsed.username) if parsed.username else None,
        password=password,
        database=(parsed.path or "/").strip("/").split("/")[0] or None,
        charset="utf8mb4",
    )


def get_sqlalchemy_engine_options(database_url: str) -> dict:
    """非 sqlite 且走 PyMySQL 时返回 {creator}，否则 {}（如 sqlite 单测）。"""
    url = (database_url or "").strip()
    if url.lower().startswith("sqlite"):
        return {}

    def creator():
        return pymysql_connect_from_url(url)

    return {"creator": creator}
