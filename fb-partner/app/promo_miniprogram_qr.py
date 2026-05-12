# -*- coding: utf-8 -*-
"""
代理商推广用微信小程序码：管理员「提交开户」时生成并写入
`fb-agent-qrcode/{agent_id}.png`（相对 monorepo 根目录 fb/），
代理商推广页与管理员查看页只读该文件，避免每次打开页面调微信。
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path

import requests

import config as _cfg

_FB_PARTNER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# fb-partner 的上级目录即 monorepo 根（文件夹名一般为 fb）
_FB_MONOREPO_ROOT = os.path.abspath(os.path.join(_FB_PARTNER_DIR, ".."))


def agent_promo_qr_storage_dir() -> str:
    raw = (_cfg.PARTNER_AGENT_QR_STORAGE_DIR or "").strip()
    if raw:
        return os.path.abspath(raw)
    return os.path.join(_FB_MONOREPO_ROOT, "fb-agent-qrcode")


def agent_promo_miniprogram_png_path(agent_id: int) -> str:
    return os.path.join(agent_promo_qr_storage_dir(), f"{int(agent_id)}.png")


def mp_promo_env_configured() -> bool:
    return bool(
        (_cfg.PARTNER_PROMO_MP_APP_ID or "").strip()
        and (_cfg.PARTNER_PROMO_MP_APP_SECRET or "").strip()
        and (_cfg.PARTNER_PROMO_MP_ENTRY_PAGE or "").strip()
    )


def _fetch_access_token_fresh() -> str:
    """每次向微信拉新 token，不落进程内缓存，减轻 40001（非最新 token）。"""
    app_id = (_cfg.PARTNER_PROMO_MP_APP_ID or "").strip()
    app_secret = (_cfg.PARTNER_PROMO_MP_APP_SECRET or "").strip()
    if not app_id or not app_secret:
        return ""
    try:
        r = requests.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": app_id,
                "secret": app_secret,
            },
            timeout=10,
        )
        data = r.json() if r.ok else {}
    except Exception:
        logging.exception("agent_promo_qr fetch wechat access_token failed")
        return ""
    tk = str((data or {}).get("access_token") or "").strip()
    if not tk:
        logging.warning("agent_promo_qr token err: %s", data)
        return ""
    return tk


def fetch_miniprogram_code_png_bytes(agent_id: int) -> bytes | None:
    entry_page = (_cfg.PARTNER_PROMO_MP_ENTRY_PAGE or "").strip()
    if not entry_page:
        return None
    access_token = _fetch_access_token_fresh()
    if not access_token:
        return None
    try:
        r = requests.post(
            "https://api.weixin.qq.com/wxa/getwxacodeunlimit",
            params={"access_token": access_token},
            json={
                "scene": f"agent_id={agent_id}",
                "page": entry_page,
                "check_path": False,
                "env_version": (_cfg.PARTNER_PROMO_MP_CODE_ENV_VERSION or "trial"),
                "width": int(_cfg.PARTNER_PROMO_MP_CODE_WIDTH or 430),
            },
            timeout=15,
        )
        body = r.content or b""
    except Exception:
        logging.exception(
            "agent_promo_qr getwxacodeunlimit request failed agent_id=%s", agent_id
        )
        return None
    if not body:
        return None
    ctype = (r.headers.get("Content-Type") or "").lower()
    is_json = "application/json" in ctype or body[:1] == b"{"
    if is_json:
        try:
            data = json.loads(body.decode("utf-8", errors="ignore"))
        except Exception:
            data = {"raw": body.decode("utf-8", errors="ignore")[:200]}
        logging.warning(
            "agent_promo_qr getwxacodeunlimit err agent_id=%s: %s", agent_id, data
        )
        return None
    return body


def save_agent_promo_miniprogram_qr(agent_id: int) -> bool:
    """
    拉取小程序码并写入 fb-agent-qrcode/{agent_id}.png。
    未配置 PARTNER_PROMO_MP_* 时跳过（返回 True，便于无小程序环境开发）。
    """
    if not mp_promo_env_configured():
        logging.info(
            "agent_promo_qr skip save agent_id=%s (PARTNER_PROMO_MP_* 未配全)",
            agent_id,
        )
        return True
    png = fetch_miniprogram_code_png_bytes(agent_id)
    if not png:
        return False
    d = agent_promo_qr_storage_dir()
    try:
        Path(d).mkdir(parents=True, exist_ok=True)
        path = agent_promo_miniprogram_png_path(agent_id)
        with open(path, "wb") as f:
            f.write(png)
        logging.info("agent_promo_qr saved agent_id=%s path=%s", agent_id, path)
    except Exception:
        logging.exception("agent_promo_qr write failed agent_id=%s", agent_id)
        return False
    return True


def load_agent_promo_miniprogram_qr_data_url(agent_id: int) -> str:
    """读取已保存的小程序码为 data URL；无文件返回空串。"""
    path = agent_promo_miniprogram_png_path(agent_id)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return ""
    except Exception:
        logging.exception(
            "agent_promo_qr read failed agent_id=%s path=%s", agent_id, path
        )
        return ""
    if not raw:
        return ""
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
