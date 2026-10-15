#!/bin/sh
# 容器入口：准备目录与配置 -> 装定时任务 -> 同时跑 crond 和网页面板
set -e

DC_HOME="${DC_HOME:-/dailycheckin}"
export DC_HOME
CONFIG_DIR="$DC_HOME/config"
CRON_FILE="$DC_HOME/cron/crontab_list.sh"

mkdir -p "$CONFIG_DIR" "$DC_HOME/cron" "$DC_HOME/logs" "$DC_HOME/data"
cd "$DC_HOME"

echo "======================================================"
echo " dailycheckin-compose"
echo "  工作目录 : $DC_HOME"
echo "  面板端口 : ${PANEL_PORT:-8080}"
echo "  时区     : ${TZ:-Asia/Shanghai}"
echo "  口令保护 : $([ -n "$PANEL_TOKEN" ] && echo 已开启 || echo 未开启)"
echo "======================================================"

# 1) 首次启动自动生成空配置与默认定时任务（已存在就一个字符都不动）
python - <<'PY'
import os
from panel import paths, schedule, store

paths.ensure_dirs()
if not os.path.exists(paths.CONFIG_PATH):
    store.write(store.empty_template(), backup=False)
    print("[初始化] 已生成空配置:", paths.CONFIG_PATH)
else:
    print("[初始化] 沿用已有配置:", paths.CONFIG_PATH)

if not os.path.exists(paths.CRON_PATH):
    schedule.write_text(schedule.read_text())
    print("[初始化] 已生成默认定时任务:", paths.CRON_PATH)
else:
    print("[初始化] 沿用已有定时任务:", paths.CRON_PATH)
PY

# 2) 装进 cron（网页上改周期后会由面板自己重装一次）
if command -v crontab >/dev/null 2>&1; then
    crontab "$CRON_FILE" && echo "[初始化] 定时任务已装载"
else
    echo "[初始化] 警告：容器内没有 crontab，定时签到不可用"
fi

# 3) 先起 crond（后台），再把网页面板放在前台
if command -v cron >/dev/null 2>&1; then
    cron -f -L 15 &
    CRON_PID=$!
    echo "[启动] crond pid=$CRON_PID"
    trap 'kill "$CRON_PID" 2>/dev/null || true' TERM INT
else
    echo "[启动] 警告：容器内没有 cron"
fi

echo "[启动] 网页管理面板 http://0.0.0.0:${PANEL_PORT:-8080}"
python -m panel
STATUS=$?

if [ -n "${CRON_PID:-}" ]; then
    kill "$CRON_PID" 2>/dev/null || true
fi
exit "$STATUS"
