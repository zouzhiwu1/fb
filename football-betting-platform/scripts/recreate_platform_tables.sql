-- 删除并重建 platform 核心业务表（与 app/models.py 一致）
-- 注意：会清空用户、验证码、会员、综合评估队列表等，仅适合开发/测试。生产环境请勿直接执行。

USE football_betting;

-- 1. 关闭外键检查后删表，避免「先删谁」导致删不干净
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS evaluation_matches;
DROP TABLE IF EXISTS membership_records;
DROP TABLE IF EXISTS verification_codes;
DROP TABLE IF EXISTS users;
SET FOREIGN_KEY_CHECKS = 1;

-- 2. 创建 users
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表：用户名、性别、手机号、邮箱、密码哈希；含新人周会员赠送时间标记';

-- 3. 创建 verification_codes
CREATE TABLE verification_codes (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    phone VARCHAR(20) NOT NULL COMMENT '接收验证码的手机号',
    code VARCHAR(10) NOT NULL COMMENT '验证码明文或存储值',
    expires_at DATETIME NOT NULL COMMENT '验证码过期时间',
    used_at DATETIME NULL COMMENT '校验成功并消费的时间；未使用则为空',
    created_at DATETIME NULL COMMENT '本条验证码记录生成时间',
    INDEX idx_phone (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='短信验证码记录：用于注册、找回密码等场景';

-- 4. 创建 membership_records
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会员记录：用户 ID、会员类型、生效/失效时间、来源（赠送/购买）、订单号（购买时）；可多条叠加';

-- 5. 创建 evaluation_matches
CREATE TABLE evaluation_matches (
    match_date CHAR(8) NOT NULL COMMENT '比赛日，固定长度字符串 YYYYMMDD',
    home_team VARCHAR(128) NOT NULL COMMENT '参赛的主场球队名称',
    away_team VARCHAR(128) NOT NULL COMMENT '参赛的客场球队名称',
    PRIMARY KEY (match_date, home_team, away_team)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='正在综合评估的比赛，完场后删除';
