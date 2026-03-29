-- 空库或误删全表后：一次性重建 platform + partner 共用库中的核心表。
-- 用法（库名与 .env 中 DATABASE_URL 一致）：
--   mysql -h HOST -u USER -p DATABASE_NAME < scripts/init_full_stack.sql
-- DBeaver：选中目标库后整段执行；会清空下列表中的数据。

SET NAMES utf8mb4;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS agent_commission_settlements;
DROP TABLE IF EXISTS points_ledger;
DROP TABLE IF EXISTS agents;
DROP TABLE IF EXISTS partner_admins;
DROP TABLE IF EXISTS payment_orders;
DROP TABLE IF EXISTS membership_records;
DROP TABLE IF EXISTS evaluation_matches;
DROP TABLE IF EXISTS verification_codes;
DROP TABLE IF EXISTS users;
SET FOREIGN_KEY_CHECKS = 1;

-- ========== platform（与 football-betting-platform app/models.py 一致）==========

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    username VARCHAR(64) NULL COMMENT '登录用户名，唯一；兼容旧数据可为空',
    gender VARCHAR(10) NULL COMMENT '性别：男/女/其他',
    phone VARCHAR(20) NOT NULL COMMENT '手机号，注册必填，唯一',
    email VARCHAR(128) NULL COMMENT '邮箱',
    password_hash VARCHAR(255) NULL COMMENT '密码哈希；新注册必填，兼容旧数据可为空',
    session_version INT NOT NULL DEFAULT 1 COMMENT '登录会话版本号：每次登录自增，旧 token 失效',
    created_at DATETIME NULL COMMENT '记录创建时间（应用层通常为 UTC）',
    updated_at DATETIME NULL COMMENT '记录最后更新时间（应用层通常为 UTC）',
    free_week_granted_at DATETIME NULL COMMENT '新人赠送周会员的生效时间；非空表示已赠送过（每人仅一次）',
    UNIQUE KEY uk_username (username),
    UNIQUE KEY uk_phone (phone),
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

CREATE TABLE verification_codes (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    phone VARCHAR(20) NOT NULL COMMENT '接收验证码的手机号',
    code VARCHAR(10) NOT NULL COMMENT '验证码明文或存储值',
    expires_at DATETIME NOT NULL COMMENT '验证码过期时间',
    used_at DATETIME NULL COMMENT '校验成功并消费的时间；未使用则为空',
    created_at DATETIME NULL COMMENT '本条验证码记录生成时间',
    INDEX idx_phone (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='短信验证码记录';

CREATE TABLE membership_records (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    user_id INT NOT NULL COMMENT '用户 ID，外键关联 users.id',
    membership_type VARCHAR(20) NOT NULL COMMENT '会员类型：week/month/quarter/year',
    effective_at DATETIME NOT NULL COMMENT '会员权益开始生效时间',
    expires_at DATETIME NOT NULL COMMENT '会员权益到期时间',
    source VARCHAR(20) NOT NULL COMMENT '来源：gift 新人赠送 / purchase 付费购买',
    order_id VARCHAR(128) NULL COMMENT '付费订单号；赠送场景可为空',
    INDEX idx_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会员记录';

CREATE TABLE evaluation_matches (
    match_date CHAR(8) NOT NULL COMMENT '比赛日 YYYYMMDD',
    home_team VARCHAR(128) NOT NULL COMMENT '主场球队名称',
    away_team VARCHAR(128) NOT NULL COMMENT '客场球队名称',
    PRIMARY KEY (match_date, home_team, away_team)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='正在综合评估的比赛';

CREATE TABLE payment_orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    out_trade_no VARCHAR(64) NOT NULL COMMENT '商户订单号',
    user_id INT NOT NULL,
    membership_type VARCHAR(20) NOT NULL,
    total_amount VARCHAR(16) NOT NULL COMMENT '与支付宝 total_amount 一致',
    subject VARCHAR(256) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/paid/closed',
    trade_no VARCHAR(64) NULL COMMENT '支付宝交易号',
    created_at DATETIME NULL,
    paid_at DATETIME NULL,
    UNIQUE KEY uk_out_trade_no (out_trade_no),
    KEY idx_user_id (user_id),
    CONSTRAINT fk_payment_orders_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========== partner（与 football-betting-partner app/models.py 一致）==========

CREATE TABLE partner_admins (
  id INT AUTO_INCREMENT PRIMARY KEY,
  login_name VARCHAR(64) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  session_version INT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_partner_admins_login (login_name),
  KEY ix_partner_admins_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE agents (
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

CREATE TABLE agent_commission_settlements (
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

CREATE TABLE points_ledger (
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
  KEY ix_pl_created (created_at),
  CONSTRAINT fk_pl_agent FOREIGN KEY (agent_id) REFERENCES agents (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- C 端用户归属代理商（platform 注册/绑定时写入）
ALTER TABLE users
  ADD COLUMN agent_id INT NULL,
  ADD KEY ix_users_agent_id (agent_id);
