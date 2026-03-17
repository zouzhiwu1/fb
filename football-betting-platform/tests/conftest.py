# -*- coding: utf-8 -*-
"""pytest 配置：测试时使用 ≥32 字节的 JWT 密钥，避免 InsecureKeyLengthWarning。"""
import os

# 在 import config / app 之前设置，否则 config 已缓存旧密钥
if len(os.environ.get("JWT_SECRET_KEY", "")) < 32:
    os.environ["JWT_SECRET_KEY"] = (
        "test-secret-key-at-least-32-bytes-long-for-pytest"
    )
