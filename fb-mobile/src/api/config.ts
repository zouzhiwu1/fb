/**
 * 与 fb-platform（Flask）通信的基地址（仅 origin，无路径）。
 * 开发机示例：http://192.168.x.x:5001；正式包：https://trybx.cn（走 443，勿写 :5001）
 * 错误：…/login、…/api/auth/login（路径由各 api 模块拼接）
 *
 * 在 fb-mobile 目录建 .env，见 .env.example。
 * 真机 / Expo Go 必须用电脑局域网 IP，127.0.0.1 指向手机自身会失败。
 */
function normalizeApiBase(raw: string): string {
  let u = raw.trim().replace(/\/+$/, '');
  // 若误填成网页地址 …/login，自动去掉（真实请求为 /api/auth/login）
  if (/\/login$/i.test(u)) {
    u = u.replace(/\/login$/i, '').replace(/\/+$/, '');
  }
  return u;
}

export function getApiBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_BASE_URL?.trim();
  if (fromEnv) {
    return normalizeApiBase(fromEnv);
  }
  return 'http://127.0.0.1:5001';
}
