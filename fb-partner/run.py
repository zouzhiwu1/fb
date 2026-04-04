# -*- coding: utf-8 -*-
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5002"))
    # debug=True 时 500 常返回 HTML 调试页，管理后台 fetch 无法解析 JSON。本地需调试再设 FLASK_DEBUG=1
    _debug = os.environ.get("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=_debug)
