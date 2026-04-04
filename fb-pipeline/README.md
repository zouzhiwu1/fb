# 网络爬虫

本仓库对应整体系统中的 **模块 1：数据抓取与曲线图生成**。打开智云比分页，抓取数据后经合并、计算，最终生成曲线图图片。

## 环境

- Python 3.10+
- Chrome 浏览器

## 安装

```bash
cd fb-pipeline
pip install -r requirements.txt
```

**说明（本地能跑、服务器报错「No module named …」）**：不是「服务器必须用 .venv、本地不用」，而是**两台机器上实际执行命令的 Python 往往不是同一个**。例如本地习惯 `python3` 且已装过依赖，服务器 cron 用 `python` 指向另一解释器且未装包。解决办法二选一：① 对**定时任务用的那条**解释器执行 `python -m pip install -r requirements.txt`；② 或用虚拟环境并把 cron 里的 `python` 写成该环境的 `python` 绝对路径（与是否叫 `.venv` 无关，本质是「固定用装过依赖的解释器」）。

## Docker / Linux 服务器：ChromeDriver `Status code was: 127`

若在容器或精简系统里出现：

`WebDriverException: Service .../chromedriver unexpectedly exited. Status code was: 127`

**含义**：`chromedriver` 这个可执行文件**没能真正跑起来**。常见原因不是「脚本路径错了」（`crawl_real.py` 已在执行），而是：

1. **缺少动态库**（最常见）：`python-webdriver-manager` 下载的 `chromedriver` 依赖 `libnss3`、`libgbm1`、`libgtk-3-0` 等，**slim/alpine 镜像未装 Chrome/Chromium 及依赖** 时会 127。  
2. **架构不符**：例如在 **ARM** 机器上用了 x86 的 driver（或反之）。

**容器内自检**（路径按报错里的 `/root/.wdm/.../chromedriver` 替换）：

```bash
ldd /root/.wdm/drivers/chromedriver/linux64/*/chromedriver   # 若有 "not found" 即缺库
/root/.wdm/drivers/chromedriver/linux64/*/chromedriver --version  # 看能否直接执行
```

**Debian/Ubuntu 系镜像建议**（在 Dockerfile 中安装 Chromium + 驱动 + 常用依赖，再 `pip install`；版本需与 `chromedriver` 大版本一致，或改用系统自带的 `chromium-driver`）：

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium chromium-driver \
    fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 libcairo2 libcups2 \
    libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 libgtk-3-0 libnspr4 libnss3 \
    libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
    libxkbcommon0 libxrandr2 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
```

在容器环境里指定 **系统 Chromium + chromedriver**（路径因发行版而异，Debian/Ubuntu 常见如下）：

```dockerfile
ENV CRAWLER_CHROME_BINARY=/usr/bin/chromium
ENV CRAWLER_CHROMEDRIVER_PATH=/usr/bin/chromedriver
```

或在 `.env` / `docker-compose` 的 `environment` 中写入同等变量。`crawl_real.create_driver()` 会优先使用上述路径，**不再**用 webdriver-manager 下载的 `chromedriver`，从而避免 slim 镜像缺库导致 **退出码 127**。

**不推荐在 Alpine 上跑官方 Linux chromedriver**（musl 与 glibc 二进制不兼容），请优先用 **debian-slim** 等 glibc 基础镜像。

### Docker / 服务器：`plot_car` 中文标题乱码或终端刷 `Glyph … missing`

Linux 精简镜像通常没有 macOS/Windows 的中文字体，Matplotlib 会退回 **DejaVu Sans**，无法绘制汉字，并出现大量 `findfont` / `Glyph missing` 警告。

在镜像中安装任一中文字体包即可，例如 Debian/Ubuntu：

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
```

或体积更小：`fonts-wqy-microhei`。装完后无需改代码，`plot_car` 会自动选用 Noto / 文泉驿等。

## 项目结构

```
fb-pipeline/
├── README.md                    # 本文件
├── run_real.py                  # 即时流程入口（crawl_real → merge_data → calc_car → plot_car）
├── run_final.py                 # 完场流程入口（crawl_final → add_score_to_image）
├── crawl_real.py                # 抓取即时比分并下载 .xls
├── merge_data.py                # 合并为 master_{YYYYMMDD}.csv
├── calc_car.py                  # 计算综合评估，输出 car_{YYYYMMDD}.xlsx
├── plot_car.py                  # 生成oupei/kaili曲线图 {主队}_VS_{客队}.png；成功后写入 evaluation_matches 入表
├── crawl_final.py               # 抓取完场比分，输出 final_{YYYYMMDD}.csv；并维护平台库 evaluation_matches 出表
├── add_score_to_image.py        # 将完场比分写入报告图片
├── evaluation_sync.py           # 与平台 MySQL evaluation_matches 同步（§3.4 入表/出表）
├── config.py                    # 配置（可被环境变量 / .env 覆盖）
├── log_cleanup.py               # 日志清理（按保留天数删除旧日志）
├── scraper_real.py              # 即时比分页爬虫逻辑
├── scraper_final.py             # 完场比分页爬虫逻辑
├── template.xlsx                # 一览表表头模板（merge_data 依赖）
├── requirements.txt
├── .env.example
├── com.fb.run_real.plist   # macOS launchd 即时流程定时任务（多整点）
├── com.fb.run_final.plist # macOS launchd 完场流程定时任务（每天 13 点）
├── gen_launchd_plist.sh                  # 根据 RUN_ROOT 生成 com.fb.run_real.plist
└── tests/                       # 单元测试
    ├── test_run_real.py
    ├── test_merge_data.py
    ├── test_calc_car.py
    ├── test_plot_car.py
    └── ...
```

数据与日志目录（默认在 `WORK_SPACE` 下，见 config.py）：`fb-data/`、`fb-report/`、`fb-log/`。

与 **fb-platform** 共用同一 MySQL 时，可在 `.env` 中设置 **`DATABASE_URL`**（与平台相同，如 `mysql+pymysql://user:pass@127.0.0.1:3306/fb`），以便 `plot_car` / `crawl_final` 自动维护 `evaluation_matches` 表；未设置则跳过同步，仅本地出图/出 CSV。

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

#### Docker：用 `.env` 代替一长串 `docker exec -e`

`config.py` 会通过 `python-dotenv` 加载：

1. **仓库根目录**下的 `.env`（即 `fb-pipeline` 的**上一级**目录）  
2. **`fb-pipeline/.env`**

容器里代码若在 `/app/fb-pipeline/`，可在宿主机编辑后拷入，例如：

```bash
# 在服务器上写好 app.env（勿提交密码到 Git）
docker cp ./app.env football-app:/app/.env
# 或：docker cp ./app.env football-app:/app/fb-pipeline/.env
```

`.env` 中写入（按实际改密码与路径）：

```env
WORK_SPACE=/app
CRAWLER_CHROME_BINARY=/usr/bin/chromium
CRAWLER_CHROMEDRIVER_PATH=
CHROMEDRIVER_PATH=
DATABASE_URL=mysql+pymysql://root:密码@football-db:3306/fb
```

之后每次只需：

```bash
docker exec -it football-app python fb-pipeline/run_real.py
```

若使用 **docker-compose**，也可把上述变量写在服务的 `environment:` 或 `env_file: ./app.env` 里，效果相同。

#### Docker：Linux 定时任务（cron）

在 **ECS 宿主机**（不是容器里）配置 cron，到点执行 `docker exec`。  
**不要**加 `-t`（无终端），建议保留 `-i` 可选。

默认整点与 `config.TRIGGER_HOURS` 一致时为：`2,4,6,13,15,17,19,21,23`（与 `CRAWLER_TRIGGER_HOURS` 可改）。

**1）时区**  
业务逻辑里的「当前时间」由 `CRAWLER_TIMEZONE`（默认 `Asia/Tokyo`）决定；**cron 触发时刻**默认跟 **系统时区** 走。若 ECS 是 UTC、你希望按 **东京整点** 跑，在 crontab **第一行**加（GNU cron）：

```cron
CRON_TZ=Asia/Tokyo
```

**2）编辑 root 的 crontab**

```bash
sudo crontab -e
```

**3）示例（整点跑即时流程；路径与容器名按实际修改）**

```cron
CRON_TZ=Asia/Tokyo
0 2,4,6,13,15,17,19,21,23 * * * docker exec football-app python /app/fb-pipeline/run_real.py >> /var/log/football-run-real.log 2>&1
```

- 环境变量已放进容器内 `/app/.env` 时，这里**不必**再写一长串 `-e`。  
- 日志：`>> ... 2>&1` 可改成你宿主机上的目录（需可写）。  
- 容器名若不是 `football-app`，用 `docker ps` 查看后替换。

**4）完场流程（若需要）**  
例如每天东京时间 **13:00** 跑一次（与仓库内 `run_final` 定时设计一致时可对齐）：

```cron
CRON_TZ=Asia/Tokyo
0 13 * * * docker exec football-app python /app/fb-pipeline/run_final.py >> /var/log/football-run-final.log 2>&1
```

**5）自检**

```bash
# 看下次 cron 是否加载成功
sudo crontab -l

# 手动模拟定时任务（与 cron 同一条命令）
docker exec football-app python /app/fb-pipeline/run_real.py
```

也可用 **systemd timer** 替代 cron，写法不同但思路相同：到点 `docker exec`。

### 2）完场流程入口：run_final.py

```bash
# 使用昨日日期（抓完场比分 → 写入图片）
python run_final.py

# 指定日期
python run_final.py 20260314
```

- 依次执行：`crawl_final.py`（抓取完场比分）→ `add_score_to_image.py`（将比分写入报告图片）。  
- 建议用**定时任务每天 13 点**执行一次（见下方「完场定时任务」）。曲线图查询功能已迁移至 **fb-platform**，请在该项目中启动服务并访问「曲线图查询」页面。

## 脚本说明

### crawl_real.py — 抓取即时比分数据

**功能**：打开智云比分页，进入「足球」→「即时比分」→「zucai」→「beidan」，等待表格刷新后，仅下载状态为空的比赛（状态列为空白或「-」），逐场点击导出并下载对应的 `.xls` 文件。文件按配置的下载目录与跨天临界点保存到子目录 `{YYYYMMDD}/`，文件名含主客队与时间点（如 `主队_VS_客队_2026030807.xls`）。

**用法**（仅接收两个时间点参数，形式与其它批处理脚本一致）：

```bash
python crawl_real.py <起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>
```

当前版本中，crawl 实际仍按“执行当下的”抓取，时间参数主要用于：

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

### plot_car.py — 生成oupei/kaili曲线图

**功能**：根据综合评估表 `car_{YYYYMMDD}.xlsx` 为每场比赛生成一张图，包含两个子图：**oupei指数曲线图**（主/平/客三条曲线，第 1 节点为初指 D/E/F，其余节点为各时间点jishipan G/H/I）、**kailizhishu曲线图**（主/平/客三条曲线，X 轴为时间点 C，Y 轴为 J/K/L）。曲线节点数量由表中该场比赛的时间点数量决定，不固定。详见 design.md 第 3.3 节。

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

- **功能**：打开智云比分页，进入「足球」→「完场比分」→「zucai」→「beidan」，等待表格刷新后抓取每行的**主队、客队、比分**，输出 CSV 供后续写入报告图片。
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
| `WORK_SPACE` | 工作目录根路径，其下默认放置 fb-data、fb-report、fb-log；改此处即可统一改默认路径 | `项目根目录上一层（例如 /Users/zhiwuzou/Documents/app/fb）` |
| `CRAWLER_BASE_URL` | 智云比分页面地址 | `https://live.nowscore.com/2in1.aspx` |
| `CRAWLER_DOWNLOAD_DIR` | 下载目录：crawl 的 .xls、merge_data 的 master_{YYYYMMDD}.csv 均在此目录下按 YYYYMMDD 子目录存放 | 默认 `WORK_SPACE/fb-data` |
| `CRAWLER_REPORT_DIR` | 报告目录：calc_car 的 car_{YYYYMMDD}.xlsx、plot_car 的 {主队}_VS_{客队}.png 写入此目录下对应的 YYYYMMDD 子目录 | 默认 `WORK_SPACE/fb-report` |
| `CRAWLER_CUTOFF_HOUR` | 跨天临界点（0～23 时）。该时及之后 → 当日文件夹；该时之前 → 前一日文件夹；`run_real.py` 也据此划分 24 小时逻辑区间 | `12` |
| `CRAWLER_TIMEZONE` | 用于“当前时间”的时区（决定下载目录/文件名） | `Asia/Tokyo` |
| `CRAWLER_HEADLESS` | `1` 无头模式（不弹窗），`0` 有浏览器界面 | `1` |
| `CRAWLER_DEBUG_LOG_DIR` | 日志目录：crawl/merge_data 等日志、调试用 `debug_export_page_*.html` 的存放路径 | 默认 `WORK_SPACE/fb-log` |
| `CRAWLER_LOG_RETENTION_DAYS` | 日志保留天数，超过此天数的日志文件会在运行前被删除 | `7` |
| `CRAWLER_TRIGGER_HOURS` | 定时任务触发整点（逗号分隔，0～23），仅影响 `run_real.py` 无参数时的区间计算 | `2,4,6,13,15,17,19,21,23` |
| `CRAWLER_DEBUG_MAX_MATCHES` | **调试用**：最多抓取场数，`0` 表示不限制；设为正整数（如 `3`）则只抓前 N 场即结束，便于快速跑通流程 | `0` |
| `CRAWLER_DEBUG_MATCH_KEYWORDS` | **调试用**：仅抓取主队或客队名称包含任一关键词的比赛，逗号分隔。例如 `帕纳辛纳科斯,里尔,博洛尼亚`。不设或为空则抓取全部 | 未设置 |
| `CRAWLER_MATCH_FILTER_VISIBLE_ONLY` | `run_real` 列表**可视过滤**：`1` 只处理页面上可见行（与「隐藏 N 场」一致）；`0` 则包含 DOM 内隐藏行 | `1` |
| `CRAWLER_MATCH_STATUS_MODES` | `run_real` 列表**状态过滤**，逗号分隔、并集：`not_started`（未开场，空白或 `-`）、`live`（进行中）、`finished`（状态列含「完」） | `not_started` |
| `CRAWLER_ALLOW_GLOBAL_TABLE_LIVE` | `1` 时在 ScoreDiv 内找不到主表则回退全局 `#table_live`（与完场逻辑类似；Docker/页面与本地不一致时可试） | 未启用 |
| `CRAWLER_WAIT_ELEMENT` | Selenium 显式等待秒数上限（跨境、弱网、容器慢） | `20` |
| `CRAWLER_PAGE_LOAD_STRATEGY` | `driver.get` 策略：`eager` 在 DOM 可交互后返回，减少因广告/统计请求卡住导致的 **HTTP read timeout**；`normal` / `none` 见 Selenium 文档 | `eager` |
| `CRAWLER_PAGE_LOAD_TIMEOUT` | 浏览器导航超时（秒），`0` 表示不限制 | `90` |
| `CRAWLER_SELENIUM_READ_TIMEOUT` | Python ↔ chromedriver 单次 HTTP 读超时（秒），应大于慢速首屏耗时 | `240` |

联赛白名单仍由 `config.py` 中 `TARGET_LEAGUE_NAMES` / 环境变量 `CRAWLER_TARGET_LEAGUES` 控制（见该文件注释）。

### 环境变量的使用方式

**1. 使用 .env 文件（推荐）**

在项目根目录（与 `run_real.py` 同级）创建 `.env`，每行一个变量，格式：`变量名=值`。  
运行 `python run_real.py` 或 `python crawl_real.py ...` 时会自动加载，无需在终端里重复设置。

```bash
# 示例：只改路径和是否无头
WORK_SPACE=/Users/xxx/Documents/fb
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
# CRAWLER_DOWNLOAD_DIR=/path/to/zuqiucaipiao/beidan
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
     D:\projects\fb-pipeline\.venv\Scripts\python.exe
     ```
   - **添加参数**：`run_real.py`
   - **起始于**：项目根目录，例如：
     ```text
     D:\projects\fb-pipeline
     ```
6. 完成创建后，在任务列表中双击该任务 → **“触发器”** 选项卡 → **“编辑”**。把“重复任务间隔”改为 **1 天**，并点击 **“新建”** 再添加 7 个触发器，开始时间分别设为当天 **02:00、04:00、06:00、15:00、17:00、19:00、21:00、23:00**（各一个，每天重复）。  
   或：创建 **8 个独立的基本任务**，每个任务只在一个时间点运行（2 点、4 点、…、23 点），程序与“起始于”同上。

**说明**：若 `.env` 放在项目根目录，任务计划程序会从该目录启动，一般能自动加载；否则可在该任务的“操作”里改为运行一个你自己写的 `.bat`，在 `.bat` 里先 `cd` 到项目目录再执行 `python run_real.py`。

---

### macOS（launchd）

1. 使用项目根目录下的 `com.fb.run_real.plist`（或自行创建后放在 `~/Library/LaunchAgents/`）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.fb.run_real</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/你的用户名/Documents/cursor/fb-pipeline/.venv/bin/python</string>
    <string>run_real.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/你的用户名/Documents/cursor/fb-pipeline</string>
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
  <string>/Users/你的用户名/Documents/cursor/fb-log/fb-run-real.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/你的用户名/Documents/cursor/fb-log/fb-run-real.err</string>
</dict>
</plist>
```

2. 将其中 **Python 路径**、**WorkingDirectory**、**StandardOutPath/StandardErrorPath** 改为你本机的项目路径（若不用虚拟环境，`ProgramArguments` 第一项改为系统 `python3` 路径，如 `/usr/bin/python3`）。
3. 加载并启用：
   ```bash
   cp com.fb.run_real.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.fb.run_real.plist
   ```
4. 查看是否加载：`launchctl list | grep com.fb`。停止：`launchctl unload ~/Library/LaunchAgents/com.fb.run_real.plist`。

**常用管理命令（macOS launchd）**：

```bash
# 查看定时任务是否已加载
launchctl list | grep com.fb

# 停止定时任务（不再按点执行）
launchctl unload ~/Library/LaunchAgents/com.fb.run_real.plist

# 重新启用定时任务
launchctl load ~/Library/LaunchAgents/com.fb.run_real.plist
```

日志输出在 `{CRAWLER_DEBUG_LOG_DIR}/fb-run-real.log`，错误在 `{CRAWLER_DEBUG_LOG_DIR}/fb-run-real.err`。日志目录与 config.py 中 `CRAWLER_DEBUG_LOG_DIR` 一致（默认 `WORK_SPACE/fb-log`），请先创建：`mkdir -p <WORK_SPACE>/fb-log`。

---

#### 完场流程定时任务（每天 13 点执行 run_final.py）

完场流程（抓完场比分 → 写入图片）建议**每天 13 点**执行一次。使用项目根目录下的 `com.fb.run_final.plist`：

1. 将 plist 中的 **Python 路径**、**WorkingDirectory**、**StandardOutPath/StandardErrorPath** 改为你本机路径（与上述 pipeline plist 同一套路径，仅程序改为 `run_final.py`，日志可设为 `fb-run-final.log` / `.err`）。
2. 复制并加载：
   ```bash
   cp com.fb.run_final.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.fb.run_final.plist
   ```
3. 查看：`launchctl list | grep com.fb`（会看到 `com.fb.run_real` 与 `com.fb.run_final` 两个任务）。

---

### Linux（cron）

1. 编辑当前用户 crontab：`crontab -e`。
2. 添加一行（整点 2、4、6、15、17、19、21、23 各执行一次）：

```cron
0 2,4,6,13,15,17,19,21,23 * * * /path/to/fb-pipeline/.venv/bin/python /path/to/fb-pipeline/run_real.py
```

或将 `python` 和 `run_real.py` 拆开，并保证在项目目录下执行：

```cron
0 2,4,6,13,15,17,19,21,23 * * * cd /path/to/fb-pipeline && .venv/bin/python run_real.py
```

**完场流程（每天 13 点）**：可再加一行

```cron
0 13 * * * cd /path/to/fb-pipeline && .venv/bin/python run_final.py
```

3. 将 `/path/to/fb-pipeline` 替换为实际项目根目录；若未使用虚拟环境，改为系统 `python3` 路径。
4. 保存退出。cron 会按系统时区在每天 02:00、04:00、06:00、15:00、17:00、19:00、21:00、23:00 执行。

**查看日志**：若未重定向，cron 输出会发到用户邮件；可改为 `... run_real.py >> /tmp/football-crawler.log 2>&1` 便于排查。

---