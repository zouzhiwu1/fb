# -*- coding: utf-8 -*-
"""
智云比分网 竞足/beidan/14场 比赛列表爬虫。
逻辑与 Java 版 ZhiyunScraperService 一致。

下载方式：
- 使用 Selenium 进入「足球 → 即时比分 → zucai → beidan」，等待表格刷新；
- 按 config：可视过滤 MATCH_FILTER_VISIBLE_ONLY、状态过滤 MATCH_STATUS_MODES、联赛白名单 TARGET_LEAGUE_NAMES；
- 对每场状态为空的比赛，点击行内的「欧」链接，打开详情页；
- 在详情页中点击「导出Excel」按钮，由浏览器下载 .xls；
- 将 .xls 文件重命名为「主队_VS_客队_{YYYYMMDDHH}.xls」。
"""
import os
import re
import time
import logging
from datetime import datetime, timedelta
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchWindowException,
    ElementNotInteractableException,
    ElementClickInterceptedException,
)

from league_whitelist import league_matches_whitelist
from match_filters import describe_status_filter_for_log, match_status_allowed
from config import (
    BASE_URL,
    DOWNLOAD_DIR,
    DEBUG_LOG_DIR,
    CUTOFF_HOUR,
    DEBUG_MAX_MATCHES,
    TEAM_WHITELIST_KEYWORDS,
    ZUCAI_MENU_OPTIONS,
    MATCH_FILTER_VISIBLE_ONLY,
    MATCH_REQUIRE_JIAN,
    TARGET_LEAGUE_NAMES,
    ALLOW_GLOBAL_TABLE_LIVE,
    COL_LEAGUE,
    COL_STATUS,
    COL_HOME,
    COL_AWAY,
    WAIT_ELEMENT,
    WAIT_AFTER_CLICK,
    WAIT_AFTER_HOVER,
    WAIT_TABLE_REFRESH,
    WAIT_FIRST_ROW_CHANGED,
    EXPORT_EXCEL_MAX_ATTEMPTS,
    EXPORT_EXCEL_DOWNLOAD_WAIT_SECONDS,
)

def _now_in_tz():
    """返回本机当前时间（本地时区），用于下载目录/文件名。"""
    return datetime.now()


class ZhiyunScraper:
    def __init__(
        self,
        driver,
        base_url=BASE_URL,
        download_dir=DOWNLOAD_DIR,
        rename_downloaded_file=True,
    ):
        self.driver = driver
        self.base_url = base_url
        self.download_dir = download_dir
        self.rename_downloaded_file = rename_downloaded_file

    def _wait_page_loaded(self, timeout=WAIT_ELEMENT):
        """等待当前页面 readyState 为 complete，超时则忽略错误。"""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass

    def run(self):
        """主流程：打开页面 -> 足球 -> 即时比分 -> zucai -> beidan，等待表格刷新后仅处理状态为空的比赛，逐场导出并下载 Excel。"""
        now = _now_in_tz()
        self._run_time_suffix = now.strftime("%Y%m%d%H")
        log = logging.getLogger("crawl_real")
        self.driver.get(self.base_url)
        self._wait_page_loaded()
        wait = WebDriverWait(self.driver, WAIT_ELEMENT)

        # 1) 点击主菜单「足球」
        football_menu = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "足球")))
        self._scroll_into_view_and_click(football_menu)

        # 2) 点击「即时比分」，依赖显式等待而非固定 sleep
        live_tab = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "即时比分")))
        self._scroll_into_view_and_click(live_tab)

        # 3) 对 竞足、beidan、14场 分别处理（当前配置里只保留了「beidan」）
        for menu_option in ZUCAI_MENU_OPTIONS:
            log.info("========== 获取 [%s] 比赛列表 ==========", menu_option)
            first_row_home_before = self._get_first_data_row_home_team()
            self._hover_zucai_then_click_option(wait, menu_option)
            self._ensure_zucai_mode(menu_option)
            # 以「首行主队是否变化」判断已切到当前zucai类型（beidan等列表常远超 150 行，旧逻辑用行数≤150 会误报）
            self._wait_until_first_row_changed(first_row_home_before)

            if not self._ensure_valid_window():
                print(f"[{menu_option}] 无可用窗口，跳过", file=__import__("sys").stderr)
                continue

            match_rows = self._collect_match_rows(
                wait, visible_only=MATCH_FILTER_VISIBLE_ONLY
            )
            log.info("[%s] 数据加载完成", menu_option)
            n_raw = len(match_rows)
            visible_desc = (
                "仅可见行（与页面「隐藏场次」一致）"
                if MATCH_FILTER_VISIBLE_ONLY
                else "含 DOM 内隐藏行"
            )
            log.info("【列表过滤】表格数据行 %d 行（可视：%s）", n_raw, visible_desc)
            log.info("【状态过滤】当前允许：%s", describe_status_filter_for_log())
            match_rows = [
                row
                for row in match_rows
                if match_status_allowed(self._get_cell_text(row, COL_STATUS))
            ]
            n_after_status = len(match_rows)
            log.info(
                "【状态过滤】%d -> %d 场（剔除 %d）",
                n_raw,
                n_after_status,
                n_raw - n_after_status,
            )
            if TARGET_LEAGUE_NAMES:
                log.info(
                    "【联赛白名单】已启用，共 %d 个联赛；不在名单内的场次将被跳过",
                    len(TARGET_LEAGUE_NAMES),
                )
            else:
                log.info(
                    "【联赛白名单】未启用（CRAWLER_TARGET_LEAGUES 为空），不限制联赛"
                )
            # 联赛白名单：按 config 名单过滤第 2 列联赛简称；名单为空则不限制
            match_rows = [
                row
                for row in match_rows
                if league_matches_whitelist(self._get_cell_text(row, COL_LEAGUE))
            ]
            n_after_league = len(match_rows)
            log.info(
                "【联赛白名单】%d -> %d 场（剔除 %d）",
                n_after_status,
                n_after_league,
                n_after_status - n_after_league,
            )
            if TEAM_WHITELIST_KEYWORDS:
                log.info(
                    "【球队白名单】已启用，共 %d 个关键词；不匹配的场次将被跳过",
                    len(TEAM_WHITELIST_KEYWORDS),
                )
            else:
                log.info(
                    "【球队白名单】未启用（CRAWLER_DEBUG_MATCH_KEYWORDS 为空），不限制球队"
                )
            match_rows = [
                row for row in match_rows if self._row_matches_team_whitelist(row)
            ]
            n_after_team = len(match_rows)
            log.info(
                "【球队白名单】%d -> %d 场（剔除 %d）",
                n_after_league,
                n_after_team,
                n_after_league - n_after_team,
            )
            if MATCH_REQUIRE_JIAN:
                log.info("【荐过滤】当前设置：仅保留含“荐”的场次")
                match_rows = [row for row in match_rows if self._row_has_jian(row)]
                n_after_jian = len(match_rows)
                log.info(
                    "【荐过滤】%d -> %d 场（剔除 %d）",
                    n_after_league,
                    n_after_jian,
                    n_after_league - n_after_jian,
                )
            else:
                log.info("【荐过滤】当前设置：未启用（CRAWLER_MATCH_REQUIRE_JIAN=0）")
            log.info("--- 主队 vs 客队（将依次尝试导出）---")
            for i, row in enumerate(match_rows, 1):
                home = self._get_cell_text(row, COL_HOME)
                away = self._get_cell_text(row, COL_AWAY)

                log.info("%d. %s vs %s", i, home, away)
                self._download_excel_for_row(wait, row, i, home, away, time_suffix=self._run_time_suffix)
                if DEBUG_MAX_MATCHES and i >= DEBUG_MAX_MATCHES:
                    log.info("[调试] 已抓取 %d 场，结束抓取。", DEBUG_MAX_MATCHES)
                    break
            log.info("")

    def _hover_zucai_then_click_option(self, wait, option_text):
        """鼠标移到「zucai」弹出菜单，再点击指定项（jingzu/beidan/14chang）。"""
        zucai_btn = wait.until(EC.presence_of_element_located((By.LINK_TEXT, "足彩")))
        ActionChains(self.driver).move_to_element(zucai_btn).perform()

        # 等待子菜单中的目标选项真正可见再点击，避免固定 sleep
        def _visible_options(d):
            opts = [o for o in d.find_elements(By.LINK_TEXT, option_text) if o.is_displayed()]
            return opts if opts else False

        try:
            options = WebDriverWait(self.driver, WAIT_ELEMENT).until(_visible_options)
        except TimeoutException:
            options = []

        to_click = options[-1] if options else None
        if to_click is None:
            to_click = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, option_text)))
        self._scroll_into_view_and_click(to_click)

    def _ensure_zucai_mode(self, menu_option):
        """若页面有 SetLevel，直接调用以切换到jingzu(3)/beidan(2)/14chang(1)。"""
        level = 3 if menu_option == "竞足" else (2 if menu_option == "北单" else 1)
        try:
            ok = self.driver.execute_script(
                f"return typeof window.SetLevel === 'function' && (window.SetLevel({level}), true);"
            )
            if ok:
                logging.getLogger("crawl_real").info("点击 [%s]", menu_option)
        except Exception:
            pass

    def _ensure_valid_window(self):
        """若当前窗口已关闭，则切换到仍存在的任一窗口。返回是否在有效窗口上。"""
        try:
            self.driver.current_window_handle
            return True
        except NoSuchWindowException:
            handles = self.driver.window_handles
            if handles:
                self.driver.switch_to.window(handles[0])
                return True
            return False

    def _get_live_score_table(self, log_if_missing=True):
        """
        列表页主比分表：优先 body→main→middle→ScoreDiv 内的 #table_live。

        #middle 下 ScoreDiv（多为 span）与 #main2 等区域并列；全局 #table_live 可能命中错误区域。
        默认不使用全局表；设置 CRAWLER_ALLOW_GLOBAL_TABLE_LIVE=1 时与完场爬虫一致，最后回退 #table_live。
        """
        log = logging.getLogger("crawl_real")
        selectors = [
            "#middle span#ScoreDiv #table_live",
            "#middle #ScoreDiv #table_live",
            "span#ScoreDiv #table_live",
            "#ScoreDiv #table_live",
        ]
        for css in selectors:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, css)
                if el:
                    return el
            except Exception:
                continue
        if ALLOW_GLOBAL_TABLE_LIVE:
            try:
                el = self.driver.find_element(By.ID, "table_live")
                if el:
                    if log_if_missing:
                        log.warning(
                            "已启用 CRAWLER_ALLOW_GLOBAL_TABLE_LIVE，使用全局 #table_live（若列表错位请关闭此项）"
                        )
                    return el
            except Exception:
                pass
        if log_if_missing:
            log.warning(
                "未在 middle→ScoreDiv 内找到 #table_live（未启用全局回退时可设 CRAWLER_ALLOW_GLOBAL_TABLE_LIVE=1）"
            )
        return None

    def _get_first_data_row_home_team(self):
        """取当前 table_live 第一行数据的主队名（非表头），无则返回空串。"""
        try:
            table = self._get_live_score_table(log_if_missing=False)
            if not table:
                return ""
            rows = table.find_elements(By.CSS_SELECTOR, "tr")
            for row in rows:
                tds = row.find_elements(By.CSS_SELECTOR, "td")
                if len(tds) < 7:
                    continue
                home = tds[COL_HOME].text.strip()
                away = tds[COL_AWAY].text.strip()
                if home == "主队" and away == "客队":
                    continue
                if not home:
                    home = self.driver.execute_script(
                        "return arguments[0].textContent", tds[COL_HOME]
                    ) or ""
                    home = home.strip()
                return home
        except Exception:
            pass
        return ""

    def _wait_until_first_row_changed(self, first_row_home_before):
        """等表格第一行数据变化，最多等 WAIT_FIRST_ROW_CHANGED 秒。"""
        start = time.time()
        wait = WebDriverWait(self.driver, WAIT_FIRST_ROW_CHANGED)

        def _first_row_changed(d):
            if time.time() - start < WAIT_TABLE_REFRESH:
                return False
            now = self._get_first_data_row_home_team()
            return bool(now and now != first_row_home_before)

        try:
            wait.until(_first_row_changed)
            return True
        except TimeoutException:
            return False

    def _collect_match_rows(self, wait, visible_only=True):
        """等待 #table_live 出现并收集数据行（非表头）。visible_only=True 时只收集当前页显示的行（style.display!='none'），与浏览器列表一致。"""
        _table_wait_css = (
            "#middle span#ScoreDiv #table_live, #middle #ScoreDiv #table_live, #ScoreDiv #table_live"
            + (", #table_live" if ALLOW_GLOBAL_TABLE_LIVE else "")
        )
        for attempt in range(2):
            try:
                if attempt > 0 and self._ensure_valid_window():
                    wait = WebDriverWait(self.driver, WAIT_ELEMENT)
                wait.until(
                    EC.presence_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            _table_wait_css,
                        )
                    )
                )
                table = self._get_live_score_table()
                if not table:
                    return []
                rows = table.find_elements(By.CSS_SELECTOR, "tr")
                match_rows = []
                for row in rows:
                    tds = row.find_elements(By.CSS_SELECTOR, "td")
                    if len(tds) < 7:
                        continue
                    home_col = tds[COL_HOME].text.strip()
                    away_col = tds[COL_AWAY].text.strip()
                    if home_col == "主队" and away_col == "客队":
                        continue
                    if visible_only:
                        try:
                            display = row.value_of_css_property("display")
                            if display == "none":
                                continue
                        except Exception:
                            pass
                    match_rows.append(row)
                return match_rows
            except (NoSuchWindowException, TimeoutException):
                if attempt > 0 and self._ensure_valid_window():
                    continue
                raise
        return []

    def _download_excel_for_row(self, wait, row, index, home, away, time_suffix=None):
        """点击当前行的「欧」链接（列表页为「析亚欧」），弹出详情页后点击「导出Excel」下载，再关闭弹窗。"""
        # 页面可能在循环中动态刷新；导出前按主客队重新定位一次行，避免点到错场次。
        refreshed_row = self._find_row_by_teams(home, away)
        if refreshed_row is not None:
            row = refreshed_row

        link = self._pick_europe_link(row)
        if not link:
            row_preview = self._preview_row(row)
            print(f"第 {index} 场比赛未找到「欧」链接，跳过。该行前几列: {row_preview}")
            return

        # 优先尝试直接用「欧」链接的 href 打开 1x2 页面；若 href 无效（空或 javascript），则只点击「欧」让站点自己弹出窗口。
        target_href = (link.get_attribute("href") or "").strip()
        href_lower = target_href.lower()
        use_direct_href = (
            bool(target_href)
            and not target_href.startswith("javascript:")
            and target_href != "#"
            and "sclass.aspx" not in href_lower
        )
        if use_direct_href:
            # 补全协议相对链接
            if target_href.startswith("//"):
                target_href = "https:" + target_href
            try:
                original_window = self.driver.current_window_handle
            except NoSuchWindowException:
                if not self._ensure_valid_window():
                    print(f"第 {index} 场 {home} vs {away}：无有效窗口，无法下载")
                    return
                original_window = self.driver.current_window_handle
            existing_windows = set(self.driver.window_handles)
            try:
                self.driver.execute_script("window.open(arguments[0], '_blank');", target_href)
            except Exception as e:
                print(f"第 {index} 场 {home} vs {away}：无法打开 1x2 链接 {target_href}：{e}")
                return
        else:
            # href 为空 / javascript / Sclass 联赛链接时，直接点击元素，交给站点 onclick 打开比赛详情页
            try:
                original_window = self.driver.current_window_handle
            except NoSuchWindowException:
                if not self._ensure_valid_window():
                    print(f"第 {index} 场 {home} vs {away}：无有效窗口，无法下载")
                    return
                original_window = self.driver.current_window_handle
            existing_windows = set(self.driver.window_handles)
            self._scroll_into_view_and_click(link)

        def _find_new_window(d):
            handles = set(d.window_handles)
            handles.difference_update(existing_windows)
            return handles.pop() if len(handles) == 1 else None

        try:
            new_handle = WebDriverWait(self.driver, WAIT_ELEMENT).until(_find_new_window)
        except TimeoutException:
            print(f"第 {index} 场 {home} vs {away}：未发现新窗口，跳过")
            return

        if not new_handle:
            print(f"第 {index} 场 {home} vs {away}：新窗口句柄为空，跳过")
            return

        try:
            self.driver.switch_to.window(new_handle)
            try:
                WebDriverWait(self.driver, WAIT_ELEMENT).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except Exception:
                pass

            self._wait_page_loaded()

            # 若当前页为盘路/资料库页，尝试跳转到对应的 1x2 百家欧指页面
            try:
                href_1x2 = None
                # 顶部菜单里的「百家欧指」
                try:
                    menu_link = self.driver.find_element(By.XPATH, "//table[@id='tb_menus']//a[contains(@href,'/1x2/')]")
                    href_1x2 = (menu_link.get_attribute('href') or '').strip()
                except Exception:
                    href_1x2 = None
                # 资料库页中指向 live.nowscore.com/1x2 的链接
                if not href_1x2:
                    for a in self.driver.find_elements(By.XPATH, "//a[contains(@href,'1x2')]"):
                        h = (a.get_attribute('href') or '').strip()
                        if h and '1x2' in h:
                            href_1x2 = h
                            break
                if href_1x2:
                    cur = (self.driver.current_url or '').strip()
                    if href_1x2.startswith('//'):
                        goto_url = 'https:' + href_1x2
                    elif href_1x2.startswith('/'):
                        goto_url = urljoin(cur, href_1x2)
                    else:
                        goto_url = href_1x2
                    if goto_url:
                        self.driver.get(goto_url)
                        WebDriverWait(self.driver, WAIT_ELEMENT).until(
                            EC.presence_of_element_located((By.TAG_NAME, 'body'))
                        )
                        self._wait_page_loaded()
            except Exception:
                pass

            # 若被重定向到 info.nowscore.com 等资料库页，仍然再兜底找一次 1x2 链接
            current_url = (self.driver.current_url or '').lower()
            if 'info.nowscore.com' in current_url:
                goto_url = None
                for a in self.driver.find_elements(By.XPATH, "//a[contains(@href,'live.nowscore.com') and contains(@href,'1x2')]"):
                    try:
                        h = (a.get_attribute('href') or '').strip()
                        if h and '1x2' in h:
                            goto_url = 'https:' + h if h.startswith('//') else h
                            break
                    except Exception:
                        continue
                if goto_url:
                    self.driver.get(goto_url)
                    WebDriverWait(self.driver, WAIT_ELEMENT).until(
                        EC.presence_of_element_located((By.TAG_NAME, 'body'))
                    )
                    self._wait_page_loaded()

            # 之前尝试过在详情页直接拼出 ExportExcelNew.aspx 的 URL 再用 requests 下载，
            # 但实际运行中返回了站内 404 页面（虽然 HTTP 状态码为 200），导致保存的 xls 无法打开。
            # 为保证数据正确性，这里暂时停用该优化，统一回退到浏览器点击「导出Excel」的稳定方案。

            # 详情页（含跳转 1x2）就绪后暂停 2 秒，便于观察页面再查找/点击「导出Excel」
            time.sleep(2)

            wait_export = WebDriverWait(self.driver, 5)
            # 导出按钮：优先用页面实际 id（debug HTML 中为 id="downobj"）
            export_btn = None
            try:
                export_btn = wait_export.until(
                    EC.element_to_be_clickable((By.ID, "downobj"))
                )
            except (TimeoutException, Exception):
                pass
            export_xpaths = [
                "//a[@id='downobj']",
                "//*[@id='downobj']",
                "//a[contains(.,'导出') and contains(.,'Excel')]",
                "//a[contains(.,'导出')]",
                "//*[contains(text(),'导出Excel')]",
                "//button[contains(.,'导出') and contains(.,'Excel')]",
                "//*[contains(text(),'导出') and contains(text(),'Excel')]",
                "//*[contains(text(),'导出')]",
                "//a[contains(.,'Excel')]",
            ]
            if not export_btn:
                for xpath in export_xpaths:
                    try:
                        els = wait_export.until(
                            EC.presence_of_all_elements_located((By.XPATH, xpath))
                        )
                        for el in els:
                            try:
                                if el.is_displayed() and el.is_enabled():
                                    export_btn = el
                                    break
                            except Exception:
                                continue
                        if export_btn:
                            break
                    except TimeoutException:
                        continue
                    except Exception:
                        continue

            if not export_btn:
                self.driver.switch_to.default_content()
                time.sleep(0.5)
                for xpath in export_xpaths[:6]:
                    try:
                        els = self.driver.find_elements(By.XPATH, xpath)
                        for el in els:
                            try:
                                if el.is_displayed() and el.is_enabled():
                                    export_btn = el
                                    break
                            except Exception:
                                continue
                        if export_btn:
                            break
                    except Exception:
                        continue

            if not export_btn:
                try:
                    self.driver.switch_to.default_content()
                    for iframe in self.driver.find_elements(By.TAG_NAME, "iframe"):
                        try:
                            self.driver.switch_to.frame(iframe)
                            for xpath in export_xpaths[:6]:
                                try:
                                    els = self.driver.find_elements(By.XPATH, xpath)
                                    for el in els:
                                        try:
                                            if el.is_displayed() and el.is_enabled():
                                                export_btn = el
                                                break
                                        except Exception:
                                            continue
                                    if export_btn:
                                        break
                                except Exception:
                                    continue
                            if export_btn:
                                break
                        except Exception:
                            pass
                        finally:
                            if not export_btn:
                                self.driver.switch_to.default_content()
                except Exception:
                    pass

            if not export_btn:
                self._save_debug_page_source(index, home, away)
                raise ValueError("未找到「导出Excel」按钮")

            # 文件名用本次运行时的当前时间 YYYYMMDDHH（由 run() 传入）；存放目录按日期
            if time_suffix is None:
                time_suffix = _now_in_tz().strftime("%Y%m%d%H")
            date_folder = self._date_folder_from_time_suffix(time_suffix)
            target_dir = os.path.join(self.download_dir, date_folder)
            os.makedirs(target_dir, exist_ok=True)
            try:
                self.driver.execute_cdp_cmd(
                    "Page.setDownloadBehavior",
                    {"behavior": "allow", "downloadPath": os.path.abspath(target_dir)},
                )
            except Exception as cdp_err:
                print(f"  设置下载目录失败，将使用默认目录: {cdp_err}", file=__import__("sys").stderr)

            log = logging.getLogger("crawl_real")
            log.info("开始下载第 %d 场: %s vs %s", index, home, away)
            saved = False
            for attempt in range(1, EXPORT_EXCEL_MAX_ATTEMPTS + 1):
                try:
                    before_attempt = {
                        f for f in os.listdir(target_dir) if f.lower().endswith(".xls")
                    }
                except Exception:
                    before_attempt = set()

                try:
                    clicked = self.driver.execute_script("""
                        var el = document.getElementById('downobj');
                        if (el) { el.scrollIntoView({block:'center'}); el.click(); return true; }
                        var f = document.getElementById('DownloadForm');
                        if (f) { f.submit(); return true; }
                        return false;
                    """)
                    if not clicked:
                        try:
                            self.driver.find_element(By.ID, "downobj").click()
                        except Exception:
                            try:
                                self.driver.find_element(By.ID, "DownloadForm").submit()
                            except Exception:
                                pass
                except Exception as click_err:
                    try:
                        self._scroll_into_view_and_click(export_btn)
                    except Exception:
                        try:
                            for xpath in ["//a[@id='downobj']", "//*[contains(text(),'导出Excel')]"]:
                                els = self.driver.find_elements(By.XPATH, xpath)
                                for el in els:
                                    try:
                                        self.driver.execute_script("arguments[0].click();", el)
                                        break
                                    except Exception:
                                        continue
                                else:
                                    continue
                                break
                        except Exception:
                            pass
                    print(
                        f"  点击导出时异常: {click_err}",
                        file=__import__("sys").stderr,
                    )

                try:
                    if self._rename_latest_download_in_dir(
                        home,
                        away,
                        target_dir,
                        before_attempt,
                        time_suffix,
                        log_if_no_new_file=(attempt == EXPORT_EXCEL_MAX_ATTEMPTS),
                    ):
                        saved = True
                        break
                except Exception as move_err:
                    print(f"  移动下载文件失败: {move_err}", file=__import__("sys").stderr)

                if saved:
                    break
                if attempt < EXPORT_EXCEL_MAX_ATTEMPTS:
                    log.info(
                        "第 %d 场 导出未检测到新文件，2 秒后进行第 %d/%d 次导出",
                        index,
                        attempt + 1,
                        EXPORT_EXCEL_MAX_ATTEMPTS,
                    )
                    time.sleep(2)

            if not saved:
                log.warning(
                    "第 %d 场 %s vs %s：导出 Excel 重试 %d 次仍失败，已跳过",
                    index,
                    home,
                    away,
                    EXPORT_EXCEL_MAX_ATTEMPTS,
                )
        except Exception as e:
            try:
                self._save_debug_page_source(index, home, away)
            except Exception:
                pass
            print(f"第 {index} 场 {home} vs {away}：下载 Excel 出错：{e}")
        finally:
            try:
                self.driver.close()
            except Exception:
                pass
            try:
                self.driver.switch_to.window(original_window)
            except Exception:
                pass

    def _find_row_by_teams(self, home: str, away: str):
        """按主队/客队在当前可见列表里重新定位比赛行；找不到时返回 None。"""
        try:
            rows = self._collect_match_rows(WebDriverWait(self.driver, WAIT_ELEMENT), visible_only=MATCH_FILTER_VISIBLE_ONLY)
        except Exception:
            return None

        for r in rows:
            try:
                r_home = self._get_cell_text(r, COL_HOME)
                r_away = self._get_cell_text(r, COL_AWAY)
                if r_home == home and r_away == away:
                    return r
            except Exception:
                continue
        return None

    def _pick_europe_link(self, row):
        """
        选择比赛级「欧/析亚欧」链接，避免误选联赛链接（如 Sclass.aspx?id=650）。
        优先级：
        1) 文本含「析亚欧」或「欧」且 href 指向 1x2 页面；
        2) 文本含「析亚欧」或「欧」且 href 为 javascript/空（交给站点 click 逻辑）；
        3) 兜底返回第一个候选。
        """
        candidates = row.find_elements(By.XPATH, ".//a[contains(normalize-space(.),'析亚欧') or contains(normalize-space(.),'欧')]")
        if not candidates:
            return None

        best_js = None
        for a in candidates:
            try:
                href = (a.get_attribute("href") or "").strip()
            except Exception:
                href = ""
            href_lower = href.lower()
            if "/1x2/" in href_lower or "1x2" in href_lower:
                return a
            if "sclass.aspx" in href_lower:
                continue
            if not href or href.startswith("javascript:") or href == "#":
                if best_js is None:
                    best_js = a

        if best_js is not None:
            return best_js

        # 最后兜底：返回非联赛链接的第一个
        for a in candidates:
            try:
                href = (a.get_attribute("href") or "").strip().lower()
            except Exception:
                href = ""
            if "sclass.aspx" not in href:
                return a
        return candidates[0]

    def _save_debug_page_source(self, index, home, away):
        """未找到导出按钮时保存当前页面 HTML，便于排查选择器。输出到 DEBUG_LOG_DIR。"""
        try:
            os.makedirs(DEBUG_LOG_DIR, exist_ok=True)
            debug_dir = DEBUG_LOG_DIR
            safe = re.sub(r'[\s\\/:*?"<>|]', "_", f"{index}_{home}_{away}")[:80]
            path = os.path.join(debug_dir, f"debug_export_page_{safe}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            print(f"  已保存页面 HTML 便于排查: {path}", file=__import__("sys").stderr)
        except Exception as e:
            print(f"  保存调试 HTML 失败: {e}", file=__import__("sys").stderr)

    def _date_folder_from_time_suffix(self, time_suffix: str) -> str:
        """
        根据 YYYYMMDDHH 返回“自然日”目录 YYYYMMDD。

        新版本约定：下载文件的存放目录仅按日期区分，与跨天临界点无关。
        临界点只用于后续 merge_data 等统计脚本按时间段切分数据。
        """
        now = _now_in_tz()
        if not time_suffix or len(time_suffix) < 8:
            return now.strftime("%Y%m%d")
        try:
            y, m, d = int(time_suffix[:4]), int(time_suffix[4:6]), int(time_suffix[6:8])
        except (ValueError, IndexError):
            return now.strftime("%Y%m%d")
        return f"{y:04d}{m:02d}{d:02d}"

    def _rename_latest_download_in_dir(
        self,
        home,
        away,
        target_dir: str,
        before_files: set,
        time_suffix: str,
        *,
        log_if_no_new_file: bool = True,
    ):
        """
        在指定目录内等待新出现的 .xls 并重命名为 主队_VS_客队_{time_suffix}.xls（不跨目录移动）。
        返回是否成功检测到新文件并完成命名；log_if_no_new_file=False 时未检测到文件不打 warning（用于重试中间次）。
        """
        try:
            wait_sec = max(0.05, float(EXPORT_EXCEL_DOWNLOAD_WAIT_SECONDS))
            poll = min(1.0, max(0.05, wait_sec / 10.0))
            deadline = time.time() + wait_sec
            new_path = None

            while time.time() < deadline:
                try:
                    current = [
                        f
                        for f in os.listdir(target_dir)
                        if f.lower().endswith(".xls")
                    ]
                except Exception:
                    time.sleep(poll)
                    continue
                added = [f for f in current if f not in before_files]
                if added:
                    candidates = [
                        os.path.join(target_dir, f) for f in added
                    ]
                    new_path = max(candidates, key=os.path.getmtime)
                    break
                time.sleep(poll)

            if not new_path:
                if log_if_no_new_file:
                    logging.getLogger("crawl_real").warning(
                        "在 %.1f 秒内未检测到新增 Excel 文件（%s vs %s）",
                        wait_sec,
                        home,
                        away,
                    )
                return False

            if self.rename_downloaded_file:
                safe_home = self._safe_name(home)
                safe_away = self._safe_name(away)
                new_name = f"{safe_home}_VS_{safe_away}_{time_suffix}.xls"
                dest_path = os.path.join(target_dir, new_name)
                if os.path.abspath(new_path) != os.path.abspath(dest_path):
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    os.rename(new_path, dest_path)
            else:
                dest_path = new_path
            # 相对路径以下载根目录的父目录为根，显示为 football-betting-data/…（不含仓库文件夹名前缀）
            root = os.path.abspath(os.path.join(self.download_dir, os.pardir))
            rel = os.path.relpath(dest_path, root)
            logging.getLogger("crawl_real").info("已保存为: %s", rel)
            return True
        except Exception as e:
            print(f"重命名下载文件失败: {e}")
            return False

    def _safe_name(self, name: str) -> str:
        """将联赛/队名中的非法文件名字符替换为下划线。"""
        invalid = '\\\\/:*?\"<>|'
        return "".join("_" if ch in invalid else ch for ch in (name or "")).strip()

    def _get_cell_text(self, row, col_index):
        """取单元格文本；若 getText 为空则用 JS textContent。"""
        tds = row.find_elements(By.CSS_SELECTOR, "td")
        if col_index < 0 or col_index >= len(tds):
            return ""
        cell = tds[col_index]
        text = cell.text.strip()
        if not text:
            text = self.driver.execute_script("return arguments[0].textContent", cell) or ""
            text = text.strip()
        # 将单元格中的换行/tab 等压缩为单个空格，避免日志被拆成多行
        return " ".join(text.split())

    def _row_has_jian(self, row) -> bool:
        """
        比赛行是否包含“荐”标记。
        仅识别“可见”的荐标记，避免 hidden 文本导致全部命中。
        """
        try:
            # 1) 行内可见文本包含“荐”
            text = (row.text or "").strip()
            if "荐" in text:
                return True

            # 2) 行内可见元素的文本包含“荐”
            candidates = row.find_elements(
                By.XPATH,
                ".//*[contains(normalize-space(string(.)), '荐')]",
            )
            for el in candidates:
                try:
                    if el.is_displayed() and "荐" in (el.text or ""):
                        return True
                except Exception:
                    continue

            # 3) 部分页面用图标表示“荐”，识别可见 img 的 alt/title
            icon_candidates = row.find_elements(
                By.XPATH,
                ".//img[contains(@alt,'荐') or contains(@title,'荐')]",
            )
            for el in icon_candidates:
                try:
                    if el.is_displayed():
                        return True
                except Exception:
                    continue

            return False
        except Exception:
            return False

    def _row_matches_team_whitelist(self, row) -> bool:
        """主队/客队命中任一球队白名单关键词时返回 True。白名单为空表示不限制。"""
        if not TEAM_WHITELIST_KEYWORDS:
            return True
        home = self._get_cell_text(row, COL_HOME)
        away = self._get_cell_text(row, COL_AWAY)
        text = f"{home} {away}"
        return any(kw in text for kw in TEAM_WHITELIST_KEYWORDS)

    def _is_status_empty(self, status_text: str) -> bool:
        """状态列为空（空白或「-」）时返回 True，仅此类比赛会下载；「比赛中」「完」等返回 False。"""
        s = (status_text or "").strip()
        return s == "" or s == "-"

    def _preview_row(self, row):
        """打印该行前几列文本，用于排查“无欧链接”的行是表头还是异常数据。"""
        tds = row.find_elements(By.CSS_SELECTOR, "td")
        texts = []
        for cell in tds[:6]:
            texts.append(cell.text.strip())
        return " | ".join(texts)

    def _scroll_into_view_and_click(self, element):
        """先滚动到元素再点击；若被遮挡或不可交互则用 JS 点击。"""
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", element
        )
        time.sleep(0.3)
        try:
            element.click()
        except (ElementNotInteractableException, ElementClickInterceptedException):
            self.driver.execute_script("arguments[0].click();", element)
