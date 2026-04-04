const api = require('../../utils/api.js');
const { API_BASE } = require('../../utils/config.js');

Page({
  data: {
    phone: '',
    password: '',
    loading: false,
  },

  onShow() {
    if (api.getToken()) {
      wx.reLaunch({ url: '/pages/home/home' });
    }
  },

  onPhone(e) {
    this.setData({ phone: e.detail.value });
  },

  onPwd(e) {
    this.setData({ password: e.detail.value });
  },

  onLogin() {
    const p = (this.data.phone || '').trim();
    if (!/^\d{11}$/.test(p)) {
      wx.showToast({ title: '请输入 11 位手机号', icon: 'none' });
      return;
    }
    if (!this.data.password) {
      wx.showToast({ title: '请输入密码', icon: 'none' });
      return;
    }
    this.setData({ loading: true });
    api
      .request('/api/auth/login', {
        method: 'POST',
        data: { phone: p, password: this.data.password },
      })
      .then(({ ok, data, status }) => {
        if (!ok || !data.ok || !data.token || !data.user) {
          wx.showModal({
            title: '登录失败',
            content: data.message || `HTTP ${status}`,
            showCancel: false,
          });
          return;
        }
        api.setSession(data.token, data.user);
        wx.reLaunch({ url: '/pages/home/home' });
      })
      .catch((e) => {
        wx.showModal({
          title: '网络错误',
          content: `当前 API：${API_BASE}\n\n请检查合法域名、HTTPS 与平台是否已启动。\n${e.errMsg || e.message || ''}`,
          showCancel: false,
        });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },
});
