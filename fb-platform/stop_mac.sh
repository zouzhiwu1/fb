#!/usr/bin/env bash
# macOS：停止由 start_mac.sh（nohup）启动的进程。启动：./start_mac.sh
set -euo pipefail
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "当前不是 macOS，Linux 请使用: ./stop_linux.sh" >&2
  exit 1
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${ROOT}/.platform.pid"
if [[ ! -f "$PID_FILE" ]]; then
  echo "未发现 ${PID_FILE}（可能未用 start_mac.sh 启动，或已停止）" >&2
  exit 1
fi
pid="$(tr -d ' \n' <"$PID_FILE" || true)"
if [[ -z "$pid" ]]; then
  rm -f "$PID_FILE"
  echo "PID 文件为空，已删除 ${PID_FILE}"
  exit 0
fi
if kill -0 "$pid" 2>/dev/null; then
  kill "$pid" || true
  echo "已停止 fb-platform，PID=${pid}"
else
  echo "进程 ${pid} 已不存在，清理 ${PID_FILE}"
fi
rm -f "$PID_FILE"
