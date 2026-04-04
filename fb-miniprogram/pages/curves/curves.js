const api = require('../../utils/api.js');
const BATCH_SIZE = 1;

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
    allItems: [],
    loadedCount: 0,
    searching: false,
    loadingMore: false,
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
        api.clearSession();
        wx.showToast({ title: '账号已在其他设备登录，请重新登录', icon: 'none' });
        setTimeout(() => wx.reLaunch({ url: '/pages/login/login' }), 700);
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
    this.setData({
      searching: true,
      items: [],
      allItems: [],
      loadedCount: 0,
      loadingMore: false,
      inlineHint: '',
    });
    const q = `date=${encodeURIComponent(d)}&team=${encodeURIComponent(team)}`;
    try {
      const { ok, status, data } = await api.request(`/api/curves/search?${q}`, {
        method: 'GET',
        token,
      });
      if (status === 401) {
        api.clearSession();
        this.setData({ inlineHint: '账号已在其他设备登录或登录已过期，请重新登录' });
        setTimeout(() => wx.reLaunch({ url: '/pages/login/login' }), 700);
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
      this.setData({ allItems: list, loadedCount: 0, items: [] });
      if (list.length > 0) {
        await this.loadNextBatch();
      }
    } catch {
      this.setData({ inlineHint: '网络错误，请稍后重试' });
    } finally {
      this.setData({ searching: false });
    }
  },

  async loadNextBatch() {
    if (this.data.loadingMore) return;
    const token = api.getToken();
    if (!token) return;
    const start = this.data.loadedCount || 0;
    const all = this.data.allItems || [];
    if (start >= all.length) return;
    const end = Math.min(start + BATCH_SIZE, all.length);
    this.setData({ loadingMore: true });
    const appended = [];
    for (let i = start; i < end; i += 1) {
      const it = all[i];
      const url = api.curveImageUrl(it.date, it.filename);
      try {
        const localPath = await api.downloadAuthorizedFile(url, token);
        appended.push({
          ...it,
          localPath,
          loadError: false,
          k: `${it.date}-${it.filename}-${i}`,
        });
      } catch {
        appended.push({
          ...it,
          localPath: '',
          loadError: true,
          k: `${it.date}-${it.filename}-${i}`,
        });
      }
    }
    this.setData({
      items: (this.data.items || []).concat(appended),
      loadedCount: end,
      loadingMore: false,
    });
  },

  onReachResultBottom() {
    this.loadNextBatch();
  },
});
