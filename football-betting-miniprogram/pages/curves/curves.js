const api = require('../../utils/api.js');

function todayYmd() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}${m}${d}`;
}

Page({
  data: {
    date: '',
    team: '',
    dates: [],
    items: [],
    searching: false,
    loadingDates: true,
  },

  onLoad() {
    this.setData({ date: todayYmd() });
    api
      .request('/api/curves/dates', { method: 'GET' })
      .then(({ ok, data }) => {
        if (ok && data.dates && data.dates.length) {
          this.setData({ dates: data.dates.slice(0, 12) });
        }
      })
      .catch(() => {})
      .finally(() => {
        this.setData({ loadingDates: false });
      });
  },

  onDate(e) {
    this.setData({ date: e.detail.value });
  },

  onTeam(e) {
    this.setData({ team: e.detail.value });
  },

  pickDate(e) {
    this.setData({ date: e.currentTarget.dataset.dt });
  },

  async onSearch() {
    const token = api.getToken();
    if (!token) {
      wx.showToast({ title: '请先登录', icon: 'none' });
      return;
    }
    const d = (this.data.date || '').trim();
    if (!/^\d{8}$/.test(d)) {
      wx.showToast({ title: '日期须为 YYYYMMDD', icon: 'none' });
      return;
    }
    const team = (this.data.team || '').trim();
    if (!team) {
      wx.showToast({ title: '请输入球队关键词', icon: 'none' });
      return;
    }
    this.setData({ searching: true, items: [] });
    const q = `date=${encodeURIComponent(d)}&team=${encodeURIComponent(team)}`;
    try {
      const { ok, status, data } = await api.request(`/api/curves/search?${q}`, {
        method: 'GET',
        token,
      });
      if (status === 401) {
        wx.showToast({ title: data.message || '登录已失效', icon: 'none' });
        this.setData({ searching: false });
        return;
      }
      if (data.error) {
        wx.showModal({ title: '查询失败', content: data.error, showCancel: false });
        this.setData({ searching: false });
        return;
      }
      if (data.member_only && data.message) {
        wx.showToast({ title: data.message, icon: 'none', duration: 2500 });
      }
      const list = data.items || [];
      if (list.length === 0 && !data.member_only) {
        wx.showToast({ title: '该条件下没有可展示的曲线图', icon: 'none' });
      }
      const enriched = [];
      for (let i = 0; i < list.length; i += 1) {
        const it = list[i];
        const url = api.curveImageUrl(it.date, it.filename);
        try {
          const localPath = await api.downloadAuthorizedFile(url, token);
          enriched.push({
            ...it,
            localPath,
            loadError: false,
            k: `${it.date}-${it.filename}-${i}`,
          });
        } catch {
          enriched.push({
            ...it,
            localPath: '',
            loadError: true,
            k: `${it.date}-${it.filename}-${i}`,
          });
        }
      }
      this.setData({ items: enriched });
    } catch {
      wx.showToast({ title: '网络错误', icon: 'none' });
    } finally {
      this.setData({ searching: false });
    }
  },
});
