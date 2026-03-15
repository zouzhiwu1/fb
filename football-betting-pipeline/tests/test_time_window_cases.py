import datetime
import logging
import os

import pytest

import main
from merge_data import _collect_files_in_range
from calc_car import _resolve_data_dir as resolve_car_data_dir
from plot_car import _resolve_data_dir as resolve_plot_data_dir
from scraper_real import ZhiyunScraper


class DummyDriver:
    """占位用的 Selenium driver，不会真正被使用到。"""

    pass


def _scraper_date_folder_from_now(now_dt: datetime.datetime) -> str:
    """
    使用给定的 now_dt，模拟 scraper 当前时间，返回自然日目录 YYYYMMDD。
    """
    import scraper_real as scraper_mod

    def fake_now():
        return now_dt

    # 构造一个 scraper 实例，仅用到 _date_folder_from_time_suffix
    s = ZhiyunScraper(DummyDriver())

    # 临时替换 _now_in_tz
    orig_now = scraper_mod._now_in_tz
    scraper_mod._now_in_tz = fake_now
    try:
        time_suffix = now_dt.strftime("%Y%m%d%H")
        return s._date_folder_from_time_suffix(time_suffix)
    finally:
        scraper_mod._now_in_tz = orig_now


def test_case1_before_cutoff(tmp_path, monkeypatch):
    """
    case1: 当前时间 2026-03-11 11:00
    """
    now = datetime.datetime(2026, 3, 11, 11, 0, 0)
    monkeypatch.setattr(main, "CUTOFF_HOUR", 12, raising=False)
    start_dt, end_dt = main._compute_default_time_window(now)

    start_arg = start_dt.strftime("%Y%m%d%H")
    end_arg = end_dt.strftime("%Y%m%d%H")

    # main.py（及各脚本）的实参
    assert start_arg == "2026031012"
    assert end_arg == "2026031111"

    # crawl_real.py / scraper：自然日目录
    natural_folder = _scraper_date_folder_from_now(now)
    assert natural_folder == "20260311"

    # merge_data.py：在 DOWNLOAD_DIR 下哪些目录里查找
    download_root = tmp_path / "data"
    (download_root / "20260310").mkdir(parents=True)
    (download_root / "20260311").mkdir()
    (download_root / "20260309").mkdir()

    # 2026-03-10 的一些时间点
    (download_root / "20260310" / "A VS B2026031011.xls").write_text("x")
    (download_root / "20260310" / "A VS B2026031012.xls").write_text("x")
    (download_root / "20260310" / "A VS B2026031023.xls").write_text("x")

    # 2026-03-11 的一些时间点
    (download_root / "20260311" / "C VS D2026031100.xls").write_text("x")
    (download_root / "20260311" / "C VS D2026031111.xls").write_text("x")
    (download_root / "20260311" / "C VS D2026031112.xls").write_text("x")

    monkeypatch.setattr("merge_data.DOWNLOAD_DIR", str(download_root))
    log = logging.getLogger("case1")

    files = _collect_files_in_range(start_dt, end_dt, log)
    time_points = sorted(tp for *_rest, tp in files)
    # 仅包含区间 [2026031012, 2026031111]
    assert time_points == [
        "2026031012",
        "2026031023",
        "2026031100",
        "2026031111",
    ]

    # calc_car.py：逻辑日期与输出目录
    logical_date = start_arg[:8]
    assert logical_date == "20260310"

    monkeypatch.setattr("calc_car.DOWNLOAD_DIR", "/fake_download_case1")
    data_dir = resolve_car_data_dir(logical_date)
    assert data_dir.endswith(os.path.join("fake_download_case1", "20260310"))

    # CAR 输出文件应为：REPORT_DIR/20260310/car_20260310.xlsx（在其它测试中已验证）

    # plot_car.py：曲线图的逻辑日期与目录解析一致
    monkeypatch.setattr("plot_car.DOWNLOAD_DIR", "/fake_download_case1")
    plot_data_dir = resolve_plot_data_dir(logical_date)
    assert plot_data_dir.endswith(os.path.join("fake_download_case1", "20260310"))


def test_case2_after_cutoff(tmp_path, monkeypatch):
    """
    case2: 当前时间 2026-03-11 12:00（按跨天临界点 12 点理解）
    """
    now = datetime.datetime(2026, 3, 11, 12, 0, 0)
    monkeypatch.setattr(main, "CUTOFF_HOUR", 12, raising=False)
    start_dt, end_dt = main._compute_default_time_window(now)

    start_arg = start_dt.strftime("%Y%m%d%H")
    end_arg = end_dt.strftime("%Y%m%d%H")

    # 12 点及之后：窗口 [今天 12, 明天 11]
    assert start_arg == "2026031112"
    assert end_arg == "2026031211"

    # crawl_real.py / scraper：自然日目录仍是当天
    natural_folder = _scraper_date_folder_from_now(now)
    assert natural_folder == "20260311"

    # merge_data.py：应在 20260311、20260312 两个自然日目录中按时间点筛选
    download_root = tmp_path / "data2"
    (download_root / "20260311").mkdir(parents=True)
    (download_root / "20260312").mkdir()

    (download_root / "20260311" / "A VS B2026031112.xls").write_text("x")
    (download_root / "20260311" / "A VS B2026031123.xls").write_text("x")
    (download_root / "20260312" / "C VS D2026031200.xls").write_text("x")
    (download_root / "20260312" / "C VS D2026031211.xls").write_text("x")
    (download_root / "20260312" / "C VS D2026031212.xls").write_text("x")  # 超出区间

    monkeypatch.setattr("merge_data.DOWNLOAD_DIR", str(download_root))
    log = logging.getLogger("case2")

    files = _collect_files_in_range(start_dt, end_dt, log)
    time_points = sorted(tp for *_rest, tp in files)
    assert time_points == [
        "2026031112",
        "2026031123",
        "2026031200",
        "2026031211",
    ]

    # calc_car.py：逻辑日期 20260311
    logical_date = start_arg[:8]
    assert logical_date == "20260311"

    monkeypatch.setattr("calc_car.DOWNLOAD_DIR", "/fake_download_case2")
    data_dir = resolve_car_data_dir(logical_date)
    assert data_dir.endswith(os.path.join("fake_download_case2", "20260311"))

    # plot_car.py：同一逻辑日期
    monkeypatch.setattr("plot_car.DOWNLOAD_DIR", "/fake_download_case2")
    plot_data_dir = resolve_plot_data_dir(logical_date)
    assert plot_data_dir.endswith(os.path.join("fake_download_case2", "20260311"))

