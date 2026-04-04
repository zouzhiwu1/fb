const api = require('../../utils/api.js');

function fmtLocal(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('zh-CN', { hour12: false });
  } catch {
    return iso;
  }
}

function daysRemaining(iso) {
  if (!iso) return null;
  const end = new Date(iso);
  const now = new Date();
  const ms = end.getTime() - now.getTime();
  if (ms <= 0) return 0;
  return Math.ceil(ms / 86400000);
}

function shortOrderId(id) {
  if (id == null || id === '') return '—';
  const s = String(id);
  return s.length > 18 ? `${s.slice(0, 18)}…` : s;
}

Page({
  data: {
    loading: true,
    err: '',
    isMember: false,
    expiresAt: '',
    expiresAtFmt: '',
    daysLeft: null,
    daysText: '',
    records: [],
    giftText: '',
  },

  onShow() {
    if (!api.getToken()) {
      wx.reLaunch({ url: '/pages/login/login' });
      return;
    }
    this.load();
  },

  onPullDownRefresh() {
    this.load().finally(() => wx.stopPullDownRefresh());
  },

  load() {
    const token = api.getToken();
    this.setData({ loading: true, err: '' });
    return api
      .request('/api/membership/status', { method: 'GET', token })
      .then(({ ok, data }) => {
        if (!ok || !data.ok) {
          this.setData({
            loading: false,
            err: data.message || '加载失败',
          });
          return;
        }
        const isMember = !!data.is_member;
        const expiresAt = data.expires_at || '';
        const days = daysRemaining(expiresAt);
        let daysText = '';
        if (days !== null) {
          daysText =
            days > 0
              ? `剩余约 ${days} 天`
              : '即将到期或已临近边界，请以到期时刻为准';
        }
        const raw = data.active_records || [];
        const records = raw.map((r) => ({
          ...r,
          effFmt: fmtLocal(r.effective_at),
          expFmt: fmtLocal(r.expires_at),
          orderShort: shortOrderId(r.order_id),
        }));
        let giftText = '';
        if (data.free_week_granted_at) {
          giftText = `注册赠送周会员已发放过（记录时间：${fmtLocal(
            data.free_week_granted_at,
          )}）。是否仍在有效期内见上表。`;
        }
        this.setData({
          loading: false,
          err: '',
          isMember,
          expiresAt,
          expiresAtFmt: fmtLocal(expiresAt),
          daysLeft: days,
          daysText,
          records,
          giftText,
        });
      })
      .catch(() => {
        this.setData({ loading: false, err: '网络错误' });
      });
  },
});
