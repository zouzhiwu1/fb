# 网络爬虫

本仓库对应整体系统中的 **模块 1：数据抓取与曲线图生成**。打开智云比分页，抓取数据后经合并、计算，最终生成曲线图图片。

## 环境

- Python 3.10+
- Chrome 浏览器

## 安装

```bash
cd football-betting-pipeline
pip install -r requirements.txt
```

## 项目结构

```
football-betting-pipeline/
├── README.md                    # 本文件
├── run_real.py                  # 即时流程入口（crawl_real → merge_data → calc_car → plot_car）
├── run_final.py                 # 完场流程入口（crawl_final → add_score_to_image）
├── crawl_real.py                # 抓取即时比分并下载 .xls
├── merge_data.py                # 合并为 master_{YYYYMMDD}.csv
├── calc_car.py                  # 计算综合评估，输出 car_{YYYYMMDD}.xlsx
├── plot_car.py                  # 生成欧赔/凯利曲线图 {主队}_VS_{客队}.png
├── crawl_final.py               # 抓取完场比分，输出 final_{YYYYMMDD}.csv
├── add_score_to_image.py        # 将完场比分写入报告图片
├── config.py                    # 配置（可被环境变量 / .env 覆盖）
├── log_cleanup.py               # 日志清理（按保留天数删除旧日志）
├── scraper_real.py              # 即时比分页爬虫逻辑
├── scraper_final.py             # 完场比分页爬虫逻辑
├── template.xlsx                # 一览表表头模板（merge_data 依赖）
├── requirements.txt
├── .env.example
├── com.football.betting.run_real.plist   # macOS launchd 即时流程定时任务（多整点）
├── com.football.betting.run_final.plist # macOS launchd 完场流程定时任务（每天 13 点）
├── gen_launchd_plist.sh                  # 根据 RUN_ROOT 生成 com.football.betting.run_real.plist
└── tests/                       # 单元测试
    ├── test_run_real.py
    ├── test_merge_data.py
    ├── test_calc_car.py
    ├── test_plot_car.py
    └── ...
```

数据与日志目录（默认在 `WORK_SPACE` 下，见 config.py）：`football-betting-data/`、`football-betting-report/`、`football-betting-log/`。

## 运行

本仓库**不启动任何 Web 服务**，仅由**定时任务**或手工命令调用，执行完整流程（抓取 → 合并 → 计算 → 曲线图）。

### 1）即时流程入口：run_real.py

```bash
# 自动按当前时间和跨天临界点计算区间
python run_real.py

# 手工指定时间区间
python run_real.py <起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>
```

- 无参数时，`run_real.py` 会根据当前时间和 `config.CUTOFF_HOUR` 计算一个 **24 小时的逻辑区间 [start,end]**：
  - 当前时间在当日 `CUTOFF_HOUR` 之前：`start = 昨天 CUTOFF_HOUR`，`end = 今天 CUTOFF_HOUR-1`；
  - 当前时间在当日 `CUTOFF_HOUR` 及之后：`start = 今天 CUTOFF_HOUR`，`end = 明天 CUTOFF_HOUR-1`。
- 显式传入 `<起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>` 时，会直接以该区间作为 [start,end]。
- 之后 `run_real.py` 会依次调用：
  - `crawl_real.py start end`
  - `merge_data.py start end`
  - `calc_car.py start end`
  - `plot_car.py start end`

也可单独执行各步骤，见下文「脚本说明」。

### 2）完场流程入口：run_final.py

```bash
# 使用昨日日期（抓完场比分 → 写入图片）
python run_final.py

# 指定日期
python run_final.py 20260314
```

- 依次执行：`crawl_final.py`（抓取完场比分）→ `add_score_to_image.py`（将比分写入报告图片）。  
- 建议用**定时任务每天 13 点**执行一次（见下方「完场定时任务」）。曲线图查询功能已迁移至 **football-betting-platform**，请在该项目中启动服务并访问「曲线图查询」页面。

## 脚本说明

### crawl_real.py — 抓取即时比分数据

**功能**：打开智云比分页，进入「足球」→「即时比分」→「足彩」→「北单」，等待表格刷新后，仅下载状态为空的比赛（状态列为空白或「-」），逐场点击导出并下载对应的 `.xls` 文件。文件按配置的下载目录与跨天临界点保存到子目录 `{YYYYMMDD}/`，文件名含主客队与时间点（如 `主队_VS_客队_2026030807.xls`）。

**用法**（仅接收两个时间点参数，形式与其它批处理脚本一致）：

```bash
python crawl_real.py <起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>
```

当前版本中，crawl 实际仍按“执行当下的实时盘口”抓取，时间参数主要用于：

- 与 `run_real.py / merge_data.py / calc_car.py / plot_car.py` 保持一致的调用方式；
- 在日志中标记本次抓取对应的逻辑时间区间，便于排查。

---

### merge_data.py — 合并一览表

**功能**：在指定时间区间 `[start,end]` 内，遍历覆盖到的日期目录 `DOWNLOAD_DIR/{YYYYMMDD}/`，根据文件名中的时间点 `YYYYMMDDHH` 过滤出在区间内的 `.xls` 文件，按文件名排序后合并为一张一览表，输出 `master_{YYYYMMDD}.csv`。表头两行来自工程目录下的 `template.xlsx` 第 1、2 行；数据列为 C/D/E/F/G/H/L/M/N 等。

**用法**（仅接收两个时间点参数）：

```bash
python merge_data.py <起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>
```

- 例如：`python merge_data.py 2026030812 2026030911`。
- 输出文件放在起始时间所在日期目录下：`DOWNLOAD_DIR/{start日期}/master_{start日期}.csv`。
- 工程目录下需有 `template.xlsx`。

---

### calc_car.py — 计算综合评估（CAR）

**功能**：在 merge_data 生成的一览表基础上，按「主队、客队、时间点」分组，对 D～L 列计算综合评估值：D～I 列用 `(MAX-MIN)/AVERAGE`，J、K、L 列用 `VARP(列)*100`，输出 `car_{YYYYMMDD}.xlsx`。

**用法**（仅接收两个时间点参数）：

```bash
python calc_car.py <起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>
```

- 实际**使用**的逻辑日期与 `merge_data.py` 一致：取 **起始时间所在日期** `YYYYMMDD`（即起始时间的前 8 位）。
- 例如：`python calc_car.py 2026030812 2026030911` 会读取 `DOWNLOAD_DIR/20260308/master_20260308.csv`，在 `REPORT_DIR/20260308/` 下生成 `car_20260308.xlsx`。
- 依赖：`DOWNLOAD_DIR/{YYYYMMDD}/` 下需已存在 `master_{YYYYMMDD}.csv`（即先运行 `merge_data.py`）；工程目录下需有 `template.xlsx`。

---

### plot_car.py — 生成欧赔/凯利曲线图

**功能**：根据综合评估表 `car_{YYYYMMDD}.xlsx` 为每场比赛生成一张图，包含两个子图：**欧赔指数曲线图**（主/平/客三条曲线，第 1 节点为初指 D/E/F，其余节点为各时间点即时盘 G/H/I）、**凯利指数曲线图**（主/平/客三条曲线，X 轴为时间点 C，Y 轴为 J/K/L）。曲线节点数量由表中该场比赛的时间点数量决定，不固定。详见 design.md 第 3.3 节。

**用法**（仅接收两个时间点参数）：

```bash
python plot_car.py <起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>
```

- 实际使用的逻辑日期与 `merge_data.py` 一致：使用 **起始时间所在日期** `YYYYMMDD`。
- 输出图片保存在对应报告目录 `REPORT_DIR/{YYYYMMDD}/` 下，文件名：`{主队}_VS_{客队}.png`。
- 依赖：`REPORT_DIR/{YYYYMMDD}/` 下需已存在 `car_{YYYYMMDD}.xlsx`（即先运行 `calc_car.py`）。

---

### 完场数据处理（设计书 2. 完场数据处理）

**crawl_final.py — 抓取完场比分**

- **功能**：打开智云比分页，进入「足球」→「完场比分」→「足彩」→「北单」，等待表格刷新后抓取每行的**主队、客队、比分**，输出 CSV 供后续写入报告图片。
- **用法**：
  ```bash
  python crawl_final.py [YYYYMMDD]
  ```
  - 无参数：使用昨日日期（完场日一般为前一天）。
  - 有参数：使用指定日期，与报告目录 `REPORT_DIR/YYYYMMDD` 对应。
- **输出**：`REPORT_DIR/{YYYYMMDD}/final_{YYYYMMDD}.csv`，列：`home, away, score`。定时器可设为每日 14 点执行（见 design.md 2.1）。

**add_score_to_image.py — 把完场比分写入图片**

- **功能**：根据完场 CSV，在 `REPORT_DIR/{YYYYMMDD}/{主队}_VS_{客队}.png` 上叠加比分文字（与 plot_car 生成的文件名一致）。
- **用法**：
  ```bash
  python add_score_to_image.py <YYYYMMDD>
  python add_score_to_image.py <path_to_final_YYYYMMDD.csv>
  ```
- **依赖**：需先运行 `crawl_final.py` 在 `REPORT_DIR/{YYYYMMDD}/` 下生成 `final_{YYYYMMDD}.csv`；对应日期的曲线图需已由 `plot_car.py` 生成。需安装 Pillow（见 requirements.txt）。

---

## 配置

所有配置均可通过**环境变量**覆盖（无需改代码）。若项目根目录存在 `.env` 文件，会先加载其中的变量（需安装 `python-dotenv`，已写在 requirements.txt 中）。

建议：复制 `.env.example` 为 `.env`，按需修改，之后直接运行 `python run_real.py` 即可生效。

### 环境变量一览

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `WORK_SPACE` | 工作目录根路径，其下默认放置 football-betting-data、football-betting-report、football-betting-log；改此处即可统一改默认路径 | `项目根目录上一层（例如 /Users/zhiwuzou/Documents/app/football-betting）` |
| `CRAWLER_BASE_URL` | 智云比分页面地址 | `https://live.nowscore.com/2in1.aspx` |
| `CRAWLER_DOWNLOAD_DIR` | 下载目录：crawl 的 .xls、merge_data 的 master_{YYYYMMDD}.csv 均在此目录下按 YYYYMMDD 子目录存放 | 默认 `WORK_SPACE/football-betting-data` |
| `CRAWLER_REPORT_DIR` | 报告目录：calc_car 的 car_{YYYYMMDD}.xlsx、plot_car 的 {主队}_VS_{客队}.png 写入此目录下对应的 YYYYMMDD 子目录 | 默认 `WORK_SPACE/football-betting-report` |
| `CRAWLER_CUTOFF_HOUR` | 跨天临界点（0～23 时）。该时及之后 → 当日文件夹；该时之前 → 前一日文件夹；`run_real.py` 也据此划分 24 小时逻辑区间 | `12` |
| `CRAWLER_TIMEZONE` | 用于“当前时间”的时区（决定下载目录/文件名） | `Asia/Tokyo` |
| `CRAWLER_HEADLESS` | `1` 无头模式，`0` 有浏览器界面 | `1` |
| `CRAWLER_DEBUG_LOG_DIR` | 日志目录：crawl/merge_data 等日志、调试用 `debug_export_page_*.html` 的存放路径 | 默认 `WORK_SPACE/football-betting-log` |
| `CRAWLER_LOG_RETENTION_DAYS` | 日志保留天数，超过此天数的日志文件会在运行前被删除 | `7` |
| `CRAWLER_TRIGGER_HOURS` | 定时任务触发整点（逗号分隔，0～23），仅影响 `run_real.py` 无参数时的区间计算 | `2,4,6,13,15,17,19,21,23` |
| `CRAWLER_DEBUG_MAX_MATCHES` | **调试用**：最多抓取场数，`0` 表示不限制；设为正整数（如 `3`）则只抓前 N 场即结束，便于快速跑通流程 | `0` |
| `CRAWLER_DEBUG_MATCH_KEYWORDS` | **调试用**：仅抓取主队或客队名称包含任一关键词的比赛，逗号分隔。例如 `帕纳辛纳科斯,里尔,博洛尼亚`。不设或为空则抓取全部 | 未设置 |

### 环境变量的使用方式

**1. 使用 .env 文件（推荐）**

在项目根目录（与 `run_real.py` 同级）创建 `.env`，每行一个变量，格式：`变量名=值`。  
运行 `python run_real.py` 或 `python crawl_real.py ...` 时会自动加载，无需在终端里重复设置。

```bash
# 示例：只改路径和是否无头
WORK_SPACE=/Users/xxx/Documents/football-betting
CRAWLER_HEADLESS=0
```

**2. 命令行临时覆盖**

在当次命令前加上 `变量名=值`，只对这一条命令生效，不影响 `.env` 或其它终端会话。

```bash
CRAWLER_HEADLESS=0 python run_real.py
CRAWLER_DEBUG_MAX_MATCHES=3 python run_real.py
```

**3. 调试时只抓部分比赛**

- **只抓前 N 场**（快速验证流程）：设置 `CRAWLER_DEBUG_MAX_MATCHES=3`（或其它正整数）。
- **只抓某几支球队**：设置 `CRAWLER_DEBUG_MATCH_KEYWORDS=主队名,客队名`，例如  
  `CRAWLER_DEBUG_MATCH_KEYWORDS=帕纳辛纳科斯,里尔,博洛尼亚`。  
  主队或客队名称包含任一关键词的比赛才会被下载。

**4. 正式跑全部比赛时关闭调试变量**

若之前为调试设置过上述变量，正式跑全量时需取消，否则仍只会抓部分场次或前 N 场。

- **若在 .env 里设置的**：打开 `.env`，删掉或注释掉 `CRAWLER_DEBUG_MAX_MATCHES`、`CRAWLER_DEBUG_MATCH_KEYWORDS` 两行。
- **若在终端里用 export 设置的**：当前终端执行 `unset CRAWLER_DEBUG_MATCH_KEYWORDS` 和 `unset CRAWLER_DEBUG_MAX_MATCHES`，再运行 `python run_real.py`。

**.env 示例**（在项目根目录创建 `.env`，按需填写）：

```bash
# 跨天临界点（例如 12 点：12 点及以后算当天，12 点前算前一天）
# CRAWLER_CUTOFF_HOUR=12
# 下载与合并/计算使用的根目录
# CRAWLER_DOWNLOAD_DIR=/path/to/足球彩票/北单
# 有界面运行（调试时可设为 0）
# CRAWLER_HEADLESS=1
# 时区（一般不需改）
# CRAWLER_TIMEZONE=Asia/Tokyo

# 调试：只抓前 3 场或只抓某几队时取消注释并填写；正式跑全量时保持注释或删除
# CRAWLER_DEBUG_MAX_MATCHES=3
# CRAWLER_DEBUG_MATCH_KEYWORDS=帕纳辛纳科斯,里尔,博洛尼亚
```

**命令行临时覆盖示例**：

```bash
CRAWLER_HEADLESS=0 CRAWLER_DOWNLOAD_DIR=/path/to/excels python run_real.py
# 调试：只抓前 5 场
CRAWLER_DEBUG_MAX_MATCHES=5 python run_real.py
```

---

## 定时任务

建议使用**操作系统自带的定时任务**在以下整点自动执行 `python run_real.py`（抓取 → 合并 → 计算 → 曲线图）：

**触发时间（每天）**：2、4、6、13、15、17、19、21、23 点。

下面按系统说明如何配置。请将示例中的 **项目目录**、**Python 路径** 替换为你本机的实际路径。

### Windows（任务计划程序）

1. 打开 **任务计划程序**（`taskschd.msc` 或“开始”菜单搜索）。
2. 右侧 **“创建基本任务”**，名称如 `足球测评`，下一步。
3. 触发器选 **“每天”**，下一步。
4. 开始时间任选一天，如 `00:00:00`，重复间隔选 **“1 天”**，下一步。
5. 操作选 **“启动程序”**：
   - **程序或脚本**：本机 Python 解释器路径（若用虚拟环境，填项目下 `.venv\Scripts\python.exe`），例如：
     ```text
     D:\projects\football-betting-pipeline\.venv\Scripts\python.exe
     ```
   - **添加参数**：`run_real.py`
   - **起始于**：项目根目录，例如：
     ```text
     D:\projects\football-betting-pipeline
     ```
6. 完成创建后，在任务列表中双击该任务 → **“触发器”** 选项卡 → **“编辑”**。把“重复任务间隔”改为 **1 天**，并点击 **“新建”** 再添加 7 个触发器，开始时间分别设为当天 **02:00、04:00、06:00、15:00、17:00、19:00、21:00、23:00**（各一个，每天重复）。  
   或：创建 **8 个独立的基本任务**，每个任务只在一个时间点运行（2 点、4 点、…、23 点），程序与“起始于”同上。

**说明**：若 `.env` 放在项目根目录，任务计划程序会从该目录启动，一般能自动加载；否则可在该任务的“操作”里改为运行一个你自己写的 `.bat`，在 `.bat` 里先 `cd` 到项目目录再执行 `python run_real.py`。

---

### macOS（launchd）

1. 使用项目根目录下的 `com.football.betting.run_real.plist`（或自行创建后放在 `~/Library/LaunchAgents/`）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.football.betting.run_real</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/你的用户名/Documents/cursor/football-betting-pipeline/.venv/bin/python</string>
    <string>run_real.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/你的用户名/Documents/cursor/football-betting-pipeline</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>4</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>StandardOutPath</key>
  <string>/Users/你的用户名/Documents/cursor/football-betting-log/football-betting-run-real.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/你的用户名/Documents/cursor/football-betting-log/football-betting-run-real.err</string>
</dict>
</plist>
```

2. 将其中 **Python 路径**、**WorkingDirectory**、**StandardOutPath/StandardErrorPath** 改为你本机的项目路径（若不用虚拟环境，`ProgramArguments` 第一项改为系统 `python3` 路径，如 `/usr/bin/python3`）。
3. 加载并启用：
   ```bash
   cp com.football.betting.run_real.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.football.betting.run_real.plist
   ```
4. 查看是否加载：`launchctl list | grep football`。停止：`launchctl unload ~/Library/LaunchAgents/com.football.betting.run_real.plist`。

**常用管理命令（macOS launchd）**：

```bash
# 查看定时任务是否已加载
launchctl list | grep football

# 停止定时任务（不再按点执行）
launchctl unload ~/Library/LaunchAgents/com.football.betting.run_real.plist

# 重新启用定时任务
launchctl load ~/Library/LaunchAgents/com.football.betting.run_real.plist
```

日志输出在 `{CRAWLER_DEBUG_LOG_DIR}/football-betting-run-real.log`，错误在 `{CRAWLER_DEBUG_LOG_DIR}/football-betting-run-real.err`。日志目录与 config.py 中 `CRAWLER_DEBUG_LOG_DIR` 一致（默认 `WORK_SPACE/football-betting-log`），请先创建：`mkdir -p <WORK_SPACE>/football-betting-log`。

---

#### 完场流程定时任务（每天 13 点执行 run_final.py）

完场流程（抓完场比分 → 写入图片）建议**每天 13 点**执行一次。使用项目根目录下的 `com.football.betting.run_final.plist`：

1. 将 plist 中的 **Python 路径**、**WorkingDirectory**、**StandardOutPath/StandardErrorPath** 改为你本机路径（与上述 pipeline plist 同一套路径，仅程序改为 `run_final.py`，日志可设为 `football-betting-run-final.log` / `.err`）。
2. 复制并加载：
   ```bash
   cp com.football.betting.run_final.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.football.betting.run_final.plist
   ```
3. 查看：`launchctl list | grep football`（会看到 `com.football.betting.run_real` 与 `com.football.betting.run_final` 两个任务）。

---

### Linux（cron）

1. 编辑当前用户 crontab：`crontab -e`。
2. 添加一行（整点 2、4、6、15、17、19、21、23 各执行一次）：

```cron
0 2,4,6,13,15,17,19,21,23 * * * /path/to/football-betting-pipeline/.venv/bin/python /path/to/football-betting-pipeline/run_real.py
```

或将 `python` 和 `run_real.py` 拆开，并保证在项目目录下执行：

```cron
0 2,4,6,13,15,17,19,21,23 * * * cd /path/to/football-betting-pipeline && .venv/bin/python run_real.py
```

**完场流程（每天 13 点）**：可再加一行

```cron
0 13 * * * cd /path/to/football-betting-pipeline && .venv/bin/python run_final.py
```

3. 将 `/path/to/football-betting-pipeline` 替换为实际项目根目录；若未使用虚拟环境，改为系统 `python3` 路径。
4. 保存退出。cron 会按系统时区在每天 02:00、04:00、06:00、15:00、17:00、19:00、21:00、23:00 执行。

**查看日志**：若未重定向，cron 输出会发到用户邮件；可改为 `... run_real.py >> /tmp/football-crawler.log 2>&1` 便于排查。

---