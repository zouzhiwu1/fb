-- 会员系统：为 users 添加赠送标记，并创建 membership_records 表。
-- 若使用 create_all() 新建库可自动建表；已有库可执行本脚本。
-- 执行前请确认数据库名（如 fb）。

USE fb;

-- 用户表：是否已赠送过周会员（仅一次）
ALTER TABLE users
    ADD COLUMN free_week_granted_at DATETIME NULL COMMENT '新人赠送周会员的生效时间；非空表示已赠送过（每人仅一次）';

-- 为 users 表补充表注释（若列已存在仅执行本句即可）
ALTER TABLE users COMMENT = '用户表：用户名、性别、手机号、邮箱、密码哈希；含新人周会员赠送时间标记';

-- 会员记录表
CREATE TABLE IF NOT EXISTS membership_records (
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

-- 若表早已存在且无表注释，可单独执行以下语句补全
ALTER TABLE membership_records COMMENT = '会员记录：用户 ID、会员类型、生效/失效时间、来源（赠送/购买）、订单号（购买时）；可多条叠加';
