const api = require('../../utils/api.js');

function todayYmd() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}${m}${d}`;
}

function offsetYmd(offsetDays) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}${m}${day}`;
}

Page({
  data: {
    date: '',
    pickerDate: '',
    team: '',
    items: [],
    searching: false,
    inlineHint: '',
  },

  onLoad() {
    this.initDefaultSearch();
  },

  async initDefaultSearch() {
    const token = api.getToken();
    if (!token) {
      const date = todayYmd();
      this.setData({
        date,
        pickerDate: `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}`,
        team: '',
      });
      return;
    }
    let isMember = false;
    try {
      const { ok, status, data } = await api.request('/api/membership/status', {
        method: 'GET',
        token,
      });
      if (status === 401 || !ok) {
        wx.showToast({ title: data.message || '请先登录', icon: 'none' });
        return;
      }
      isMember = !!data.is_member;
    } catch {
      isMember = false;
    }
    const date = isMember ? todayYmd() : offsetYmd(-1);
    this.setData({
      date,
      pickerDate: `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}`,
      team: '',
    });
    this.onSearch();
  },

  onDate(e) {
    const raw = e.detail.value || '';
    const normalized = /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw.replace(/-/g, '') : raw;
    this.setData({ date: normalized, pickerDate: raw });
  },

  onTeam(e) {
    this.setData({ team: e.detail.value });
  },

  async onSearch() {
    const token = api.getToken();
    if (!token) {
      this.setData({ inlineHint: '请先登录后再查询' });
      return;
    }
    const d = (this.data.date || '').trim();
    if (!/^\d{8}$/.test(d)) {
      this.setData({ inlineHint: '日期须为 YYYYMMDD' });
      return;
    }
    const team = (this.data.team || '').trim();
    this.setData({ searching: true, items: [], inlineHint: '' });
    const q = `date=${encodeURIComponent(d)}&team=${encodeURIComponent(team)}`;
    try {
      const { ok, status, data } = await api.request(`/api/curves/search?${q}`, {
        method: 'GET',
        token,
      });
      if (status === 401) {
        this.setData({ inlineHint: data.message || '登录已失效，请重新登录' });
        this.setData({ searching: false });
        return;
      }
      if (data.error) {
        this.setData({ inlineHint: data.error });
        this.setData({ searching: false });
        return;
      }
      if (data.member_only && data.message) {
        this.setData({ inlineHint: data.message });
      }
      const list = data.items || [];
      if (list.length === 0 && !data.member_only) {
        this.setData({
          inlineHint: team ? '该日期下没有与该球队相关的曲线图' : '该日期下没有可展示的曲线图',
        });
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
      this.setData({ inlineHint: '网络错误，请稍后重试' });
    } finally {
      this.setData({ searching: false });
    }
  },
});
