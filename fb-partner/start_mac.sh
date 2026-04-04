#!/usr/bin/env bash
# macOS：后台启动 partner 进程（nohup）。业务日志：<仓库根>/fb-log/YYYYMMDD/partner_YYYYMMDD.log
# nohup 合并输出：<仓库根>/fb-log/YYYYMMDD/partner_nohup.log
# 停止：./stop_mac.sh
set -euo pipefail
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "当前不是 macOS，Linux 请使用: ./start_linux.sh" >&2
  exit 1
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
LOG_PARENT="$(cd "${ROOT}/.." && pwd)"
LOG_DIR="${LOG_PARENT}/fb-log"
DAY="$(date +%Y%m%d)"
PARTNER_LOG="${LOG_DIR}/${DAY}/partner_${DAY}.log"

mkdir -p "$(dirname "$PARTNER_LOG")"
export PORT="${PORT:-5002}"

if [[ ! -x "$PY" ]]; then
  echo "未找到 ${PY}。请先:" >&2
  echo "  cd \"${ROOT}\" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
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

nohup env PORT="$PORT" "$PY" "${ROOT}/run.py" >>"${LOG_DIR}/${DAY}/partner_nohup.log" 2>&1 &
echo $! >"$PID_FILE"
echo "已在后台启动 fb-partner，PID=$(cat "$PID_FILE") PORT=$PORT"
echo "业务日志: ${PARTNER_LOG}"
