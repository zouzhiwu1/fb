const api = require('../../utils/api.js');

Page({
  data: {
    displayName: '用户',
  },

  onShow() {
    const token = api.getToken();
    if (!token) {
      wx.reLaunch({ url: '/pages/login/login' });
      return;
    }
    const user = api.getUser();
    const name = user?.username || user?.phone || '用户';
    this.setData({ displayName: name });
    api.bindWechatMp();
  },

  go(e) {
    const url = e.currentTarget.dataset.url;
    wx.navigateTo({ url });
  },

  onLogout() {
    wx.showModal({
      title: '退出登录',
      content: '确定要退出吗？',
      success: (res) => {
        if (res.confirm) {
          api.clearSession();
          wx.reLaunch({ url: '/pages/login/login' });
        }
      },
    });
  },
});
