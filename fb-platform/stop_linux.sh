#!/usr/bin/env bash
# Linux：若已用 systemd 安装则 stop 服务；否则停止 start_linux.sh nohup 分支写入的进程。启动：./start_linux.sh
set -euo pipefail
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "当前不是 Linux，macOS 请使用: ./stop_mac.sh" >&2
  exit 1
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="fb-platform"
UNIT="/etc/systemd/system/${SERVICE}.service"

if [[ -f "$UNIT" ]] && command -v systemctl >/dev/null 2>&1; then
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    systemctl stop "$SERVICE"
  else
    sudo systemctl stop "$SERVICE"
  fi
  echo "已停止 systemd 服务 ${SERVICE}"
  exit 0
fi

PID_FILE="${ROOT}/.platform.pid"
if [[ ! -f "$PID_FILE" ]]; then
  echo "未发现 systemd 单元 ${UNIT}，也未发现 ${PID_FILE}（可能未在本机用 start_linux.sh 启动）" >&2
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
