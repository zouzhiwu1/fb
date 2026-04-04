# -*- coding: utf-8 -*-
"""注册与修改密码共用的强度规则（platform、partner 后端应调用）。"""
from __future__ import annotations

import re

MIN_PASSWORD_LEN = 8

PASSWORD_POLICY_HINT = (
    f"密码至少 {MIN_PASSWORD_LEN} 位，须同时含英文字母、数字和符号（如 ! # $ - _ 等），不能含空格"
)

_LETTER = re.compile(r"[A-Za-z]")
_DIGIT = re.compile(r"\d")
_SPECIAL = re.compile(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/\\~`\'"]')
_SPACE = re.compile(r"\s")


def validate_password_strength(password: str | None) -> tuple[bool, str]:
    """
    合法返回 (True, "")；否则 (False, 面向用户的说明)。
    部署用环境变量密码（如 PARTNER_ROOT_PASSWORD）不在此校验。
    """
    if password is None or not str(password).strip():
        return False, "请输入密码"
    p = str(password).strip()
    if _SPACE.search(p):
        return False, "密码不能包含空格"
    if len(p) < MIN_PASSWORD_LEN:
        return False, f"密码至少 {MIN_PASSWORD_LEN} 位"
    if not _LETTER.search(p):
        return False, "密码须包含至少一个英文字母"
    if not _DIGIT.search(p):
        return False, "密码须包含至少一个数字"
    if not _SPECIAL.search(p):
        return False, "密码须包含至少一个符号（如 ! # $ - _ 等）"
    return True, ""
