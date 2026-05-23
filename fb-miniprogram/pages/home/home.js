const api = require('../../utils/api.js');

Page({
  data: {
    displayName: '游客',
    loggedIn: false,
  },

  onShow() {
    const token = api.getToken();
    if (!token) {
      this.setData({ displayName: '游客', loggedIn: false });
      return;
    }
    const user = api.getUser();
    const name = user?.username || user?.phone || '用户';
    this.setData({ displayName: name, loggedIn: true });
    api.bindWechatMp();
  },

  go(e) {
    const url = e.currentTarget.dataset.url;
    if (url !== '/pages/curves/curves' && !api.getToken()) {
      wx.showModal({
        title: '请先注册登录',
        content: '该功能需要登录后使用。您可以先浏览已完场的曲线图。',
        confirmText: '去登录',
        cancelText: '先浏览',
        success: (res) => {
          if (res.confirm) {
            wx.navigateTo({ url: '/pages/login/login' });
          }
        },
      });
      return;
    }
    wx.navigateTo({ url });
  },

  onLogin() {
    wx.navigateTo({ url: '/pages/login/login' });
  },

  onLogout() {
    wx.showModal({
      title: '退出登录',
      content: '确定要退出吗？',
      success: (res) => {
        if (res.confirm) {
          api.clearSession();
          this.setData({ displayName: '游客', loggedIn: false });
        }
      },
    });
  },
});
