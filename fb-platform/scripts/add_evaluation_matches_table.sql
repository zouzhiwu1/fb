-- 正在综合评估的比赛表（与 app.models.EvaluationMatch 一致）
-- 联合主键：(match_date, home_team, away_team)，无单独 id。
-- 若曾创建过旧版（含 id 列），须先删除旧表再执行（会清空该表数据）。

USE fb;

DROP TABLE IF EXISTS evaluation_matches;

CREATE TABLE evaluation_matches (
    match_date CHAR(8) NOT NULL COMMENT '比赛日，固定长度字符串 YYYYMMDD',
    home_team VARCHAR(128) NOT NULL COMMENT '参赛的主场球队名称',
    away_team VARCHAR(128) NOT NULL COMMENT '参赛的客场球队名称',
    PRIMARY KEY (match_date, home_team, away_team)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='正在综合评估的比赛：联合主键为日期+主队+客队';
