const { API_BASE } = require('./config.js');

const TOKEN_KEY = 'football_platform_token';
const USER_KEY = 'football_platform_user';

function normalizePath(path) {
  return path.startsWith('/') ? path : `/${path}`;
}

function request(path, options = {}) {
  const { method = 'GET', data, token } = options;
  const header = {
    'Content-Type': 'application/json',
  };
  if (token) {
    header.Authorization = `Bearer ${token}`;
  }
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${API_BASE}${normalizePath(path)}`,
      method,
      data: method === 'GET' ? undefined : data,
      header,
      success(res) {
        resolve({
          ok: res.statusCode >= 200 && res.statusCode < 300,
          status: res.statusCode,
          data: res.data || {},
        });
      },
      fail(err) {
        reject(err);
      },
    });
  });
}

function getToken() {
  return wx.getStorageSync(TOKEN_KEY) || '';
}

function getUser() {
  try {
    const u = wx.getStorageSync(USER_KEY);
    return u ? JSON.parse(u) : null;
  } catch {
    return null;
  }
}

function setSession(token, user) {
  wx.setStorageSync(TOKEN_KEY, token);
  wx.setStorageSync(USER_KEY, JSON.stringify(user));
}

function clearSession() {
  wx.removeStorageSync(TOKEN_KEY);
  wx.removeStorageSync(USER_KEY);
}

/**
 * 登录/进入首页后调用：wx.login 换 code，服务端绑定 openid（微信小程序支付前置条件）。
 */
function bindWechatMp() {
  const token = getToken();
  if (!token) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    wx.login({
      success: (r) => {
        if (!r.code) {
          resolve();
          return;
        }
        request('/api/auth/wechat-mp/bind', {
          method: 'POST',
          token,
          data: { code: r.code },
        })
          .then((res) => {
            if (res.ok && res.data && res.data.ok && res.data.user) {
              setSession(token, res.data.user);
            }
          })
          .catch(() => {})
          .finally(resolve);
      },
      fail: () => resolve(),
    });
  });
}

/**
 * 微信小程序一键登录（wx.login + getPhoneNumber）。
 */
function quickLoginWechatMp(phoneCode) {
  return new Promise((resolve, reject) => {
    if (!phoneCode) {
      reject(new Error('缺少手机号授权 code'));
      return;
    }
    wx.login({
      success: (r) => {
        const loginCode = (r && r.code) || '';
        if (!loginCode) {
          reject(new Error('微信登录失败，请重试'));
          return;
        }
        request('/api/auth/wechat-mp/quick-login', {
          method: 'POST',
          data: {
            login_code: loginCode,
            phone_code: phoneCode,
          },
        })
          .then(resolve)
          .catch(reject);
      },
      fail: () => reject(new Error('微信登录失败，请重试')),
    });
  });
}

function curveImageUrl(date, filename) {
  return `${API_BASE}/api/curves/img/${date}/${encodeURIComponent(filename)}`;
}

function downloadAuthorizedFile(url, token) {
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url,
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success(res) {
        // 有些情况下图片可能返回 304（未修改），但 downloadFile 仍可能给出 tempFilePath。
        // 这里把 304 也视为成功，避免把“未变化”误判为下载失败。
        const sc = res.statusCode;
        const ok =
          res.tempFilePath &&
          (sc === undefined || sc === 200 || sc === 304);
        if (ok) resolve(res.tempFilePath);
        else reject(new Error(`download ${sc || 'fail'}`));
      },
      fail: reject,
    });
  });
}

module.exports = {
  API_BASE,
  request,
  getToken,
  getUser,
  setSession,
  clearSession,
  bindWechatMp,
  quickLoginWechatMp,
  curveImageUrl,
  downloadAuthorizedFile,
};
