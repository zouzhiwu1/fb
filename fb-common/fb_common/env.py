# -*- coding: utf-8 -*-
import os


def load_dotenv_stack(service_root: str) -> None:
    """
    与 platform/partner 原配置一致：仓库根 .env → 子项目根 .env → 当前工作目录。
    service_root：一般为内含 config.py 的目录绝对路径（例如 .../fb-platform）。
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = os.path.abspath(service_root)
    repo_root = os.path.dirname(root)
    load_dotenv(os.path.join(repo_root, ".env"))
    load_dotenv(os.path.join(root, ".env"))
    load_dotenv()
