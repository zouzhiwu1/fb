#!/usr/bin/env bash
# 一键安装 systemd 单元并 enable --now（需 root）。关终端、SSH 断线不影响进程。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_NAME="football-betting-platform"
TEMPLATE="${SCRIPT_DIR}/${SERVICE_NAME}.service.example"
TARGET="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "找不到模板: $TEMPLATE" >&2
  exit 1
fi
if [[ ! -x "${ROOT}/.venv/bin/python" ]]; then
  echo "请先创建虚拟环境并安装依赖，再执行本脚本。例如：" >&2
  echo "  cd \"${ROOT}\" && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "安装 systemd 需要 root，请执行:" >&2
  echo "  sudo \"$0\"" >&2
  exit 1
fi

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
sed "s|@INSTALL_ROOT@|${ROOT}|g" "$TEMPLATE" >"$tmp"
install -m 0644 "$tmp" "$TARGET"

systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
echo "已写入 $TARGET 并已启动: $SERVICE_NAME"
echo "查看状态: systemctl status $SERVICE_NAME"
echo "看日志:   journalctl -u $SERVICE_NAME -f"
