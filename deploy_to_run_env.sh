#!/usr/bin/env bash
# 将开发环境（/Users/zhiwuzou/Documents/cursor/fb）中的代码项目
# 同步到运行环境（/Users/zhiwuzou/app/fb），供定时器使用。
# 仅同步代码/文档目录：
#   - fb-doc
#   - fb-pipeline
#   - fb-platform
#   - fb-mobile
# 初次部署时，在运行环境创建数据/日志/报表目录（不会覆盖已有内容）：
#   - fb-data
#   - fb-log
#   - fb-report
# 用法: 在 /Users/zhiwuzou/Documents/cursor/fb 下执行 ./deploy_to_run_env.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEV_ROOT="$SCRIPT_DIR"
RUN_ROOT="/Users/zhiwuzou/app/fb"

CODE_DIRS=(
  fb-pipeline
  fb-platform
  fb-mobile
)

EXCLUDE="--exclude=.git --exclude=__pycache__ --exclude=.pytest_cache --exclude=.coverage --exclude=.venv --exclude=.DS_Store --exclude=*.pyc --exclude=com.fb.run_real.plist"

echo "===> 开发环境: $DEV_ROOT"
echo "===> 运行环境: $RUN_ROOT"
echo ""

# 确保运行环境根目录以及数据/日志/报表目录存在（仅创建，不同步内容）
mkdir -p "$RUN_ROOT"
mkdir -p "$RUN_ROOT/fb-data" "$RUN_ROOT/fb-log" "$RUN_ROOT/fb-report"

# 同步代码项目
for dir in "${CODE_DIRS[@]}"; do
  if [[ -d "$DEV_ROOT/$dir" ]]; then
    echo "同步 $dir ..."
    rsync -a $EXCLUDE "$DEV_ROOT/$dir/" "$RUN_ROOT/$dir/"
  else
    echo "跳过 $dir (开发环境不存在)"
  fi
done

echo ""
echo "===> 更新运行环境 pipeline 依赖..."
RUN_PIPELINE="$RUN_ROOT/fb-pipeline"
if [[ -f "$RUN_PIPELINE/requirements.txt" ]]; then
  if [[ -x "$RUN_PIPELINE/.venv/bin/pip" ]]; then
    "$RUN_PIPELINE/.venv/bin/pip" install -q -r "$RUN_PIPELINE/requirements.txt"
    echo "已执行: pip install -r requirements.txt"
  else
    echo "未找到 .venv，正在创建..."
    /usr/bin/python3 -m venv "$RUN_PIPELINE/.venv"
    "$RUN_PIPELINE/.venv/bin/pip" install -r "$RUN_PIPELINE/requirements.txt"
    echo "已创建 .venv 并安装依赖"
  fi
fi

echo ""
echo "===> 根据 RUN_ROOT 生成 LaunchAgent plist（避免写死路径）..."
if [[ -x "$RUN_PIPELINE/gen_launchd_plist.sh" ]]; then
  RUN_ROOT="$RUN_ROOT" "$RUN_PIPELINE/gen_launchd_plist.sh" > "$RUN_PIPELINE/com.fb.run_real.plist"
  echo "已生成: $RUN_PIPELINE/com.fb.run_real.plist"
else
  echo "未找到 gen_launchd_plist.sh，跳过 plist 生成"
fi

echo ""
echo "部署完成。定时器将执行: $RUN_PIPELINE/run_real.py（即时流程）、$RUN_PIPELINE/run_final.py（完场流程，若已配置）"
echo "如需加载定时器: cp $RUN_PIPELINE/com.fb.run_real.plist ~/Library/LaunchAgents/ && launchctl bootout gui/\$(id -u)/com.fb.run_real 2>/dev/null; launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/com.fb.run_real.plist"
