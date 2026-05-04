const api = require('../../utils/api.js');
const { PASSWORD_POLICY_HINT, validatePasswordClient } = require('../../utils/passwordPolicy.js');

Page({
  data: {
    username: '',
    gender: '',
    password: '',
    phone: '',
    email: '',
    loading: false,
    passwordPolicyHint: PASSWORD_POLICY_HINT,
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
  onEmail(e) {
    this.setData({ email: e.detail.value });
  },

  onGender(e) {
    const g = e.currentTarget.dataset.g;
    this.setData({ gender: g });
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
          api.bindWechatMp();
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
