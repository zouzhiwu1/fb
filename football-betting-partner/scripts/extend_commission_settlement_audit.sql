-- 佣金结算流水扩展：操作管理员、结算月份、代理商银行账户快照。
-- 在已存在 agent_commission_settlements 的库上执行；若列已存在请注释对应行。

ALTER TABLE agent_commission_settlements
  ADD COLUMN partner_admin_id INT NULL,
  ADD COLUMN settlement_month VARCHAR(7) NULL,
  ADD COLUMN agent_bank_account TEXT NULL,
  ADD KEY ix_acs_partner_admin (partner_admin_id),
  ADD KEY ix_acs_settlement_month (settlement_month),
  ADD CONSTRAINT fk_acs_partner_admin FOREIGN KEY (partner_admin_id) REFERENCES partner_admins (id);
