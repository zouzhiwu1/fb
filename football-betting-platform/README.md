# football-betting-platform

用户管理后端（注册、登录），使用 MySQL，注册时通过手机号 + 短信验证码校验。

## 技术栈

- Python 3.10+
- Flask + Flask-SQLAlchemy + PyMySQL
- JWT 登录态
- 短信验证码：默认 mock（写入 `football-betting-log/platform_YYYYMMDD.log`），可接阿里云/腾讯云等

## 本地运行

### 1. 创建 MySQL 数据库

```sql
CREATE DATABASE football_betting CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. 环境变量

复制 `.env.example` 为 `.env`，填写：

- `DATABASE_URL`：MySQL 连接串，例如  
  `mysql+pymysql://YOUR_MYSQL_USER:YOUR_MYSQL_PASSWORD@localhost:3306/football_betting`
- `JWT_SECRET_KEY`：任意随机长字符串，用于签发登录 token

不填短信相关则使用 mock，验证码会记入 **`football-betting-log/platform_YYYYMMDD.log`**（`[SMS Mock]` 行）。

### 3. 安装依赖

```bash
cd football-betting-platform
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

服务默认端口 `5001`（可在 `.env` 中设置 `PORT`）。

### 4. 启动（统一入口，后台 + 日志）

业务日志始终在 **`football-betting-log/platform_YYYYMMDD.log`**（与 `football-betting-platform` 同级的 `football-betting-log` 目录，例如 `/root/projects/football-betting/football-betting-log/platform_20260325.log`）。

| 环境 | 命令（在 `football-betting-platform` 目录下） |
|------|-----------------------------------------------|
| **macOS** | `chmod +x run_mac.sh && ./run_mac.sh` |
| **Linux（云服务器等）** | `chmod +x run_linux.sh && ./run_linux.sh` |

- **macOS**：`nohup` 后台运行；同目录会写 `.platform.pid`，再次执行会先停旧进程再起。
- **Linux**：首次运行会提示 **sudo**，自动安装 systemd 并启动；之后再执行同一脚本只做 **`systemctl restart`**。若无 systemd，会退化为与 Mac 相同的 `nohup`。
- **排查**：`tail -f ../football-betting-log/platform_$(date +%Y%m%d).log`；Linux 还可 `sudo systemctl status football-betting-platform`、`sudo journalctl -u football-betting-platform -f`。
- **仅调试、要前台看控制台**：`./scripts/run.sh`（关终端即停）。
- 若修改了 `scripts/football-betting-platform.service.example` 或更换了部署路径，可先删掉 `/etc/systemd/system/football-betting-platform.service` 后再执行 **`./run_linux.sh`**，或直接 **`sudo ./scripts/install-systemd.sh`**。

### 5. 网页

- **登录**：http://127.0.0.1:5001/login  
- **注册**：http://127.0.0.1:5001/register（新用户可点「去注册」进入）  
- **首页**：登录成功后跳转 http://127.0.0.1:5001/home  
- **账户资料**：http://127.0.0.1:5001/account（需已登录；展示注册时的用户名、性别、手机、邮箱、注册时间；可修改密码、手机号、邮箱）  
- **会员信息**：http://127.0.0.1:5001/membership（需已登录；会员状态、最晚到期时间、剩余天数、当前有效权益明细表、注册赠送周会员是否已发放）  
- **会员充值**：http://127.0.0.1:5001/recharge（需已登录；选择档位、创建订单，展示回调地址与本地 mock 脚本示例）  
- **充值信息**：http://127.0.0.1:5001/recharge-records（需已登录；列表查询当前账号的 `payment_orders`，默认最近 100 条：状态、金额、支付时间、渠道流水号等）  
- **曲线图查询**：http://127.0.0.1:5001/curves（按日期、球队名搜索并展示 football-betting-pipeline 生成的曲线图；需在 `.env` 中配置 `CURVE_IMAGE_DIR` 与 pipeline 的输出目录一致）  
  非会员能否查看某场，由 MySQL 表 `evaluation_matches` 判定（见《会员系统设计书》§3.3）；该表由 pipeline 在出图/完场流程中维护（§3.4），pipeline 需配置与平台相同的 `DATABASE_URL`。

注册需填写：用户名、性别、密码、手机号、邮箱；手机号需先「获取验证码」（mock 下请在同目录日志文件查看 `[SMS Mock]`）。

若之前已创建过 `users` 表且没有 `username`/`gender`/`email` 列，请在 MySQL 中执行：

```sql
ALTER TABLE users ADD COLUMN username VARCHAR(64) NULL, ADD COLUMN gender VARCHAR(10) NULL, ADD COLUMN email VARCHAR(128) NULL;
ALTER TABLE users ADD UNIQUE KEY username (username);
```

## API 说明

### 发送验证码

- **POST** `/api/auth/send-code`
- Body: `{ "phone": "13800138000" }`
- 成功: `{ "ok": true, "message": "验证码已发送" }`
- 频率限制：同一手机 60 秒内只能发一次

### 注册（手机号 + 验证码）

- **POST** `/api/auth/register`
- Body: `{ "phone": "13800138000", "code": "123456", "password": "可选" }`
- 成功: `{ "ok": true, "user": {...}, "token": "jwt..." }`

### 登录

- **POST** `/api/auth/login`
- 方式一（验证码）：`{ "phone": "13800138000", "code": "123456" }`
- 方式二（密码）：`{ "phone": "13800138000", "password": "xxx" }`
- 成功: `{ "ok": true, "user": {...}, "token": "jwt..." }`

后续请求在 Header 中携带：`Authorization: Bearer <token>` 即可（后续支付、查询等接口会用到）。

### 当前用户与账户修改

- **GET** `/api/auth/me` — Header: `Authorization: Bearer <token>`  
  返回 `user`：`username`、`gender`、`phone`、`email`、`created_at`、**`password_set`**（是否已设置密码，便于前端提示「当前密码」是否必填）。

- **POST** `/api/auth/change-password` — Body: `{ "current_password": "...", "new_password": "..." }`  
  已设置过密码时必须填对 `current_password`；若账号从未设置密码（仅验证码登录过），可只传 `new_password` 完成首次设置。新密码至少 6 位。

- **POST** `/api/auth/change-email` — Body: `{ "email": "new@example.com" }`  
  邮箱会规范为小写；不能与已被其他账号占用的邮箱重复。

- **POST** `/api/auth/change-phone` — Body: `{ "new_phone": "13800138000", "code": "123456" }`  
  需先对**新手机号**调用 **`/api/auth/send-code`** 获取验证码；不能与当前手机号相同、不能占用他人已注册手机号。成功后请使用新手机号登录（JWT 仍有效直至过期）。

### 会员状态

- **GET** `/api/membership/status`  
- Header: `Authorization: Bearer <token>`  
- 返回字段：  
  - **`is_member`**：当前是否为有效会员（存在 `effective_at <= now < expires_at` 的记录）。  
  - **`expires_at`**：所有**当前有效**权益中**最晚**的到期时间（ISO 字符串）；非会员为 `null`。  
  - **`active_records`**：当前仍在有效期内的权益明细列表；每项含 `membership_type`、`membership_type_label`（中文档名）、`effective_at`、`expires_at`、`source`（`gift`/`purchase`）、`source_label`、`order_id`（购买时有值）。  
  - **`free_week_granted_at`**：若注册时曾成功发放过赠送周会员，为该操作时间（ISO）；否则 `null`。  

网页 **`/membership`** 使用上述接口展示状态、到期时间与表格明细。

### 会员充值（支付宝）流程

以下为**标准对接方式**下的端到端说明；用户的钱在**支付宝侧**完成支付，本系统**不**直接经手用户银行卡/余额，仅通过支付宝异步通知确认到账后再开通会员。

1. **客户端 → 本系统：创建商户订单**  
   用户登录后，客户端携带 `Authorization: Bearer <token>` 调用 **`POST /api/pay/orders`**（例如 body 指定 `membership_type`：周/月/季/年）。  
   本系统在库中生成 **`payment_orders`** 记录（含商户订单号 `out_trade_no`、金额、`notify_url` 等），并将订单信息返回给客户端。

2. **本系统 → 支付宝：发起待支付订单（预下单 / 获取支付参数）**  
   服务端使用支付宝开放平台提供的接口（如**手机网站支付**、**APP 支付**等，依客户端形态选择），用 **应用私钥** 对请求签名，向支付宝发起**一笔待用户支付的订单**。  
   支付宝返回**签名后的支付参数**、或**收银台链接**、或由客户端 SDK 调起支付所需的数据。  
   **注意**：这一步是「让用户去支付宝付钱」的凭证，**不是**本系统代替用户完成转账。

3. **客户端 → 支付宝：用户完成支付**  
   客户端使用第 2 步拿到的参数**调起支付宝**（跳转 H5 收银台、唤起支付宝 App、或 APP 内 SDK 等），用户在**支付宝**完成付款。

4. **支付宝 → 本系统：异步通知（`notify_url`）**  
   支付成功后，支付宝向你在下单时配置的 **`notify_url`**（本系统为 **`POST /api/pay/alipay/notify`**）发送 **POST** 表单通知（`application/x-www-form-urlencoded`）。  
   本系统必须 **验签**、核对 `out_trade_no` 与 `total_amount` 与本地订单一致，并 **幂等** 处理（同一订单多次通知只发货一次）。

5. **本系统：开通会员**  
   验签与业务校验通过后，写入 **`membership_records`**（`source=purchase`，`order_id=out_trade_no`），并将订单标为已支付。  
   **开通会员必须以异步通知（或服务端主动「查单」确认）为准**；不要仅依赖用户支付完成后的**同步跳转页**或纯前端回调，避免丢单或伪造。

**与本仓库当前实现的关系**：已实现第 1 步（建单并返回订单信息）、第 4～5 步（回调验签 + 开通会员，含 mock / RSA 两种模式）。第 2～3 步需你在服务端集成支付宝官方 SDK，在创建本系统订单成功后追加「向支付宝下单并返回支付参数给客户端」的逻辑。

#### 时序图（支付宝支付）

```mermaid
sequenceDiagram
    autonumber
    participant C as 客户端
    participant P as 本系统 Platform
    participant AO as 支付宝开放平台
    participant AP as 支付宝收银台/App
    participant N as 异步通知来源

    Note over P,AO: 预下单需支付宝 SDK + 应用私钥，本仓库未实现
    C->>P: POST /api/pay/orders（Authorization: Bearer JWT）
    P->>P: 写入 payment_orders（pending）
    P-->>C: out_trade_no、total_amount、notify_url 等

    P->>AO: 预下单（SDK 签名，可选步骤）
    AO-->>P: 支付参数 / 收银台 URL
    P-->>C: 返回支付参数给前端
    C->>AP: 调起收银台 / App，用户完成付款

    Note over N,P: 生产环境 N=支付宝；本地联调 N=simulate_alipay_notify.py
    N->>P: POST /api/pay/alipay/notify（form 表单）
    P->>P: payment_providers.alipay 验签
    P->>P: payment_fulfillment 校验订单与金额、幂等
    P->>P: add_membership + 更新订单 paid
    P-->>N: 纯文本 success（失败则 fail，按渠道重试策略）
```

**时序图上的 ①②③…（`autonumber`）和下面 curl「0）～6）」是什么关系？**

| 说明 | 内容 |
|------|------|
| **①②③…** | Mermaid 按**箭头出现顺序**自动编号，描述**完整生产流程**（建单 → 预下单 → 用户支付 → 异步通知 → 验签履约 → 回 `success`）。 |
| **0）～2）** | 仅为在终端里**拿到 JWT**（发码、登录、`export TOKEN`），**不在时序图里**；图里默认「客户端已登录」。 |
| **3）** | 可选：查会员状态，**也不画在支付主路径上**。 |
| **4）** | 对应时序图 **「客户端 → 本系统：POST /api/pay/orders」** 及紧挨的写库、响应（图中靠前的几条消息）。 |
| **5）** | 本地**不经过**图中「预下单 → 收银台付款」那段；用脚本**直接扮演「异步通知来源 N」** 调用 **`/api/pay/alipay/notify`**，对应图中 **N → P 及之后**的验签、履约、回 `success`。 |
| **6）** | 再调 **`/api/membership/status`** 核对是否已开通；这是**人工验收步骤**，时序图里一般不再单独画一条线。 |

简记：**0～3 = 测接口前的登录准备；4 = 图的前半段建单；5 = 图的后半段通知（本地用脚本代替真支付宝）；6 = 查结果。**

#### curl 本地联调备注（对应时序图）

以下默认服务 **`http://127.0.0.1:5001`**（`python run.py`）；请将示例中的手机号、验证码、`TOKEN` 换成你本机真实值。

**0）发验证码（mock 下验证码在 `football-betting-log/platform_YYYYMMDD.log` 的 `[SMS Mock]` 行）**

```bash
curl -s -X POST http://127.0.0.1:5001/api/auth/send-code \
  -H "Content-Type: application/json" \
  -d '{"phone":"13800138000"}'
```

**1）登录，取得 `token`（把 `CODE` 换成终端里的 6 位验证码）**

```bash
curl -s -X POST http://127.0.0.1:5001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone":"13800138000","code":"CODE"}'
```

**2）导出 token（把下面引号内换成上一步 JSON 里的 `token` 整段）**

```bash
export TOKEN='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9....'
```

**3）（可选）先验证登录态 —— 对应「已登录用户查会员」**

```bash
curl -s http://127.0.0.1:5001/api/membership/status \
  -H "Authorization: Bearer $TOKEN"
```

**4）创建商户订单 —— 对应时序图「POST /api/pay/orders」**

```bash
curl -s -X POST http://127.0.0.1:5001/api/pay/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"membership_type":"month"}'
```

记下返回 JSON 中的 **`out_trade_no`**、**`total_amount`**（须与库中订单一致）。

**5）模拟支付宝异步通知 —— 对应时序图「POST /api/pay/alipay/notify」**  
（生产环境由支付宝服务器发起；本地用脚本代替 **`N`**。若 `.env` 配置了 `ALIPAY_MOCK_SECRET`，需增加 `--mock-secret` 参数。）

```bash
cd football-betting-platform
python3 scripts/simulate_alipay_notify.py \
  --base-url http://127.0.0.1:5001 \
  --out-trade-no <上一步 out_trade_no> \
  --total-amount <上一步 total_amount> \
  --mock-secret <仅当配置了 ALIPAY_MOCK_SECRET 时填写>
```

脚本输出中 HTTP 响应体应为 **`success`**。

**6）再次查询会员 —— 确认履约（`payment_fulfillment`）已写入权益**

```bash
curl -s http://127.0.0.1:5001/api/membership/status \
  -H "Authorization: Bearer $TOKEN"
```

**提示**：zsh 下请勿把 JSON 响应多行粘贴执行，易触发 `command not found: message:`；长命令可写成一行，或 `-d @body.json` 从文件读 body。

#### 单元测试（支付宝与本节 curl 对应）

在项目根目录 `football-betting-platform` 下执行（需已配置可测的 `DATABASE_URL`，与 `tests/conftest.py` 一致）：

```bash
cd football-betting-platform
python3 -m pytest tests/test_pay.py tests/test_alipay_notify.py -v
```

- **`tests/test_pay.py`**：`POST /api/pay/orders`、mock 模式下 `POST /api/pay/alipay/notify` 与履约（`payment_fulfillment`）等。  
- **`tests/test_alipay_notify.py`**：支付宝签名字符串拼装（不启 Flask）。  

可加 `-q` 精简输出；全量回归：`python3 -m pytest tests/ -q`。

### 会员充值（微信支付）流程

与支付宝类似：用户的钱在**微信侧**完成支付，本系统仅通过**微信支付结果通知**确认到账后再开通会员；**同一套**商户订单仍由 **`POST /api/pay/orders`** 创建（与支付宝共用 `out_trade_no` / `payment_orders`）。

1. **客户端 → 本系统：创建商户订单**（同上，返回中额外包含 **`wechat_notify_url`**。）

2. **本系统 → 微信：统一下单 / 获取预支付参数**  
   使用微信支付商户 API（如 JSAPI、APP、H5 等），用商户证书或 API 密钥签名，换取 **`prepay_id`** 等，交给客户端调起支付。本仓库**未实现**该步，需你自行接官方 SDK 或 HTTP。

3. **客户端 → 微信：用户完成支付**  
   客户端调起微信收银台，用户在**微信**内付款。

4. **微信 → 本系统：支付结果通知**  
   微信向 **`notify_url`**（本系统为 **`POST /api/pay/wechat/notify`**）POST 通知。生产常见为 **XML** 正文；本服务亦支持联调用的 **JSON**。  
   本系统验签（mock / 微信 V2 MD5）、核对 `out_trade_no` 与金额、**幂等**发货。

5. **本系统：开通会员**  
   与支付宝相同：走 **`payment_fulfillment`**（`VerifiedPayment` + `DefaultMembershipFulfillment`），`payment_orders.trade_no` 存微信 **`transaction_id`**。

**与本仓库当前实现的关系**：已实现第 1、4、5 步（建单 + 回调解析/验签 + 开通会员）；第 2～3 步需对接微信官方接口。

#### 时序图（微信支付）

```mermaid
sequenceDiagram
    autonumber
    participant C as 客户端
    participant P as 本系统 Platform
    participant WX as 微信支付/API
    participant WP as 微信客户端/收银台
    participant N as 异步通知来源

    Note over P,WX: 统一下单需微信商户配置 + SDK/HTTP，本仓库未实现
    C->>P: POST /api/pay/orders（Authorization: Bearer JWT）
    P->>P: 写入 payment_orders（pending）
    P-->>C: out_trade_no、total_amount、wechat_notify_url 等

    P->>WX: 统一下单（签名，可选步骤）
    WX-->>P: prepay_id / 调起参数
    P-->>C: 返回调起参数给前端
    C->>WP: 调起支付，用户完成付款

    Note over N,P: 生产环境 N=微信；本地联调 N=simulate_wechat_notify.py
    N->>P: POST /api/pay/wechat/notify（JSON 或 XML）
    P->>P: payment_providers.wechat 验签/解析
    P->>P: payment_fulfillment 校验订单与金额、幂等
    P->>P: add_membership + 更新订单 paid
    P-->>N: XML：return_code SUCCESS（失败则 FAIL，按渠道重试）
```

**时序图编号与下面 curl「0）～6）」的对应关系**（与支付宝一节相同约定）：

| 说明 | 内容 |
|------|------|
| **①②③…** | 自动编号表示完整生产路径：建单 → 统一下单 → 用户支付 → 异步通知 → 验签履约 → 回包。 |
| **0）～3）** | 登录准备 / 可选查会员，**不在图内**。 |
| **4）** | **客户端 → 本系统：`POST /api/pay/orders`**（与支付宝共用，一次建单可同时用于后续选支付宝或微信预下单）。 |
| **5）** | 本地用 **`simulate_wechat_notify.py`** 扮演 **N**，请求 **`/api/pay/wechat/notify`**；对应图中 **N → P** 及后续。 |
| **6）** | **`GET /api/membership/status`** 人工验收。 |

#### curl 本地联调备注（微信支付，对应时序图）

**0）～4）** 与上文支付宝一节相同（同一 `TOKEN`、同一 **`POST /api/pay/orders`**）。记下返回中的 **`out_trade_no`**、**`total_amount`**。

**5）模拟微信支付结果通知 —— 对应时序图「POST /api/pay/wechat/notify」**  
（生产由微信服务器发起；本地用脚本代替 **N**。若配置了 `WECHAT_MOCK_SECRET`，需传 `--mock-secret` 或设置环境变量。）

默认发 **JSON**（与 curl 一致）；加 **`--xml`** 更接近生产 XML：

```bash
cd football-betting-platform
python3 scripts/simulate_wechat_notify.py \
  --base-url http://127.0.0.1:5001 \
  --out-trade-no <上一步 out_trade_no> \
  --total-amount <上一步 total_amount> \
  --mock-secret <仅当配置了 WECHAT_MOCK_SECRET 时填写>
```

或使用微信 **`total_fee`（分）**：

```bash
python3 scripts/simulate_wechat_notify.py \
  --base-url http://127.0.0.1:5001 \
  --out-trade-no <上一步 out_trade_no> \
  --total-fee 2990
```

成功时响应体为 **XML**，正文含 **`return_code`** 为 **`SUCCESS`**（CDATA 或纯文本均可被脚本判定）。

**6）再次查询会员** —— 同支付宝一节。

#### 单元测试（微信支付与本节 curl 对应）

```bash
cd football-betting-platform
python3 -m pytest tests/test_wechat_notify.py tests/test_wechat_pay.py -v
```

- **`tests/test_wechat_notify.py`**：V2 签名字符串、MD5 签名、XML 解析等（不启 Flask）。  
- **`tests/test_wechat_pay.py`**：mock 通知（JSON/XML + `total_fee`）、履约注入、创建订单响应中含 `wechat_notify_url` 等。

**一次性跑通支付宝 + 微信支付相关用例**：

```bash
cd football-betting-platform
python3 -m pytest tests/test_pay.py tests/test_alipay_notify.py tests/test_wechat_notify.py tests/test_wechat_pay.py -q
```

### 充值档位与订单列表（API）

- **GET** `/api/pay/membership-options`（无需登录）  
  返回各档 **`membership_type`**、中文 **`label`**、**`price`**（元），与 `MEMBERSHIP_PRICES` / `MEMBERSHIP_PRICES_JSON` 一致；供 **`/recharge`** 页展示。

- **GET** `/api/pay/orders`  
  Header: `Authorization: Bearer <token>`  
  Query: **`limit`** 可选，默认 50，最大 100。  
  返回当前用户的充值订单列表（按创建时间倒序），每项含 `out_trade_no`、`membership_type`、`membership_type_label`、`total_amount`、`subject`、`status`、`status_label`（待支付/已支付/已关闭）、`trade_no`、`created_at`、`paid_at`（不含 `user_id`）。网页 **充值信息**（`/recharge-records`）使用此接口。

### 创建购买订单（商户侧下单）

- **POST** `/api/pay/orders`
- Header: `Authorization: Bearer <token>`
- Body: `{ "membership_type": "week" | "month" | "quarter" | "year" }`
- 成功：返回 `out_trade_no`、`total_amount`、`subject`、**`notify_url`**（支付宝回调）、**`wechat_notify_url`**（微信回调）、`app_id` / `mode`（支付宝侧）、**`wechat`**（`mode`、`simulate` 联调提示）等。生产环境在返回给客户端前，还应分别完成 **支付宝「充值流程」第 2 步** 或 **微信「统一下单」**；本仓库当前提供 **订单落库 + 各渠道异步通知验签与发货**。

### 支付宝异步通知（回调）

- **POST** `/api/pay/alipay/notify`  
- Content-Type: `application/x-www-form-urlencoded`（与支付宝一致）  
- 验签与字段解析在 **`app/payment_providers/alipay.py`**；支付成功后开通会员在 **`app/payment_fulfillment.py`**（`VerifiedPayment` + `DefaultMembershipFulfillment`），便于再接微信等渠道时只新增适配器、共用同一套履约逻辑。  
- `trade_status` 为 `TRADE_SUCCESS` / `TRADE_FINISHED` 时校验金额、**幂等**写入 `membership_records`（`source=purchase`，`order_id=out_trade_no`）  
- 响应体必须为纯文本 **`success`**（小写），否则支付宝会重试。

环境变量（见 `config.py`）：

| 变量 | 说明 |
|------|------|
| `ALIPAY_MODE` | `mock`（默认）：不验 RSA，便于本地联调；`rsa`：用支付宝公钥验签 |
| `ALIPAY_MOCK_SECRET` | 非空时，mock 模式下请求须带 Header `X-Alipay-Mock-Secret` |
| `ALIPAY_PUBLIC_KEY_PEM` / `ALIPAY_PUBLIC_KEY_PATH` | `rsa` 模式必填 |
| `PUBLIC_BASE_URL` | 拼回调地址用，需与公网可访问域名一致；本地开发可设为 `http://127.0.0.1:5001`（与 `run.py` 默认端口一致） |
| `MEMBERSHIP_PRICES_JSON` | 可选，JSON 覆盖各档标价，如 `{"month":"1000.00"}` |

首次部署若 MySQL 已存在旧库，可执行 `scripts/add_payment_orders.sql` 创建 `payment_orders` 表（否则依赖 `db.create_all()`）。

### 微信支付异步通知（回调）

- **POST** `/api/pay/wechat/notify`  
- Content-Type：生产多为 **`application/xml`** 或 **`text/xml`**；联调可用 **`application/json`**。  
- 解析与验签在 **`app/payment_providers/wechat.py`**；履约与支付宝共用 **`app/payment_fulfillment.py`**。  
- 金额字段：微信 V2 为 **`total_fee`（分）**；mock 下 JSON 可传 **`total_amount`（元）** 便于与订单小数一致。  
- 响应体须为 **XML**，且 **`return_code`** 为 **`SUCCESS`** 表示处理成功；否则微信会重试（与支付宝返回纯文本 `success` 不同）。

环境变量（见 `config.py`）：

| 变量 | 说明 |
|------|------|
| `WECHAT_PAY_MODE` | `mock`（默认）：不按 V2 验签；`v2`：用 `WECHAT_API_KEY` 做 MD5 签名验证 |
| `WECHAT_MOCK_SECRET` | 非空时，mock 模式下请求须带 Header `X-Wechat-Mock-Secret` |
| `WECHAT_API_KEY` | `v2` 模式必填（商户平台 API 密钥） |
| `PUBLIC_BASE_URL` | 拼 `wechat_notify_url` 用，与支付宝共用 |

#### 下单返回「请先登录」时排查

1. **Token 必须来自当前正在跑的这套服务**：登录接口返回的 `token` 与 `JWT_SECRET_KEY`（`.env`）一致；换机器、改密钥、或用了浏览器里旧环境的 token 都会验签失败。  
2. **Header 写法**：`Authorization: Bearer <token>` 中间有空格；`Bearer` / `bearer` 均可。不要把 token 截断或夹进换行。  
3. **curl 与 zsh**：若把多行 JSON 直接粘进终端，可能出现 `zsh: command not found: message:`（shell 把 JSON 当命令执行）。请用**一行 curl**，或把 JSON 放进文件：  
   `curl ... -d @body.json http://127.0.0.1:5001/api/pay/orders`  
4. **先验证 token**：`curl -s http://127.0.0.1:5001/api/membership/status -H "Authorization: Bearer $TOKEN"` 若仍为请先登录，说明 token 无效或已过期（默认约 7 天），请重新登录再试。

## 短信接入（生产环境）

当前默认 `SMS_PROVIDER=mock`，验证码写入日志文件（`[SMS Mock]`）。生产可：

1. 在 `.env` 中设置 `SMS_PROVIDER=aliyun`（或你实现的厂商名）。
2. 在 `app/sms.py` 的 `send_verification_code` 中根据 `SMS_PROVIDER` 调用对应厂商 API（阿里云、腾讯云等），并配置 `SMS_ACCESS_KEY_ID`、`SMS_ACCESS_KEY_SECRET`、签名、模板等（变量名见 `.env.example`）。

## 数据库表

- `users`：用户（id, phone, password_hash, created_at, updated_at）
- `verification_codes`：验证码记录（phone, code, expires_at, used_at），用于防重放与过期校验
- `payment_orders`：会员购买订单（`out_trade_no`、金额、状态；渠道支付单号存 `trade_no`，支付宝为 `trade_no`，微信为 `transaction_id`）
- `membership_records`：会员权益记录

表在首次启动时通过 `db.create_all()` 自动创建。
