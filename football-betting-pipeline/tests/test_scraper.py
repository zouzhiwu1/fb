# -*- coding: utf-8 -*-
"""爬虫状态过滤等逻辑的单元测试。"""
import pytest

from scraper import ZhiyunScraper


def test_is_status_empty_accepts_empty():
    """状态为空或仅空白时视为空，会下载。"""
    scraper = ZhiyunScraper(driver=None)
    assert scraper._is_status_empty("") is True
    assert scraper._is_status_empty("   ") is True
    assert scraper._is_status_empty("\t") is True
    assert scraper._is_status_empty(None) is True


def test_is_status_empty_accepts_dash():
    """状态为「-」或带空格的「-」时视为空，会下载。"""
    scraper = ZhiyunScraper(driver=None)
    assert scraper._is_status_empty("-") is True
    assert scraper._is_status_empty(" - ") is True


def test_is_status_empty_rejects_playing():
    """状态为「比赛中」时不视为空，不下载。"""
    scraper = ZhiyunScraper(driver=None)
    assert scraper._is_status_empty("比赛中") is False


def test_is_status_empty_rejects_finished():
    """状态为「完」时不视为空，不下载。"""
    scraper = ZhiyunScraper(driver=None)
    assert scraper._is_status_empty("完") is False


def test_is_status_empty_rejects_minute():
    """状态为比赛分钟数（如 67'）时不视为空，不下载。"""
    scraper = ZhiyunScraper(driver=None)
    assert scraper._is_status_empty("67'") is False
    assert scraper._is_status_empty("25'") is False
    assert scraper._is_status_empty("90+2'") is False


def test_is_status_empty_rejects_other_non_empty():
    """其他非空状态均不下载。"""
    scraper = ZhiyunScraper(driver=None)
    assert scraper._is_status_empty("未开赛") is False
    assert scraper._is_status_empty("延期") is False
    assert scraper._is_status_empty("0") is False
