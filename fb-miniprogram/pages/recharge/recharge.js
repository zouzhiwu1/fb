const api = require('../../utils/api.js');

function compareVersion(v1, v2) {
  if (typeof v1 !== 'string' || typeof v2 !== 'string') return 0;
  const a = v1.split('.');
  const b = v2.split('.');
  const len = Math.max(a.length, b.length);
  while (a.length < len) a.push('0');
  while (b.length < len) b.push('0');
  for (var i = 0; i < len; i++) {
    var n1 = parseInt(a[i], 10);
    var n2 = parseInt(b[i], 10);
    if (n1 > n2) return 1;
    if (n1 < n2) return -1;
  }
  return 0;
}

function canUseVirtualPayment() {
  try {
    var sdk = (wx.getSystemInfoSync() && wx.getSystemInfoSync().SDKVersion) || '';
    if (compareVersion(sdk, '2.19.2') >= 0) return true;
  } catch (e) {}
  return typeof wx.canIUse === 'function' && wx.canIUse('requestVirtualPayment');
}

Page({
  data: {
    options: [],
    loading: true,
    buying: '',
    virtualReady: false,
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
          this.setData({
            options: data.options,
            virtualReady: !!data.wechat_virtual_pay_ready,
          });
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
    if (!this.data.virtualReady) {
      wx.showModal({
        title: '暂无法充值',
        content:
          '小程序会员充值需使用「虚拟支付」，当前服务端尚未配置。请联系管理员在平台环境变量中配置虚拟支付参数（见 fb-platform/.env.example）。',
        showCancel: false,
      });
      return;
    }
    if (!canUseVirtualPayment()) {
      wx.showModal({
        title: '请升级微信',
        content: '当前微信版本过低，不支持虚拟支付，请升级后再试。',
        showCancel: false,
      });
      return;
    }
    this.setData({ buying: mtype });
    wx.login({
      success: (lr) => {
        const code = lr && lr.code ? String(lr.code).trim() : '';
        if (!code) {
          wx.showToast({ title: '登录态获取失败', icon: 'none' });
          this.setData({ buying: '' });
          return;
        }
        api
          .request('/api/pay/orders', {
            method: 'POST',
            token,
            data: {
              membership_type: mtype,
              payment_channel: 'wechat_mp_virtual',
              login_code: code,
            },
          })
          .then(({ ok, data, status }) => {
            if (!ok || !data.ok) {
              wx.showToast({
                title: data.message || '创建订单失败 ' + (status || ''),
                icon: 'none',
              });
              return;
            }
            const outNo = data.out_trade_no;
            const vp = data.virtual_pay;
            if (vp && vp.signData && vp.paySig && vp.signature) {
              wx.requestVirtualPayment({
                signData: vp.signData,
                paySig: vp.paySig,
                signature: vp.signature,
                mode: vp.mode || 'short_series_goods',
                success: () => {
                  wx.login({
                    success: (lr2) => {
                      const c2 = lr2 && lr2.code ? String(lr2.code).trim() : '';
                      if (!c2) {
                        wx.showModal({
                          title: '请稍后确认',
                          content: '支付可能已成功，但未能自动确认订单，请稍后在「会员状态」查看。',
                          showCancel: false,
                        });
                        return;
                      }
                      api
                        .request('/api/pay/wechat-virtual/confirm', {
                          method: 'POST',
                          token,
                          data: { out_trade_no: outNo, login_code: c2 },
                        })
                        .then(({ ok: cok, data: cdata }) => {
                          if (cok && cdata && cdata.ok) {
                            wx.showToast({
                              title: cdata.fulfilled ? '会员已开通' : '已确认',
                              icon: 'success',
                            });
                          } else {
                            wx.showModal({
                              title: '确认订单',
                              content:
                                (cdata && cdata.message) ||
                                '支付可能已成功，请稍后在「会员状态」查看。',
                              showCancel: false,
                            });
                          }
                        })
                        .catch(() => {
                          wx.showModal({
                            title: '网络异常',
                            content: '支付可能已成功，请稍后在「会员状态」查看。',
                            showCancel: false,
                          });
                        });
                    },
                    fail: () => {
                      wx.showModal({
                        title: '请稍后确认',
                        content: '请稍后在「会员状态」查看是否已开通。',
                        showCancel: false,
                      });
                    },
                  });
                },
                fail: (err) => {
                  const raw =
                    (err && err.errMsg) ||
                    (typeof err === 'string' ? err : '') ||
                    '';
                  let msg = '支付未完成';
                  if (/cancel|-2/i.test(raw)) {
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
            wx.showModal({
              title: '下单异常',
              content: '未返回虚拟支付参数，请稍后重试。',
              showCancel: false,
            });
          })
          .catch(() => {
            wx.showToast({ title: '网络错误', icon: 'none' });
          })
          .finally(() => this.setData({ buying: '' }));
      },
      fail: () => {
        wx.showToast({ title: 'wx.login 失败', icon: 'none' });
        this.setData({ buying: '' });
      },
    });
  },
});
