-- 与 football-betting-partner 配套；在与 platform 同一 MySQL 库执行。
-- 若列/表已存在，按需注释掉对应语句。
--
-- DBeaver：请按顺序分段执行（Ctrl+Enter / 选中一段执行），每段成功后再执行下一段。
-- 若只执行 points_ledger 会报 1824「Failed to open the referenced table 'agents'」——须先建好 agents。
-- 外键在 agents 建表之后用单独 ALTER 添加，避免部分客户端同批解析顺序问题。

CREATE TABLE IF NOT EXISTS partner_admins (
  id INT AUTO_INCREMENT PRIMARY KEY,
  login_name VARCHAR(64) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  session_version INT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_partner_admins_login (login_name),
  KEY ix_partner_admins_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS agents (
  id INT AUTO_INCREMENT PRIMARY KEY,
  agent_code VARCHAR(32) NOT NULL,
  login_name VARCHAR(64) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  display_name VARCHAR(128) NOT NULL DEFAULT '',
  real_name VARCHAR(64) NULL,
  age INT NULL,
  phone VARCHAR(20) NULL,
  bank_account TEXT NULL,
  contact VARCHAR(128) NULL,
  current_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
  bank_info TEXT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  session_version INT NOT NULL DEFAULT 1,
  settled_commission_yuan DECIMAL(14,2) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_agents_agent_code (agent_code),
  UNIQUE KEY uq_agents_login_name (login_name),
  UNIQUE KEY uq_agents_phone (phone),
  KEY ix_agents_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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

CREATE TABLE IF NOT EXISTS points_ledger (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  agent_id INT NOT NULL,
  user_id INT NULL,
  order_id VARCHAR(64) NULL,
  event_type VARCHAR(32) NOT NULL,
  base_amount DECIMAL(14,2) NOT NULL DEFAULT 0,
  applied_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
  points_delta DECIMAL(14,2) NOT NULL DEFAULT 0,
  settlement_month VARCHAR(7) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_pl_agent (agent_id),
  KEY ix_pl_user (user_id),
  KEY ix_pl_order (order_id),
  KEY ix_pl_event (event_type),
  KEY ix_pl_month (settlement_month),
  KEY ix_pl_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 须在 agents 表已存在且为 InnoDB 后执行；重复执行若报外键已存在可忽略或先 DROP 该约束
ALTER TABLE points_ledger
  ADD CONSTRAINT fk_pl_agent FOREIGN KEY (agent_id) REFERENCES agents (id);

-- C 端用户归属代理商（platform 注册/绑定时写入；若列已存在请整段注释）
ALTER TABLE users
  ADD COLUMN agent_id INT NULL,
  ADD KEY ix_users_agent_id (agent_id);
