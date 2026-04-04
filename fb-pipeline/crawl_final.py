# -*- coding: utf-8 -*-
"""
抓取完场比分数据：进入「足球」→「完场比分」→「beidan」，抓取主队、客队、比分，
并输出 CSV 供 add_score_to_image.py 写入报告图片。

用法:
  python crawl_final.py [YYYYMMDD]
  - 无参数：使用昨日日期（完场日一般为前一天）
  - 有参数：使用指定日期，与报告目录 REPORT_DIR/YYYYMMDD 对应

输出: REPORT_DIR/{YYYYMMDD}/final_{YYYYMMDD}.csv，列：home,away,score
"""
import csv
import logging
import os
import sys
from datetime import datetime, timedelta

from config import BASE_URL, REPORT_DIR, DEBUG_LOG_DIR, LOG_RETENTION_DAYS
from log_cleanup import delete_old_logs
from scraper_final import run_finished_scraper
from evaluation_sync import remove_matches_from_final_csv

# 复用 crawl_real 的 driver 创建与日志目录
from crawl_real import create_driver


def _setup_logging():
    """配置 crawl_final 独立日志（与 crawl_real 同目录，文件名带 crawl_final）。"""
    os.makedirs(DEBUG_LOG_DIR, exist_ok=True)
    time_suffix = datetime.now().strftime("%Y%m%d%H")
    log_path = os.path.join(DEBUG_LOG_DIR, f"crawl_final_{time_suffix}.log")
    logger = logging.getLogger("crawl_final")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    # 相对路径以 pipeline 父目录为根，日志中不含外层 fb/ 前缀
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    rel_log_path = os.path.relpath(log_path, project_root)
    logger.info("日志文件: %s", rel_log_path)
    return logger


def main():
    log = _setup_logging()
    removed = delete_old_logs(DEBUG_LOG_DIR, days=LOG_RETENTION_DAYS)
    if removed:
        _display_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        rel_removed = [os.path.relpath(p, _display_root) for p in removed]
        log.info("已删除 %d 个超过 %d 天的日志文件: %s", len(removed), LOG_RETENTION_DAYS, rel_removed)

    args = sys.argv[1:]
    if len(args) == 0:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        target_date = yesterday
        log.info("未指定日期，使用昨日: %s", target_date)
    elif len(args) == 1 and len(args[0]) == 8 and args[0].isdigit():
        target_date = args[0]
    else:
        log.error("用法: python crawl_final.py [YYYYMMDD]，例如: python crawl_final.py 20260312")
        sys.exit(1)

    driver = None
    try:
        log.info("创建 Chrome 驱动...")
        driver = create_driver()
        log.info("开始抓取完场比分（日期=%s）", target_date)
        rows = run_finished_scraper(driver, target_date_yyyymmdd=target_date, base_url=BASE_URL)
        out_dir = os.path.join(REPORT_DIR, target_date)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"final_{target_date}.csv")
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["home", "away", "score"])
            for _date, home, away, score in rows:
                w.writerow([home, away, score])
        _display_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        rel = os.path.relpath(out_path, _display_root)
        log.info("已写入 %d 条完场记录 -> %s", len(rows), rel)
        try:
            remove_matches_from_final_csv(target_date, out_path)
        except Exception as e:
            log.warning("evaluation_matches 出表失败（CSV 已写入）: %s", e)
    except Exception as e:
        log.exception("执行失败: %s", e)
        sys.exit(1)
    finally:
        if driver:
            driver.quit()
            log.debug("驱动已关闭")


if __name__ == "__main__":
    main()
