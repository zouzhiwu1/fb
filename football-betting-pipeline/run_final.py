# -*- coding: utf-8 -*-
"""
完场流程：先抓取完场比分，再将比分写入报告图片。

  1. crawl_final.py — 抓取完场比分，输出 REPORT_DIR/{YYYYMMDD}/final_{YYYYMMDD}.csv
  2. add_score_to_image.py — 根据该 CSV 将实际比分写入同目录下的曲线图

任一步失败则终止，不执行后续步骤。

用法:
  python run_final.py [YYYYMMDD]
    - 无参数：使用昨日日期（与 crawl_final.py 默认一致）
    - 有参数：使用指定日期，与报告目录 REPORT_DIR/YYYYMMDD 对应

日志：DEBUG_LOG_DIR/run_final_{YYYYMMDDHH}.log
"""
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta

from config import DEBUG_LOG_DIR, LOG_RETENTION_DAYS
from log_cleanup import delete_old_logs


def _setup_logging():
    """配置 run_final 日志到 run_final_{YYYYMMDDHH}.log。"""
    os.makedirs(DEBUG_LOG_DIR, exist_ok=True)
    time_suffix = datetime.now().strftime("%Y%m%d%H")
    log_path = os.path.join(DEBUG_LOG_DIR, f"run_final_{time_suffix}.log")
    logger = logging.getLogger("run_final")
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
    _display_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    rel_log_path = os.path.relpath(log_path, _display_root)
    logger.info("完场流程日志: %s", rel_log_path)
    return logger


def main():
    log = _setup_logging()
    removed = delete_old_logs(DEBUG_LOG_DIR, days=LOG_RETENTION_DAYS)
    if removed:
        _display_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        rel_removed = [os.path.relpath(p, _display_root) for p in removed]
        log.info("已删除 %d 个超过 %d 天的日志: %s", len(removed), LOG_RETENTION_DAYS, rel_removed)

    args = sys.argv[1:]
    if len(args) == 0:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        log.info("未指定日期，使用昨日: %s", target_date)
    elif len(args) == 1 and len(args[0]) == 8 and args[0].isdigit():
        target_date = args[0]
    else:
        log.error("用法: python run_final.py [YYYYMMDD]，例如: python run_final.py 20260314")
        sys.exit(1)

    steps = [
        ("crawl_final.py", ["crawl_final.py", target_date]),
        ("add_score_to_image.py", ["add_score_to_image.py", target_date]),
    ]
    for name, cmd in steps:
        log.info(">>> 执行: %s", " ".join(cmd))
        ret = subprocess.run([sys.executable] + cmd)
        if ret.returncode != 0:
            log.error(">>> %s 退出码 %d，流程已终止。", name, ret.returncode)
            sys.exit(ret.returncode)
    log.info(">>> 完场流程执行完成。")


if __name__ == "__main__":
    main()
