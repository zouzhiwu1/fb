"""
爬虫配置。可通过环境变量覆盖（若存在 .env 会先加载）：
  WORK_SPACE  工作目录根路径，其下放置 football-betting-data、football-betting-report、football-betting-log 等
  CRAWLER_BASE_URL  页面地址
  CRAWLER_DOWNLOAD_DIR  下载目录（crawl 的 xls、merge_data 的 master_{YYYYMMDD}.csv）
  CRAWLER_REPORT_DIR  报告目录（calc_car 的 car_{YYYYMMDD}.xlsx、plot_car 的 {主队}_VS_{客队}.png，其下按 YYYYMMDD 子目录）
  CRAWLER_CUTOFF_HOUR  跨天时间临界点（时，0～23），默认 12
  CRAWLER_TIMEZONE  用于“当前时间”的时区（决定下载目录/文件名），默认 Asia/Tokyo
  CRAWLER_HEADLESS  设为 1 则无头模式（不弹窗），默认 1
  CRAWLER_DEBUG_LOG_DIR  日志目录（定时任务日志、debug_export_page_*.html 等），默认 football-betting-log
  CRAWLER_LOG_RETENTION_DAYS  日志保留天数，超过此天数的日志文件将被删除，默认 7
  CRAWLER_DEBUG_MAX_MATCHES  调试时最多抓取场数，0 表示不限制；设为 3 可快速跑通 main 流程验证
  CRAWLER_TARGET_LEAGUES  联赛白名单（逗号分隔）；设为空字符串表示不限制联赛
  CRAWLER_EXPORT_EXCEL_MAX_ATTEMPTS  单场「导出 Excel」最多重试次数（默认 3）
  CRAWLER_MATCH_FILTER_VISIBLE_ONLY  1=只收集页面上可见行；0=含 DOM 隐藏行
  CRAWLER_MATCH_STATUS_MODES  状态过滤，逗号分隔：not_started,live,finished（默认 not_started）
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 工作目录：其下统一管理 data、report、log 等子目录，便于迁移或换机器时只改一处。
# 默认使用当前文件所在目录的上一级（即包含 football-betting-data / football-betting-log / football-betting-report 的目录）。
_DEFAULT_WORK_SPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK_SPACE = os.environ.get("WORK_SPACE", _DEFAULT_WORK_SPACE).rstrip(os.sep)

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
HEADLESS = os.environ.get("CRAWLER_HEADLESS", "1") == "1"
# 日志目录：定时任务 stdout/stderr、调试导出的页面 HTML（debug_export_page_*.html）等
DEBUG_LOG_DIR = os.environ.get(
    "CRAWLER_DEBUG_LOG_DIR",
    os.path.join(WORK_SPACE, "football-betting-log")
)
# 日志保留天数：crawl/merge_data/calc_car/plot_car 执行前会删除超过此天数的日志文件
LOG_RETENTION_DAYS = int(os.environ.get("CRAWLER_LOG_RETENTION_DAYS", "7"))
# 调试：最多抓取场数，0=不限制；设为 3 时只抓 3 场即结束，便于快速验证 run_real.py 全流程
DEBUG_MAX_MATCHES = int(os.environ.get("CRAWLER_DEBUG_MAX_MATCHES", "0"))
# 调试：仅抓取包含指定关键词的比赛（主队或客队含任一关键词）。
# 例如: CRAWLER_DEBUG_MATCH_KEYWORDS="帕纳辛纳科斯,里尔,博洛尼亚"
_match_keywords_raw = os.environ.get("CRAWLER_DEBUG_MATCH_KEYWORDS", "")
DEBUG_MATCH_KEYWORDS = [
    kw.strip()
    for kw in _match_keywords_raw.split(",")
    if kw.strip()
]

# 足彩子菜单：目前只抓取「北单」
ZUCAI_MENU_OPTIONS = ["北单"]

# 联赛白名单：北单「即时比分」「完场比分」主表仅抓取下列联赛（单元格简称与名单匹配，见 league_whitelist.py）。
# 可通过环境变量 CRAWLER_TARGET_LEAGUES 覆盖（英文逗号分隔）；设为空字符串表示关闭联赛白名单（不限制）。
_DEFAULT_TARGET_LEAGUES = (
    "澳超,罗甲,波兰超,奥甲,奥乙,意甲,意乙,德甲,德乙,法甲,法乙,英超,英冠,英甲,英乙,"
    "荷甲,荷乙,比甲,比乙,西甲,西乙,爱超,爱甲,葡超,葡甲,阿甲,墨西联春,日职联,日职乙,"
    "韩K联,韩K2联,丹麦甲,苏超,苏冠,瑞士超,瑞士甲,挪超,美职业,巴西甲,巴西乙,智利甲,希腊超"
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
WAIT_ELEMENT = 20
WAIT_AFTER_CLICK = 0.5
WAIT_AFTER_HOVER = 0.4
WAIT_TABLE_REFRESH = 3
WAIT_FIRST_ROW_CHANGED = 12
# 单场「导出 Excel」未检测到新文件时的最大重试次数（仅重试点击导出，不含整页重新导航）
EXPORT_EXCEL_MAX_ATTEMPTS = int(os.environ.get("CRAWLER_EXPORT_EXCEL_MAX_ATTEMPTS", "3"))
# 每次点击导出后，在下载目录内等待新 .xls 的最长时间（秒）
EXPORT_EXCEL_DOWNLOAD_WAIT_SECONDS = 10.0
