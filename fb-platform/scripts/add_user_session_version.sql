-- 为 users 表添加 session_version（单设备登录：每次登录成功自增，旧 token 立即失效）
-- 在 DBeaver 中选中 fb 库执行；若报 Duplicate column name 说明已存在，可忽略。

USE fb;

ALTER TABLE users
  ADD COLUMN session_version INT NOT NULL DEFAULT 1 COMMENT '登录会话版本号：每次登录自增，旧 token 失效';

