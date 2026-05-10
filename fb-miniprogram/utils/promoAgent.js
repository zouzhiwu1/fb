/**
 * 代理商推广：太阳码 scene / 入口参数 agent_id 解析与本地暂存。
 * 小程序码 scene 与 partner 后台生成格式一致：agent_id=数字
 */
var STORAGE_KEY = 'pending_promo_agent_id';

function parseAgentIdFromOptions(options) {
  if (!options) return null;
  if (options.scene) {
    var scene = options.scene;
    try {
      scene = decodeURIComponent(scene);
    } catch (e) {
      /* 非编码串 */
    }
    var m = /agent_id=(\d+)/.exec(String(scene));
    if (m) return parseInt(m[1], 10);
  }
  if (options.agent_id) {
    var n = parseInt(String(options.agent_id), 10);
    if (!isNaN(n) && n > 0) return n;
  }
  return null;
}

function persistPendingAgentId(aid) {
  if (aid && aid > 0) {
    try {
      wx.setStorageSync(STORAGE_KEY, aid);
    } catch (e) {}
  }
}

function readPendingAgentId() {
  try {
    var s = wx.getStorageSync(STORAGE_KEY);
    if (s === '' || s === undefined || s === null) return null;
    var n = parseInt(String(s), 10);
    return !isNaN(n) && n > 0 ? n : null;
  } catch (e) {
    return null;
  }
}

function clearPendingAgentId() {
  try {
    wx.removeStorageSync(STORAGE_KEY);
  } catch (e) {}
}

module.exports = {
  STORAGE_KEY: STORAGE_KEY,
  parseAgentIdFromOptions: parseAgentIdFromOptions,
  persistPendingAgentId: persistPendingAgentId,
  readPendingAgentId: readPendingAgentId,
  clearPendingAgentId: clearPendingAgentId,
};
