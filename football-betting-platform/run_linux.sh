#!/usr/bin/env bash
# Linux：后台常驻。首次运行会自动安装 systemd 单元（需 sudo），之后仅重启服务。
# 业务日志: <仓库根>/football-betting-log/platform_YYYYMMDD.log
set -euo pipefail
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "当前不是 Linux，macOS 请使用: ./run_mac.sh" >&2
  exit 1
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
LOG_PARENT="$(cd "${ROOT}/.." && pwd)"
LOG_DIR="${LOG_PARENT}/football-betting-log"
DAY="$(date +%Y%m%d)"
PLATFORM_LOG="${LOG_DIR}/platform_${DAY}.log"
SERVICE="football-betting-platform"
UNIT="/etc/systemd/system/${SERVICE}.service"

mkdir -p "$LOG_DIR"

if [[ ! -x "$PY" ]]; then
  echo "未找到 ${PY}。请先:" >&2
  echo "  cd \"${ROOT}\" && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

_nohup_fallback() {
  echo "未检测到 systemd，使用 nohup 后台启动（关 SSH 仍可能运行，但不如 systemd 稳）。"
  PID_FILE="${ROOT}/.platform.pid"
  if [[ -f "$PID_FILE" ]]; then
    old="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${old:-}" ]] && kill -0 "$old" 2>/dev/null; then
      echo "停止已有进程 PID=${old} ..."
      kill "$old" 2>/dev/null || true
      sleep 1
    fi
  fi
  nohup "$PY" "${ROOT}/run.py" >/dev/null 2>&1 &
  echo $! >"$PID_FILE"
  echo "已在后台启动，PID=$(cat "$PID_FILE")"
  echo "业务日志: ${PLATFORM_LOG}"
}

if command -v systemctl >/dev/null 2>&1; then
  if [[ ! -f "$UNIT" ]]; then
    echo "首次运行：安装 systemd 服务（需要 sudo，仅需一次）..."
    sudo "${ROOT}/scripts/install-systemd.sh"
  else
    echo "重启 systemd 服务 ${SERVICE} ..."
    EUID_="${EUID:-$(id -u)}"
    if [[ "$EUID_" -ne 0 ]]; then
      sudo systemctl restart "$SERVICE"
    else
      systemctl restart "$SERVICE"
    fi
  fi
  echo "业务日志: ${PLATFORM_LOG}"
  echo "状态（可选）: sudo systemctl status ${SERVICE}"
else
  _nohup_fallback
fi
