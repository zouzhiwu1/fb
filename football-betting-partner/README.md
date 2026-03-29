# football-betting-partner

代理商 Web 门户：独立 Flask 进程、独立 **PARTNER_JWT_SECRET_KEY**，可与 `football-betting-platform` 共用同一 MySQL 库 `DATABASE_URL`（默认端口 **5002**，platform 一般为 5001）。

## 角色

- **部署根账号**：登录名固定为 **`root`**（不区分大小写），密码仅在 **`.env`** 的 **`PARTNER_ROOT_PASSWORD`**，**不入库**。与库内管理员共用 **`/admin/login`**，登录后进入 **`/admin/managers`**（管理员一览），可 **添加 / 修改 / 删除** 库内管理员（含改密、禁用）；**不能**操作代理商数据。**其它登录名**一律走表 **`partner_admins`**。
- **库内管理员（admin）**：账号在表 **`partner_admins`**。登录后进入 **`/admin/agents`**，维护代理商。JWT 均为 `sub_type=partner_admin`，通过载荷中的 `admin_role`（`root` / `admin`）区分。
- **代理商**：使用「代理商登录」进入 `/dashboard`。JWT 声明 `sub_type=partner`（与管理员令牌互不通用）。

库内管理员登录名 **禁止为 `root`**（含 API 与 bootstrap），以免与部署根账号混淆。

## 初始化数据库

**误删全表或全新空库**（platform + partner 同一 MySQL 库）：在项目根目录执行：

```bash
.venv/bin/python scripts/init_database.py
```

会按 `DATABASE_URL` 连接并执行 `scripts/init_full_stack.sql`（含 `users`、`payment_orders`、`agents`、`points_ledger` 等）。**会清空上述表的数据**，请勿在生产未备份时执行。

**仅需要 partner 表、且 `users` 表已由 platform 建好**时，可只执行：

```bash
mysql -h … -u … -p football_betting < scripts/add_partner_tables.sql
```

用 **DBeaver** 时建议**分段执行**脚本（先 `partner_admins` → `agents` → `points_ledger` → 外键 `ALTER` → 最后 `users`）。若只执行 `points_ledger` 会出现 **1824 / Failed to open the referenced table 'agents'**，说明 **`agents` 尚未创建成功**，请先执行并刷新确认左侧已出现 `agents` 表。

**已有旧版 partner 表**（无 `partner_admins`、无代理商档案字段时）再执行：

```bash
mysql -h … -u … -p football_betting < scripts/migrate_partner_admin_and_agent_profile.sql
```

并按需为 `agents.phone` 增加唯一索引（脚本内有说明）。

## 管理员：`partner_admins` 与部署根账号

- **表 `partner_admins`**：仅存 **库内管理员** 的登录名与密码哈希、`session_version`、`status` 等；由根账号在 **`/admin/managers`** 或运维通过 **`bootstrap-admin`** 写入。
- **根账号**：仅 `.env`，改密后需重启进程；若需使根账号已签发的 JWT 全部失效，可提高 **`PARTNER_ROOT_SESSION_VERSION`**（整数，默认 `1`）。

## 子路径部署与「网络错误」

若浏览器地址为 `https://域名/some-prefix/admin`，而页面里的接口请求发往 `https://域名/api/...`（少了前缀），会得到 **404/HTML 或非 JSON**，前端曾一律显示「网络错误」。

请在 **`.env`** 设置（**勿尾斜杠**）：

```env
PARTNER_APPLICATION_PREFIX=/some-prefix
```

与地址栏中 **partner 应用的路径前缀**一致；并确保反代把 **`前缀` 与 `前缀/api`** 都转到本进程。根路径部署则**留空或不设**该变量。

设置前缀后，本服务在 WSGI 层会**自动剥掉**请求路径中的该前缀再匹配路由，因此直接 `python run.py` 访问 `http://127.0.0.1:5002/partner/admin/login` 也会命中 `/admin/login`。若反代已去掉前缀再转发，请求形如 `/admin/login`，中间件不会重复剥离。

## 部署根账号与库内管理员（推荐流程）

在 **`.env`** 配置（**勿提交真实密码**）：

```env
PARTNER_ROOT_PASSWORD=你的强密码
# 可选：修改后 bump，可使所有根账号 JWT 失效
# PARTNER_ROOT_SESSION_VERSION=1
```

重启进程后，用 **登录名 `root`** + 上述密码打开 **`/admin/login`**，进入 **`/admin/managers`** 添加库内管理员；再用库内管理员登录，进入 **`/admin/agents`** 维护代理商。

## 首个库内管理员（bootstrap，备选）

无根账号或自动化脚本场景可用（需 `PARTNER_BOOTSTRAP_KEY`），**登录名不可为 `root`**：

```bash
curl -s -X POST http://127.0.0.1:5002/api/partner/auth/bootstrap-admin \
  -H "Content-Type: application/json" \
  -H "X-Partner-Bootstrap-Key: $KEY" \
  -d '{"login_name":"admin","password":"your-admin-pass"}'
```

之后在 `/admin/agents` 为代理商录入：**用户姓名、年龄、电话、银行账户**以及登录名、登录密码、推广码等。

## 首个代理商（仅运维/无管理员时的捷径）

仍可使用 `bootstrap-agent`（可不填档案字段）；正式流程推荐由管理员在 `/admin` 开户。

```bash
curl -s -X POST http://127.0.0.1:5002/api/partner/auth/bootstrap-agent \
  -H "Content-Type: application/json" \
  -H "X-Partner-Bootstrap-Key: $KEY" \
  -d '{"login_name":"demo","password":"your-pass","agent_code":"D001","display_name":"演示","current_rate":0.08}'
```

## 本地运行

```bash
cd football-betting-partner
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # 编辑 DATABASE_URL 与 PARTNER_JWT_SECRET_KEY
PORT=5002 .venv/bin/python run.py
```

打开 `/` 选择「管理员登录」或「代理商登录」。

**管理页报「响应非 JSON」且 HTTP 500**：先确认 MySQL 已执行 `scripts/migrate_partner_admin_and_agent_profile.sql`（或完整 `add_partner_tables.sql`），使 `agents` 含 `real_name` 等字段；并避免默认开启 `FLASK_DEBUG`（`run.py` 默认已关闭，需要时再在 `.env` 设 `FLASK_DEBUG=1`）。

## 后台常驻

- **macOS**：`./start_mac.sh` / `./stop_mac.sh`（默认 `PORT=5002`，可用环境变量覆盖）
- **Linux**：`./start_linux.sh` / `./stop_linux.sh`

## 测试

```bash
.venv/bin/pytest -q
```
