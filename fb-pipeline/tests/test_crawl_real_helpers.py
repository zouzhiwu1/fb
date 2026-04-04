# -*- coding: utf-8 -*-
"""crawl_real 驱动解析等小函数单测。"""
import pytest

from crawl_real import _chromium_semver_from_binary


def test_chromium_semver_from_binary_missing_file(tmp_path):
    assert _chromium_semver_from_binary(str(tmp_path / "nope")) is None


def test_chromium_semver_from_binary_parses_version(tmp_path):
    p = tmp_path / "fake-chromium"
    p.write_text("#!/bin/sh\necho 'Chromium 146.0.7680.153 official'\n")
    p.chmod(0o755)
    assert _chromium_semver_from_binary(str(p)) == "146.0.7680"


def test_chromium_semver_from_binary_google_chrome_style(tmp_path):
    p = tmp_path / "fake-chrome"
    p.write_text("#!/bin/sh\necho 'Google Chrome 122.0.6261.69'\n")
    p.chmod(0o755)
    assert _chromium_semver_from_binary(str(p)) == "122.0.6261"
