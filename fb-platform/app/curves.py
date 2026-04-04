# -*- coding: utf-8 -*-
"""
曲线图查询：按日期和球队名搜索并展示 pipeline 生成的曲线图。
数据来源：CURVE_IMAGE_DIR 下各日期目录中的 {主队}_VS_{客队}.png（与 plot_car.py 生成格式一致）
权限：按《会员系统设计书》§3.3 — 会员可查全部；非会员仅当该场不在 evaluation_matches（未在综合评估中）时可查。
"""
import os
import re
from urllib.parse import unquote

from flask import Blueprint, current_app, send_from_directory, jsonify, request

from app.membership import is_member, is_match_under_evaluation

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

# 与 plot_car.py 一致：文件名为 主队_VS_客队.png（无「_曲线」）
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
    """按日期和球队名搜索曲线图。参数: date=YYYYMMDD, team=可选。需登录；非会员仅可查历史综合评估。"""
    date = (request.args.get("date") or "").strip()
    team = (request.args.get("team") or "").strip()
    if not date or not re.match(r"^\d{8}$", date):
        return jsonify({"error": "请提供有效日期 YYYYMMDD", "items": []})
    user_id = _get_user_id_from_request()
    if user_id is None:
        return jsonify(
            {
                "ok": False,
                "message": "账号已在其他设备登录或登录已过期，请重新登录",
                "items": [],
            }
        ), 401
    member = is_member(user_id)
    # 可选策略：过期即不能看任何曲线（与默认「非会员可看完场/历史」不同）
    if current_app.config.get("CURVES_REQUIRE_ACTIVE_MEMBERSHIP") and not member:
        return jsonify({
            "date": date,
            "items": [],
            "member_only": True,
            "message": "查看曲线图需要当前有效的会员身份。您的会员已过期或未开通。",
        })
    base = _get_curve_dir()
    dir_path = os.path.join(base, date)
    logger = getattr(current_app, "logger", None)
    if not os.path.isdir(dir_path):
        if logger:
            logger.warning("曲线图目录不存在: %s（CURVE_IMAGE_DIR=%s）", dir_path, base)
        return jsonify({"date": date, "items": []})
    items = []
    matched_team_count = 0
    skipped_under_evaluation = 0
    for fn in os.listdir(dir_path):
        if not fn.endswith(CURVE_SUFFIX):
            continue
        parsed = _parse_curve_filename(fn)
        if not parsed:
            continue
        home, away = parsed
        if not _match_team(team, home, away):
            continue
        matched_team_count += 1
        if not member and is_match_under_evaluation(date, home, away):
            skipped_under_evaluation += 1
            continue
        items.append({
            "date": date,
            "home": home,
            "away": away,
            "filename": fn,
        })
    if not items and logger:
        if matched_team_count > 0 and skipped_under_evaluation > 0:
            logger.info(
                "曲线图搜索：磁盘上有匹配球队的结果，但非会员且均在 evaluation_matches（综合评估中）"
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
    payload = {"date": date, "items": items}
    # 有文件且队名对得上，但全部被「评估中」权限挡住时，避免用户误以为「没有这张图」
    if (
        not items
        and matched_team_count > 0
        and skipped_under_evaluation > 0
        and not member
    ):
        payload["member_only"] = True
        payload["message"] = (
            f"已找到 {matched_team_count} 场与「{team}」相关的曲线图，但该日期场次仍在综合评估中，"
            "按规则仅会员可查看。开通会员后即可浏览。"
        )
    return jsonify(payload)


@curves_bp.route("/img/<date>/<path:filename>")
def serve_image(date, filename):
    """按日期和文件名提供曲线图图片。当前综合评估需会员，非会员返回 403。"""
    if not re.match(r"^\d{8}$", date):
        return "", 404
    user_id = _get_user_id_from_request()
    if user_id is None:
        return jsonify(
            {"ok": False, "message": "账号已在其他设备登录或登录已过期，请重新登录"}
        ), 401
    if current_app.config.get("CURVES_REQUIRE_ACTIVE_MEMBERSHIP") and not is_member(user_id):
        return jsonify({
            "ok": False,
            "message": "查看曲线图需要当前有效的会员身份。您的会员已过期或未开通。",
        }), 403
    filename = unquote(filename)
    if ".." in filename or not filename.endswith(CURVE_SUFFIX):
        return "", 404
    parsed = _parse_curve_filename(filename)
    if not parsed:
        return "", 404
    home, away = parsed
    if not is_member(user_id) and is_match_under_evaluation(date, home, away):
        return jsonify({
            "ok": False,
            "message": "只有会员才能查看正在综合评估中的比赛",
        }), 403
    base = _get_curve_dir()
    dir_path = os.path.join(base, date)
    path = os.path.join(dir_path, filename)
    if not os.path.isfile(path):
        return "", 404
    return send_from_directory(dir_path, filename, mimetype="image/png")
