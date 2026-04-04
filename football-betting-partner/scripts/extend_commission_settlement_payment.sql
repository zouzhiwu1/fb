-- 服务费结算流水：线下打款凭证（支付渠道 + 订单号 + 备注），不再使用 agent_bank_account。
-- 在已有 agent_commission_settlements 的库上执行；若列已存在请注释对应行。

ALTER TABLE agent_commission_settlements
  ADD COLUMN payment_channel VARCHAR(16) NULL COMMENT 'alipay | wechat',
  ADD COLUMN payment_reference VARCHAR(256) NULL COMMENT '支付宝/微信账单订单号',
  ADD COLUMN payment_note TEXT NULL COMMENT '备注';
