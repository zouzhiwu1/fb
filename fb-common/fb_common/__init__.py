# -*- coding: utf-8 -*-
"""Shared utilities for fb Python services."""

from fb_common.env import load_dotenv_stack
from fb_common.mysql import (
    MYSQL_USER_PLACEHOLDERS,
    ensure_mysql_user_not_placeholder,
    get_sqlalchemy_engine_options,
    pymysql_connect_from_url,
)
from fb_common.password_policy import (
    MIN_PASSWORD_LEN,
    PASSWORD_POLICY_HINT,
    validate_password_strength,
)

__all__ = [
    "MIN_PASSWORD_LEN",
    "MYSQL_USER_PLACEHOLDERS",
    "PASSWORD_POLICY_HINT",
    "ensure_mysql_user_not_placeholder",
    "get_sqlalchemy_engine_options",
    "load_dotenv_stack",
    "pymysql_connect_from_url",
    "validate_password_strength",
]
