-- 代理商：登录名加长（邮箱）、线下收款档案（支付渠道+账号+收款实名）。
-- 在已有 agents 表上执行；可重复执行（已存在的列会跳过）。

SET @db = DATABASE();

-- payout_channel
SELECT COUNT(*) INTO @cnt FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'agents' AND COLUMN_NAME = 'payout_channel';
SET @sql = IF(@cnt = 0,
  'ALTER TABLE agents ADD COLUMN payout_channel VARCHAR(16) NULL COMMENT ''alipay | wechat''',
  'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- payout_account
SELECT COUNT(*) INTO @cnt FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'agents' AND COLUMN_NAME = 'payout_account';
SET @sql = IF(@cnt = 0,
  'ALTER TABLE agents ADD COLUMN payout_account VARCHAR(256) NULL COMMENT ''收款账号（支付宝/微信）''',
  'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- payout_holder_name
SELECT COUNT(*) INTO @cnt FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'agents' AND COLUMN_NAME = 'payout_holder_name';
SET @sql = IF(@cnt = 0,
  'ALTER TABLE agents ADD COLUMN payout_holder_name VARCHAR(64) NULL COMMENT ''收款实名''',
  'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 加长登录名（重复执行安全）
ALTER TABLE agents
  MODIFY COLUMN login_name VARCHAR(128) NOT NULL;
