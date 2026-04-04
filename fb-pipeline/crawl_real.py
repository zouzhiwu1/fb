# -*- coding: utf-8 -*-
"""
抓取即时比分数据：创建 Chrome WebDriver，运行爬虫后退出。
执行时以当前时间点作为文件名中的小时（如 09:08 -> 09）。
详细日志写入 logs/crawl_real_{YYYYMMDDHH}.log。
"""
import logging
import os
import re
import subprocess
import sys
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

from config import (
    BASE_URL,
    CHROME_BINARY_PATH,
    CHROME_DISABLE_HTTP2,
    CHROMEDRIVER_PATH,
    CHROME_USER_AGENT,
    DEBUG_LOG_DIR,
    DOWNLOAD_DIR,
    HEADLESS,
    LOG_RETENTION_DAYS,
    PAGE_LOAD_STRATEGY,
    PAGE_LOAD_TIMEOUT_SECONDS,
    SELENIUM_REMOTE_READ_TIMEOUT,
)
from log_cleanup import delete_old_logs
from scraper_real import ZhiyunScraper


def _setup_logging():
    """配置详细日志到独立文件：crawl_real_{YYYYMMDDHH}.log。"""
    os.makedirs(DEBUG_LOG_DIR, exist_ok=True)
    time_suffix = datetime.now().strftime("%Y%m%d%H")
    log_path = os.path.join(DEBUG_LOG_DIR, f"crawl_real_{time_suffix}.log")
    logger = logging.getLogger("crawl_real")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    _display_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    rel_log_path = os.path.relpath(log_path, _display_root)
    logger.info("日志文件: %s", rel_log_path)
    return logger


def _chromium_semver_from_binary(binary_path: str) -> str | None:
    """从 Chromium/Chrome 可执行文件解析主版本三元组，供 webdriver-manager 下载匹配 chromedriver。"""
    if not binary_path or not os.path.isfile(binary_path):
        return None
    try:
        proc = subprocess.run(
            [binary_path, "--version"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        text = (proc.stdout or "") + (proc.stderr or "")
        m = re.search(r"(\d+\.\d+\.\d+)", text)
        return m.group(1) if m else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _chromedriver_path_webdriver_manager() -> str:
    """
    未指定系统 chromedriver 时，用 webdriver-manager 下载驱动。

    Docker 内常见仅有 /usr/bin/chromium、无 google-chrome；默认 ChromeDriverManager
    按 Google Chrome 检测版本会得到 None，进而落到旧版 LATEST_RELEASE（如 114），
    与真实 Chromium 主版本不一致。此处若配置了 CHROME_BINARY_PATH，则按其 --version
    解析版本并显式指定 driver_version。
    """
    log = logging.getLogger("crawl_real")
    if CHROME_BINARY_PATH:
        ver = _chromium_semver_from_binary(CHROME_BINARY_PATH)
        binary_lower = CHROME_BINARY_PATH.lower()
        is_chromium = "chromium" in binary_lower
        chrome_type = ChromeType.CHROMIUM if is_chromium else ChromeType.GOOGLE
        browser_label = "Chromium" if is_chromium else "Google Chrome"
        if ver:
            return ChromeDriverManager(
                driver_version=ver,
                chrome_type=chrome_type,
            ).install()
        log.warning(
            "无法从 %s 解析版本，回退为按系统浏览器类型(%s)探测 chromedriver",
            CHROME_BINARY_PATH,
            browser_label,
        )
        return ChromeDriverManager(chrome_type=chrome_type).install()
    return ChromeDriverManager().install()


def create_driver():
    """创建 Chrome 驱动，使用 webdriver-manager 自动管理 chromedriver。"""
    options = webdriver.ChromeOptions()
    options.page_load_strategy = PAGE_LOAD_STRATEGY
    if HEADLESS:
        options.add_argument("--headless=new")
        # Linux 无头容器常见 GPU/渲染崩溃，与 <unknown> 栈相关时可稳定页面
        options.add_argument("--disable-gpu")
    if CHROME_USER_AGENT:
        options.add_argument(f"--user-agent={CHROME_USER_AGENT}")
    if CHROME_DISABLE_HTTP2:
        options.add_argument("--disable-http2")
    # 降低无头自动化特征（部分站点会挡 HeadlessChrome / webdriver）
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=zh-CN,zh")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # 静音浏览器，避免访问比分页时进球/口哨等提示音干扰本机
    options.add_argument("--mute-audio")
    # 禁止自动播放媒体（需用户交互后才可播放），进一步减少页面音效
    options.add_argument("--autoplay-policy=document-user-activation-required")

    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    if CHROME_BINARY_PATH:
        options.binary_location = CHROME_BINARY_PATH

    if CHROMEDRIVER_PATH:
        service = Service(executable_path=CHROMEDRIVER_PATH)
    else:
        service = Service(_chromedriver_path_webdriver_manager())

    driver = webdriver.Chrome(service=service, options=options)

    # ChromiumRemoteConnection 默认 HTTP 读超时 120s；须在首次 driver.get 前改 command_executor
    if SELENIUM_REMOTE_READ_TIMEOUT > 0:
        try:
            ce = driver.command_executor
            if hasattr(ce, "client_config") and ce.client_config is not None:
                ce.client_config.timeout = SELENIUM_REMOTE_READ_TIMEOUT
        except Exception:
            pass

    if PAGE_LOAD_TIMEOUT_SECONDS > 0:
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)

    # 在每个新页面注入静音脚本：静音所有 audio/video，并定期拉取新元素（应对动态加载）
    _inject_mute_script(driver)
    _inject_hide_webdriver(driver)
    return driver


def _inject_hide_webdriver(driver):
    """通过 CDP 隐藏 navigator.webdriver，减轻反爬脚本识别。"""
    src = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
"""
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": src},
        )
    except Exception:
        pass


def _inject_mute_script(driver):
    """通过 CDP 在每次加载新文档时注入静音脚本，确保页面内音视频与部分 Web Audio 被静音。"""
    script = """
(function() {
  function muteMedia() {
    document.querySelectorAll('audio, video').forEach(function(el) {
      el.muted = true;
      el.volume = 0;
    });
  }
  muteMedia();
  setInterval(muteMedia, 800);
})();
"""
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": script})
    except Exception:
        pass


def main():
    """
    抓取即时比分数据。

    用法（与 merge_data.py 保持一致的参数形式）:
      python crawl_real.py <起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>

    说明：
    - 目前 crawl_real.py 实际仍按「执行当下的shishipankou」抓取，不依赖传入时间点，
      这里的起始/终止时间主要用于与 merge_data.py 等脚本保持一致的调用方式，
      便于 run_real.py 统一管理参数，避免混淆。
    """
    log = _setup_logging()
    removed = delete_old_logs(DEBUG_LOG_DIR, days=LOG_RETENTION_DAYS)
    if removed:
        _display_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        rel_removed = [os.path.relpath(p, _display_root) for p in removed]
        log.info("已删除 %d 个超过 %d 天的日志文件: %s", len(removed), LOG_RETENTION_DAYS, rel_removed)

    args = sys.argv[1:]
    if len(args) != 2 or not all(len(a) == 10 and a.isdigit() for a in args):
        log.error(
            "用法: python crawl_real.py <起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>，例如: python crawl_real.py 2026031012 2026031111"
        )
        sys.exit(1)
    start_arg, end_arg = args
    log.info("收到时间区间参数: [%s, %s]（当前版本仅用于日志标记，不影响抓取行为）", start_arg, end_arg)
    driver = None
    try:
        log.info("创建 Chrome 驱动...")
        driver = create_driver()
        log.info("驱动已创建，开始执行爬虫")
        scraper = ZhiyunScraper(driver, base_url=BASE_URL)
        scraper.run()
        log.info("爬虫执行完成")
    except Exception as e:
        log.exception("执行失败: %s", e)
        raise
    finally:
        if driver:
            driver.quit()
            log.debug("驱动已关闭")


if __name__ == "__main__":
    main()
