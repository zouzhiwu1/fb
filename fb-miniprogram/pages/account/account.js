const api = require('../../utils/api.js');
const { PASSWORD_POLICY_HINT, validatePasswordClient } = require('../../utils/passwordPolicy.js');

Page({
  data: {
    user: {},
    curPwd: '',
    newPwd: '',
    passwordPolicyHint: PASSWORD_POLICY_HINT,
    email: '',
    busy: false,
  },

  loadUser() {
    const user = api.getUser() || {};
    this.setData({
      user,
      email: user.email || '',
    });
  },

  onShow() {
    if (!api.getToken()) {
      wx.reLaunch({ url: '/pages/login/login' });
      return;
    }
    this.loadUser();
    this.refreshUser();
  },

  onPullDownRefresh() {
    this.refreshUser().finally(() => wx.stopPullDownRefresh());
  },

  async refreshUser() {
    const token = api.getToken();
    if (!token) return;
    const { ok, data } = await api.request('/api/auth/me', { method: 'GET', token });
    if (ok && data.ok && data.user) {
      api.setSession(token, data.user);
      this.setData({ user: data.user, email: data.user.email || '' });
    }
  },

  onCurPwd(e) {
    this.setData({ curPwd: e.detail.value });
  },
  onNewPwd(e) {
    this.setData({ newPwd: e.detail.value });
  },
  onEmail(e) {
    this.setData({ email: e.detail.value });
  },

  doChangePassword() {
    const token = api.getToken();
    if (!token) return;
    const pe = validatePasswordClient(this.data.newPwd);
    if (pe) {
      wx.showToast({ title: pe, icon: 'none' });
      return;
    }
    this.setData({ busy: true });
    const body = {
      new_password: this.data.newPwd,
    };
    if (this.data.user.password_set) {
      body.current_password = this.data.curPwd || '';
    }
    api
      .request('/api/auth/change-password', {
        method: 'POST',
        token,
        data: body,
      })
      .then(({ ok, data }) => {
        if (!ok || !data.ok) {
          wx.showToast({ title: data.message || '失败', icon: 'none' });
          return;
        }
        wx.showToast({ title: data.message || '已更新', icon: 'success' });
        this.setData({ curPwd: '', newPwd: '' });
        this.refreshUser();
      })
      .finally(() => this.setData({ busy: false }));
  },

  doChangeEmail() {
    const token = api.getToken();
    if (!token || !(this.data.email || '').includes('@')) {
      wx.showToast({ title: '请输入有效邮箱', icon: 'none' });
      return;
    }
    api
      .request('/api/auth/change-email', {
        method: 'POST',
        token,
        data: { email: this.data.email.trim() },
      })
      .then(({ ok, data }) => {
        if (!ok || !data.ok) {
          wx.showToast({ title: data.message || '失败', icon: 'none' });
          return;
        }
        wx.showToast({ title: data.message || '已更新', icon: 'success' });
        this.refreshUser();
      });
  },
});
