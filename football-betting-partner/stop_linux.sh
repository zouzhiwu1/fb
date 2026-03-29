#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${ROOT}/.partner.pid"
if [[ ! -f "$PID_FILE" ]]; then
  echo "无 PID 文件"
  exit 0
fi
old="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -z "${old:-}" ]]; then
  rm -f "$PID_FILE"
  exit 0
fi
if kill -0 "$old" 2>/dev/null; then
  kill "$old" || true
  echo "已停止 PID=$old"
else
  echo "进程已不存在 PID=$old"
fi
rm -f "$PID_FILE"
