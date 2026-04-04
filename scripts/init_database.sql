-- =============================================================================
-- football-betting 全库初始化（platform + partner 共用 MySQL 库）
-- =============================================================================
-- 与以下代码保持一致（变更表结构时请同步改此文件）：
--   football-betting-platform/app/models.py
--   football-betting-partner/app/models.py
--
-- 警告：会 DROP 下列表并重建，所有业务数据清空。仅用于空库、开发/测试或明确要重建时。
-- 成功后：配置 PARTNER_ROOT_PASSWORD、JWT 等并重启 platform / partner。
--
-- 用法（将 YOUR_DB 换成 .env 中 DATABASE_URL 的库名）：
--   mysql -h HOST -u USER -p YOUR_DB < scripts/init_database.sql
--
-- 或在本机已配置 partner/.env 时：
--   cd football-betting-partner && .venv/bin/python scripts/init_database.py
--
-- DBeaver（最容易踩坑）：
--   • 「执行 SQL 语句」（菜单第一项、工具栏最上面单独闪电 / 快捷键 Ctrl+Enter）：
--     只会执行光标所在的【那一条】语句。即使用 Cmd+A 全选，也不会按顺序跑完整文件，表不会建好。
--   • 必须用「执行 SQL 脚本」（菜单第二项 Execute SQL Script、闪电旁带小文档/脚本的图标、多为 Alt+X）：
--     才会从第一行到最后一行顺序执行全部 DROP/CREATE。
--   • 单独跑到 CREATE points_ledger 而没建 agents → 报 1824。
--   • 执行成功后：左侧 football_betting → 表 → 右键 → 刷新。
--
-- 其它客户端：命令行建议 mysql … YOUR_DB < init_database.sql（库名在命令里指定）。
-- DBeaver：若左侧未选中库，请取消下面注释并把库名改成与 .env 一致（与 init_database.py 无关）。
-- =============================================================================

-- USE football_betting;

SET NAMES utf8mb4;

/* DBeaver：带「闪电+文档」= 执行整个脚本（Execute SQL Script），多为 Alt+X。
   仅「闪电」= Ctrl+Enter 只跑光标一句，建表不会执行。成功后：表 → 右键 → 刷新。 */
SELECT '若只有本行结果、没有表：你用了 Ctrl+Enter，请 Alt+X 执行完整文件' AS dbeaver_check;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS agent_commission_settlements;
DROP TABLE IF EXISTS points_ledger;
DROP TABLE IF EXISTS payment_orders;
DROP TABLE IF EXISTS membership_records;
DROP TABLE IF EXISTS agents;
DROP TABLE IF EXISTS partner_admins;
DROP TABLE IF EXISTS evaluation_matches;
DROP TABLE IF EXISTS verification_codes;
DROP TABLE IF EXISTS users;

-- ---------------------------------------------------------------------------
-- platform（用户、验证码、会员、评估队列、支付订单）
-- ---------------------------------------------------------------------------

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
    agent_id INT NULL COMMENT '拉新归属代理商 agents.id；无 FK 便于迁移顺序',
    UNIQUE KEY uk_username (username),
    UNIQUE KEY uk_phone (phone),
    INDEX idx_email (email),
    INDEX ix_users_agent_id (agent_id)
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

CREATE TABLE evaluation_matches (
    match_date CHAR(8) NOT NULL COMMENT '比赛日 YYYYMMDD',
    home_team VARCHAR(128) NOT NULL COMMENT '主场球队名称',
    away_team VARCHAR(128) NOT NULL COMMENT '客场球队名称',
    PRIMARY KEY (match_date, home_team, away_team)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='正在综合评估的比赛';

CREATE TABLE membership_records (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    user_id INT NOT NULL COMMENT '用户 ID，外键关联 users.id',
    membership_type VARCHAR(20) NOT NULL COMMENT '会员类型：week/month/quarter/year',
    effective_at DATETIME NOT NULL COMMENT '会员权益开始生效时间',
    expires_at DATETIME NOT NULL COMMENT '会员权益到期时间',
    source VARCHAR(20) NOT NULL COMMENT '来源：gift 新人赠送 / purchase 付费购买',
    order_id VARCHAR(128) NULL COMMENT '付费订单号；赠送场景可为空',
    INDEX idx_user_id (user_id),
    CONSTRAINT fk_membership_records_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会员记录';

CREATE TABLE payment_orders (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    out_trade_no VARCHAR(64) NOT NULL COMMENT '商户订单号',
    user_id INT NOT NULL COMMENT '用户 ID，外键关联 users.id',
    membership_type VARCHAR(20) NOT NULL COMMENT '购买的会员类型：week/month/quarter/year',
    total_amount VARCHAR(16) NOT NULL COMMENT '与支付宝 total_amount 一致',
    subject VARCHAR(256) NOT NULL COMMENT '订单标题/商品描述',
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/paid/closed',
    trade_no VARCHAR(64) NULL COMMENT '支付宝交易号',
    created_at DATETIME NULL COMMENT '订单创建时间',
    paid_at DATETIME NULL COMMENT '支付完成时间；未支付为空',
    UNIQUE KEY uk_out_trade_no (out_trade_no),
    KEY idx_user_id (user_id),
    CONSTRAINT fk_payment_orders_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会员支付订单';

-- ---------------------------------------------------------------------------
-- partner（管理员、代理商、服务费结算流水、积分流水）
-- ---------------------------------------------------------------------------

CREATE TABLE partner_admins (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    login_name VARCHAR(64) NOT NULL COMMENT '管理员登录名，唯一',
    password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
    status VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT '状态：active/disabled',
    session_version INT NOT NULL DEFAULT 1 COMMENT '登录会话版本号：每次登录自增，旧 token 失效',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY uq_partner_admins_login (login_name),
    KEY ix_partner_admins_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='合作方管理员';

CREATE TABLE agents (
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
    current_rate DECIMAL(6,4) NOT NULL DEFAULT 0 COMMENT '当前服务费比例',
    bank_info TEXT NULL COMMENT '银行信息备注（历史兼容字段）',
    status VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT '状态：active/disabled',
    session_version INT NOT NULL DEFAULT 1 COMMENT '登录会话版本号：每次登录自增，旧 token 失效',
    settled_commission_yuan DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '累计已结算服务费（元）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY uq_agents_agent_code (agent_code),
    UNIQUE KEY uq_agents_login_name (login_name),
    UNIQUE KEY uq_agents_phone (phone),
    KEY ix_agents_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='代理商档案';

CREATE TABLE agent_commission_settlements (
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

CREATE TABLE payout_orders (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    order_id VARCHAR(64) NOT NULL COMMENT '支付单号（业务唯一）',
    agent_id INT NOT NULL COMMENT '代理商 ID，关联 agents.id',
    total_amount DECIMAL(14,2) NOT NULL COMMENT '本次支付总金额（元）',
    paid_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '实际支付时间',
    paid_by_admin_id INT NULL COMMENT '经办管理员 ID，关联 partner_admins.id',
    payout_reference VARCHAR(256) NOT NULL COMMENT '线下支付凭证号/流水号',
    status VARCHAR(16) NOT NULL DEFAULT 'paid' COMMENT '支付状态：draft/paid/cancelled/reversed',
    remark TEXT NULL COMMENT '备注',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uq_po_order_id (order_id),
    KEY ix_po_agent (agent_id),
    KEY ix_po_admin (paid_by_admin_id),
    KEY ix_po_status (status),
    CONSTRAINT fk_po_agent FOREIGN KEY (agent_id) REFERENCES agents (id),
    CONSTRAINT fk_po_admin FOREIGN KEY (paid_by_admin_id) REFERENCES partner_admins (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='服务费支付主表（线下打款批次）';

CREATE TABLE agent_commission_lines (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    agent_id INT NOT NULL COMMENT '代理商 ID，关联 agents.id',
    user_id INT NOT NULL COMMENT '用户 ID',
    username VARCHAR(128) NOT NULL DEFAULT '' COMMENT '用户名快照（展示）',
    commission_type VARCHAR(16) NOT NULL COMMENT '服务费类型：registration/recharge',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '服务费产生时间',
    reg_factor DECIMAL(14,4) NULL COMMENT '拉新系数快照（仅拉新行）',
    payment_order_id VARCHAR(64) NULL COMMENT '充值订单 ID（仅充值行）',
    recharge_amount DECIMAL(14,2) NULL COMMENT '充值金额快照（仅充值行）',
    rebate_rate DECIMAL(6,4) NULL COMMENT '分润率快照（仅充值行）',
    commission_amount DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '本行应付服务费（元）',
    payment_status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '支付状态：pending/paid',
    paid_at DATETIME NULL COMMENT '支付时间',
    paid_by_admin_id INT NULL COMMENT '经办管理员 ID，关联 partner_admins.id',
    payout_reference VARCHAR(256) NULL COMMENT '线下打款凭证号',
    payment_batch_id VARCHAR(64) NULL COMMENT '批量打款批次号',
    payout_order_id INT NULL COMMENT '支付主表 ID，关联 payout_orders.id',
    KEY ix_acl_agent (agent_id),
    KEY ix_acl_user (user_id),
    KEY ix_acl_type (commission_type),
    KEY ix_acl_created (created_at),
    KEY ix_acl_payment_order (payment_order_id),
    KEY ix_acl_status (payment_status),
    KEY ix_acl_batch (payment_batch_id),
    KEY ix_acl_paid_at (paid_at),
    KEY ix_acl_payout_order (payout_order_id),
    UNIQUE KEY uq_acl_registration (agent_id, user_id, commission_type),
    UNIQUE KEY uq_acl_recharge (agent_id, payment_order_id, commission_type),
    CONSTRAINT fk_acl_agent FOREIGN KEY (agent_id) REFERENCES agents (id),
    CONSTRAINT fk_acl_admin FOREIGN KEY (paid_by_admin_id) REFERENCES partner_admins (id),
    CONSTRAINT fk_acl_payout_order FOREIGN KEY (payout_order_id) REFERENCES payout_orders (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='服务费明细（拉新/充值统一）';

CREATE TABLE points_ledger (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    agent_id INT NOT NULL COMMENT '代理商 ID，关联 agents.id',
    user_id INT NULL COMMENT '关联用户 ID（可空）',
    order_id VARCHAR(64) NULL COMMENT '关联订单号（可空）',
    event_type VARCHAR(32) NOT NULL COMMENT '事件类型：registration/recharge 等',
    base_amount DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '计算积分前的基准金额',
    applied_rate DECIMAL(6,4) NOT NULL DEFAULT 0 COMMENT '应用的服务费比例',
    points_delta DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '本次积分变动（正负）',
    settlement_month VARCHAR(7) NULL COMMENT '归属结算月份 YYYY-MM',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '流水创建时间',
    KEY ix_pl_agent (agent_id),
    KEY ix_pl_user (user_id),
    KEY ix_pl_order (order_id),
    KEY ix_pl_event (event_type),
    KEY ix_pl_month (settlement_month),
    KEY ix_pl_created (created_at),
    CONSTRAINT fk_pl_agent FOREIGN KEY (agent_id) REFERENCES agents (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='代理商积分流水';

SET FOREIGN_KEY_CHECKS = 1;

-- 执行结果里应出现 current_database 与约 9 张表；若 current_database 为 NULL 说明未选中库。
SELECT DATABASE() AS current_database;
SHOW TABLES;
