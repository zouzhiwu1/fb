# -*- coding: utf-8 -*-
import logging
import os

from flask import Flask, jsonify, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

from config import (
    CURVES_REQUIRE_ACTIVE_MEMBERSHIP,
    DailyPlatformFileHandler,
    JWT_SECRET_KEY,
    LOG_DIR,
    LOG_FILE,
)

db = SQLAlchemy()


def create_app():
    app = Flask(__name__, template_folder="templates")

    # 日志：挂到 root，werkzeug 访问日志与 app 日志都会进 fb-log/platform_YYYYMMDD.log
    # （仅挂 app.logger 时 werkzeug 不打进文件，易出现 0 字节）
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        root = logging.getLogger()
        if not any(getattr(h, "_fb_platform_handler", False) for h in root.handlers):
            if LOG_FILE:
                file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            else:
                file_handler = DailyPlatformFileHandler(LOG_DIR, encoding="utf-8")
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            file_handler._fb_platform_handler = True
            root.addHandler(file_handler)
            root.setLevel(logging.INFO)
        logging.getLogger("werkzeug").setLevel(logging.INFO)
        app.logger.setLevel(logging.INFO)
    except OSError:
        pass
    import config as _cfg

    app.config["SQLALCHEMY_DATABASE_URI"] = _cfg.DATABASE_URL
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = _cfg.get_sqlalchemy_engine_options()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = JWT_SECRET_KEY
    app.config["CURVES_REQUIRE_ACTIVE_MEMBERSHIP"] = CURVES_REQUIRE_ACTIVE_MEMBERSHIP
    CORS(app)

    db.init_app(app)

    from app.auth import auth_bp
    from app.curves import curves_bp
    from app.membership_api import membership_bp
    from app.pay_api import pay_bp
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(curves_bp, url_prefix="/api/curves")
    app.register_blueprint(membership_bp, url_prefix="/api/membership")
    app.register_blueprint(pay_bp, url_prefix="/api/pay")

    @app.route("/")
    def index():
        return redirect(url_for("login_page"))

    @app.route("/login")
    def login_page():
        return render_template("login.html")

    @app.route("/register")
    def register_page():
        return render_template("register.html")

    @app.route("/home")
    def home_page():
        return render_template("home.html")

    @app.route("/curves")
    def curves_page():
        return render_template("curves.html")

    @app.route("/account")
    def account_page():
        return render_template("account.html")

    @app.route("/membership")
    def membership_page():
        return render_template("membership.html")

    @app.route("/recharge")
    def recharge_page():
        return render_template("recharge.html")

    @app.route("/recharge-records")
    def recharge_records_page():
        return render_template("recharge_records.html")

    # 勿写 import app.models：在函数内会把局部名 app 绑定成包对象，覆盖 Flask 实例。
    from app import models  # noqa: F401  # 注册全部模型，供 db.create_all() 建表

    with app.app_context():
        db.create_all()

    # 保证 500 时也返回 JSON，避免前端收到 HTML 显示「网络错误」
    @app.errorhandler(500)
    def handle_500(e):
        app.logger.exception("服务器内部错误")
        return jsonify({
            "ok": False,
            "message": "服务器错误，请稍后重试。若为首次部署，请执行 fb-platform/scripts/add_membership_tables.sql 并重启。",
        }), 500

    logging.info(
        "fb-platform 应用已加载（后续 HTTP 访问由 werkzeug 记入本日志）"
    )
    return app
