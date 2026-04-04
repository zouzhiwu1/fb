# -*- coding: utf-8 -*-
"""
与平台 MySQL 表 evaluation_matches 同步（《会员系统设计书》§3.4）。

- 入表：综合评估已计算并出图后，将当日 car 表中每场写入 evaluation_matches（INSERT IGNORE）。
- 出表：完场比分抓取并写入 final_*.csv 后，按 CSV 行从 evaluation_matches 删除。

队名使用与 plot_car._safe_filename 相同的规则，须与曲线图文件名 {主队}_VS_{客队}.png 一致。

在 config.py 中从环境变量读取 DATABASE_URL（.env 或 export），与平台一致，例如：
  mysql+pymysql://user:pass@127.0.0.1:3306/fb
未配置或非 MySQL 时跳过同步。
"""
from __future__ import annotations

import csv
import logging
import os
import re
from urllib.parse import urlparse, unquote

import pandas as pd

from config import DATABASE_URL, REPORT_DIR

LOG = logging.getLogger(__name__)

# 与 plot_car.py 一致
CAR_HEADER_ROWS = 2


def _safe_filename(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "_", (name or "").strip())
    return s.strip() or "match"


def _mysql_params_from_database_url(url: str) -> dict | None:
    if not (url or "").strip():
        return None
    u = urlparse(url.strip())
    if u.scheme not in ("mysql", "mysql+pymysql"):
        return None
    path = (u.path or "").strip("/")
    database = path.split("/")[0] if path else ""
    if not database:
        return None
    return {
        "host": u.hostname or "localhost",
        "port": int(u.port or 3306),
        "user": unquote(u.username) if u.username else "",
        "password": unquote(u.password) if u.password else "",
        "database": database,
    }


def _connect():
    """返回 PyMySQL 连接；不可用时返回 None。"""
    try:
        import pymysql
    except ImportError:
        LOG.warning("evaluation_matches：未安装 pymysql（pip install pymysql），已跳过同步")
        return None
    params = _mysql_params_from_database_url(DATABASE_URL)
    if not params:
        LOG.debug("DATABASE_URL 未配置或非 MySQL，跳过 evaluation_matches 同步")
        return None
    password = params["password"]
    if password:
        # 与平台 config._pymysql_creator 一致：密码含中文等非 ASCII 时避免 PyMySQL latin-1 报错
        try:
            password = password.encode("utf-8").decode("latin-1")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    try:
        return pymysql.connect(
            host=params["host"],
            port=params["port"],
            user=params["user"],
            password=password,
            database=params["database"],
            charset="utf8mb4",
        )
    except Exception as e:
        LOG.warning("连接 MySQL 失败，跳过 evaluation_matches 同步: %s", e)
        return None


def sync_matches_from_car_for_date(match_date: str) -> int:
    """
    §3.4 入表：读取 REPORT_DIR/{date}/car_{date}.xlsx，对每场 INSERT IGNORE。
    返回本次尝试写入的行数（含已存在而忽略的）。
    """
    if len(match_date) != 8 or not match_date.isdigit():
        LOG.warning("sync_matches_from_car_for_date: 非法日期 %s", match_date)
        return 0
    car_path = os.path.join(REPORT_DIR, match_date, f"car_{match_date}.xlsx")
    if not os.path.isfile(car_path):
        LOG.warning("evaluation_matches：未找到 car 文件，跳过入表: %s（请确认 REPORT_DIR）", car_path)
        return 0
    try:
        df = pd.read_excel(car_path, header=None, engine="openpyxl")
    except Exception as e:
        LOG.warning("读取 car 表失败，跳过入表: %s", e)
        return 0
    if len(df) <= CAR_HEADER_ROWS or df.shape[1] < 2:
        return 0
    body = df.iloc[CAR_HEADER_ROWS:]
    pairs: set[tuple[str, str]] = set()
    for _, row in body.iterrows():
        h = str(row.iloc[0]).strip()
        a = str(row.iloc[1]).strip()
        if not h or not a or h.lower() == "nan" or a.lower() == "nan":
            continue
        pairs.add((_safe_filename(h), _safe_filename(a)))
    if not pairs:
        if len(body) > 0:
            LOG.warning(
                "evaluation_matches：%s 有数据行但解析不出主客队（检查 car 表 A/B 列）",
                car_path,
            )
        return 0
    conn = _connect()
    if conn is None:
        LOG.warning(
            "evaluation_matches 未入表（本日 car 中共有 %d 场待登记）：请配置 DATABASE_URL 并确保能连上 MySQL",
            len(pairs),
        )
        return 0
    sql = (
        "INSERT IGNORE INTO evaluation_matches (match_date, home_team, away_team) "
        "VALUES (%s, %s, %s)"
    )
    n = 0
    try:
        with conn.cursor() as cur:
            for home, away in sorted(pairs):
                cur.execute(sql, (match_date, home, away))
                n += cur.rowcount
        conn.commit()
    except Exception as e:
        LOG.warning("evaluation_matches：执行 INSERT 失败（表是否存在？）: %s", e, exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
    LOG.info(
        "evaluation_matches 入表完成 date=%s 场次数=%d INSERT 新行 rowcount 累加=%d（重复主键 IGNORE 时多为 0）",
        match_date,
        len(pairs),
        n,
    )
    return n


def remove_matches_from_final_csv(match_date: str, csv_path: str) -> int:
    """
    §3.4 出表：根据 final_*.csv 的 home, away 列删除 evaluation_matches 对应行。
    返回 DELETE 影响行数之和。
    """
    if len(match_date) != 8 or not match_date.isdigit():
        return 0
    if not os.path.isfile(csv_path):
        return 0
    conn = _connect()
    if conn is None:
        return 0
    rows: list[tuple[str, str]] = []
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return 0
            for line in reader:
                h = line.get("home") or line.get("Home")
                a = line.get("away") or line.get("Away")
                if h is None or a is None:
                    continue
                hs = _safe_filename(str(h))
                aws = _safe_filename(str(a))
                if hs and aws:
                    rows.append((hs, aws))
    except Exception as e:
        LOG.warning("读取完场 CSV 失败，跳过出表: %s", e)
        conn.close()
        return 0
    if not rows:
        conn.close()
        return 0
    sql = (
        "DELETE FROM evaluation_matches WHERE match_date = %s AND home_team = %s AND away_team = %s"
    )
    total = 0
    try:
        with conn.cursor() as cur:
            for home, away in rows:
                cur.execute(sql, (match_date, home, away))
                total += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    LOG.info("evaluation_matches 出表 date=%s 自 %s 删除 %d 行", match_date, csv_path, total)
    return total
