-- 为 users 表添加 用户名、性别、邮箱 列（若表是旧版创建的）
-- 在 DBeaver 中选中 fb 库，逐条执行下面每条 ALTER。
-- 若某条报 "Duplicate column name" 或 "Duplicate key"，说明该列/索引已存在，可跳过。

USE fb;

-- 以下三条每条单独执行；缺哪列就执行哪条（已存在的列会报错，忽略即可）
ALTER TABLE users ADD COLUMN username VARCHAR(64) NULL COMMENT '登录用户名，唯一；兼容旧数据可为空';
ALTER TABLE users ADD COLUMN gender VARCHAR(10) NULL COMMENT '性别：男/女/其他';
ALTER TABLE users ADD COLUMN email VARCHAR(128) NULL COMMENT '邮箱';

-- 最后为 username 建唯一索引（若已存在会报错，可忽略）
ALTER TABLE users ADD UNIQUE KEY uk_username (username);

-- 表注释（与 app/models.User 一致；若已设置过可重复执行覆盖为同文案）
ALTER TABLE users COMMENT = '用户表：用户名、性别、手机号、邮箱、密码哈希；含新人周会员赠送时间标记';
