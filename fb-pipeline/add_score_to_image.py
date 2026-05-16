# -*- coding: utf-8 -*-
"""
将完场比分写入报告图片文件名。
以 REPORT_DIR/{YYYYMMDD}/ 目录下的曲线图（{主队}_VS_{客队}.png）为基准，解析每张图的主客队，
在 final_{YYYYMMDD}.csv 中按队名模糊匹配（忽略 [春1]、[11]、(中) 等后缀），查找到比分后
将图片重命名为 {主队}[主队比分]_VS_{客队}[客队比分].png。

用法:
  python add_score_to_image.py <YYYYMMDD>
  python add_score_to_image.py <path_to_final_YYYYMMDD.csv>

若使用日期：报告目录 REPORT_DIR/YYYYMMDD/，CSV 为 REPORT_DIR/YYYYMMDD/final_YYYYMMDD.csv；
若使用路径：CSV 所在目录为报告目录。CSV 列：home, away, score。
"""
import csv
import logging
import os
import re
import sys

from config import REPORT_DIR

# 日志中路径相对于 pipeline 父目录为根，显示为 fb-data/、fb-report/ 等（无外层 fb/ 前缀）
def _display_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

def _safe_filename(name: str) -> str:
    """与 plot_car 一致：去掉或替换文件名非法字符。"""
    s = re.sub(r'[<>:"/\\|?*]', "_", (name or "").strip())
    return s or "match"


def _normalize_team_for_match(name: str) -> str:
    """统一主客队名称用于匹配：去掉 [春1]、[11]、(中) 等后缀，便于 CSV 与图片文件名对应。"""
    if not name:
        return ""
    s = re.sub(r'\[[^\]]*\]', "", name)
    s = re.sub(r'\([^\)]*\)', "", s)
    return s.strip() or name


def _strip_score_suffix(name: str) -> str:
    """去掉本脚本追加的末尾比分，如 `马里迪莫[1]` -> `马里迪莫`，便于重复执行。"""
    return re.sub(r"\[\d+\]$", "", (name or "").strip()).strip()


def _parse_score(score_text: str):
    """解析 `2-1` / `2 : 1` / `2：1` 等比分，返回 (home_score, away_score)。"""
    m = re.search(r"(\d+)\s*[-:：]\s*(\d+)", score_text or "")
    if not m:
        return None
    return m.group(1), m.group(2)


def rename_image_with_score(
    image_path: str,
    home: str,
    away: str,
    score_text: str,
    log,
    display_path: str = None,
) -> bool:
    """
    将 `主队_VS_客队.png` 重命名为 `主队[主队比分]_VS_客队[客队比分].png`。
    若重复执行，先去掉已有末尾比分后再生成目标名。
    """
    parsed_score = _parse_score(score_text)
    if not parsed_score:
        log.warning("无法解析比分，跳过重命名: %s score=%s", os.path.basename(image_path), score_text)
        return False
    hs, aws = parsed_score
    clean_home = _strip_score_suffix(home)
    clean_away = _strip_score_suffix(away)
    new_filename = f"{clean_home}[{hs}]_VS_{clean_away}[{aws}].png"
    new_path = os.path.join(os.path.dirname(image_path), new_filename)
    if os.path.abspath(image_path) == os.path.abspath(new_path):
        if display_path is None:
            display_path = _rel_path(image_path)
        log.info("比分已在文件名中: %s", display_path)
        return True
    if os.path.exists(new_path):
        os.remove(new_path)
    os.rename(image_path, new_path)
    log.info("已按比分重命名: %s -> %s", _rel_path(image_path), _rel_path(new_path))
    return True


def _rel_path(path: str) -> str:
    try:
        return os.path.relpath(path, _display_root()).replace(os.sep, "/")
    except Exception:
        return os.path.basename(path)


def _parse_match_from_image_filename(basename: str):
    """从曲线图文件名解析出 (主队, 客队)。文件名格式：{主队}_VS_{客队}.png。"""
    if not basename.endswith(".png") or "_VS_" not in basename:
        return None, None
    s = basename[:-len(".png")]
    parts = s.rsplit("_VS_", 1)
    if len(parts) != 2:
        return None, None
    return parts[0].strip(), parts[1].strip()

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log = logging.getLogger("add_score_to_image")

    args = sys.argv[1:]
    if len(args) != 1:
        log.error("用法: python add_score_to_image.py <YYYYMMDD> 或 python add_score_to_image.py <path_to_final_*.csv>")
        sys.exit(1)
    arg = args[0].strip()

    csv_path = None
    report_dir = None
    if len(arg) == 8 and arg.isdigit():
        report_dir = os.path.join(REPORT_DIR, arg)
        csv_path = os.path.join(report_dir, f"final_{arg}.csv")
        if not os.path.isfile(csv_path):
            try:
                _rel = os.path.relpath(csv_path, _display_root())
            except Exception:
                _rel = csv_path
            log.error("未找到完场 CSV（final_YYYYMMDD.csv）: %s", _rel)
            sys.exit(1)
    elif os.path.isfile(arg):
        csv_path = arg
        report_dir = os.path.dirname(csv_path)
    else:
        log.error("参数应为 8 位日期 YYYYMMDD 或 CSV 文件路径")
        sys.exit(1)

    if not report_dir or not os.path.isdir(report_dir):
        try:
            _rel = os.path.relpath(report_dir, _display_root()) if report_dir else report_dir
        except Exception:
            _rel = report_dir
        log.error("报告目录不存在: %s", _rel)
        sys.exit(1)

    # 以 CSV 为数据源：规范化队名 (去掉 [春1]、[11]、(中) 等) 作为 key，取第一条匹配的 score
    score_by_match = {}
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            home = (row.get("home") or "").strip()
            away = (row.get("away") or "").strip()
            score = (row.get("score") or "").strip()
            if not home or not away:
                continue
            key = (_normalize_team_for_match(home), _normalize_team_for_match(away))
            if key not in score_by_match:
                score_by_match[key] = score

    if not score_by_match:
        log.warning("CSV 中无有效记录")
        sys.exit(0)

    # 以 {YYYYMMDD} 目录下的曲线图为基准，逐张解析主客队，在 CSV 中模糊匹配后重命名文件
    images = [f for f in os.listdir(report_dir) if f.endswith(".png") and "_VS_" in f]
    done = 0
    no_match = 0
    for filename in images:
        img_home, img_away = _parse_match_from_image_filename(filename)
        if not img_home or not img_away:
            log.debug("无法解析文件名: %s", filename)
            continue
        key = (
            _normalize_team_for_match(_strip_score_suffix(img_home)),
            _normalize_team_for_match(_strip_score_suffix(img_away)),
        )
        score = score_by_match.get(key)
        if not score:
            log.debug("未找到匹配的完场记录: %s", filename)
            no_match += 1
            continue
        image_path = os.path.join(report_dir, filename)
        display_path = _rel_path(image_path)
        if rename_image_with_score(image_path, img_home, img_away, score, log, display_path=display_path):
            done += 1
    log.info("共处理 %d 张图片重命名（目录内曲线图 %d 张，%d 张未匹配到完场记录）", done, len(images), no_match)


if __name__ == "__main__":
    main()
