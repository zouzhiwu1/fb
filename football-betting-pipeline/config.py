"""
爬虫配置。可通过环境变量覆盖（若存在 .env 会先加载）：
  WORK_SPACE  工作目录根路径，其下放置 football-betting-data、football-betting-report、football-betting-log 等
  CRAWLER_BASE_URL  页面地址
  CRAWLER_DOWNLOAD_DIR  下载目录（crawl 的 xls、merge_data 的 master_{YYYYMMDD}.csv）
  CRAWLER_REPORT_DIR  报告目录（calc_car 的 car_{YYYYMMDD}.xlsx、plot_car 的 {主队}_VS_{客队}.png，其下按 YYYYMMDD 子目录）
  CRAWLER_CUTOFF_HOUR  跨天时间临界点（时，0～23），默认 12
  CRAWLER_TIMEZONE  用于“当前时间”的时区（决定下载目录/文件名），默认 Asia/Tokyo
  CRAWLER_HEADLESS  设为 1 则无头模式
  CRAWLER_DEBUG_LOG_DIR  日志目录（定时任务日志、debug_export_page_*.html 等），默认 football-betting-log
  CRAWLER_LOG_RETENTION_DAYS  日志保留天数，超过此天数的日志文件将被删除，默认 7
  CRAWLER_DEBUG_MAX_MATCHES  调试时最多抓取场数，0 表示不限制；设为 3 可快速跑通 main 流程验证
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

# 表格列索引（与页面一致）：选、日期、时间、状态、主队、比分、客队、…
COL_DATE = 1
COL_TIME = 2
COL_STATUS = 3   # 状态列：仅下载状态为空的比赛（空白或「-」），不下载「比赛中」「完」等
COL_HOME = 4
COL_SCORE = 5    # 比分列（即时比分/完场比分均用）
COL_AWAY = 6

# 等待时间（秒）
WAIT_ELEMENT = 20
WAIT_AFTER_CLICK = 0.5
WAIT_AFTER_HOVER = 0.4
WAIT_TABLE_REFRESH = 3
WAIT_ROW_COUNT = 20
WAIT_FIRST_ROW_CHANGED = 12
