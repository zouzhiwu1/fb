# Football-betting

本系统通过网络爬虫抓取专业机构对比赛的评估数据，进行分析综合再评估，生成综合评估报告。然后对用户提供数据分析服务，主要针对手机移动端客户。

## 系统架构（三模块）

整体系统分为三个模块：

| 模块 | 职责 |
|------|------|
| **1. 数据抓取与数据分析** | 爬虫抓取、数据处理、生成曲线图图片 |
| **2. 用户管理系统** | 注册、登录、支付、**查询**（按日期/球队查曲线图等） |
| **3. 手机客户端** | React（Expo）实现，对接用户管理系统 |

- **模块 1** 输出：按日期目录存放的曲线图，供模块 2 读取。
- **模块 2**（用户管理系统）提供「曲线图查询」页面与 API，按日期、球队名搜索并展示曲线图。
- **模块 3** 提供安卓和苹果操作系统的移动端 App。

---

## 项目结构

```
football-betting/
├── README.md                    # 本文件
├── requirements.txt             # 顶层统一 Python 依赖（platform + pipeline 合并，可选使用）
├── football-betting-pipeline/   # 模块 1：爬虫 + 合并 + 计算 + 曲线图
│   ├── run_real.py              # 即时流程入口（crawl_real → merge_data → calc_car → plot_car）
│   ├── run_final.py             # 完场流程入口（crawl_final → add_score_to_image）
│   ├── crawl_real.py, merge_data.py, calc_car.py, plot_car.py
│   ├── config.py                # 配置（可被环境变量 / .env 覆盖）
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md                # 详细说明与定时任务配置
├── football-betting-platform/   # 模块 2：用户管理后端（Flask）
│   ├── run.py                   # 启动服务
│   ├── app/
│   ├── config.py
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── football-betting-mobile/     # 模块 3：移动端（Expo / React Native）
│   ├── package.json
│   └── README.md
├── football-betting-doc/        # 设计/架构文档
├── football-betting-data/       # 数据目录（爬虫 .xls、Master*.csv，按需创建或由 WORK_SPACE 指定）
├── football-betting-report/    # 报告目录（CAR*.xlsx、*_曲线.png，按需创建）
└── football-betting-log/       # 日志目录（run_real_*.log、run_final_*.log 等，按需创建）
```

`football-betting-data`、`football-betting-report`、`football-betting-log` 可由环境变量指定到其它路径，见下文「环境变量」。

---

## 环境要求

| 组件 | 要求 |
|------|------|
| **模块 1（pipeline）** | Python 3.10+、Chrome 浏览器（爬虫用 Selenium + webdriver-manager 自动管理驱动） |
| **模块 2（platform）** | Python 3.10+、MySQL 5.7+（或 8.x） |
| **模块 3（mobile）** | Node.js 18+、npm / yarn，开发时需 Expo Go 或模拟器 |

---

## 安装与运行

### 顶层统一依赖（可选）

若希望在一个虚拟环境中同时安装 **pipeline** 与 **platform** 的 Python 依赖，可在项目根目录使用顶层 `requirements.txt`：

```bash
cd football-betting
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

该文件由 `football-betting-platform/requirements.txt` 与 `football-betting-pipeline/requirements.txt` 合并去重得到。若只运行单一模块，也可直接进入对应子目录执行 `pip install -r requirements.txt`。

---

### 模块 1：数据抓取与曲线图（pipeline）

1. **安装依赖**

   ```bash
   cd football-betting-pipeline
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **配置（可选）**  
   复制 `.env.example` 为 `.env`，按需修改工作目录、跨天临界点、无头模式等。不配置则使用默认值（见 `config.py` 或 [pipeline 的 README](football-betting-pipeline/README.md)）。

3. **运行**

   ```bash
   # 自动按当前时间计算统计区间并执行：抓取 → 合并 → 计算 → 曲线图
   python run_real.py

   # 或指定时间区间（YYYYMMDDHH 各 10 位）
   python run_real.py 2026031312 2026031411
   ```

4. **定时任务**  
   建议用系统定时任务在固定整点执行 `python run_real.py`（如 2、4、6、13、15、17、19、21、23 点）；完场流程（抓完场比分并写入图片）可每天 13 点执行 `python run_final.py`。Windows 用「任务计划程序」，macOS 用 launchd，Linux 用 cron。详细步骤见 [football-betting-pipeline/README.md](football-betting-pipeline/README.md)。

---

### 模块 2：用户管理后端（platform）

1. **创建数据库**

   ```sql
   CREATE DATABASE football_betting CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

2. **配置环境变量**  
   复制 `football-betting-platform/.env.example` 为 `.env`，必填：

   - `DATABASE_URL`：MySQL 连接串，如  
     `mysql+pymysql://用户名:密码@localhost:3306/football_betting`
   - `JWT_SECRET_KEY`：随机长字符串，用于登录 token

   曲线图查询功能需让平台能访问 pipeline 生成的图片目录，可设置 `WORK_SPACE` 或 `CURVE_IMAGE_DIR` 与 pipeline 的 `CRAWLER_REPORT_DIR` 一致。

3. **安装并启动**

   ```bash
   cd football-betting-platform
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   python run.py
   ```

   服务默认在 `http://127.0.0.1:5001`。登录、注册、曲线图查询等见 [football-betting-platform/README.md](football-betting-platform/README.md)。

---

### 模块 3：移动端（mobile）

```bash
cd football-betting-mobile
npm install
npx expo start
```

按提示用 Expo Go 或模拟器打开。对接后端时需在 App 内配置 platform 的 API 地址。详见 [football-betting-mobile/README.md](football-betting-mobile/README.md)。

---

## 环境变量与配置

两处会读取环境变量（或项目根目录下的 `.env`，需安装 `python-dotenv`）：

- **football-betting-pipeline**：工作目录、爬虫地址、下载/报告/日志路径、跨天临界点、时区、无头模式、调试开关等。  
  完整列表见 [football-betting-pipeline/README.md#配置](football-betting-pipeline/README.md) 或 `football-betting-pipeline/.env.example`。

- **football-betting-platform**：数据库连接、JWT 密钥、短信配置、曲线图目录等。  
  见 `football-betting-platform/.env.example` 与 [football-betting-platform/README.md](football-betting-platform/README.md)。

### 常用环境变量速览（pipeline）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `WORK_SPACE` | 工作目录根路径（其下为 data/report/log） | 项目上一级目录 |
| `CRAWLER_DOWNLOAD_DIR` | 下载目录（.xls、Master*.csv） | `WORK_SPACE/football-betting-data` |
| `CRAWLER_REPORT_DIR` | 报告目录（CAR*.xlsx、*_曲线.png） | `WORK_SPACE/football-betting-report` |
| `CRAWLER_DEBUG_LOG_DIR` | 日志目录 | `WORK_SPACE/football-betting-log` |
| `CRAWLER_CUTOFF_HOUR` | 跨天临界点（0～23 时） | `12` |
| `CRAWLER_TIMEZONE` | 时区 | `Asia/Tokyo` |
| `CRAWLER_HEADLESS` | 爬虫无头模式：`1` 无头，`0` 有界面 | `1` |
| `CRAWLER_DEBUG_MAX_MATCHES` | 调试：最多抓取场数，0=不限制 | `0` |

### 常用环境变量速览（platform）

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | MySQL 连接串（必填） |
| `JWT_SECRET_KEY` | 登录 token 密钥（必填） |
| `WORK_SPACE` / `CURVE_IMAGE_DIR` | 曲线图目录，与 pipeline 输出一致时才能正确展示「曲线图查询」 |

---

## 部署要点

- **模块 1**：无 Web 服务，仅通过定时任务或命令行执行 `python run_real.py`（即时流程）或 `python run_final.py`（完场流程）。生产环境建议用 cron（Linux）或 launchd（macOS）在指定整点运行，并保证 `WORK_SPACE`（或各目录）指向持久化磁盘。
- **模块 2**：生产环境建议用 gunicorn/uWSGI 等托管 Flask，并配置 Nginx 反向代理；务必修改 `DATABASE_URL`、`JWT_SECRET_KEY`，并配置好 `CURVE_IMAGE_DIR` 以便曲线图查询。
- **模块 3**：按 Expo/React Native 流程打包为 Android/iOS 安装包，在 App 内配置生产环境 API 地址。

