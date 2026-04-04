-- 服务费结算流水扩展：操作管理员、结算月份、代理商银行账户快照。
-- 在已存在 agent_commission_settlements 的库上执行；若列已存在请注释对应行。

ALTER TABLE agent_commission_settlements
  ADD COLUMN partner_admin_id INT NULL COMMENT '操作结算的管理员 ID，关联 partner_admins.id',
  ADD COLUMN settlement_month VARCHAR(7) NULL COMMENT '结算月份 YYYY-MM',
  ADD COLUMN agent_bank_account TEXT NULL COMMENT '历史字段：代理商银行卡快照（已废弃）',
  ADD KEY ix_acs_partner_admin (partner_admin_id),
  ADD KEY ix_acs_settlement_month (settlement_month),
  ADD CONSTRAINT fk_acs_partner_admin FOREIGN KEY (partner_admin_id) REFERENCES partner_admins (id);

-- 后续若需「支付渠道 + 订单号」凭证，请执行 extend_commission_settlement_payment.sql（新库请用含 payment_* 的建表脚本）。
