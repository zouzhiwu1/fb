const api = require('../../utils/api.js');

Page({
  data: {
    orders: [],
    loading: true,
    emptyHint: '暂无订单',
  },

  onShow() {
    this.load();
  },

  onPullDownRefresh() {
    this.load().finally(() => wx.stopPullDownRefresh());
  },

  load() {
    const token = api.getToken();
    if (!token) {
      this.setData({
        loading: false,
        orders: [],
        emptyHint: '请先登录',
      });
      return Promise.resolve();
    }
    this.setData({ loading: true });
    return api
      .request('/api/pay/orders?limit=50', { method: 'GET', token })
      .then(({ ok, data }) => {
        if (ok && data.ok && data.orders) {
          this.setData({ orders: data.orders, emptyHint: '暂无订单' });
        } else {
          this.setData({ orders: [], emptyHint: '暂无订单' });
        }
      })
      .finally(() => this.setData({ loading: false }));
  },
});
