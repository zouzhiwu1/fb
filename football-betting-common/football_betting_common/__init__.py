# -*- coding: utf-8 -*-
"""Shared utilities for football-betting Python services."""

from football_betting_common.env import load_dotenv_stack
from football_betting_common.mysql import (
    MYSQL_USER_PLACEHOLDERS,
    ensure_mysql_user_not_placeholder,
    get_sqlalchemy_engine_options,
    pymysql_connect_from_url,
)

__all__ = [
    "MYSQL_USER_PLACEHOLDERS",
    "ensure_mysql_user_not_placeholder",
    "get_sqlalchemy_engine_options",
    "load_dotenv_stack",
    "pymysql_connect_from_url",
]
