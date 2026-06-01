const api = require('../../utils/api.js');

function fmtLocal(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
  } catch {
    return iso;
  }
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
    activeExpiresAtFmt: '',
    activeDaysText: '',
    showSegment: false,
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
        const days = data.days_remaining;
        let daysText = '';
        if (days != null) {
          daysText =
            days > 0
              ? `总剩余约 ${days} 天（至上述日期止）`
              : '总权益即将到期，请以到期时刻为准';
        }
        const activeDays = data.active_days_remaining;
        const hasPending = (data.pending_records || []).length > 0;
        let activeDaysText = '';
        if (hasPending && data.active_expires_at && activeDays != null) {
          activeDaysText =
            activeDays > 0
              ? `本段剩余约 ${activeDays} 天；续期权益将在生效后继续累计`
              : '本段即将结束，续期权益将接续生效';
        }
        const mapRec = (r) => ({
          ...r,
          effFmt: fmtLocal(r.effective_at),
          expFmt: fmtLocal(r.expires_at),
          orderShort: shortOrderId(r.order_id),
          statusLabel: r.status_label || (r.status === 'pending' ? '待生效' : '生效中'),
          isPending: r.status === 'pending',
        });
        const records = [
          ...(data.active_records || []).map(mapRec),
          ...(data.pending_records || []).map(mapRec),
        ];
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
          activeExpiresAtFmt: fmtLocal(data.active_expires_at),
          activeDaysText,
          showSegment: hasPending && !!data.active_expires_at,
          records,
          giftText,
        });
      })
      .catch(() => {
        this.setData({ loading: false, err: '网络错误' });
      });
  },
});
