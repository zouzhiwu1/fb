#!/usr/bin/env bash
# 始终用项目内 .venv 启动，避免 SSH 重连后未 activate 导致「No module named flask」。
# 前台运行：关终端会结束进程。需要常驻请执行一次：sudo ./scripts/install-systemd.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "错误: 未找到 ${PY}" >&2
  echo "请先在本目录创建虚拟环境并安装依赖，例如：" >&2
  echo "  cd \"${ROOT}\"" >&2
  echo "  python3.11 -m venv .venv   # 无 python3.11 则换成你机器上的 3.8+" >&2
  echo "  .venv/bin/pip install -U pip setuptools wheel" >&2
  echo "  .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
exec "$PY" "${ROOT}/run.py" "$@"
