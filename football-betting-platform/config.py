# -*- coding: utf-8 -*-
"""
平台配置。通过环境变量或 .env 配置。
"""
import datetime
import logging
import os
from urllib.parse import urlparse, unquote

try:
    from dotenv import load_dotenv

    _cfg_dir = os.path.dirname(os.path.abspath(__file__))
    _repo_root = os.path.dirname(_cfg_dir)
    # 仓库根目录 .env → 子项目 .env → 当前工作目录（后者仅补充未出现的键）
    load_dotenv(os.path.join(_repo_root, ".env"))
    load_dotenv(os.path.join(_cfg_dir, ".env"))
    load_dotenv()
except ImportError:
    pass

# MySQL
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+pymysql://root:123456@localhost:3306/football_betting"
)

# 占位符检测：若未修改 .env 会提示
_DB_PLACEHOLDERS = ("用户", "密码", "YOUR_MYSQL_USER", "YOUR_MYSQL_PASSWORD")
_parsed = urlparse(DATABASE_URL)
_db_user = unquote(_parsed.username or "")
if _db_user in _DB_PLACEHOLDERS:
    raise ValueError(
        "请在项目根目录的 .env 文件中配置真实的 MySQL 用户名和密码。\n"
        "将 DATABASE_URL 改为例如：mysql+pymysql://root:你的密码@localhost:3306/football_betting\n"
        "（不要使用“用户”“密码”或 YOUR_MYSQL_USER 等占位符）"
    )


def _pymysql_creator():
    """
    PyMySQL 默认用 latin-1 编码密码，中文等非 ASCII 会报错。
    用自定义 creator 把密码按 UTF-8 转成 PyMySQL 能发送的格式。
    """
    import pymysql
    parsed = urlparse(DATABASE_URL)
    password = unquote(parsed.password) if parsed.password else ""
    if password:
        # 使 password.encode('latin1') 等于 UTF-8 字节，这样 PyMySQL 发出去的就是正确密码
        password = password.encode("utf-8").decode("latin-1")
    return pymysql.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        user=unquote(parsed.username) if parsed.username else None,
        password=password,
        database=(parsed.path or "/").strip("/").split("/")[0] or None,
        charset="utf8mb4",
    )


def get_sqlalchemy_engine_options():
    """若使用 PyMySQL 且密码可能含非 ASCII，用自定义 creator 避免 UnicodeEncodeError。"""
    return {"creator": _pymysql_creator}

# JWT（RFC 7518 建议 HS256 密钥至少 32 字节，否则会触发 InsecureKeyLengthWarning）
JWT_SECRET_KEY = os.environ.get(
    "JWT_SECRET_KEY",
    "change-me-in-production-min-32-bytes-long",
)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7  # 7 天

# 短信验证码
SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "mock")
SMS_CODE_EXPIRE = int(os.environ.get("SMS_CODE_EXPIRE", "300"))  # 秒
SMS_CODE_LENGTH = 6
# 同一手机号发送间隔（秒）
SMS_SEND_INTERVAL = 60

# 工作目录：与 pipeline 的 WORK_SPACE 一致，便于统一管理 data/report 等路径
WORK_SPACE = os.environ.get(
    "WORK_SPACE",
    os.path.expanduser("~/Documents/cursor")
).rstrip(os.sep)
# 曲线图目录：与 plot_car.py 输出一致，按 YYYYMMDD 子目录存放 主队_VS_客队.png
# 优先用环境变量；否则尝试「项目根/football-betting-report」（platform 在项目内时）
_def_report = os.path.join(WORK_SPACE, "football-betting-report")
_config_dir = os.path.dirname(os.path.abspath(__file__))
_repo_report = os.path.join(os.path.dirname(_config_dir), "football-betting-report")
if os.path.isdir(_repo_report):
    _def_report = _repo_report
CURVE_IMAGE_DIR = os.environ.get("CURVE_IMAGE_DIR", _def_report)

# 曲线图：默认 1 = 仅当前有效会员可查看任何曲线（会员过期后一律不可看，避免与 evaluation_matches 判场不一致时仍能看图）。
# 若需严格按设计书「非会员可看完场/历史」：在 .env 设置 CURVES_REQUIRE_ACTIVE_MEMBERSHIP=0
_CURVES_REQ = os.environ.get("CURVES_REQUIRE_ACTIVE_MEMBERSHIP", "0").strip().lower()
CURVES_REQUIRE_ACTIVE_MEMBERSHIP = _CURVES_REQ not in ("0", "false", "no", "off")

# 平台日志目录（与 pipeline 一致：仓库根下 football-betting-log）
LOG_DIR = os.environ.get(
    "LOG_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "football-betting-log"),
)
# 若设置 LOG_FILE 则写入该固定路径（测试或特殊部署）；否则为 platform_YYYYMMDD.log 按自然日切换
LOG_FILE = os.environ.get("LOG_FILE", "").strip()


class DailyPlatformFileHandler(logging.FileHandler):
    """写入 LOG_DIR/platform_YYYYMMDD.log，跨自然日自动换文件。"""

    def __init__(self, log_dir, encoding="utf-8"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self._current_date = datetime.date.today()
        path = self._path_for_date(self._current_date)
        super().__init__(path, encoding=encoding, delay=False)

    def _path_for_date(self, d: datetime.date) -> str:
        return os.path.join(self.log_dir, f"platform_{d.strftime('%Y%m%d')}.log")

    def emit(self, record):
        today = datetime.date.today()
        if self._current_date != today:
            self.close()
            self.baseFilename = os.path.abspath(self._path_for_date(today))
            self.stream = self._open()
            self._current_date = today
        super().emit(record)

# ---------------------------------------------------------------------------
# 支付宝 / 会员标价（支付回调开通会员）
# ---------------------------------------------------------------------------
# mock：不验 RSA，便于本地联调；需配合 ALIPAY_MOCK_SECRET + 请求头 X-Alipay-Mock-Secret
# rsa ：按支付宝公钥验签（ALIPAY_PUBLIC_KEY_PEM 或 ALIPAY_PUBLIC_KEY_PATH）
ALIPAY_MODE = os.environ.get("ALIPAY_MODE", "mock").strip().lower()
ALIPAY_APP_ID = os.environ.get("ALIPAY_APP_ID", "")
ALIPAY_MOCK_SECRET = os.environ.get("ALIPAY_MOCK_SECRET", "")
# 异步通知完整 URL 前缀，用于下单返回给前端配置收银台（示例）
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:5001").rstrip("/")

_alipay_pem_path = os.environ.get("ALIPAY_PUBLIC_KEY_PATH", "")
if _alipay_pem_path and os.path.isfile(_alipay_pem_path):
    with open(_alipay_pem_path, "r", encoding="utf-8") as _f:
        ALIPAY_PUBLIC_KEY_PEM = _f.read()
else:
    ALIPAY_PUBLIC_KEY_PEM = os.environ.get("ALIPAY_PUBLIC_KEY_PEM", "")

# ---------------------------------------------------------------------------
# 微信支付 / 结果通知（V2 MD5 验签）
# ---------------------------------------------------------------------------
# mock：不验签；可选 WECHAT_MOCK_SECRET + 请求头 X-Wechat-Mock-Secret
# v2 ：按商户平台 API 密钥验 MD5 签名（XML/表单字段）
WECHAT_PAY_MODE = os.environ.get("WECHAT_PAY_MODE", "mock").strip().lower()
WECHAT_MOCK_SECRET = os.environ.get("WECHAT_MOCK_SECRET", "")
WECHAT_API_KEY = os.environ.get("WECHAT_API_KEY", "")


def _load_membership_prices() -> dict[str, str]:
    """各会员类型标价（元，两位小数字符串）。可用环境变量 MEMBERSHIP_PRICES_JSON 覆盖。"""
    import json

    raw = os.environ.get("MEMBERSHIP_PRICES_JSON", "").strip()
    defaults = {
        "week": "9.90",
        "month": "29.90",
        "quarter": "79.90",
        "year": "299.90",
    }
    if not raw:
        return defaults
    try:
        data = json.loads(raw)
        out = dict(defaults)
        for k, v in data.items():
            if k in out and v is not None:
                out[k] = str(v)
        return out
    except (json.JSONDecodeError, TypeError):
        return defaults


MEMBERSHIP_PRICES = _load_membership_prices()
