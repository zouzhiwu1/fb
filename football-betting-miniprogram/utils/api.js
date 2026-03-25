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

function curveImageUrl(date, filename) {
  return `${API_BASE}/api/curves/img/${date}/${encodeURIComponent(filename)}`;
}

function downloadAuthorizedFile(url, token) {
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url,
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success(res) {
        const ok =
          res.tempFilePath &&
          (res.statusCode === undefined || res.statusCode === 200);
        if (ok) {
          resolve(res.tempFilePath);
        } else {
          reject(new Error(`download ${res.statusCode || 'fail'}`));
        }
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
  curveImageUrl,
  downloadAuthorizedFile,
};
