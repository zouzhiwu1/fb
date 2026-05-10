// app.js
var promo = require('./utils/promoAgent.js');

App({
  onLaunch(options) {
    try {
      var aid = promo.parseAgentIdFromOptions(options || {});
      if (!aid && options && options.query) {
        aid =
          promo.parseAgentIdFromOptions(options.query) ||
          (options.query.scene
            ? promo.parseAgentIdFromOptions({ scene: options.query.scene })
            : null);
      }
      if (!aid && typeof wx.getLaunchOptionsSync === 'function') {
        var lo = wx.getLaunchOptionsSync();
        aid = promo.parseAgentIdFromOptions(lo || {});
        if (!aid && lo && lo.query) {
          aid =
            promo.parseAgentIdFromOptions(lo.query) ||
            (lo.query.scene
              ? promo.parseAgentIdFromOptions({ scene: lo.query.scene })
              : null);
        }
      }
      if (aid) {
        promo.persistPendingAgentId(aid);
      }
    } catch (e) {}
  },
  globalData: {},
});
