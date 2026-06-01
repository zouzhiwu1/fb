const api = require('../../utils/api.js');

function fmtDateTime(iso) {
  if (!iso) return '—';
  return String(iso).replace('T', ' ').replace(/\.\d+/, '');
}

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
          const orders = (data.orders || []).map((o) => ({
            ...o,
            created_at_fmt: fmtDateTime(o.created_at),
            paid_at_fmt: o.paid_at ? fmtDateTime(o.paid_at) : '',
          }));
          this.setData({ orders, emptyHint: '暂无订单' });
        } else {
          this.setData({ orders: [], emptyHint: '暂无订单' });
        }
      })
      .finally(() => this.setData({ loading: false }));
  },
});
