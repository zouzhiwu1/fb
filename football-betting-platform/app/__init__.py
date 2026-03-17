# -*- coding: utf-8 -*-
import logging
import os

from flask import Flask, jsonify, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

from config import (
    DATABASE_URL,
    JWT_SECRET_KEY,
    get_sqlalchemy_engine_options,
    LOG_DIR,
    LOG_FILE,
)

db = SQLAlchemy()


def create_app():
    app = Flask(__name__, template_folder="templates")

    # 日志写入 football-betting-log/platform.log
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
    except OSError:
        pass
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = get_sqlalchemy_engine_options()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = JWT_SECRET_KEY
    CORS(app)

    db.init_app(app)

    from app.auth import auth_bp
    from app.curves import curves_bp
    from app.membership_api import membership_bp
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(curves_bp, url_prefix="/api/curves")
    app.register_blueprint(membership_bp, url_prefix="/api/membership")

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

    with app.app_context():
        db.create_all()

    # 保证 500 时也返回 JSON，避免前端收到 HTML 显示「网络错误」
    @app.errorhandler(500)
    def handle_500(e):
        app.logger.exception("服务器内部错误")
        return jsonify({
            "ok": False,
            "message": "服务器错误，请稍后重试。若为首次部署，请执行 football-betting-platform/scripts/add_membership_tables.sql 并重启。",
        }), 500

    return app
