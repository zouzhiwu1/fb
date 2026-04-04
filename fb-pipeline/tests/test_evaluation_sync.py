# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import pandas as pd

from evaluation_sync import (
    _mysql_params_from_database_url,
    _safe_filename,
    remove_matches_from_final_csv,
    sync_matches_from_car_for_date,
)


def test_safe_filename():
    assert _safe_filename('a/b') == "a_b"
    assert _safe_filename("  x  ") == "x"


def test_mysql_params_from_database_url():
    assert _mysql_params_from_database_url("") is None
    assert _mysql_params_from_database_url("sqlite:///x") is None
    p = _mysql_params_from_database_url("mysql+pymysql://u:p@h:3307/db")
    assert p["host"] == "h" and p["port"] == 3307 and p["database"] == "db"
    assert p["user"] == "u" and p["password"] == "p"


@patch("evaluation_sync._connect")
def test_sync_matches_from_car_skips_without_file(mock_connect, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://u:p@localhost:3306/testdb")
    monkeypatch.setattr(
        "evaluation_sync.REPORT_DIR", str(tmp_path), raising=False
    )
    n = sync_matches_from_car_for_date("20250101")
    assert n == 0
    mock_connect.assert_not_called()


@patch("evaluation_sync._connect")
def test_sync_matches_from_car_inserts(mock_connect, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://u:p@localhost:3306/testdb")
    monkeypatch.setattr("evaluation_sync.REPORT_DIR", str(tmp_path), raising=False)
    day = "20250101"
    d = tmp_path / day
    d.mkdir(parents=True)
    xlsx = d / f"car_{day}.xlsx"
    df = pd.DataFrame(
        [
            [None, None],
            [None, None],
            ["主队A", "客队B"],
            ["主队A", "客队B"],
        ]
    )
    df.to_excel(xlsx, index=False, header=False)

    cur = MagicMock()
    cur.rowcount = 1
    cursor_cm = MagicMock()
    cursor_cm.__enter__ = MagicMock(return_value=cur)
    cursor_cm.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cursor_cm
    mock_connect.return_value = conn

    n = sync_matches_from_car_for_date(day)
    assert n >= 1
    cur.execute.assert_called()
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


@patch("evaluation_sync._connect")
def test_remove_matches_from_final_csv(mock_connect, tmp_path):
    csv_path = tmp_path / "final.csv"
    csv_path.write_text("home,away,score\n甲队,乙队,1-0\n", encoding="utf-8-sig")
    cur = MagicMock()
    cur.rowcount = 1
    cursor_cm = MagicMock()
    cursor_cm.__enter__ = MagicMock(return_value=cur)
    cursor_cm.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cursor_cm
    mock_connect.return_value = conn

    total = remove_matches_from_final_csv("20250101", str(csv_path))
    assert total == 1
    conn.close.assert_called_once()
