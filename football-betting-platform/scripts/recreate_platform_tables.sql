-- 删除并重建 platform 三张表（与 app/models.py 完全一致）
-- 注意：会清空所有用户、验证码、会员记录，仅适合开发/测试环境。生产环境请勿直接执行。

USE football_betting;

-- 1. 关闭外键检查后删表，避免「先删谁」导致删不干净
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS membership_records;
DROP TABLE IF EXISTS verification_codes;
DROP TABLE IF EXISTS users;
SET FOREIGN_KEY_CHECKS = 1;

-- 2. 创建 users
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NULL,
    gender VARCHAR(10) NULL,
    phone VARCHAR(20) NOT NULL,
    email VARCHAR(128) NULL,
    password_hash VARCHAR(255) NULL,
    created_at DATETIME NULL,
    updated_at DATETIME NULL,
    free_week_granted_at DATETIME NULL,
    UNIQUE KEY uk_username (username),
    UNIQUE KEY uk_phone (phone),
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 创建 verification_codes
CREATE TABLE verification_codes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    phone VARCHAR(20) NOT NULL,
    code VARCHAR(10) NOT NULL,
    expires_at DATETIME NOT NULL,
    used_at DATETIME NULL,
    created_at DATETIME NULL,
    INDEX idx_phone (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. 创建 membership_records（列名为 effective_at，与代码一致）
CREATE TABLE membership_records (
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
