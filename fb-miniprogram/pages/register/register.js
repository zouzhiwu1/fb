const api = require('../../utils/api.js');
const { PASSWORD_POLICY_HINT, validatePasswordClient } = require('../../utils/passwordPolicy.js');

Page({
  data: {
    username: '',
    gender: '',
    password: '',
    phone: '',
    code: '',
    email: '',
    loading: false,
    sending: false,
    cooldown: 0,
    passwordPolicyHint: PASSWORD_POLICY_HINT,
  },

  timer: null,

  onUnload() {
    if (this.timer) clearInterval(this.timer);
  },

  onUsername(e) {
    this.setData({ username: e.detail.value });
  },
  onPassword(e) {
    this.setData({ password: e.detail.value });
  },
  onPhone(e) {
    this.setData({ phone: e.detail.value });
  },
  onCode(e) {
    this.setData({ code: e.detail.value });
  },
  onEmail(e) {
    this.setData({ email: e.detail.value });
  },

  onGender(e) {
    const g = e.currentTarget.dataset.g;
    this.setData({ gender: g });
  },

  onSendCode() {
    const p = (this.data.phone || '').trim();
    if (!/^\d{11}$/.test(p)) {
      wx.showToast({ title: '请先输入 11 位手机号', icon: 'none' });
      return;
    }
    if (this.data.cooldown > 0 || this.data.sending) return;
    this.setData({ sending: true });
    api
      .request('/api/auth/send-code', {
        method: 'POST',
        data: { phone: p },
      })
      .then(({ ok, data }) => {
        if (!ok || !data.ok) {
          wx.showToast({ title: data.message || '发送失败', icon: 'none' });
          return;
        }
        wx.showToast({
          title: data.message || '验证码已发送',
          icon: 'none',
          duration: 2500,
        });
        this.startCooldown();
      })
      .catch(() => {
        wx.showToast({ title: '网络错误', icon: 'none' });
      })
      .finally(() => {
        this.setData({ sending: false });
      });
  },

  startCooldown() {
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
  },

  onSubmit() {
    if (!(this.data.username || '').trim()) {
      wx.showToast({ title: '请输入用户名', icon: 'none' });
      return;
    }
    if (!this.data.gender) {
      wx.showToast({ title: '请选择性别', icon: 'none' });
      return;
    }
    const pe = validatePasswordClient(this.data.password);
    if (pe) {
      wx.showToast({ title: pe, icon: 'none' });
      return;
    }
    if (!/^\d{11}$/.test((this.data.phone || '').trim())) {
      wx.showToast({ title: '请输入有效手机号', icon: 'none' });
      return;
    }
    if (!(this.data.code || '').trim()) {
      wx.showToast({ title: '请输入验证码', icon: 'none' });
      return;
    }
    if (!(this.data.email || '').includes('@')) {
      wx.showToast({ title: '请输入有效邮箱', icon: 'none' });
      return;
    }
    this.setData({ loading: true });
    api
      .request('/api/auth/register', {
        method: 'POST',
        data: {
          username: this.data.username.trim(),
          gender: this.data.gender,
          password: this.data.password,
          phone: this.data.phone.trim(),
          email: this.data.email.trim(),
          code: this.data.code.trim(),
        },
      })
      .then(({ ok, data, status }) => {
        if (!ok || !data.ok) {
          wx.showModal({
            title: '注册失败',
            content: data.message || `HTTP ${status}`,
            showCancel: false,
          });
          return;
        }
        if (data.token && data.user) {
          api.setSession(data.token, data.user);
          wx.reLaunch({ url: '/pages/home/home' });
          return;
        }
        wx.showToast({ title: data.message || '请登录', icon: 'none' });
        wx.navigateTo({ url: '/pages/login/login' });
      })
      .catch(() => {
        wx.showToast({ title: '网络错误', icon: 'none' });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },
});
