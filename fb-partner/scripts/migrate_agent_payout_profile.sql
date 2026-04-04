-- 代理商：登录名加长（邮箱）、线下收款档案（支付渠道+账号+收款实名）。
-- 在已有 agents 表上执行；若列已存在或 MODIFY 不适用请按需注释。

ALTER TABLE agents
  MODIFY COLUMN login_name VARCHAR(128) NOT NULL;

ALTER TABLE agents
  ADD COLUMN payout_channel VARCHAR(16) NULL COMMENT 'alipay | wechat',
  ADD COLUMN payout_account VARCHAR(256) NULL COMMENT '收款账号（支付宝/微信）',
  ADD COLUMN payout_holder_name VARCHAR(64) NULL COMMENT '收款实名';
