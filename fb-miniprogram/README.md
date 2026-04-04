# fb-miniprogram

微信小程序客户端，与 **fb-mobile** 使用同一套 **fb-platform** API（登录、注册、账户、会员、充值、曲线图查询）。

## 功能页面

| 页面 | 对应移动端 | 说明 |
|------|------------|------|
| 登录 | `(auth)/login` | 手机号 + 密码 |
| 注册 | `(auth)/register` | 用户名、性别、密码、手机验证码、邮箱 |
| 首页 | `(app)/home` | 入口菜单、退出登录 |
| 曲线图查询 | `(app)/curves` | 日期/球队搜索；图片经 `wx.downloadFile` 带 JWT 拉取 |
| 账户资料 | `(app)/account` | 资料展示、改密码/邮箱/手机（下拉刷新） |
| 会员状态 | `(app)/membership` | 与 `/api/membership/status` 一致（下拉刷新） |
| 充值 | `(app)/recharge` | 创建支付宝订单（与网页一致，小程序内未接微信支付） |
| 充值记录 | `(app)/records` | `GET /api/pay/orders`（下拉刷新） |

## 配置

1. **AppID**  
   用微信开发者工具打开本目录，在 `project.config.json` 中填写你的小程序 `appid`（测试可选用测试号）。

2. **API 地址**  
   编辑 `utils/config.js`，将 `API_BASE` 改为你的平台 **HTTPS** 根地址（无路径、无末尾 `/`），例如：

   ```js
   const API_BASE = 'https://trybx.cn';
   ```

   须与 **fb-mobile** 的 `EXPO_PUBLIC_API_BASE_URL` 指向同一套后端。

3. **服务器域名（小程序后台）**  
   登录 [微信公众平台](https://mp.weixin.qq.com/) → 开发 → 开发管理 → 开发设置 → **服务器域名**，添加：

   - **request 合法域名**：你的 API 域名（如 `https://trybx.cn`）
   - **downloadFile 合法域名**：同上（曲线图图片走 `/api/curves/img/...`）

   本地调试可在开发者工具 **详情 → 本地设置** 勾选 **不校验合法域名、web-view（含 TLS 版本）、TLS 证书以及 HTTPS 证书**。

4. **短信验证码**  
   与网页/移动端相同：开发环境下验证码在运行 `python run.py` 的终端中打印。

## 导入项目

1. 安装 [微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)。
2. 选择「导入项目」，目录选本仓库下的 `fb-miniprogram`。
3. 填写 AppID 后编译预览。

## 主题

全局样式与移动端 `constants/ui.ts` 深色主题一致（背景 `#050816`、强调色 `#22c55e` 等）。

## 说明

- **支付**：当前仍为平台侧的 **支付宝** 下单流程；若要在小程序内用 **微信支付**，需在平台新增微信统一下单与回调，小程序再调用 `wx.requestPayment`（本仓库未实现）。
- **曲线图**：依赖 `downloadFile` 携带 `Authorization: Bearer <token>`，请保证基础库版本较新（建议 `project.config.json` 中 `libVersion` 与工具一致）。
