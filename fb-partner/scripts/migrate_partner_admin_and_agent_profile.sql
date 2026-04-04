-- 已有旧版 partner 表结构时执行：管理员表 + 代理商档案字段。
--
-- DBeaver 等客户端：勿一次执行多条「独立」ALTER（易报 1064）。本文件 agents 段已合并为一条 ALTER。
-- 若某列已存在，从下面 ADD 列表中删掉对应行后再执行。
-- 主 ALTER 不含 bank_account：不少库已先行添加该列，整段执行会 1060 Duplicate column。
-- partner_admins 与 agents 可分两格执行：先 CREATE，再 ALTER。

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

ALTER TABLE agents
  ADD COLUMN real_name VARCHAR(64) NULL COMMENT '真实姓名',
  ADD COLUMN age INT NULL COMMENT '年龄',
  ADD COLUMN phone VARCHAR(20) NULL COMMENT '联系电话';

-- 若 agents 尚无 bank_account 再单独执行（一行即可）：
-- ALTER TABLE agents ADD COLUMN bank_account TEXT NULL;

-- 若 phone 尚无唯一索引（新库已在 add_partner_tables.sql 中建 UNIQUE），再执行：
-- ALTER TABLE agents ADD UNIQUE KEY uq_agents_phone (phone);
