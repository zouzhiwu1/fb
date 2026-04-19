-- 微信小程序支付：绑定用户 openid（已有库执行一次；新建库可由 SQLAlchemy create_all 自动加列则不必执行）
-- USE fb;

ALTER TABLE users
    ADD COLUMN wechat_mp_openid VARCHAR(64) NULL COMMENT '微信小程序 openid，用于 JSAPI 支付'
    AFTER free_week_granted_at;

CREATE INDEX idx_users_wechat_mp_openid ON users (wechat_mp_openid);
