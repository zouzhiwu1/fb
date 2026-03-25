# -*- coding: utf-8 -*-
"""
批处理3：根据综合评估表（car_{YYYYMMDD}.xlsx）生成欧赔指数曲线图和凯利指数曲线图。
参见 design.md 第 3.3 节。
详细日志写入 logs/plot_car{YYYYMMDDHH}.log。

曲线节点数量由综合评估表中该场比赛的时间点数量决定，不固定。

- 欧赔指数曲线图：主、平、客三条曲线。第 1 个节点为初指（D/E/F 列），
  其余节点为各时间点即时盘（G/H/I 列），节点数 = 1 + 时间点个数。X 轴为「初指」+ 第 C 列各时间点。
- 凯利指数曲线图：主、平、客三条曲线。X 轴为时间（第 C 列），Y 轴为 J/K/L 列，节点数 = 时间点个数。

用法（与 merge_data.py 参数形式保持一致，仅接收两个时间点参数）:
  python plot_car.py <起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>

说明：
- 实际使用的逻辑日期与 merge_data.py 一致：使用起始时间所在日期 YYYYMMDD。
- 输出图片保存在对应报告目录 REPORT_DIR/{YYYYMMDD}/ 下，
  文件名：{主队}_VS_{客队}.png
"""
import datetime
import logging
import math
import os
import re
import sys

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from config import DOWNLOAD_DIR, REPORT_DIR, DEBUG_LOG_DIR, LOG_RETENTION_DAYS
from evaluation_sync import sync_matches_from_car_for_date
from log_cleanup import delete_old_logs

# 综合评估表列：A=主队(0), B=客队(1), C=时间点(2), D～L=数据(3～11)
# 欧赔：初指 D/E/F(3,4,5)，即时 G/H/I(6,7,8)；凯利 J/K/L(9,10,11)
COL_HOME, COL_AWAY, COL_TIME = 0, 1, 2
COL_INIT_MAIN, COL_INIT_DRAW, COL_INIT_AWAY = 3, 4, 5   # 初指 主/平/客
COL_LIVE_MAIN, COL_LIVE_DRAW, COL_LIVE_AWAY = 6, 7, 8   # 即时 主/平/客
COL_KELLY_MAIN, COL_KELLY_DRAW, COL_KELLY_AWAY = 9, 10, 11
CAR_HEADER_ROWS = 2
NUM_COLUMNS = 12


def _setup_logging():
    """配置详细日志到独立文件：plot_car_{YYYYMMDDHH}.log。"""
    os.makedirs(DEBUG_LOG_DIR, exist_ok=True)
    time_suffix = datetime.datetime.now().strftime("%Y%m%d%H")
    log_path = os.path.join(DEBUG_LOG_DIR, f"plot_car_{time_suffix}.log")
    logger = logging.getLogger("plot_car")
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


def _safe_filename(name: str) -> str:
    """去掉或替换文件名非法字符。"""
    s = re.sub(r'[<>:"/\\|?*]', "_", name)
    return s.strip() or "match"


def _annotate_line_points(ax, x_vals, y_vals, color: str, decimal_places: int = 3) -> None:
    """在每个数据点旁标注 y 数值（与曲线同色，略上移避免压住标记）。"""
    for x, y in zip(x_vals, y_vals):
        if pd.isna(y):
            continue
        try:
            yf = float(y)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(yf):
            continue
        ax.annotate(
            f"{yf:.{decimal_places}f}",
            (x, yf),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            fontsize=7,
            color=color,
            clip_on=True,
        )


def _setup_chinese_font():
    """设置 matplotlib 支持中文标签，避免中文显示为方框。"""
    # 桌面常见 + Linux/Docker 常见（需在镜像内 apt 安装 fonts-noto-cjk 或 fonts-wqy-microhei）
    preferred = [
        "PingFang SC",
        "Heiti SC",
        "STHeiti",
        "Songti SC",
        "Hiragino Sans GB",
        "SimHei",
        "Microsoft YaHei",
        "WenQuanYi Micro Hei",
        "WenQuanYi Zen Hei",
        "Noto Sans CJK SC",
        "Noto Serif CJK SC",
        "Source Han Sans SC",
        "Source Han Sans CN",
        "Droid Sans Fallback",
    ]
    all_names = {f.name for f in fm.fontManager.ttflist}
    chosen = None
    for name in preferred:
        if name in all_names:
            chosen = name
            break
    if not chosen:  # pragma: no cover
        for f in fm.fontManager.ttflist:
            n = f.name
            if any(
                k in n
                for k in (
                    "PingFang",
                    "Heiti",
                    "STHeiti",
                    "Noto Sans CJK",
                    "Noto Serif CJK",
                    "WenQuanYi",
                    "Source Han",
                    "Droid Sans Fallback",
                )
            ):
                chosen = n
                break
    # 仍无时不要用「一串不存在的字体名」，否则 matplotlib 会落到 DejaVu 并刷 Glyph missing
    if chosen:
        plt.rcParams["font.sans-serif"] = [chosen]
    else:
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
        logging.getLogger("plot_car").warning(
            "未检测到任何中文字体（建议在 Docker/服务器执行: "
            "apt-get install -y fonts-noto-cjk 或 fonts-wqy-microhei），"
            "图中中文可能显示为方框"
        )
    plt.rcParams["axes.unicode_minus"] = False


def _to_float(series: pd.Series):
    """转为浮点，无效为 NaN。"""
    return pd.to_numeric(series, errors="coerce")


def _time_point_to_mmddhh(time_str: str) -> str:
    """将 YYYYMMDDHH 转为 MMDDHH 显示；不足 10 位则原样返回。"""
    s = (time_str or "").strip()
    if len(s) >= 10 and s[:10].isdigit():
        return s[4:10]  # MMDDHH
    return s


def _compute_prediction(grp: pd.DataFrame, data: pd.DataFrame) -> str:
    """
    预测结果算法（design.md 3.3.3）：
    取最后时间点的即时盘 G/H/I（主/平/客），按值升序排序，
    最小的作为预测结果1，次小的作为预测结果2，组合为「预测结果1预测结果2」如「客平」。
    """
    if len(grp) == 0:
        return "数据不足"
    last = grp.iloc[-1]
    main_val = pd.to_numeric(last[data.columns[COL_LIVE_MAIN]], errors="coerce")
    draw_val = pd.to_numeric(last[data.columns[COL_LIVE_DRAW]], errors="coerce")
    away_val = pd.to_numeric(last[data.columns[COL_LIVE_AWAY]], errors="coerce")
    pairs = [
        (main_val, "主"),
        (draw_val, "平"),
        (away_val, "客"),
    ]
    valid = [(v, label) for v, label in pairs if pd.notna(v)]
    if len(valid) < 2:
        return "数据不足"
    valid.sort(key=lambda x: x[0])
    return valid[0][1] + valid[1][1]


def plot_match_curves(data_dir: str, project_dir: str) -> int:
    """
    读取 REPORT_DIR/{YYYYMMDD}/ 下的 car_{YYYYMMDD}.xlsx，按（主队、客队）分组，
    为每场比赛生成一张图，包含欧赔指数曲线图与凯利指数曲线图两个子图；
    图片写入 REPORT_DIR/{YYYYMMDD}/。
    返回成功生成的图片数量。
    """
    folder_name = os.path.basename(data_dir.rstrip(os.sep))
    report_dir = os.path.join(REPORT_DIR, folder_name)
    car_path = os.path.join(report_dir, f"car_{folder_name}.xlsx")
    if not os.path.isfile(car_path):
        raise FileNotFoundError(f"综合评估表不存在，请先执行 calc_car.py: {car_path}")

    log = logging.getLogger("plot_car")
    df = pd.read_excel(car_path, header=None, engine="openpyxl")
    if len(df) <= CAR_HEADER_ROWS:
        log.info("  [%s] 综合评估表无数据行，跳过", folder_name)
        return 0
    data = df.iloc[CAR_HEADER_ROWS:].copy()
    if data.shape[1] < NUM_COLUMNS:
        raise ValueError(f"综合评估表列数不足 {NUM_COLUMNS} 列: {car_path}")

    data.columns = [f"C{i}" for i in range(data.shape[1])]
    for j in range(COL_INIT_MAIN, NUM_COLUMNS):
        data[data.columns[j]] = _to_float(data[data.columns[j]])

    group_cols = [data.columns[COL_HOME], data.columns[COL_AWAY]]
    count = 0
    for (home, away), grp in data.groupby(group_cols, dropna=False):
        grp = grp.sort_values(by=data.columns[COL_TIME]).reset_index(drop=True)
        if len(grp) == 0:
            continue
        home_str = str(home).strip()
        away_str = str(away).strip()
        prediction = _compute_prediction(grp, data)
        times = grp[data.columns[COL_TIME]].astype(str).tolist()
        # 时间点范围：起始～终止，格式 YYYYMMDDHH；不足 10 位则原样显示
        def _to_yyyymmddhh(t: str) -> str:
            s = (t or "").strip()
            if len(s) >= 10 and s[:10].isdigit():
                return s[:10]
            return s
        start_ts = _to_yyyymmddhh(times[0]) if times else ""
        end_ts = _to_yyyymmddhh(times[-1]) if times else ""
        time_range_str = f"时间点：{start_ts}～{end_ts}" if (start_ts and end_ts) else "时间点：—"
        times_display = [_time_point_to_mmddhh(t) for t in times]

        # 为手机端展示优化：偏竖屏比例、较高分辨率，便于在窄屏上查看
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 10))
        fig.suptitle(f"{home_str} VS {away_str}", fontsize=14, fontweight="bold", y=0.99)
        # 左上角：时间点范围、预测结果（置于主标题与欧赔曲线图之间的空隙，对齐虚线框）
        fig.text(0.02, 0.96, f"{time_range_str}\n预测结果：{prediction}", fontsize=11,
                 verticalalignment="top", horizontalalignment="left",
                 transform=fig.transFigure)

        # ---------- 欧赔指数曲线图 ----------
        # 第 1 节点：初指 D/E/F；第 2～N+1 节点：即时 G/H/I（N = 该场比赛时间点数量，由表决定）
        init_main = grp.iloc[0][data.columns[COL_INIT_MAIN]]
        init_draw = grp.iloc[0][data.columns[COL_INIT_DRAW]]
        init_away = grp.iloc[0][data.columns[COL_INIT_AWAY]]
        x_labels = ["初指"] + times_display
        x_pos = list(range(len(x_labels)))

        y_main = [init_main] + grp[data.columns[COL_LIVE_MAIN]].tolist()
        y_draw = [init_draw] + grp[data.columns[COL_LIVE_DRAW]].tolist()
        y_away = [init_away] + grp[data.columns[COL_LIVE_AWAY]].tolist()

        ax1.plot(x_pos, y_main, "o-", label="主", color="C0", linewidth=2, markersize=5)
        ax1.plot(x_pos, y_draw, "s-", label="平", color="C1", linewidth=2, markersize=5)
        ax1.plot(x_pos, y_away, "^-", label="客", color="C2", linewidth=2, markersize=5)
        _annotate_line_points(ax1, x_pos, y_main, "C0")
        _annotate_line_points(ax1, x_pos, y_draw, "C1")
        _annotate_line_points(ax1, x_pos, y_away, "C2")
        ax1.set_xticks(x_pos)
        ax1.set_xticklabels(x_labels, rotation=45, ha="right")
        ax1.set_ylabel("评估值", fontsize=11)
        ax1.set_title("欧赔指数曲线图", fontsize=12)
        ax1.legend(loc="best")
        ax1.grid(True, alpha=0.3)

        # ---------- 凯利指数曲线图 ----------
        x_kelly = list(range(len(times)))
        ax2.plot(
            x_kelly,
            grp[data.columns[COL_KELLY_MAIN]],
            "o-",
            label="主",
            color="C0",
            linewidth=2,
            markersize=5,
        )
        ax2.plot(
            x_kelly,
            grp[data.columns[COL_KELLY_DRAW]],
            "s-",
            label="平",
            color="C1",
            linewidth=2,
            markersize=5,
        )
        ax2.plot(
            x_kelly,
            grp[data.columns[COL_KELLY_AWAY]],
            "^-",
            label="客",
            color="C2",
            linewidth=2,
            markersize=5,
        )
        ax2.set_xticks(x_kelly)
        ax2.set_xticklabels(times_display, rotation=45, ha="right")
        ax2.set_xlabel("时间点", fontsize=11)
        ax2.set_ylabel("凯利指数", fontsize=11)
        ax2.set_title("凯利指数曲线图", fontsize=12)
        ax2.legend(loc="best")
        ax2.grid(True, alpha=0.3)
        k_main = grp[data.columns[COL_KELLY_MAIN]].tolist()
        k_draw = grp[data.columns[COL_KELLY_DRAW]].tolist()
        k_away = grp[data.columns[COL_KELLY_AWAY]].tolist()
        _annotate_line_points(ax2, x_kelly, k_main, "C0")
        _annotate_line_points(ax2, x_kelly, k_draw, "C1")
        _annotate_line_points(ax2, x_kelly, k_away, "C2")

        plt.tight_layout(rect=[0, 0, 1, 0.86])
        os.makedirs(report_dir, exist_ok=True)
        safe_name = f"{_safe_filename(home_str)}_VS_{_safe_filename(away_str)}.png"
        out_path = os.path.join(report_dir, safe_name)
        # 提升 dpi 以在手机端放大时保持清晰
        plt.savefig(out_path, dpi=200, bbox_inches="tight")
        plt.close()
        # 相对路径以 pipeline 父目录为根，与全项目日志路径风格一致
        _display_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        rel_path = os.path.relpath(out_path, _display_root)
        log.info("已生成: %s", rel_path)
        count += 1

    return count


def _resolve_data_dir(raw_arg: str) -> str:
    """将参数解析为绝对数据目录。"""
    raw_arg = raw_arg.strip().rstrip(os.sep)
    if os.path.isabs(raw_arg):
        return os.path.abspath(raw_arg)
    return os.path.abspath(os.path.join(DOWNLOAD_DIR, raw_arg))


def main():
    log = _setup_logging()
    removed = delete_old_logs(DEBUG_LOG_DIR, days=LOG_RETENTION_DAYS)
    if removed:
        _display_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        rel_removed = [os.path.relpath(p, _display_root) for p in removed]
        log.info("已删除 %d 个超过 %d 天的日志文件: %s", len(removed), LOG_RETENTION_DAYS, rel_removed)
    _setup_chinese_font()

    args = sys.argv[1:]
    if len(args) != 2 or not all(len(a) == 10 and a.isdigit() for a in args):
        log.error(
            "用法: python plot_car.py <起始时间YYYYMMDDHH> <终止时间YYYYMMDDHH>，例如: python plot_car.py 2026031012 2026031111"
        )
        sys.exit(1)

    start_arg, end_arg = args
    logical_date = start_arg[:8]
    log.info(
        "收到时间区间参数 [%s, %s]，将按逻辑日期 %s 生成曲线图。",
        start_arg,
        end_arg,
        logical_date,
    )

    project_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = _resolve_data_dir(logical_date)
    if not os.path.isdir(data_dir):
        log.error("目录不存在: %s", data_dir)
        sys.exit(1)

    total = 0
    try:
        log.info("处理目录: %s", data_dir)
        n = plot_match_curves(data_dir, project_dir)
        total += n
        # §3.4 入表：只要有 car 表就尝试同步（不依赖 n>0，避免「有评估数据但出图 0 张」时不入表）
        car_path = os.path.join(REPORT_DIR, logical_date, f"car_{logical_date}.xlsx")
        if os.path.isfile(car_path):
            try:
                ins = sync_matches_from_car_for_date(logical_date)
                log.info(
                    "evaluation_matches：已执行同步 date=%s REPORT_DIR=%s INSERT rowcount 累计=%s",
                    logical_date,
                    REPORT_DIR,
                    ins,
                )
            except Exception as e:
                log.warning("evaluation_matches 入表失败（不影响出图）: %s", e, exc_info=True)
        else:
            log.warning("evaluation_matches：未找到 %s，跳过入表", car_path)
        if n == 0:
            log.info("本次未生成任何曲线图（n=0），若 car 有数据请检查本日志中的报错。")
    except (FileNotFoundError, ValueError) as e:  # pragma: no cover
        log.error("[%s] %s", data_dir, e)
        sys.exit(1)
    if total:
        log.info("共生成 %d 张曲线图。", total)


if __name__ == "__main__":
    main()
