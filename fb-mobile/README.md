# fb-mobile

手机端（Expo / React Native），与 **fb-platform** 共用同一套 Flask JSON API。

## 功能（与 Web 对齐）

- 登录 / 注册（短信验证码）
- 首页入口：曲线图查询、账户资料、会员状态、充值、充值记录
- 曲线：日期列表、搜索、图片（请求带 `Authorization: Bearer`）
- 账户：资料、改密码 / 邮箱 / 手机

## API 地址

- **模拟器在本机**：可不设，默认 `http://127.0.0.1:5001`。
- **真机 / Expo Go**：`127.0.0.1` 是手机自己，会失败。必须用电脑的局域网 IP，且**只写到端口**，不要加网页路径 `/login`（接口实际是 `/api/auth/login`，由 App 自动拼接）。

```bash
EXPO_PUBLIC_API_BASE_URL=http://192.168.11.2:5001 npx expo start
```

本地可维护 `fb-mobile/.env`（已加入仓库 `.gitignore`，勿提交）；若无该文件，请复制 `.env.example` 为 `.env`。修改 IP 后务必**重新**执行 `npx expo start` 才会生效。

原生 App 直连 HTTP，一般**不**涉及浏览器 CORS；若用 **Expo Web**，需后端允许对应来源。

### 正式包 / 线上 API（与网页 [trybx.cn](https://trybx.cn) 同源服务）

打包时使用 **HTTPS 根地址、不要带端口 5001**（公网手机往往访问不到 `:5001`，应由 Nginx 443 反代到本机 Flask）：

`EXPO_PUBLIC_API_BASE_URL=https://trybx.cn`

**不要**把环境变量写成 `…/login`。App 会自行请求 `https://trybx.cn/api/auth/login` 等接口。

## 打包安装包（Android APK / iOS IPA）

使用 [EAS Build](https://docs.expo.dev/build/introduction/)（Expo 云端编译）。

1. 注册/登录 [expo.dev](https://expo.dev)，安装并登录 CLI：

   ```bash
   npm install
   npx eas-cli login
   ```

2. **首次**在本目录关联项目（会往 `app.json` 写入 `extra.eas.projectId`）：

   ```bash
   cd fb-mobile
   npx eas-cli build:configure
   ```

3. 构建：

   ```bash
   npm run build:android
   npm run build:ios
   ```

   或在 `preview` 配置下打内测包：`npm run build:android:preview` / `npm run build:ios:preview`。

4. 完成后在 [expo.dev 控制台](https://expo.dev) 对应项目 **Builds** 里下载 **APK** / **IPA**。

**说明：**

- `eas.json` 的 `production` / `preview` 已设置 `EXPO_PUBLIC_API_BASE_URL=https://trybx.cn`。换域名时改 `eas.json` 的 `env` 后**重新构建**。
- **Android**：当前 `production` 使用 `buildType: "apk"`，便于直接安装。
- **iOS**：需 **Apple 开发者账号**；正式包使用 **HTTPS** 更符合上架要求。
- `app.json` 中 `trybx.cn` 的 HTTP ATS 例外、Android `usesCleartextTraffic` 仍可用于开发机访问 `http://…:5001`；正式 API 以 **HTTPS** 为主。

## 备忘录：线上 APK 下载（Nginx，与当前 trybx.cn 服务器一致）

生产环境用 **Nginx** 对外提供 HTTPS；安装包放在固定目录，由站点配置中的 **`alias`** 映射到 URL。下列路径与策略与当前部署一致，换机部署时可照抄目录与文件名习惯。

### 目录约定（服务器）

| 用途 | 路径 |
| --- | --- |
| APK（及可选其他分发文件） | `/var/www/trybx-downloads/` |
| 当前 Android 包文件名示例 | `/var/www/trybx-downloads/fb.apk` |
| Nginx 站点片段 | `/etc/nginx/conf.d/trybx.conf` |

**当前线上对外下载链接（与 `trybx.conf` 中 `location /downloads/` 一致）：**

`https://trybx.cn/downloads/fb.apk`

注意路径是 **`/downloads/`**（复数），不是 `/download/`。写成 `/download/...` 会落到站点的 `location /`，由 Nginx 反代到本机 Flask，通常返回 **404**。

创建目录并赋权（示例，用户/组以发行版为准，常见为 `nginx` 或 `www-data`）：

```bash
sudo mkdir -p /var/www/trybx-downloads
sudo chown -R nginx:nginx /var/www/trybx-downloads   # Debian/Ubuntu 可能是 www-data:www-data
```

### 安装 Nginx

**AlmaLinux / Rocky / CentOS / RHEL：**

```bash
sudo dnf install -y nginx    # 或 yum install -y nginx
sudo systemctl enable --now nginx
sudo nginx -t && sudo systemctl reload nginx
```

**Debian / Ubuntu：**

```bash
sudo apt update && sudo apt install -y nginx
sudo systemctl enable --now nginx
sudo nginx -t && sudo systemctl reload nginx
```

### 配置要点（`trybx.conf`）

在同一域名（如 `trybx.cn`）的 `server` 中，除反代 API/Web 外，为下载目录增加独立 `location`，与线上一致的核心写法是 **`alias` 指向物理目录**（前缀与 `alias` 末尾斜杠需配对，按你实际 URL 调整）：

```nginx
# 示例：若对外地址为 https://trybx.cn/downloads/fb.apk
# 则 location 前缀须与 alias 物理路径对应（以下仅为结构示意）
location /downloads/ {
    alias /var/www/trybx-downloads/;
    default_type application/vnd.android.package-archive;
    # 可选：add_header Content-Disposition "attachment; filename=fb.apk";
}
```

线上实际 `location` 前缀以 `/etc/nginx/conf.d/trybx.conf` 为准；修改后执行：

```bash
sudo nginx -t && sudo systemctl reload nginx
```

**HTTPS**：证书与 `listen 443 ssl` 可在同文件或其它 `conf.d` 片段中配置；常用 [Let’s Encrypt](https://letsencrypt.org/) + `certbot`（`certbot --nginx -d trybx.cn`）自动续期。

### 更新 APK 后的操作

1. 将 EAS 打完的 APK 上传到服务器，覆盖  
   `/var/www/trybx-downloads/fb.apk`（或与 Nginx/对外链接约定一致的文件名）。  
2. 一般**无需**重载 Nginx，仅替换文件即可。  
3. 浏览器或 `curl -I https://trybx.cn/downloads/fb.apk` 验证 `200` 与 `Content-Type`。

### 常用自检命令

```bash
sudo systemctl status nginx --no-pager
sudo nginx -t
grep -R "trybx-downloads" /etc/nginx/conf.d/
ls -la /var/www/trybx-downloads/
```


