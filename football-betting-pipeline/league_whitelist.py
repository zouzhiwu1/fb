# -*- coding: utf-8 -*-
"""
联赛白名单：即时比分、完场比分抓取共用。

名单来自 config.TARGET_LEAGUE_NAMES；空列表表示不限制联赛。
"""
from config import TARGET_LEAGUE_NAMES


def league_matches_whitelist(league_cell_text: str) -> bool:
    """
    判断联赛列单元格文本是否命中联赛白名单。

    匹配规则：去空白后完全相等，或（长度>=2 时）白名单项与单元格文本互为子串，
    以兼容站点略长写法。
    """
    if not TARGET_LEAGUE_NAMES:
        return True
    t = " ".join((league_cell_text or "").split())
    if not t:
        return False
    for name in TARGET_LEAGUE_NAMES:
        n = name.strip()
        if not n:
            continue
        if t == n:
            return True
        if len(n) >= 2 and n in t:
            return True
        if len(t) >= 2 and t in n:
            return True
    return False
