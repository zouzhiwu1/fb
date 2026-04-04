# -*- coding: utf-8 -*-
import os
import sys

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "1") not in ("0", "false", "False")
    # nohup / 后台启动时 stdin 非 TTY；debug 默认开启重载易导致子进程退出、端口无人监听
    use_reloader = debug and sys.stdin.isatty()
    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
        use_reloader=use_reloader,
    )
