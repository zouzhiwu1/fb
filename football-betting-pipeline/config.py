"""
爬虫配置。可通过环境变量覆盖（若存在 .env 会先加载）：
  WORK_SPACE  工作目录根路径，其下放置 football-betting-data、football-betting-report、football-betting-log 等
  CRAWLER_BASE_URL  页面地址
  CRAWLER_DOWNLOAD_DIR  下载目录（crawl 的 xls、merge_data 的 master_{YYYYMMDD}.csv）
  CRAWLER_REPORT_DIR  报告目录（calc_car 的 car_{YYYYMMDD}.xlsx、plot_car 的 {主队}_VS_{客队}.png，其下按 YYYYMMDD 子目录）
  CRAWLER_CUTOFF_HOUR  跨天时间临界点（时，0～23），默认 12
  CRAWLER_TIMEZONE  用于“当前时间”的时区（决定下载目录/文件名），默认 Asia/Tokyo
  CRAWLER_HEADLESS  设为 1/true 则无头模式（不弹窗），默认 1
  CRAWLER_DEBUG_LOG_DIR  日志目录（定时任务日志、debug_export_page_*.html 等），默认 football-betting-log
  CRAWLER_LOG_RETENTION_DAYS  日志保留天数，超过此天数的日志文件将被删除，默认 7
  CRAWLER_DEBUG_MAX_MATCHES  调试时最多抓取场数，0 表示不限制；设为 3 可快速跑通 main 流程验证
  CRAWLER_DEBUG_MATCH_KEYWORDS  球队白名单关键词（逗号分隔）；设为空字符串表示不限制球队
  CRAWLER_TARGET_LEAGUES  联赛白名单（逗号分隔）；设为空字符串表示不限制联赛
  CRAWLER_EXPORT_EXCEL_MAX_ATTEMPTS  单场「导出 Excel」最多重试次数（默认 3）
  CRAWLER_MATCH_FILTER_VISIBLE_ONLY  1=只收集页面上可见行；0=含 DOM 隐藏行
  CRAWLER_MATCH_STATUS_MODES  状态过滤，逗号分隔：not_started,live,finished（默认 not_started）
  CRAWLER_MATCH_REQUIRE_JIAN  1=仅保留包含“荐”的比赛；0=不过滤“荐”（默认 1）
  CRAWLER_CHROME_USER_AGENT  覆盖 Chrome User-Agent（默认桌面 Chrome，避免 HeadlessChrome 被拒）
  CRAWLER_CHROME_DISABLE_HTTP2  设为 1 时禁用 HTTP/2（排查协议问题时使用）
  CRAWLER_CHROME_BINARY  浏览器可执行文件路径（Docker 内常见 /usr/bin/chromium）；简写 CHROME_BINARY 亦有效
  CRAWLER_CHROMEDRIVER_PATH  chromedriver 路径，须与 Chromium 主版本一致；简写 CHROMEDRIVER_PATH 亦有效
  CRAWLER_ALLOW_GLOBAL_TABLE_LIVE  设为 1 时，即时比分在 middle→ScoreDiv 内找不到 #table_live 则回退全局 #table_live（与完场逻辑类似，Docker/页面差异时可开）
  CRAWLER_WAIT_ELEMENT  Selenium 显式等待上限秒数（默认 20），服务器慢或跨境可改为 40～60
  CRAWLER_PAGE_LOAD_STRATEGY  driver.get 页面加载策略：normal / eager / none（默认 eager，避免第三方资源卡死导致 120s 读超时）
  CRAWLER_PAGE_LOAD_TIMEOUT  浏览器导航超时秒数（默认 90）；0 表示不设置
  CRAWLER_SELENIUM_READ_TIMEOUT  Python 与 chromedriver HTTP 读超时秒数（默认 240，须大于导航耗时）
  DATABASE_URL  与 football-betting-platform 相同（mysql+pymysql://...），供 evaluation_matches 入表/出表；未设置则跳过
"""
import os


def _env_flag(name: str, default: str = "0") -> bool:
    """将环境变量解析为布尔值，兼容 1/true/yes/on。"""
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")

# 始终先加载与 config.py 同目录下的 .env（即 football-betting-pipeline/.env），
# 避免从仓库根目录或其他 cwd 运行 run_real / plot_car 时读不到 DATABASE_URL。
_PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_PIPELINE_DIR)
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_REPO_ROOT, ".env"))
    load_dotenv(os.path.join(_PIPELINE_DIR, ".env"))
    load_dotenv()  # 当前工作目录 .env，仅补充未出现的键
except ImportError:
    pass

# 工作目录：其下统一管理 data、report、log 等子目录，便于迁移或换机器时只改一处。
# 默认使用当前文件所在目录的上一级（即包含 football-betting-data / football-betting-log / football-betting-report 的目录）。
_DEFAULT_WORK_SPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK_SPACE = os.environ.get("WORK_SPACE", _DEFAULT_WORK_SPACE).rstrip(os.sep)

# 与 football-betting-platform 共用 MySQL 时配置；供 evaluation_matches 入表/出表。
# 若 .env 里写了 DATABASE_URL=（空），仅用 get 的第二个参数无法回退，故用「or 本地默认」。
_env_db = os.environ.get("DATABASE_URL", "").strip()
DATABASE_URL = _env_db or "mysql+pymysql://root:123456@localhost:3306/football_betting"

BASE_URL = os.environ.get(
    "CRAWLER_BASE_URL",
    "https://live.nowscore.com/2in1.aspx"
)
DOWNLOAD_DIR = os.environ.get(
    "CRAWLER_DOWNLOAD_DIR",
    os.path.join(WORK_SPACE, "football-betting-data")
)
# calc_car.py / plot_car.py 生成文件（car_{YYYYMMDD}.xlsx、{主队}_VS_{客队}.png）的根目录，其下按 YYYYMMDD 建子目录
REPORT_DIR = os.environ.get(
    "CRAWLER_REPORT_DIR",
    os.path.join(WORK_SPACE, "football-betting-report")
)
# 跨天时间临界点（时）：当日该时及之后 → 当日文件夹；次日该时之前 → 前一日文件夹
CUTOFF_HOUR = int(os.environ.get("CRAWLER_CUTOFF_HOUR", "12"))
# 主流程触发小时（整点，0～23）。run_real.py 依此计算每次统计区间 [start,end]。
# 如需调整定时任务时间，只需修改此处或设置环境变量 CRAWLER_TRIGGER_HOURS（逗号分隔）。
TRIGGER_HOURS = [
    int(h)
    for h in os.environ.get("CRAWLER_TRIGGER_HOURS", "2,4,6,13,15,17,19,21,23").split(",")
    if h.strip()
]
TRIGGER_HOURS.sort()
# 用于“当前时间”的时区（避免服务器 UTC 导致临界点错位）
TIMEZONE = os.environ.get("CRAWLER_TIMEZONE", "Asia/Tokyo")
HEADLESS = _env_flag("CRAWLER_HEADLESS", "1")
# Chrome User-Agent：无头模式默认 UA 常含 HeadlessChrome，易被目标站拒绝；与「curl + 桌面 Chrome UA」成功时保持一致。
_DEFAULT_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_raw_chrome_ua = os.environ.get("CRAWLER_CHROME_USER_AGENT", "").strip()
CHROME_USER_AGENT = _raw_chrome_ua if _raw_chrome_ua else _DEFAULT_CHROME_UA
# 设为 1 时禁用 HTTP/2（与部分环境下 curl 的 HTTP/2 PROTOCOL_ERROR 类似问题时可试）
CHROME_DISABLE_HTTP2 = os.environ.get("CRAWLER_CHROME_DISABLE_HTTP2", "").strip().lower() in (
    "1",
    "true",
    "yes",
)
# Docker / 服务器：指定系统已安装的 Chromium 与 chromedriver，避免 webdriver-manager 下载的二进制缺库退出 127
# 兼容简写环境变量 CHROME_BINARY / CHROMEDRIVER_PATH（易与文档笔误混淆时仍可用）
CHROME_BINARY_PATH = (
    os.environ.get("CRAWLER_CHROME_BINARY", "").strip()
    or os.environ.get("CHROME_BINARY", "").strip()
)
CHROMEDRIVER_PATH = (
    os.environ.get("CRAWLER_CHROMEDRIVER_PATH", "").strip()
    or os.environ.get("CHROMEDRIVER_PATH", "").strip()
)
# 日志目录：定时任务 stdout/stderr、调试导出的页面 HTML（debug_export_page_*.html）等
DEBUG_LOG_DIR = os.environ.get(
    "CRAWLER_DEBUG_LOG_DIR",
    os.path.join(WORK_SPACE, "football-betting-log")
)
# 日志保留天数：crawl/merge_data/calc_car/plot_car 执行前会删除超过此天数的日志文件
LOG_RETENTION_DAYS = int(os.environ.get("CRAWLER_LOG_RETENTION_DAYS", "7"))
# 调试：最多抓取场数，0=不限制；设为 3 时只抓 3 场即结束，便于快速验证 run_real.py 全流程
DEBUG_MAX_MATCHES = int(os.environ.get("CRAWLER_DEBUG_MAX_MATCHES", "0"))
# 球队白名单：主队/客队名称包含任一关键词才保留。
# 用法与联赛白名单一致：环境变量存在时按其覆盖；值为空字符串表示不限制球队。
# 例如: CRAWLER_DEBUG_MATCH_KEYWORDS="帕纳辛纳科斯,里尔,博洛尼亚"
_DEFAULT_TEAM_WHITELIST_KEYWORDS = ""
_team_keywords_env = os.environ.get("CRAWLER_DEBUG_MATCH_KEYWORDS")
if _team_keywords_env is not None:
    TEAM_WHITELIST_KEYWORDS = [
        kw.strip() for kw in _team_keywords_env.split(",") if kw.strip()
    ]
else:
    TEAM_WHITELIST_KEYWORDS = [
        kw.strip() for kw in _DEFAULT_TEAM_WHITELIST_KEYWORDS.split(",") if kw.strip()
    ]

# 足彩子菜单：目前只抓取「北单」
ZUCAI_MENU_OPTIONS = ["北单"]

# 联赛白名单：北单「即时比分」「完场比分」主表仅抓取下列联赛（单元格简称与名单匹配，见 league_whitelist.py）。
# 可通过环境变量 CRAWLER_TARGET_LEAGUES 覆盖（英文逗号分隔）；设为空字符串表示关闭联赛白名单（不限制）。
_DEFAULT_TARGET_LEAGUES = (
    "澳超,罗甲,波兰超,奥甲,奥乙,意甲,意乙,德甲,德乙,法甲,法乙,英超,英冠,英甲,英乙,"
    "荷甲,荷乙,比甲,比乙,西甲,西乙,爱超,爱甲,葡超,葡甲,阿甲,墨西联春,日职联,日职乙,"
    "韩K联,韩K2联,丹麦甲,苏超,苏冠,瑞士超,瑞士甲,挪超,美职业,巴西甲,巴西乙,智利甲,希腊超,欧洲预选,国际友谊,世界杯附,欧国联"
)
_target_leagues_env = os.environ.get("CRAWLER_TARGET_LEAGUES")
if _target_leagues_env is not None:
    # 联赛白名单（环境变量覆盖）；空列表表示不限制联赛
    TARGET_LEAGUE_NAMES = [
        x.strip() for x in _target_leagues_env.split(",") if x.strip()
    ]
else:
    TARGET_LEAGUE_NAMES = [
        x.strip() for x in _DEFAULT_TARGET_LEAGUES.split(",") if x.strip()
    ]

# ---------- run_real 比赛列表三层过滤（可视 / 状态 / 联赛白名单）----------
# 1) 可视：与页面「隐藏 N 场」一致，True 只处理当前能看见的行
MATCH_FILTER_VISIBLE_ONLY = os.environ.get("CRAWLER_MATCH_FILTER_VISIBLE_ONLY", "1") == "1"
# 2) 状态：允许类别的并集。not_started=未开场（空白或「-」）；live=进行中（非空且未完场）；
#    finished=完场（状态列含「完」）。默认仅 not_started，与历史「仅状态为空」一致。
_status_modes_raw = os.environ.get("CRAWLER_MATCH_STATUS_MODES", "not_started")
MATCH_STATUS_MODES = [x.strip().lower() for x in _status_modes_raw.split(",") if x.strip()]
if not MATCH_STATUS_MODES:
    MATCH_STATUS_MODES = ["not_started"]
# 3) 联赛：TARGET_LEAGUE_NAMES；空列表表示不限制（见上）
# 4) 推荐：是否仅保留记录里包含“荐”的比赛（默认开启）
MATCH_REQUIRE_JIAN = _env_flag("CRAWLER_MATCH_REQUIRE_JIAN", "1")

# 即时比分：strict 选择器找不到主表时是否允许回退到页面内任意 #table_live（默认关，避免误用 main2）
ALLOW_GLOBAL_TABLE_LIVE = os.environ.get(
    "CRAWLER_ALLOW_GLOBAL_TABLE_LIVE", ""
).strip().lower() in ("1", "true", "yes")

# 表格列索引（与页面一致）：选、联赛、时间、状态、主队、比分、客队、…
# 第 2 列（索引 1）为联赛简称，用于联赛白名单（TARGET_LEAGUE_NAMES）过滤。
COL_LEAGUE = 1
COL_DATE = 1   # 与联赛同索引（历史字段名）；无日期文本时时间后缀解析会回退到 COL_TIME/当前时间
COL_TIME = 2
COL_STATUS = 3   # 状态列：由 MATCH_STATUS_MODES 决定保留哪些
COL_HOME = 4
COL_SCORE = 5    # 比分列（即时比分/完场比分均用）
COL_AWAY = 6

# 等待时间（秒）
WAIT_ELEMENT = int(os.environ.get("CRAWLER_WAIT_ELEMENT", "20"))

# driver.get：normal=等 load 完成；eager=DOM 可交互后返回（适合本站 + 服务器防卡死）；none=几乎立即返回
_raw_pls = os.environ.get("CRAWLER_PAGE_LOAD_STRATEGY", "eager").strip().lower()
PAGE_LOAD_STRATEGY = _raw_pls if _raw_pls in ("normal", "eager", "none") else "eager"
PAGE_LOAD_TIMEOUT_SECONDS = int(os.environ.get("CRAWLER_PAGE_LOAD_TIMEOUT", "90"))
# Selenium → chromedriver 单次 HTTP 读超时（默认 120 时，首屏若永不 complete 会在 driver.get 上报错）
SELENIUM_REMOTE_READ_TIMEOUT = int(os.environ.get("CRAWLER_SELENIUM_READ_TIMEOUT", "240"))
WAIT_AFTER_CLICK = 0.5
WAIT_AFTER_HOVER = 0.4
WAIT_TABLE_REFRESH = 3
WAIT_FIRST_ROW_CHANGED = 12
# 单场「导出 Excel」未检测到新文件时的最大重试次数（仅重试点击导出，不含整页重新导航）
EXPORT_EXCEL_MAX_ATTEMPTS = int(os.environ.get("CRAWLER_EXPORT_EXCEL_MAX_ATTEMPTS", "3"))
# 每次点击导出后，在下载目录内等待新 .xls 的最长时间（秒）
EXPORT_EXCEL_DOWNLOAD_WAIT_SECONDS = 3.0
