#!/usr/bin/env bash
# 根据 RUN_ROOT 生成 LaunchAgent plist，避免在 plist 里写死多处分发路径。
# launchd 不支持 plist 内使用环境变量，因此通过本脚本用单一变量生成 plist。
#
# 用法:
#   RUN_ROOT=/path/to/fb ./gen_launchd_plist.sh
#   或
#   ./gen_launchd_plist.sh /path/to/fb
#
# 输出到 stdout，部署时可重定向到 com.fb.run_real.plist

set -e

RUN_ROOT="${RUN_ROOT:-$1}"
if [[ -z "$RUN_ROOT" ]]; then
  RUN_ROOT="/Users/zhiwuzou/Documents/app/fb"
fi
RUN_ROOT="$(cd "$RUN_ROOT" 2>/dev/null && pwd || echo "$RUN_ROOT")"

PIPELINE="$RUN_ROOT/fb-pipeline"
LOG_DIR="$RUN_ROOT/fb-log"
PYTHON="$PIPELINE/.venv/bin/python"
LOG="$LOG_DIR/fb-run-real.log"
ERR="$LOG_DIR/fb-run-real.err"

cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.fb.run_real</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>run_real.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$PIPELINE</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>4</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>StandardOutPath</key>
  <string>$LOG</string>
  <key>StandardErrorPath</key>
  <string>$ERR</string>
</dict>
</plist>
EOF
