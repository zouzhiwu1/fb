# -*- coding: utf-8 -*-
"""
智云比分网 完场比分抓取。
进入「足球」→「完场比分」→「足彩」→「北单」→（可选）选择日期，
等待表格刷新后抓取每行的 主队、客队、比分，用于后续写入报告图片。
"""
import logging
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from config import (
    BASE_URL,
    WAIT_ELEMENT,
    WAIT_AFTER_CLICK,
    WAIT_AFTER_HOVER,
    WAIT_TABLE_REFRESH,
    ZUCAI_MENU_OPTIONS,
    COL_HOME,
    COL_SCORE,
    COL_AWAY,
)


def _get_cell_text(driver, cell):
    """取单元格文本；若 getText 为空则用 JS textContent。"""
    text = (cell.text or "").strip()
    if not text:
        text = driver.execute_script("return arguments[0].textContent", cell) or ""
        text = text.strip()
    return " ".join(text.split())


def _scroll_into_view_and_click(driver, element):
    """先滚动到元素再点击；若被遮挡则用 JS 点击。"""
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});", element
    )
    time.sleep(0.3)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def _click_beidan_after_finished(driver, wait, option_text, log):
    """
    完场比分页可能无「足彩」一级菜单，设计书为 足球→完场比分→北单→日期。
    先尝试直接点击「北单」，若超时再走 足彩→北单。
    """
    short_wait = WebDriverWait(driver, 5)
    # 1) 先尝试直接点击「北单」（完场页常见布局）
    try:
        beidan = short_wait.until(EC.element_to_be_clickable((By.LINK_TEXT, option_text)))
        if beidan and beidan.is_displayed():
            log.debug("完场页直接点击 [%s]", option_text)
            _scroll_into_view_and_click(driver, beidan)
            time.sleep(WAIT_AFTER_CLICK)
            return
    except TimeoutException:
        pass
    # 2) 回退：足彩 → 北单（与即时比分一致）
    log.debug("未找到直接 [%s]，尝试 足彩 → %s", option_text, option_text)
    zucai_btn = wait.until(EC.presence_of_element_located((By.LINK_TEXT, "足彩")))
    ActionChains(driver).move_to_element(zucai_btn).perform()
    time.sleep(WAIT_AFTER_HOVER)
    opts = [o for o in driver.find_elements(By.LINK_TEXT, option_text) if o.is_displayed()]
    to_click = opts[-1] if opts else wait.until(EC.element_to_be_clickable((By.LINK_TEXT, option_text)))
    _scroll_into_view_and_click(driver, to_click)
    time.sleep(WAIT_AFTER_CLICK)


def run_finished_scraper(driver, target_date_yyyymmdd, base_url=BASE_URL):
    """
    完场比分抓取主流程。
    - 打开 base_url → 足球 → 完场比分 → 足彩 → 北单
    - 等待表格刷新后抓取 主队、客队、比分
    - target_date_yyyymmdd: 用于标记数据所属日期（与报告目录 YYYYMMDD 对应），若页面有日期选择可在此前设置
    返回: [(date_yyyymmdd, home, away, score), ...]
    """
    log = logging.getLogger("crawl_final")
    driver.get(base_url)
    wait = WebDriverWait(driver, WAIT_ELEMENT)

    # 1) 点击「足球」
    football_menu = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "足球")))
    _scroll_into_view_and_click(driver, football_menu)
    time.sleep(WAIT_AFTER_CLICK)

    # 2) 点击「完场比分」
    finished_tab = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "完场比分")))
    _scroll_into_view_and_click(driver, finished_tab)
    time.sleep(WAIT_AFTER_CLICK)

    # 3) 北单（完场页多为直接「北单」；若无则走 足彩→北单）
    for menu_option in ZUCAI_MENU_OPTIONS:
        log.info("========== 完场 [%s] ==========", menu_option)
        _click_beidan_after_finished(driver, wait, menu_option, log)
        break
    time.sleep(WAIT_TABLE_REFRESH)

    # 4) 可选：设置日期。若页面有日期控件可根据 target_date_yyyymmdd 设置，此处仅等待表格稳定
    wait.until(EC.presence_of_element_located((By.ID, "table_live")))
    time.sleep(WAIT_TABLE_REFRESH)

    # 5) 收集所有数据行：主队、客队、比分
    rows = driver.find_elements(By.CSS_SELECTOR, "#table_live tr")
    result = []
    for row in rows:
        tds = row.find_elements(By.CSS_SELECTOR, "td")
        if len(tds) <= max(COL_HOME, COL_SCORE, COL_AWAY):
            continue
        home = _get_cell_text(driver, tds[COL_HOME])
        away = _get_cell_text(driver, tds[COL_AWAY])
        score = _get_cell_text(driver, tds[COL_SCORE])
        if home == "主队" and away == "客队":
            continue
        if not home or not away:
            continue
        result.append((target_date_yyyymmdd, home.strip(), away.strip(), score.strip()))
        log.info("完场: %s VS %s  %s", home.strip(), away.strip(), score.strip())

    log.info("完场比分共抓取 %d 场", len(result))
    return result
