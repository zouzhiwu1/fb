# -*- coding: utf-8 -*-
"""
按顺序执行完整流程：
  1. crawl_real.py — 抓取即时比分数据并下载
  2. merge_data.py — 合并为一览表 master_{YYYYMMDD}.csv
  3. calc_car.py   — 计算综合评估并输出 car_{YYYYMMDD}.xlsx
  4. plot_car.py   — 根据综合评估表生成欧赔/凯利曲线图

任一步失败则终止，不执行后续步骤。

日志：
- 详细流程日志写入 DEBUG_LOG_DIR/run_real_{YYYYMMDDHH}.log（按小时分文件，带日期时间）。
- 若通过 launchd 等重定向 stdout/stderr，则仍可在系统指定的 log/err 文件中看到部分输出。

用法:
  python run_real.py
    - 无参数：按当前时间和跨天临界点 CUTOFF_HOUR 自动计算本次统计区间 [start,end]，
      然后依次执行 crawl_real.py、merge_data.py start end、calc_car.py start end、plot_car.py start end。

  python run_real.py <起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>
    - 显式指定本次统计区间 [start,end]，直接传递给各批处理脚本。
"""
import logging
import os
from datetime import datetime, timedelta
import subprocess
import sys

from config import DEBUG_LOG_DIR, LOG_RETENTION_DAYS, CUTOFF_HOUR
from log_cleanup import delete_old_logs


def _setup_logging():
    """配置主流程日志到 run_real_{YYYYMMDDHH}.log，并输出到终端。"""
    os.makedirs(DEBUG_LOG_DIR, exist_ok=True)
    time_suffix = datetime.now().strftime("%Y%m%d%H")
    log_path = os.path.join(DEBUG_LOG_DIR, f"run_real_{time_suffix}.log")
    logger = logging.getLogger("run_real")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # 相对路径以「工作目录上一级」为根，显示为 football-betting/football-betting-*
    _display_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
    rel_log_path = os.path.relpath(log_path, _display_root)
    logger.info("主流程日志文件: %s", rel_log_path)
    return logger


def _compute_default_time_window(now: datetime):
    """
    根据当前时间计算本次统计区间 [start_dt, end_dt]（闭区间，按小时）。

    规则（以 CUTOFF_HOUR 作为跨天临界点）：
    - 若当前时间在当日 CUTOFF_HOUR 之前：
        start = 昨天 CUTOFF_HOUR
        end   = start + 23 小时（即今天 CUTOFF_HOUR-1）
    - 若当前时间在当日 CUTOFF_HOUR 及之后：
        start = 今天 CUTOFF_HOUR
        end   = start + 23 小时（即明天 CUTOFF_HOUR-1）
    """
    today = now.date()
    if now.hour < CUTOFF_HOUR:
        start_day = today - timedelta(days=1)
    else:
        start_day = today

    start_dt = datetime(start_day.year, start_day.month, start_day.day, CUTOFF_HOUR)
    end_dt = start_dt + timedelta(hours=23)
    return start_dt, end_dt


def main():
    log = _setup_logging()
    removed = delete_old_logs(DEBUG_LOG_DIR, days=LOG_RETENTION_DAYS)
    if removed:
        _display_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
        rel_removed = [os.path.relpath(p, _display_root) for p in removed]
        log.info(
            "已删除 %d 个超过 %d 天的日志文件: %s",
            len(removed),
            LOG_RETENTION_DAYS,
            rel_removed,
        )

    args = sys.argv[1:]

    # 调用形式：
    #   python run_real.py
    #   python run_real.py <起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>
    if len(args) == 0:
        # 无参数：使用当前时间，通过 _compute_default_time_window 计算 [start,end]
        now = datetime.now()
        start_dt, end_dt = _compute_default_time_window(now)
    elif len(args) == 2 and all(len(a) == 10 and a.isdigit() for a in args):
        # 显式指定 [start,end]，直接解析
        start_arg_raw, end_arg_raw = args
        try:
            start_dt = datetime.strptime(start_arg_raw, "%Y%m%d%H")
            end_dt = datetime.strptime(end_arg_raw, "%Y%m%d%H")
        except ValueError:
            log.error(
                "时间参数格式错误，应为 YYYYMMDDHH，例如: python run_real.py 2026031012 2026031111"
            )
            sys.exit(1)
        if start_dt > end_dt:
            log.error(
                "起始时间晚于终止时间: %s > %s",
                start_arg_raw,
                end_arg_raw,
            )
            sys.exit(1)
    else:
        log.error(
            "用法:\n  python run_real.py\n  python run_real.py <起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>"
        )
        sys.exit(1)

    logical_date = start_dt.strftime("%Y%m%d")  # 与 merge_data.py 的输出日期一致

    start_arg = start_dt.strftime("%Y%m%d%H")
    end_arg = end_dt.strftime("%Y%m%d%H")

    log.info(
        "本次统计区间: [%s, %s]，逻辑日期=%s",
        start_arg,
        end_arg,
        logical_date,
    )

    steps = [
        ("crawl_real.py", ["crawl_real.py", start_arg, end_arg]),
        ("merge_data.py", ["merge_data.py", start_arg, end_arg]),
        ("calc_car.py", ["calc_car.py", start_arg, end_arg]),
        ("plot_car.py", ["plot_car.py", start_arg, end_arg]),
    ]
    for name, cmd in steps:
        log.info(">>> 执行: %s", " ".join(cmd))
        ret = subprocess.run([sys.executable] + cmd)
        if ret.returncode != 0:
            log.error(">>> %s 退出码 %d，流程已终止。", name, ret.returncode)
            sys.exit(ret.returncode)
    log.info(">>> 全部步骤执行完成。")


if __name__ == "__main__":
    main()
