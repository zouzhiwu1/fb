from app.curves import _parse_curve_filename, _match_team


def test_parse_curve_filename_ok():
    home, away = _parse_curve_filename("A_VS_B.png")
    assert home == "A"
    assert away == "B"


def test_parse_curve_filename_invalid():
    assert _parse_curve_filename("not_a_curve.png") is None


def test_parse_curve_filename_suffix_but_no_vs_returns_none():
    """以 _曲线.png 结尾但无 _VS_ 时返回 None。"""
    assert _parse_curve_filename("仅主队_曲线.png") is None


def test_match_team_empty_keyword_matches_all():
    assert _match_team("", "Home", "Away")
    assert _match_team("   ", "Home", "Away")


def test_match_team_keyword_in_home_or_away():
    assert _match_team("Ho", "Home", "Away")
    assert _match_team("ome", "Home", "Away")
    assert _match_team("Aw", "Home", "Away")
    assert _match_team("ay", "Home", "Away")
    assert not _match_team("ZZZ", "Home", "Away")

