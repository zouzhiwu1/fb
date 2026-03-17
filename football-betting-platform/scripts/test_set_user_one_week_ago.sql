-- 测试用：把用户改为「一周前注册」，且赠送的周会员已过期
-- 不用变量，直接写死时间，避免 DBeaver 执行脚本时对 SET @变量 的语法解析报错

USE football_betting;

-- 1. 修改 users：created_at、updated_at、free_week_granted_at 改为一周前（2026-03-08）
UPDATE users
SET
  created_at = '2026-03-08 10:00:00',
  updated_at = '2026-03-08 10:00:00',
  free_week_granted_at = '2026-03-08 10:00:00'
WHERE id = 1;

-- 2. 修改该用户的「赠送」周会员记录：生效为一周前，失效为 2026-03-15 00:00（已过期）
UPDATE membership_records
SET
  effective_at = '2026-03-08 10:00:00',
  expires_at = '2026-03-15 00:00:00'
WHERE user_id = 1 AND source = 'gift';
