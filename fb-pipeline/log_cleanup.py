# -*- coding: utf-8 -*-
"""
删除指定目录下超过保留期的日志，避免占用过多磁盘空间。
供 crawl_real.py、merge_data.py、calc_car.py、plot_car.py、run_real 等在执行前调用。

- fb-log 根下「平铺」的旧 *.log：仍按文件 mtime 判断。
- fb-log 根下 `YYYYMMDD` 子目录：按目录日期删除整夹（早于今天往前数 days 天之前的日子）。
"""
import datetime
import os
import re
import shutil
import time

_DATE_DIR = re.compile(r"^\d{8}$")


def _is_log_day_directory(path: str) -> bool:
    """避免 fb-log 与数据目录误共用时删掉 master/csv 等：仅当目录为空或含有典型日志/调试文件时视为日志日录。"""
    try:
        names = os.listdir(path)
    except OSError:
        return False
    if not names:
        # 空目录可能是误用的数据日录占位，勿整夹删除；仅当存在典型日志/调试文件时才认定。
        return False
    for n in names:
        lo = n.lower()
        if lo.endswith(".log") or lo.endswith(".html"):
            return True
    return False


def delete_old_logs(log_dir: str, days: int = 7) -> list:
    """
    :param log_dir: 日志根目录（如 fb-log）
    :param days: 保留最近约多少自然日；子目录 YYYYMMDD 若日期早于此窗口则整目录删除
    :return: 被删除的文件名或目录名列表
    """
    if not os.path.isdir(log_dir):
        return []
    threshold = time.time() - days * 86400
    cutoff_date = datetime.date.today() - datetime.timedelta(days=days)
    deleted = []
    for fname in os.listdir(log_dir):
        path = os.path.join(log_dir, fname)
        if os.path.isfile(path):
            try:
                if os.path.getmtime(path) < threshold:
                    os.remove(path)
                    deleted.append(fname)
            except OSError:
                pass
            continue
        if os.path.isdir(path) and _DATE_DIR.fullmatch(fname):
            try:
                d = datetime.date(int(fname[:4]), int(fname[4:6]), int(fname[6:8]))
            except ValueError:
                continue
            if d < cutoff_date and _is_log_day_directory(path):
                try:
                    shutil.rmtree(path)
                    deleted.append(fname + "/")
                except OSError:
                    pass
    return deleted
