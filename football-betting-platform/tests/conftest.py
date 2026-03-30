# -*- coding: utf-8 -*-
"""pytest 配置：测试时使用 ≥32 字节的 JWT 密钥，避免 InsecureKeyLengthWarning。"""
import os
import secrets
import tempfile

import pytest

# 在 import config / app 之前设置，否则 config 已缓存旧密钥
if len(os.environ.get("JWT_SECRET_KEY", "")) < 32:
    os.environ["JWT_SECRET_KEY"] = (
        "test-secret-key-at-least-32-bytes-long-for-pytest"
    )
# 测试固定单一日志文件，不写入仓库 football-betting-log
if not os.environ.get("LOG_FILE"):
    os.environ["LOG_FILE"] = os.path.join(
        tempfile.gettempdir(), "football_betting_platform_pytest.log"
    )

@pytest.fixture
def platform_app():
    """带上下文的 Flask 应用（支付等集成测试用）。"""
    from app import create_app, db

    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        yield app


@pytest.fixture
def platform_client(platform_app):
    return platform_app.test_client()


def make_test_user_and_token(platform_app):
    """创建用户并返回 (user_id, token)。"""
    from app import db
    from app.auth import _create_token
    from app.models import User
    from werkzeug.security import generate_password_hash

    with platform_app.app_context():
        phone = f"138{secrets.randbelow(10**8):08d}"
        u = User(
            phone=phone,
            password_hash=generate_password_hash("TestPass1!"),
        )
        db.session.add(u)
        db.session.commit()
        uid = u.id
        tok = _create_token(uid)
    return uid, tok
