#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
LOG_PARENT="$(cd "${ROOT}/.." && pwd)"
LOG_DIR="${LOG_PARENT}/fb-log"
mkdir -p "$LOG_DIR"
export PORT="${PORT:-5002}"

if [[ ! -x "$PY" ]]; then
  echo "未找到 ${PY}。请先: cd \"${ROOT}\" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

PID_FILE="${ROOT}/.partner.pid"
if [[ -f "$PID_FILE" ]]; then
  old="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${old:-}" ]] && kill -0 "$old" 2>/dev/null; then
    echo "停止已有进程 PID=${old} ..."
    kill "$old" 2>/dev/null || true
    sleep 1
  fi
fi
nohup env PORT="$PORT" "$PY" "${ROOT}/run.py" >>"${LOG_DIR}/partner_nohup.log" 2>&1 &
echo $! >"$PID_FILE"
echo "partner 已在后台启动 PID=$(cat "$PID_FILE") PORT=$PORT"
