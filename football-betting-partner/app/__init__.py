# -*- coding: utf-8 -*-
import logging
import os

from flask import Flask, jsonify, redirect, render_template
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

from config import (
    DailyPartnerFileHandler,
    LOG_DIR,
    LOG_FILE,
    PARTNER_JWT_SECRET_KEY,
    partner_application_prefix,
)

db = SQLAlchemy()


def create_app():
    app = Flask(__name__, template_folder="templates")

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        root = logging.getLogger()
        if not any(getattr(h, "_fb_partner_handler", False) for h in root.handlers):
            if LOG_FILE:
                file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            else:
                file_handler = DailyPartnerFileHandler(LOG_DIR, encoding="utf-8")
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            file_handler._fb_partner_handler = True
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
    app.config["SECRET_KEY"] = PARTNER_JWT_SECRET_KEY

    db.init_app(app)
    CORS(app)

    @app.context_processor
    def _partner_template_globals():
        return {"partner_url_prefix": partner_application_prefix()}

    from app.admin_api import partner_admin_bp
    from app.auth_partner import partner_auth_bp
    from app.dashboard import partner_ui_bp

    app.register_blueprint(partner_auth_bp, url_prefix="/api/partner/auth")
    app.register_blueprint(partner_admin_bp)
    app.register_blueprint(partner_ui_bp)

    @app.route("/")
    def index():
        return render_template("home.html")

    @app.route("/login")
    def partner_login_page():
        return render_template("login.html")

    @app.route("/dashboard")
    def partner_dashboard_page():
        return render_template("dashboard.html")

    @app.route("/account")
    def partner_account_page():
        return render_template("agent_account.html")

    @app.route("/promo")
    def partner_promo_page():
        return render_template("agent_promo.html")

    @app.route("/admin/login")
    def admin_login_page():
        return render_template("admin_login.html")

    @app.route("/admin/managers")
    def admin_managers_page():
        return render_template("admin_managers.html")

    @app.route("/admin")
    def admin_root_redirect():
        return redirect(partner_application_prefix() + "/admin/agents")

    @app.route("/admin/agents")
    def admin_agents_list_page():
        return render_template("admin_agents_list.html")

    @app.route("/admin/agents/new")
    def admin_agent_register_page():
        return render_template("admin_agent_register.html")

    @app.route("/admin/agents/<int:agent_id>")
    def admin_agent_view_page(agent_id: int):
        return render_template("admin_agent_view.html", agent_id=agent_id)

    @app.route("/admin/agents/<int:agent_id>/edit")
    def admin_agent_edit_page(agent_id: int):
        return render_template("admin_agent_edit.html", agent_id=agent_id)

    @app.route("/admin/agents/<int:agent_id>/commission")
    def admin_agent_commission_page(agent_id: int):
        return render_template("admin_agent_commission.html", agent_id=agent_id)

    @app.route("/admin/agents/<int:agent_id>/dashboard")
    def admin_agent_board_page(agent_id: int):
        p = partner_application_prefix()
        return redirect(f"{p}/admin/agents/{agent_id}/commission", code=302)

    from app import models  # noqa: F401

    with app.app_context():
        db.create_all()

    @app.errorhandler(500)
    def handle_500(e):
        app.logger.exception("partner 服务器内部错误")
        return jsonify({"ok": False, "message": "服务器错误，请稍后重试。"}), 500

    pfx = partner_application_prefix()
    if pfx:
        from app.wsgi_prefix import PartnerPathPrefixMiddleware

        app.wsgi_app = PartnerPathPrefixMiddleware(app.wsgi_app, pfx)
        logging.info("已启用路径前缀 WSGI 剥离: %s", pfx)

    logging.info("football-betting-partner 已加载")
    return app
