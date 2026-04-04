const api = require('../../utils/api.js');
const { PASSWORD_POLICY_HINT, validatePasswordClient } = require('../../utils/passwordPolicy.js');

Page({
  data: {
    user: {},
    curPwd: '',
    newPwd: '',
    passwordPolicyHint: PASSWORD_POLICY_HINT,
    email: '',
    newPhone: '',
    phoneCode: '',
    busy: false,
    cooldown: 0,
  },

  timer: null,

  onUnload() {
    if (this.timer) clearInterval(this.timer);
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
  onNewPhone(e) {
    this.setData({ newPhone: e.detail.value });
  },
  onPhoneCode(e) {
    this.setData({ phoneCode: e.detail.value });
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

  sendForNewPhone() {
    const p = (this.data.newPhone || '').trim();
    if (!/^\d{11}$/.test(p)) {
      wx.showToast({ title: '请输入新手机号 11 位', icon: 'none' });
      return;
    }
    if (this.data.cooldown > 0) return;
    api
      .request('/api/auth/send-code', {
        method: 'POST',
        data: { phone: p },
      })
      .then(({ ok, data }) => {
        if (!ok || !data.ok) {
          wx.showToast({ title: data.message || '失败', icon: 'none' });
          return;
        }
        wx.showToast({ title: data.message || '已发送', icon: 'none' });
        if (this.timer) clearInterval(this.timer);
        this.setData({ cooldown: 60 });
        this.timer = setInterval(() => {
          const c = this.data.cooldown - 1;
          if (c <= 0) {
            clearInterval(this.timer);
            this.timer = null;
            this.setData({ cooldown: 0 });
          } else {
            this.setData({ cooldown: c });
          }
        }, 1000);
      });
  },

  doChangePhone() {
    const token = api.getToken();
    if (!token) return;
    if (!/^\d{11}$/.test((this.data.newPhone || '').trim()) || !(this.data.phoneCode || '').trim()) {
      wx.showToast({ title: '请填写新手机号与验证码', icon: 'none' });
      return;
    }
    api
      .request('/api/auth/change-phone', {
        method: 'POST',
        token,
        data: {
          new_phone: this.data.newPhone.trim(),
          code: this.data.phoneCode.trim(),
        },
      })
      .then(({ ok, data }) => {
        if (!ok || !data.ok) {
          wx.showToast({ title: data.message || '失败', icon: 'none' });
          return;
        }
        wx.showToast({ title: data.message || '请用新手机号登录', icon: 'none' });
        this.setData({ newPhone: '', phoneCode: '' });
        this.refreshUser();
      });
  },
});
