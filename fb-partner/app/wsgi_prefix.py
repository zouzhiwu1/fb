# -*- coding: utf-8 -*-
"""
当浏览器访问带路径前缀的 URL（如 /partner/admin）而 Flask 路由注册在根路径时，
在 WSGI 层剥掉前缀，使路由与无反代「去前缀」时一致。

反代若已去掉前缀再转发，则请求 PATH_INFO 为 /admin/login，本中间件不会改写。
"""


class PartnerPathPrefixMiddleware:
    def __init__(self, app, prefix: str):
        self.app = app
        self.prefix = (prefix or "").rstrip("/")

    def __call__(self, environ, start_response):
        if not self.prefix:
            return self.app(environ, start_response)
        path = environ.get("PATH_INFO") or "/"
        if path == self.prefix or path.startswith(self.prefix + "/"):
            new_environ = environ.copy()
            rest = path[len(self.prefix) :]
            new_environ["PATH_INFO"] = rest if rest else "/"
            script = environ.get("SCRIPT_NAME", "") or ""
            new_environ["SCRIPT_NAME"] = script + self.prefix
            return self.app(new_environ, start_response)
        return self.app(environ, start_response)
