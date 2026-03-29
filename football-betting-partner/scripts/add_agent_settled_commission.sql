-- 已有 partner 库升级：佣金累计与结算流水。
-- 若列/表已存在，请注释掉对应语句后执行。

ALTER TABLE agents
  ADD COLUMN settled_commission_yuan DECIMAL(14,2) NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS agent_commission_settlements (
  id INT AUTO_INCREMENT PRIMARY KEY,
  partner_admin_id INT NULL,
  agent_id INT NOT NULL,
  settlement_month VARCHAR(7) NULL,
  agent_bank_account TEXT NULL,
  amount_yuan DECIMAL(14,2) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_acs_partner_admin (partner_admin_id),
  KEY ix_acs_agent (agent_id),
  KEY ix_acs_settlement_month (settlement_month),
  CONSTRAINT fk_acs_partner_admin FOREIGN KEY (partner_admin_id) REFERENCES partner_admins (id),
  CONSTRAINT fk_acs_agent FOREIGN KEY (agent_id) REFERENCES agents (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
