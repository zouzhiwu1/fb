-- 已有旧版 partner 表结构时执行：管理员表 + 代理商档案字段。
--
-- DBeaver 等客户端：勿一次执行多条「独立」ALTER（易报 1064）。本文件 agents 段已合并为一条 ALTER。
-- 若某列已存在，从下面 ADD 列表中删掉对应行后再执行。
-- 主 ALTER 不含 bank_account：不少库已先行添加该列，整段执行会 1060 Duplicate column。
-- partner_admins 与 agents 可分两格执行：先 CREATE，再 ALTER。

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

ALTER TABLE agents
  ADD COLUMN real_name VARCHAR(64) NULL,
  ADD COLUMN age INT NULL,
  ADD COLUMN phone VARCHAR(20) NULL;

-- 若 agents 尚无 bank_account 再单独执行（一行即可）：
-- ALTER TABLE agents ADD COLUMN bank_account TEXT NULL;

-- 若 phone 尚无唯一索引（新库已在 add_partner_tables.sql 中建 UNIQUE），再执行：
-- ALTER TABLE agents ADD UNIQUE KEY uq_agents_phone (phone);
