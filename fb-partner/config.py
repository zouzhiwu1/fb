# -*- coding: utf-8 -*-
"""代理商门户配置：与 fb-platform 共用 DATABASE_URL，JWT/SECRET 必须独立。"""
import datetime
import logging
import os
import re

from fb_common import (
    ensure_mysql_user_not_placeholder,
    get_sqlalchemy_engine_options as _get_sqlalchemy_engine_options,
    load_dotenv_stack,
)

_service_root = os.path.dirname(os.path.abspath(__file__))
load_dotenv_stack(_service_root)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+pymysql://root:123456@localhost:3306/fb",
)

ensure_mysql_user_not_placeholder(
    DATABASE_URL,
    error_message="请在 .env 中配置 DATABASE_URL（与 platform 可相同库 fb）。",
)


def get_sqlalchemy_engine_options():
    return _get_sqlalchemy_engine_options(DATABASE_URL)


# 须与 platform 的 JWT_SECRET_KEY 不同
PARTNER_JWT_SECRET_KEY = os.environ.get(
    "PARTNER_JWT_SECRET_KEY",
    "change-me-partner-only-min-32-bytes-long-key",
)
PARTNER_JWT_ALGORITHM = "HS256"
PARTNER_JWT_EXPIRE_HOURS = int(os.environ.get("PARTNER_JWT_EXPIRE_HOURS", "168"))

# 仅用于调用 /api/partner/auth/bootstrap-agent 创建首个代理商；不设则不开放该接口
PARTNER_BOOTSTRAP_KEY = os.environ.get("PARTNER_BOOTSTRAP_KEY", "").strip()

# 部署根账号：登录名固定为 root（不区分大小写），密码仅此一项；与库内管理员共用 /admin/login。
PARTNER_ROOT_PASSWORD = os.environ.get("PARTNER_ROOT_PASSWORD", "").strip()
PARTNER_ROOT_SESSION_VERSION = int(
    os.environ.get("PARTNER_ROOT_SESSION_VERSION", "1") or "1"
)

# 每名有效拉新折算的业绩（元），与文档 2.1 中 R_reg 一致；platform 入账积分流水时可另记 event_type。
PARTNER_YUAN_PER_VALID_REGISTRATION = float(
    os.environ.get("PARTNER_YUAN_PER_VALID_REGISTRATION", "100")
)
# 服务费：积分 × 系数（文档默认 1 积分 = 1 元）
PARTNER_COMMISSION_PER_POINT = float(
    os.environ.get("PARTNER_COMMISSION_PER_POINT", "1")
)
# 拉新服务费系数（用于 registration 明细行快照与金额计算）
PARTNER_REG_FACTOR = float(
    os.environ.get("PARTNER_REG_FACTOR", "1")
)
# 视为「注册奖励」类积分流水的 event_type（可逗号分隔）
PARTNER_LEDGER_EVENT_TYPES_REG = tuple(
    x.strip()
    for x in os.environ.get(
        "PARTNER_LEDGER_EVENT_TYPES_REG",
        "registration,register,reg_bonus,user_register",
    ).split(",")
    if x.strip()
)

def _expand_promo_template(template: str, agent_id: int, agent_code: str) -> str:
    if not template or not template.strip():
        return ""
    return (
        template.strip()
        .replace("{agent_id}", str(agent_id))
        .replace("{agent_code}", str(agent_code or ""))
    )


def _fix_android_apk_query_separator(url: str) -> str:
    """误把查询串写成「.apk 空格 key=」时改为「.apk?key=」。"""
    if not url:
        return url
    return re.sub(
        r"(\.(?:apk|APK))(\s+)([\w][\w.-]*=)",
        r"\1?\3",
        url.strip(),
        count=1,
    )


def partner_promo_bundle(agent_id: int, agent_code: str | None) -> dict:
    """
    代理商看板推广二维码所用链接与小程序 path/scene 提示。
    环境变量模板支持占位符 {agent_id}、{agent_code}。
    """
    code = agent_code or ""
    h5_base = os.environ.get("PARTNER_PROMO_H5_BASE", "").strip().rstrip("/")
    mp_tpl = os.environ.get("PARTNER_PROMO_MP_QR_TARGET", "").strip()
    web_tpl = os.environ.get("PARTNER_PROMO_WEB_URL", "").strip()
    android_tpl = os.environ.get("PARTNER_PROMO_ANDROID_URL", "").strip()
    ios_tpl = os.environ.get("PARTNER_PROMO_IOS_URL", "").strip()
    mp_entry = os.environ.get(
        "PARTNER_PROMO_MP_ENTRY_PAGE",
        "pages/register/register",
    ).strip()

    mp_url = _expand_promo_template(mp_tpl, agent_id, code)
    if not mp_url and h5_base:
        mp_url = f"{h5_base}/open-weapp?agent_id={agent_id}"

    android_url = _fix_android_apk_query_separator(
        _expand_promo_template(android_tpl, agent_id, code)
    )
    ios_url = _expand_promo_template(ios_tpl, agent_id, code)
    web_url = _expand_promo_template(web_tpl, agent_id, code)

    sep = "&" if "?" in mp_entry else "?"
    miniprogram_path = f"{mp_entry}{sep}agent_id={agent_id}"
    scene_suggestion = str(agent_id)
    if len(scene_suggestion) > 32:
        scene_suggestion = scene_suggestion[:32]

    channels = [
        {
            "id": "miniprogram",
            "title": "微信小程序",
            "hint": (
                "微信扫码打开 H5/中转页，再跳转小程序并带上代理商参数；"
                "或在公众平台用「小程序码」场景值绑定拉新。"
            ),
            "qr_url": mp_url,
            "configured": bool(mp_url),
            "wechat_scene": scene_suggestion,
            "miniprogram_path": miniprogram_path,
        },
        {
            "id": "web",
            "title": "WEB端",
            "hint": "扫码打开 H5/网页注册页；页面应从 URL 中读取 ref 或 agent_id 完成拉新归因。",
            "qr_url": web_url,
            "configured": bool(web_url),
        },
        {
            "id": "android",
            "title": "Android 客户端",
            "hint": "扫码下载安装包；客户端应读取 URL 中的 ref 或 agent_id 完成归因（与文档一致）。",
            "qr_url": android_url,
            "configured": bool(android_url),
        },
        {
            "id": "ios",
            "title": "iOS 客户端",
            "hint": "扫码跳转 App Store 或分发页；安装后由 App 解析 ref/agent_id。",
            "qr_url": ios_url,
            "configured": bool(ios_url),
        },
    ]
    return {
        "agent_id": agent_id,
        "agent_code": code,
        "channels": channels,
    }


# 浏览器访问路径前缀（反代子路径部署时必填，如 /partner）。勿尾斜杠。见 README。
def partner_application_prefix() -> str:
    raw = os.environ.get("PARTNER_APPLICATION_PREFIX", "").strip().rstrip("/")
    if not raw:
        return ""
    return raw if raw.startswith("/") else f"/{raw}"

_partner_root = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_partner_root)
LOG_DIR = os.environ.get(
    "LOG_DIR",
    os.path.join(_repo_root, "fb-log"),
)
LOG_FILE = os.environ.get("PARTNER_LOG_FILE", "").strip()


class DailyPartnerFileHandler(logging.FileHandler):
    def __init__(self, log_dir, encoding="utf-8"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self._current_date = datetime.date.today()
        path = self._path_for_date(self._current_date)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        super().__init__(path, encoding=encoding, delay=False)

    def _path_for_date(self, d: datetime.date) -> str:
        day = d.strftime("%Y%m%d")
        return os.path.join(self.log_dir, day, f"partner_{day}.log")

    def emit(self, record):
        today = datetime.date.today()
        if self._current_date != today:
            self.close()
            self.baseFilename = os.path.abspath(self._path_for_date(today))
            os.makedirs(os.path.dirname(self.baseFilename), exist_ok=True)
            self.stream = self._open()
            self._current_date = today
        super().emit(record)
