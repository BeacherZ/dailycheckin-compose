"""运行时路径与配置项。"""

from __future__ import annotations

import os


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "")
    return value.strip() if value and value.strip() else default


# 容器内工作目录，引擎按 `./config/config.json` 找配置，必须保持一致
# 本地直接 `python -m panel` 时（仓库根目录就是工作目录），自动回落到当前目录
_DEFAULT_HOME = "/dailycheckin"
if not os.path.isdir(_DEFAULT_HOME) and os.path.isdir(os.path.join(os.getcwd(), "panel")):
    _DEFAULT_HOME = os.getcwd()

HOME = _env("DC_HOME", _DEFAULT_HOME)

CONFIG_PATH = _env("DC_CONFIG_PATH", os.path.join(HOME, "config", "config.json"))
CRON_PATH = _env("DC_CRON_PATH", os.path.join(HOME, "cron", "crontab_list.sh"))
LOG_DIR = _env("DC_LOG_DIR", os.path.join(HOME, "logs"))
DATA_DIR = _env("DC_DATA_DIR", os.path.join(HOME, "data"))

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

STATUS_PATH = os.path.join(DATA_DIR, "panel_status.json")
RUNS_PATH = os.path.join(DATA_DIR, "panel_runs.json")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")

HOST = _env("PANEL_HOST", "0.0.0.0")
PORT = int(_env("PANEL_PORT", "8080"))
# 留空表示不校验（默认，适合内网）。填了之后所有 /api 请求都要带这个口令
TOKEN = _env("PANEL_TOKEN", "")
TITLE = _env("PANEL_TITLE", "签到管理面板")
TZ = _env("TZ", "Asia/Shanghai")

MAX_BACKUPS = 30
MAX_RUNS = 20
RUN_TIMEOUT = int(_env("PANEL_RUN_TIMEOUT", "1800"))


def ensure_dirs() -> None:
    for path in (os.path.dirname(CONFIG_PATH), LOG_DIR, DATA_DIR, BACKUP_DIR):
        if path:
            os.makedirs(path, exist_ok=True)
