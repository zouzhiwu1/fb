#!/usr/bin/env bash
# 安装/更新 systemd 单元（由 start_linux.sh 在首次部署时自动调用；也可手动 sudo 执行）。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_NAME="fb-platform"
TEMPLATE="${SCRIPT_DIR}/${SERVICE_NAME}.service.example"
TARGET="/etc/systemd/system/${SERVICE_NAME}.service"
WORK_ROOT="$(cd "${ROOT}/.." && pwd)"
APP_LOG_DIR="${WORK_ROOT}/fb-log"
DAY="$(date +%Y%m%d)"
APP_LOG="${APP_LOG_DIR}/${DAY}/platform_${DAY}.log"

if ! command -v systemctl >/dev/null 2>&1; then
  echo "未找到 systemctl：本脚本只用于带 systemd 的 Linux（如云服务器），macOS 请勿执行。" >&2
  echo "在 Mac 上请使用项目根目录: ./start_mac.sh（或前台 ./scripts/run.sh）" >&2
  exit 1
fi
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

mkdir -p "$APP_LOG_DIR" "$(dirname "$APP_LOG")"
chmod 755 "$APP_LOG_DIR"

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
sed "s|@INSTALL_ROOT@|${ROOT}|g" "$TEMPLATE" >"$tmp"
install -m 0644 "$tmp" "$TARGET"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo ""
echo "=== fb-platform 已安装并重启 ==="
echo "业务日志:  $APP_LOG_DIR/YYYYMMDD/platform_YYYYMMDD.log  （当天示例: $APP_LOG）"
echo "看今天日志: tail -f ${APP_LOG}"
echo "日常重启请: ${ROOT}/start_linux.sh"
echo "仅当改了单元模板或项目路径变了再: sudo ${ROOT}/scripts/install-systemd.sh"
echo "状态（可选）: systemctl status ${SERVICE_NAME}"
echo ""
