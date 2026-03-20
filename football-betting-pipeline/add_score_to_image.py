# -*- coding: utf-8 -*-
"""
将完场比分写入报告图片。
以 REPORT_DIR/{YYYYMMDD}/ 目录下的曲线图（{主队}_VS_{客队}.png）为基准，解析每张图的主客队，
在 final_{YYYYMMDD}.csv 中按队名模糊匹配（忽略 [春1]、[11]、(中) 等后缀），查找到比分后写入图片。

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

from config import REPORT_DIR, WORK_SPACE

# 日志中路径相对于 pipeline 父目录为根，显示为 football-betting-data/、football-betting-report/ 等（无外层 football-betting/ 前缀）
def _display_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None


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


def _find_font(size: int):
    """优先使用系统中文字体，否则回退到默认。"""
    if not ImageFont:
        return None
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def draw_score_on_image(image_path: str, score_text: str, log, display_path: str = None) -> bool:
    """
    在图片上「预测结果」下一行绘制「实际比分：x-x」，左对齐（与 plot_car 的年度/预测结果一致），覆盖保存。
    score_text: 如 "2-1" 或 "1 : 0"，会显示为「实际比分：2-1」
    display_path: 日志中显示的路径（如 football-betting-report/20260313/xxx.png），未传则用相对 WORK_SPACE 的路径。
    """
    if not Image or not ImageDraw:
        log.error("未安装 Pillow，无法写入图片")
        return False
    try:
        img = Image.open(image_path).convert("RGBA")
    except Exception as e:
        try:
            _rel = os.path.relpath(image_path, _display_root())
        except Exception:
            _rel = image_path
        log.warning("无法打开图片 %s: %s", _rel, e)
        return False
    w, h = img.size
    # 与 plot_car 左上角「预测结果」一致：fontsize=11，图高 10 英寸、dpi=200 时约 11/72*200≈30px
    font_size = max(14, int(h * 0.015))
    font = _find_font(font_size)
    draw = ImageDraw.Draw(img)
    label = f"实际比分：{score_text}"
    # 紧贴预测结果下一行，无空白。plot_car 两行(年度/预测结果)底部约在 0.93 fig，对应距顶约 7%
    x = int(w * 0.02)
    y = int(h * 0.072)
    tw = len(label) * (font_size if font else 8)
    if font:
        try:
            bbox = draw.textbbox((0, 0), label, font=font)
            tw = bbox[2] - bbox[0]
        except (AttributeError, TypeError):
            pass
    padding = 4
    if font:
        draw.rectangle([x - padding, y - padding, x + tw + padding, y + font_size + padding], fill=(255, 255, 255, 220))
        draw.text((x, y), label, fill=(0, 0, 0), font=font)
    else:
        draw.text((x, y), label, fill=(0, 0, 0))
    img.save(image_path, "PNG")
    if display_path is None:
        try:
            display_path = os.path.relpath(image_path, _display_root()).replace(os.sep, "/")
        except Exception:
            display_path = os.path.basename(image_path)
    log.info("已写入比分到: %s", display_path)
    return True


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

    # 以 {YYYYMMDD} 目录下的曲线图为基准，逐张解析主客队，在 CSV 中模糊匹配后写入比分
    images = [f for f in os.listdir(report_dir) if f.endswith(".png") and "_VS_" in f]
    done = 0
    no_match = 0
    for filename in images:
        img_home, img_away = _parse_match_from_image_filename(filename)
        if not img_home or not img_away:
            log.debug("无法解析文件名: %s", filename)
            continue
        key = (_normalize_team_for_match(img_home), _normalize_team_for_match(img_away))
        score = score_by_match.get(key)
        if not score:
            log.debug("未找到匹配的完场记录: %s", filename)
            no_match += 1
            continue
        image_path = os.path.join(report_dir, filename)
        try:
            display_path = os.path.relpath(image_path, _display_root()).replace(os.sep, "/")
        except Exception:
            display_path = filename
        if draw_score_on_image(image_path, score, log, display_path=display_path):
            done += 1
    log.info("共处理 %d 张图片（目录内曲线图 %d 张，%d 张未匹配到完场记录）", done, len(images), no_match)


if __name__ == "__main__":
    main()
