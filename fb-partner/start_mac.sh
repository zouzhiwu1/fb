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
PIP="${ROOT}/.venv/bin/pip"
REQ_FILE="${ROOT}/requirements.txt"
REQ_STAMP="${ROOT}/.venv/.requirements.sha256"
LOG_PARENT="$(cd "${ROOT}/.." && pwd)"
LOG_DIR="${LOG_PARENT}/fb-log"
DAY="$(date +%Y%m%d)"
PARTNER_LOG="${LOG_DIR}/${DAY}/partner_${DAY}.log"

mkdir -p "$(dirname "$PARTNER_LOG")"
export PORT="${PORT:-5002}"

if [[ ! -x "$PY" ]]; then
  echo "未发现虚拟环境，正在创建 .venv ..."
  python3 -m venv .venv
fi

if [[ ! -x "$PIP" ]]; then
  echo "未发现 pip，正在修复虚拟环境 ..."
  "$PY" -m ensurepip --upgrade
fi

need_install=0
if [[ ! -f "$REQ_STAMP" ]]; then
  need_install=1
elif [[ -f "$REQ_FILE" ]]; then
  current_sha="$(shasum -a 256 "$REQ_FILE" | awk '{print $1}')"
  installed_sha="$(cat "$REQ_STAMP" 2>/dev/null || true)"
  if [[ "$current_sha" != "$installed_sha" ]]; then
    need_install=1
  fi
fi

if [[ "$need_install" -eq 1 ]]; then
  echo "正在安装/更新依赖 ..."
  "$PIP" install -r "$REQ_FILE"
  shasum -a 256 "$REQ_FILE" | awk '{print $1}' > "$REQ_STAMP"
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
