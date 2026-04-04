-- 已有 partner 库升级：服务费累计与结算流水。
-- 若列/表已存在，请注释掉对应语句后执行。

ALTER TABLE agents
  ADD COLUMN settled_commission_yuan DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '累计已结算服务费（元）';

CREATE TABLE IF NOT EXISTS agent_commission_settlements (
  id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
  partner_admin_id INT NULL COMMENT '操作结算的管理员 ID，关联 partner_admins.id',
  agent_id INT NOT NULL COMMENT '被结算的代理商 ID，关联 agents.id',
  settlement_month VARCHAR(7) NULL COMMENT '结算月份 YYYY-MM',
  payment_channel VARCHAR(16) NULL COMMENT '支付渠道：alipay/wechat',
  payment_reference VARCHAR(256) NULL COMMENT '支付凭证号（支付宝/微信订单号）',
  payment_note TEXT NULL COMMENT '打款备注',
  amount_yuan DECIMAL(14,2) NOT NULL COMMENT '本次结算金额（元）',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '结算记录创建时间',
  KEY ix_acs_partner_admin (partner_admin_id),
  KEY ix_acs_agent (agent_id),
  KEY ix_acs_settlement_month (settlement_month),
  CONSTRAINT fk_acs_partner_admin FOREIGN KEY (partner_admin_id) REFERENCES partner_admins (id),
  CONSTRAINT fk_acs_agent FOREIGN KEY (agent_id) REFERENCES agents (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='代理商服务费结算流水';
