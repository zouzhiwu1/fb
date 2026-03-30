# -*- coding: utf-8 -*-
"""中国大陆手机号、代理商登录名（邮箱）格式校验。"""
from __future__ import annotations

import re

# 中国大陆 11 位手机号，1 开头第二位 3–9
_CN_MOBILE_RE = re.compile(r"^1[3-9]\d{9}$")

def validate_cn_mobile(phone: str | None) -> tuple[bool, str]:
    p = (phone or "").strip()
    if not p:
        return False, "请输入电话号码"
    if not _CN_MOBILE_RE.match(p):
        return False, "请输入 11 位中国大陆手机号（1 开头）"
    return True, ""


def validate_agent_login_email(login_name: str | None) -> tuple[bool, str]:
    s = (login_name or "").strip()
    if not s:
        return False, "请输入登录名（邮箱）"
    if len(s) > 128:
        return False, "登录名过长（最多 128 字符）"
    if any(c.isspace() for c in s):
        return False, "登录名不能包含空格"
    if s.count("@") != 1:
        return False, "登录名须为有效邮箱地址"
    local, _, domain = s.partition("@")
    if not local or not domain or "." not in domain:
        return False, "登录名须为有效邮箱地址"
    if len(local) > 64 or len(domain) > 63:
        return False, "登录名须为有效邮箱地址"
    # 本地与域名：字母数字及常见邮箱符号，无中文
    token = re.compile(r"^[a-zA-Z0-9._%+\-]+$")
    dom_lab = domain.split(".")
    if not all(token.match(p) and p for p in dom_lab):
        return False, "登录名须为有效邮箱地址"
    if not token.match(local):
        return False, "登录名须为有效邮箱地址"
    return True, ""


def normalize_email(login_name: str | None) -> str:
    return (login_name or "").strip().lower()


def validate_payout_channel(channel: str | None) -> tuple[bool, str]:
    c = (channel or "").strip().lower()
    if c not in ("alipay", "wechat"):
        return False, "请选择支付渠道：支付宝或微信"
    return True, ""


def validate_payout_account(account: str | None) -> tuple[bool, str]:
    a = (account or "").strip()
    if not a:
        return False, "请输入支付账号"
    if len(a) > 256:
        return False, "支付账号过长（最多 256 字符）"
    return True, ""


def validate_payout_holder_name(name: str | None) -> tuple[bool, str]:
    n = (name or "").strip()
    if not n:
        return False, "请填写收款真实姓名"
    if len(n) > 64:
        return False, "收款真实姓名过长（最多 64 字符）"
    return True, ""
