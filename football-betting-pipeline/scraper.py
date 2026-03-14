# -*- coding: utf-8 -*-
"""
智云比分网 竞足/北单/14场 比赛列表爬虫。
逻辑与 Java 版 ZhiyunScraperService 一致。

下载方式：
- 使用 Selenium 进入「足球 → 即时比分 → 足彩 → 北单」，等待表格刷新后仅处理状态为空的比赛（空白或「-」）；
- 对每场状态为空的比赛，点击行内的「欧」链接，打开详情页；
- 在详情页中点击「导出Excel」按钮，由浏览器下载 .xls；
- 将 .xls 文件重命名为「主队 VS 客队{YYYYMMDDHH}.xls」。
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

from config import (
    BASE_URL,
    DOWNLOAD_DIR,
    DEBUG_LOG_DIR,
    CUTOFF_HOUR,
    DEBUG_MAX_MATCHES,
    DEBUG_MATCH_KEYWORDS,
    ZUCAI_MENU_OPTIONS,
    COL_DATE,
    COL_TIME,
    COL_STATUS,
    COL_HOME,
    COL_AWAY,
    WAIT_ELEMENT,
    WAIT_AFTER_CLICK,
    WAIT_AFTER_HOVER,
    WAIT_TABLE_REFRESH,
    WAIT_ROW_COUNT,
    WAIT_FIRST_ROW_CHANGED,
)

def _now_in_tz():
    """返回本机当前时间（本地时区），用于下载目录/文件名。"""
    return datetime.now()


class ZhiyunScraper:
    def __init__(self, driver, base_url=BASE_URL, download_dir=DOWNLOAD_DIR):
        self.driver = driver
        self.base_url = base_url
        self.download_dir = download_dir

    def _wait_page_loaded(self, timeout=WAIT_ELEMENT):
        """等待当前页面 readyState 为 complete，超时则忽略错误。"""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass

    def run(self):
        """主流程：打开页面 -> 足球 -> 即时比分 -> 足彩 -> 北单，等待表格刷新后仅处理状态为空的比赛，逐场导出并下载 Excel。"""
        now = _now_in_tz()
        self._run_time_suffix = now.strftime("%Y%m%d%H")
        log = logging.getLogger("crawl_real")
        log.info("[爬虫] 本次运行时间戳（文件名用）: %s （当前时区时间: %s）", self._run_time_suffix, now.strftime('%Y-%m-%d %H:%M'))
        self.driver.get(self.base_url)
        wait = WebDriverWait(self.driver, WAIT_ELEMENT)

        # 1) 点击主菜单「足球」
        football_menu = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "足球")))
        self._scroll_into_view_and_click(football_menu)

        # 2) 点击「即时比分」，依赖显式等待而非固定 sleep
        live_tab = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "即时比分")))
        self._scroll_into_view_and_click(live_tab)

        # 3) 对 竞足、北单、14场 分别处理（当前配置里只保留了「北单」）
        for menu_option in ZUCAI_MENU_OPTIONS:
            log.info("========== 获取 [%s] 比赛列表 ==========", menu_option)
            first_row_home_before = self._get_first_data_row_home_team()
            self._hover_zucai_then_click_option(wait, menu_option)
            self._ensure_zucai_mode(menu_option)
            # SetLevel 后等待表格行数“收敛”，这里将超时限制在 10 秒以内，避免长时间阻塞
            row_ok = self._wait_until_match_row_count_at_most(150, timeout=10)
            if not row_ok:
                ts = _now_in_tz().strftime("%Y-%m-%d %H:%M:%S")
                log.warning("%s [%s] 警告：表格行数仍很多，可能未切换到当前类型", ts, menu_option)
            else:
                # 只有在行数已经收敛时，才再等第一行变化，避免额外长时间等待
                self._wait_until_first_row_changed(first_row_home_before)

            if not self._ensure_valid_window():
                print(f"[{menu_option}] 无可用窗口，跳过", file=__import__("sys").stderr)
                continue

            self._select_primary_matches(wait)

            match_rows = self._collect_match_rows(wait, visible_only=True)
            hidden_in_dom = self._count_hidden_rows_in_table()
            log.info("[%s] 当前列表显示: %d 场，表格中隐藏行: %d 场", menu_option, len(match_rows), hidden_in_dom)
            # 仅处理状态为空的比赛（未开赛等；状态为「比赛中」「完」或分钟数的不下载）
            match_rows = [row for row in match_rows if self._is_status_empty(self._get_cell_text(row, COL_STATUS))]
            log.info("[%s] 过滤后（仅状态为空）: %d 场", menu_option, len(match_rows))
            log.info("--- 主队 vs 客队 ---")
            for i, row in enumerate(match_rows, 1):
                home = self._get_cell_text(row, COL_HOME)
                away = self._get_cell_text(row, COL_AWAY)
                # 使用解析后的时间戳，避免原始单元格中换行导致日志换行
                match_ts = self._get_time_suffix_from_row(row)

                # 若配置了 DEBUG_MATCH_KEYWORDS，则仅抓取主队/客队名称包含任一关键词的比赛
                if DEBUG_MATCH_KEYWORDS:
                    text = f"{home} {away}"
                    if not any(kw in text for kw in DEBUG_MATCH_KEYWORDS):
                        continue

                msg = f"{i}. {match_ts} {home} vs {away}"
                log.info(msg)
                self._download_excel_for_row(wait, row, i, home, away, time_suffix=self._run_time_suffix)
                if DEBUG_MAX_MATCHES and i >= DEBUG_MAX_MATCHES:
                    log.info("[调试] 已抓取 %d 场，结束抓取。", DEBUG_MAX_MATCHES)
                    break
            log.info("")

    def _hover_zucai_then_click_option(self, wait, option_text):
        """鼠标移到「足彩」弹出菜单，再点击指定项（竞足/北单/14场）。"""
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
        """若页面有 SetLevel，直接调用以切换到竞足(3)/北单(2)/14场(1)。"""
        level = 3 if menu_option == "竞足" else (2 if menu_option == "北单" else 1)
        try:
            ok = self.driver.execute_script(
                f"return typeof window.SetLevel === 'function' && (window.SetLevel({level}), true);"
            )
            if ok:
                ts = _now_in_tz().strftime("%Y-%m-%d %H:%M:%S")
                print(f"{ts} 已通过 SetLevel({level}) 切换到 [{menu_option}]")
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

    def _get_first_data_row_home_team(self):
        """取当前 table_live 第一行数据的主队名（非表头），无则返回空串。"""
        try:
            rows = self.driver.find_elements(By.CSS_SELECTOR, "#table_live tr")
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

    def _get_match_row_count(self):
        """当前 table_live 中数据行数（不含表头）。"""
        try:
            rows = self.driver.find_elements(By.CSS_SELECTOR, "#table_live tr")
            n = 0
            for row in rows:
                tds = row.find_elements(By.CSS_SELECTOR, "td")
                if len(tds) < 7:
                    continue
                h = tds[COL_HOME].text.strip()
                a = tds[COL_AWAY].text.strip()
                if h == "主队" and a == "客队":
                    continue
                n += 1
            return n
        except Exception:
            return 999

    def _wait_until_match_row_count_at_most(self, max_count, timeout=None):
        """等表格行数 <= maxCount，最多等 timeout(秒)，默认 WAIT_ROW_COUNT。"""
        start = time.time()
        if timeout is None:
            timeout = WAIT_ROW_COUNT
        wait = WebDriverWait(self.driver, timeout)

        def _row_count_ok(d):
            # 先等过一个最小刷新间隔，再判断行数条件
            if time.time() - start < WAIT_TABLE_REFRESH:
                return False
            cnt = self._get_match_row_count()
            return 0 < cnt <= max_count

        try:
            wait.until(_row_count_ok)
            return True
        except TimeoutException:
            return False

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

    def _select_primary_matches(self, wait):
        """打开「赛事选择」弹窗，点击「一级赛事」，再关闭弹窗。多策略查找 + 弹窗等待 + 重试。"""
        # 为避免在找不到弹窗/按钮时长时间阻塞，这里限制为单次尝试，并控制整体超时时间。
        for attempt in range(1):
            try:
                # 1) 点「赛事选择」打开弹窗（链接或可点击文字）
                choice_selectors = [
                    By.LINK_TEXT, "赛事选择",
                    By.XPATH, "//*[contains(text(),'赛事选择') and (self::a or self::span or self::button)]",
                ]
                choice_btn = None
                for i in range(0, len(choice_selectors), 2):
                    by, value = choice_selectors[i], choice_selectors[i + 1]
                    try:
                        choice_btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((by, value))
                        )
                        if choice_btn and choice_btn.is_displayed():
                            break
                    except Exception:
                        continue
                if not choice_btn or not choice_btn.is_displayed():
                    raise ValueError("未找到可点击的「赛事选择」")
                self._scroll_into_view_and_click(choice_btn)

                # 2) 等弹窗出现后再找「一级赛事」（支持文本含空格、子节点）
                dialog_wait = WebDriverWait(self.driver, 8)
                primary_selectors = [
                    "//*[normalize-space(text())='一级赛事']",
                    "//*[contains(text(),'一级赛事')]",
                    "//button[contains(.,'一级赛事')]",
                    "//a[contains(.,'一级赛事')]",
                    "//span[contains(.,'一级赛事')]",
                ]
                primary_btn = None
                def _find_primary(d):
                    for xpath in primary_selectors:
                        try:
                            els = d.find_elements(By.XPATH, xpath)
                        except Exception:
                            continue
                        for el in els:
                            try:
                                if el.is_displayed() and el.is_enabled():
                                    return el
                            except Exception:
                                continue
                    return False

                try:
                    primary_btn = dialog_wait.until(_find_primary)
                except TimeoutException:
                    primary_btn = None
                if not primary_btn:
                    raise ValueError("弹窗内未找到「一级赛事」")
                self._scroll_into_view_and_click(primary_btn)

                # 3) 点「关闭」：优先找弹窗内的（含「赛事选择」的容器内的关闭）
                close_selectors = [
                    "//div[contains(@class,'modal') or contains(@class,'dialog') or contains(@id,'dialog')]//*[normalize-space(text())='关闭']",
                    "//div[.//*[contains(text(),'一级赛事')]]//*[normalize-space(text())='关闭']",
                    "//*[normalize-space(text())='关闭']",
                ]
                close_btn = None
                for xpath in close_selectors:
                    try:
                        els = self.driver.find_elements(By.XPATH, xpath)
                        for el in els:
                            if el.is_displayed() and el.is_enabled():
                                close_btn = el
                                break
                        if close_btn:
                            break
                    except Exception:
                        continue
                if not close_btn:
                    raise ValueError("未找到「关闭」按钮")
                self._scroll_into_view_and_click(close_btn)
                # 关闭后等待表格刷新完成（行数收敛），避免固定 sleep
                try:
                    self._wait_until_match_row_count_at_most(300)
                except Exception:
                    pass
                print("已选「一级赛事」并关闭赛事选择")
                return
            except Exception as e:
                ts = _now_in_tz().strftime("%Y-%m-%d %H:%M:%S")
                logging.getLogger("crawl_real").warning(
                    "%s 赛事选择/一级赛事 未应用（%s），继续用当前列表", ts, e
                )
                return

    def _count_hidden_rows_in_table(self):
        """表格 #table_live 中带 index 且 display:none 的行数（与页面「隐藏 XX 场」对应，仅统计当前表内）。"""
        try:
            n = self.driver.execute_script("""
                var rows = document.querySelectorAll('#table_live tr[index]');
                var count = 0;
                for (var i = 0; i < rows.length; i++) {
                    if (rows[i].style.display === 'none') count++;
                }
                return count;
            """)
            return n if n is not None else 0
        except Exception:
            return 0

    def _collect_match_rows(self, wait, visible_only=True):
        """等待 #table_live 出现并收集数据行（非表头）。visible_only=True 时只收集当前页显示的行（style.display!='none'），与浏览器列表一致。"""
        for attempt in range(2):
            try:
                if attempt > 0 and self._ensure_valid_window():
                    wait = WebDriverWait(self.driver, WAIT_ELEMENT)
                wait.until(EC.presence_of_element_located((By.ID, "table_live")))
                table = self.driver.find_element(By.ID, "table_live")
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
                if attempt == 0 and self._ensure_valid_window():
                    continue
                raise
        return []

    def _download_excel_for_row(self, wait, row, index, home, away, time_suffix=None):
        """点击当前行的「欧」链接（列表页为「析亚欧」），弹出详情页后点击「导出Excel」下载，再关闭弹窗。"""
        # 兼容「欧」「析亚欧」等，含欧字的链接或可点击元素
        europe_links = row.find_elements(By.XPATH, ".//a[contains(.,'欧')]")
        if not europe_links:
            europe_links = row.find_elements(By.XPATH, ".//*[contains(text(),'析亚欧') or contains(text(),'欧')]")
        if not europe_links:
            row_preview = self._preview_row(row)
            print(f"第 {index} 场比赛未找到「欧」链接，跳过。该行前几列: {row_preview}")
            return

        # 优先尝试直接用「欧」链接的 href 打开 1x2 页面；若 href 无效（空或 javascript），则只点击「欧」让站点自己弹出窗口。
        link = europe_links[0]
        target_href = (link.get_attribute("href") or "").strip()
        if target_href and not target_href.startswith("javascript:") and target_href != "#":
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
            # href 为空或为 javascript 等无效时，直接点击「欧」链接，让站点自身逻辑决定打开的页面
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
            try:
                before_files = {
                    f for f in os.listdir(target_dir) if f.lower().endswith(".xls")
                }
            except Exception:
                before_files = set()

            logging.getLogger("crawl_real").info("开始下载第 %d 场 Excel: %s vs %s", index, home, away)
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
                print(f"  点击导出时异常（仍会尝试移动已下载文件）: {click_err}", file=__import__("sys").stderr)
            try:
                self._rename_latest_download_in_dir(home, away, target_dir, before_files, time_suffix)
            except Exception as move_err:
                print(f"  移动下载文件到子目录失败: {move_err}", file=__import__("sys").stderr)
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

    def _get_time_suffix_from_row(self, row):
        """从表格行解析日期、时间，返回 10 位 YYYYMMDDHH；解析失败时用当前时间。"""
        date_str = self._get_cell_text(row, COL_DATE).strip()
        time_str = self._get_cell_text(row, COL_TIME).strip()
        y, m, d, h = None, None, None, None
        for sep in ["-", "/", ".", "－"]:
            if sep in date_str:
                parts = re.split(r"[-/.\s－]+", date_str, maxsplit=2)
                if len(parts) >= 2:
                    a, b = parts[0].strip(), parts[1].strip()
                    if len(a) == 4 and a.isdigit():
                        y = int(a)
                        m = int(b) if b.isdigit() else None
                        d = int(parts[2].strip()) if len(parts) > 2 and parts[2].strip().isdigit() else None
                    else:
                        m = int(a) if a.isdigit() else None
                        d = int(b) if b.isdigit() else None
                break
        if m is None and date_str.isdigit() and len(date_str) >= 4:
            m, d = int(date_str[:2]), int(date_str[2:4]) if len(date_str) >= 4 else None
        if time_str:
            mt = re.search(r"(\d{1,2})", time_str)
            if mt:
                h = int(mt.group(1))
        now = _now_in_tz()
        if y is None:
            y = now.year
        if m is None:
            m = now.month
        if d is None:
            d = now.day
        if h is None:
            h = now.hour
        return f"{y:04d}{m:02d}{d:02d}{h:02d}"

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
        self, home, away, target_dir: str, before_files: set, time_suffix: str
    ):
        """在指定目录内等待新出现的 .xls 并重命名为 主队 VS 客队{time_suffix}.xls（不跨目录移动）。"""
        try:
            # 为避免单场比赛下载卡住太久，将等待上限从 60 秒缩短为 30 秒。
            deadline = time.time() + 30
            new_path = None

            while time.time() < deadline:
                try:
                    current = [
                        f
                        for f in os.listdir(target_dir)
                        if f.lower().endswith(".xls")
                    ]
                except Exception:
                    time.sleep(1.0)
                    continue
                added = [f for f in current if f not in before_files]
                if added:
                    candidates = [
                        os.path.join(target_dir, f) for f in added
                    ]
                    new_path = max(candidates, key=os.path.getmtime)
                    break
                time.sleep(1.0)

            if not new_path:
                logging.getLogger("crawl_real").warning(
                    "在 30 秒内未检测到新增 Excel 文件（%s vs %s），跳过重命名", home, away
                )
                return

            safe_home = self._safe_name(home)
            safe_away = self._safe_name(away)
            new_name = f"{safe_home} VS {safe_away}{time_suffix}.xls"
            dest_path = os.path.join(target_dir, new_name)

            if os.path.abspath(new_path) != os.path.abspath(dest_path):
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                os.rename(new_path, dest_path)
            root = os.path.abspath(os.path.join(self.download_dir, os.pardir))
            rel = os.path.relpath(dest_path, root)
            logging.getLogger("crawl_real").info("已保存为: %s", rel)
        except Exception as e:
            print(f"重命名下载文件失败: {e}")

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
