-- 与 football-betting-partner 配套；在与 platform 同一 MySQL 库执行。
-- 若列/表已存在，按需注释掉对应语句。
--
-- DBeaver：请按顺序分段执行（Ctrl+Enter / 选中一段执行），每段成功后再执行下一段。
-- 若只执行 points_ledger 会报 1824「Failed to open the referenced table 'agents'」——须先建好 agents。
-- 外键在 agents 建表之后用单独 ALTER 添加，避免部分客户端同批解析顺序问题。

CREATE TABLE IF NOT EXISTS partner_admins (
  id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
  login_name VARCHAR(64) NOT NULL COMMENT '管理员登录名，唯一',
  password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
  status VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT '状态：active/disabled',
  session_version INT NOT NULL DEFAULT 1 COMMENT '登录会话版本号：每次登录自增，旧 token 失效',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  UNIQUE KEY uq_partner_admins_login (login_name),
  KEY ix_partner_admins_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='合作方管理员';

CREATE TABLE IF NOT EXISTS agents (
  id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
  agent_code VARCHAR(32) NOT NULL COMMENT '代理商推广码，唯一',
  login_name VARCHAR(128) NOT NULL COMMENT '代理商登录名（邮箱），唯一',
  password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
  display_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '展示名称/昵称',
  real_name VARCHAR(64) NULL COMMENT '真实姓名',
  age INT NULL COMMENT '年龄',
  phone VARCHAR(20) NULL COMMENT '联系电话',
  bank_account TEXT NULL COMMENT '历史字段：银行卡账号（兼容旧数据）',
  payout_channel VARCHAR(16) NULL COMMENT '收款渠道：alipay/wechat',
  payout_account VARCHAR(256) NULL COMMENT '收款账号（支付宝/微信）',
  payout_holder_name VARCHAR(64) NULL COMMENT '收款实名',
  contact VARCHAR(128) NULL COMMENT '联系信息备注',
  current_rate DECIMAL(6,4) NOT NULL DEFAULT 0 COMMENT '当前佣金比例',
  bank_info TEXT NULL COMMENT '银行信息备注（历史兼容字段）',
  status VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT '状态：active/disabled',
  session_version INT NOT NULL DEFAULT 1 COMMENT '登录会话版本号：每次登录自增，旧 token 失效',
  settled_commission_yuan DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '累计已结算佣金（元）',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  UNIQUE KEY uq_agents_agent_code (agent_code),
  UNIQUE KEY uq_agents_login_name (login_name),
  UNIQUE KEY uq_agents_phone (phone),
  KEY ix_agents_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='代理商档案';

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='代理商佣金结算流水';

CREATE TABLE IF NOT EXISTS points_ledger (
  id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
  agent_id INT NOT NULL COMMENT '代理商 ID，关联 agents.id',
  user_id INT NULL COMMENT '关联用户 ID（可空）',
  order_id VARCHAR(64) NULL COMMENT '关联订单号（可空）',
  event_type VARCHAR(32) NOT NULL COMMENT '事件类型：registration/recharge 等',
  base_amount DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '计算积分前的基准金额',
  applied_rate DECIMAL(6,4) NOT NULL DEFAULT 0 COMMENT '应用的佣金比例',
  points_delta DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '本次积分变动（正负）',
  settlement_month VARCHAR(7) NULL COMMENT '归属结算月份 YYYY-MM',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '流水创建时间',
  KEY ix_pl_agent (agent_id),
  KEY ix_pl_user (user_id),
  KEY ix_pl_order (order_id),
  KEY ix_pl_event (event_type),
  KEY ix_pl_month (settlement_month),
  KEY ix_pl_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='代理商积分流水';

-- 须在 agents 表已存在且为 InnoDB 后执行；重复执行若报外键已存在可忽略或先 DROP 该约束
ALTER TABLE points_ledger
  ADD CONSTRAINT fk_pl_agent FOREIGN KEY (agent_id) REFERENCES agents (id);

-- C 端用户归属代理商（platform 注册/绑定时写入；若列已存在请整段注释）
ALTER TABLE users
  ADD COLUMN agent_id INT NULL COMMENT '拉新归属代理商 agents.id；无 FK 便于迁移顺序',
  ADD KEY ix_users_agent_id (agent_id);
