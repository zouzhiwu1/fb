const api = require('../../utils/api.js');

Page({
  data: {
    options: [],
    loading: true,
    buying: '',
  },

  onShow() {
    this.load();
  },

  onPullDownRefresh() {
    this.load().finally(() => wx.stopPullDownRefresh());
  },

  load() {
    this.setData({ loading: true });
    return api
      .request('/api/pay/membership-options', { method: 'GET' })
      .then(({ ok, data }) => {
        if (ok && data.ok && data.options) {
          this.setData({ options: data.options });
        }
      })
      .finally(() => this.setData({ loading: false }));
  },

  buy(e) {
    const mtype = e.currentTarget.dataset.type;
    const token = api.getToken();
    if (!token) {
      wx.showToast({ title: '请先登录', icon: 'none' });
      return;
    }
    this.setData({ buying: mtype });
    api
      .request('/api/pay/orders', {
        method: 'POST',
        token,
        data: { membership_type: mtype, payment_channel: 'wechat_mp' },
      })
      .then(({ ok, data }) => {
        if (!ok || !data.ok) {
          wx.showToast({ title: data.message || '失败', icon: 'none' });
          return;
        }
        if (data.wx_pay && data.wx_pay.timeStamp) {
          const wp = data.wx_pay;
          wx.requestPayment({
            timeStamp: wp.timeStamp,
            nonceStr: wp.nonceStr,
            package: wp.package,
            signType: wp.signType || 'MD5',
            paySign: wp.paySign,
            success: () => {
              wx.showToast({ title: '支付成功', icon: 'success' });
            },
            fail: (err) => {
              const raw =
                (err && err.errMsg) ||
                (typeof err === 'string' ? err : '') ||
                '';
              let msg = '支付未完成';
              if (
                /requestPayment:fail\s*cancel/i.test(raw) ||
                /cancel/i.test(raw)
              ) {
                msg = '您已取消支付';
              } else if (raw) {
                msg = raw;
              }
              wx.showModal({
                title: '支付',
                content: msg,
                showCancel: false,
              });
            },
          });
          return;
        }
        const hint =
          (data.simulate && data.simulate.hint) ||
          '当前为 mock 或未返回支付参数：请在服务器配置 WECHAT_PAY_MODE=v2/v3 或使用模拟回调脚本';
        wx.showModal({
          title: '订单已创建',
          content: `订单号：${data.out_trade_no}\n金额：${data.total_amount}\n${data.subject || ''}\n\n${hint}`,
          showCancel: false,
        });
      })
      .catch(() => {
        wx.showToast({ title: '网络错误', icon: 'none' });
      })
      .finally(() => this.setData({ buying: '' }));
  },
});
