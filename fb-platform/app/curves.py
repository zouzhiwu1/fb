# -*- coding: utf-8 -*-
"""
曲线图查询：按日期和球队名搜索并展示 pipeline 生成的曲线图。
数据来源：CURVE_IMAGE_DIR 下各日期目录中的 {主队}_VS_{客队}.png；完场后可重命名为
{主队}[主队比分]_VS_{客队}[客队比分].png。
权限：按《会员系统设计书》§3.3 — 会员可查全部；非会员仅可查完场比赛。
完场判定以图片文件名为准：{主队}[主队比分]_VS_{客队}[客队比分].png 表示完场。
"""
import os
import re
from urllib.parse import unquote

from flask import Blueprint, current_app, send_from_directory, jsonify, request

from app.membership import is_member

curves_bp = Blueprint("curves", __name__)

# 与 auth 中一致：从 Header 解析 token 得到 user_id（未登录返回 None）
def _get_user_id_from_request():
    try:
        from app.auth import _verify_token
        auth = request.headers.get("Authorization") or ""
        if not auth.startswith("Bearer "):
            return None
        token = auth[7:].strip()
        return _verify_token(token)
    except Exception:
        return None

# 与 plot_car.py 一致：文件名为 主队_VS_客队.png（无「_曲线」）；完场后允许追加末尾比分 [n]。
CURVE_SUFFIX = ".png"
VS_SEP = "_VS_"


def _get_curve_dir():
    from config import CURVE_IMAGE_DIR
    return CURVE_IMAGE_DIR


def _parse_curve_filename(basename: str):
    """从文件名解析出 (主队, 客队)，若不是曲线图（*_VS_*.png）返回 None。"""
    if not basename.endswith(CURVE_SUFFIX):
        return None
    name = basename[: -len(CURVE_SUFFIX)]
    if VS_SEP not in name:
        return None
    parts = name.split(VS_SEP, 1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else None


def _strip_score_suffix(team_name: str) -> str:
    """去掉完场流程追加的末尾比分，如 `马里迪莫[1]` -> `马里迪莫`。"""
    return re.sub(r"\[\d+\]$", "", (team_name or "").strip()).strip()


def _score_suffix(team_name: str) -> str | None:
    """返回文件名队名末尾的比分数字；没有则表示未完场。"""
    m = re.search(r"\[(\d+)\]$", (team_name or "").strip())
    return m.group(1) if m else None


def _curve_item_from_filename(date: str, filename: str, home_raw: str, away_raw: str) -> dict:
    """根据文件名生成前端展示项；是否完场完全由文件名是否带比分后缀判断。"""
    home = _strip_score_suffix(home_raw)
    away = _strip_score_suffix(away_raw)
    home_score = _score_suffix(home_raw)
    away_score = _score_suffix(away_raw)
    finished = home_score is not None and away_score is not None
    title = (
        f"{home}[{home_score}] : {away}[{away_score}]"
        if finished
        else f"{home} : {away}"
    )
    return {
        "date": date,
        "home": home,
        "away": away,
        "home_score": home_score,
        "away_score": away_score,
        "finished": finished,
        "title": title,
        "filename": filename,
    }


def _is_finished_by_filename(home_raw: str, away_raw: str) -> bool:
    """是否完场只看文件名：主客队两侧都带末尾比分 [数字] 才算完场。"""
    return _score_suffix(home_raw) is not None and _score_suffix(away_raw) is not None


def _match_team(keyword: str, home: str, away: str) -> bool:
    if not keyword or not keyword.strip():
        return True
    k = keyword.strip()
    return k in home or k in away


@curves_bp.route("/dates")
def api_dates():
    """列出曲线图目录下所有日期目录（YYYYMMDD）。"""
    base = _get_curve_dir()
    if not os.path.isdir(base):
        return jsonify({"dates": []})
    dirs = []
    for name in os.listdir(base):
        path = os.path.join(base, name)
        if os.path.isdir(path) and re.match(r"^\d{8}$", name):
            dirs.append(name)
    dirs.sort(reverse=True)
    return jsonify({"dates": dirs})


@curves_bp.route("/search")
def api_search():
    """按日期和球队名搜索曲线图。会员可查全部；游客/非会员仅可查文件名带比分的完场图。"""
    date = (request.args.get("date") or "").strip()
    team = (request.args.get("team") or "").strip()
    if not date or not re.match(r"^\d{8}$", date):
        return jsonify({"error": "请提供有效日期 YYYYMMDD", "items": []})
    user_id = _get_user_id_from_request()
    member = bool(user_id is not None and is_member(user_id))
    base = _get_curve_dir()
    dir_path = os.path.join(base, date)
    logger = getattr(current_app, "logger", None)
    if not os.path.isdir(dir_path):
        if logger:
            logger.warning("曲线图目录不存在: %s（CURVE_IMAGE_DIR=%s）", dir_path, base)
        return jsonify({"date": date, "items": []})
    items = []
    matched_team_count = 0
    skipped_unfinished = 0
    for fn in os.listdir(dir_path):
        if not fn.endswith(CURVE_SUFFIX):
            continue
        parsed = _parse_curve_filename(fn)
        if not parsed:
            continue
        home_raw, away_raw = parsed
        home = _strip_score_suffix(home_raw)
        away = _strip_score_suffix(away_raw)
        if not _match_team(team, home, away):
            continue
        matched_team_count += 1
        item = _curve_item_from_filename(date, fn, home_raw, away_raw)
        # 同一天可能同时存在已完场和未完场的图片。游客/非会员只过滤当前这张未完场图，
        # 不能因为前面某张未完场就影响后续已完场图片。
        if not member and not item["finished"]:
            skipped_unfinished += 1
            continue
        items.append(item)
    if not items and logger:
        if matched_team_count > 0 and skipped_unfinished > 0:
            logger.info(
                "曲线图搜索：磁盘上有匹配球队的结果，但非会员且文件名未带完场比分"
                " date=%s team=%s 匹配=%d 目录=%s",
                date,
                team,
                matched_team_count,
                dir_path,
            )
        else:
            count_png = sum(1 for f in os.listdir(dir_path) if f.endswith(CURVE_SUFFIX))
            logger.info("曲线图搜索无匹配: date=%s team=%s 目录=%s 该日共 %d 个 .png", date, team, dir_path, count_png)
    items.sort(key=lambda x: (x["home"], x["away"]))
    payload = {
        "date": date,
        "items": items,
        "matched_count": matched_team_count,
        "skipped_unfinished": skipped_unfinished,
    }
    # 有文件且队名对得上，但全部被「评估中」权限挡住时，避免用户误以为「没有这张图」
    if (
        not items
        and matched_team_count > 0
        and skipped_unfinished > 0
        and not member
    ):
        payload["member_only"] = True
        action = "请先注册登录" if user_id is None else "请开通会员后查看"
        payload["message"] = (
            f"已找到 {matched_team_count} 场与「{team}」相关的曲线图，但文件名尚未带完场比分，"
            f"未完场比赛仅会员可查看，{action}。"
        )
    return jsonify(payload)


@curves_bp.route("/img/<date>/<path:filename>")
def serve_image(date, filename):
    """按日期和文件名提供曲线图图片。会员可查全部；游客/非会员仅可查文件名带比分的完场图。"""
    if not re.match(r"^\d{8}$", date):
        return "", 404
    user_id = _get_user_id_from_request()
    member = bool(user_id is not None and is_member(user_id))
    filename = unquote(filename)
    if ".." in filename or not filename.endswith(CURVE_SUFFIX):
        return "", 404
    parsed = _parse_curve_filename(filename)
    if not parsed:
        return "", 404
    home, away = parsed
    if not member and not _is_finished_by_filename(home, away):
        action = "请先注册登录" if user_id is None else "请开通会员后查看"
        return jsonify({
            "ok": False,
            "message": f"未完场比赛仅会员可查看，{action}。",
        }), 403
    base = _get_curve_dir()
    dir_path = os.path.join(base, date)
    path = os.path.join(dir_path, filename)
    if not os.path.isfile(path):
        return "", 404
    return send_from_directory(dir_path, filename, mimetype="image/png")
