-- 会员系统：为 users 添加赠送标记，并创建 membership_records 表。
-- 若使用 create_all() 新建库可自动建表；已有库可执行本脚本。
-- 执行前请确认数据库名（如 football_betting）。

USE football_betting;

-- 用户表：是否已赠送过周会员（仅一次）
ALTER TABLE users ADD COLUMN free_week_granted_at DATETIME NULL;

-- 会员记录表
CREATE TABLE IF NOT EXISTS membership_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    membership_type VARCHAR(20) NOT NULL,
    effective_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    source VARCHAR(20) NOT NULL,
    order_id VARCHAR(128) NULL,
    INDEX idx_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
