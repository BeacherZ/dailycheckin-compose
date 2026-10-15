"""定时任务管理。

面板只维护 crontab 文件里的一段**带标记的区块**，其余行原样保留，
所以用户自己写的其它定时任务不会被覆盖：

    # >>> dailycheckin-compose managed >>>
    0 9 * * * cd /dailycheckin && dailycheckin >> /dailycheckin/logs/dailycheckin.log 2>&1
    # <<< dailycheckin-compose managed <<<
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

from . import paths

BEGIN = "# >>> dailycheckin-compose managed >>>"
END = "# <<< dailycheckin-compose managed <<<"

def _log_clean_line() -> str:
    return f"50 23 */2 * * rm -f {paths.LOG_DIR}/*.log"

DEFAULT_CRON = "0 9 * * *"

PRESETS = [
    {"cron": "0 9 * * *", "label": "每天 09:00"},
    {"cron": "30 0 * * *", "label": "每天 00:30"},
    {"cron": "0 8,20 * * *", "label": "每天 08:00 / 20:00"},
    {"cron": "0 */6 * * *", "label": "每 6 小时"},
    {"cron": "0 9 * * 1-5", "label": "工作日 09:00"},
]

CRON_FIELD = re.compile(r"^[\d*/,\-]+$")
# 匹配「真的在调用 dailycheckin 命令」，避免误认 /dailycheckin/logs 这类路径
CALL_RE = re.compile(r"(?:^|[\s;&|])dailycheckin(?:\s|$)")


def _default_text() -> str:
    """默认 crontab。

    cron 不会继承容器的环境变量，所以 TZ / PATH 要在文件里显式声明，
    否则任务可能按 UTC 时间跑，或者找不到 dailycheckin 命令。
    """
    return (
        f"TZ={paths.TZ}\n"
        f"PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin\n"
        f"DC_HOME={paths.HOME}\n\n"
        "##############默认任务##############\n"
        "# 每 2 天的 23:50 清理一次日志\n"
        f"{_log_clean_line()}\n\n"
        "##############每日签到任务##############\n"
        f"{BEGIN}\n"
        f"{_run_line(DEFAULT_CRON)}\n"
        f"{END}\n"
    )


def _run_line(cron: str) -> str:
    return f"{cron} cd {paths.HOME} && dailycheckin >> {paths.LOG_DIR}/dailycheckin.log 2>&1"


def read_text() -> str:
    if not os.path.exists(paths.CRON_PATH):
        return _default_text()
    with open(paths.CRON_PATH, encoding="utf-8") as f:
        return f.read()


def write_text(text: str) -> None:
    paths.ensure_dirs()
    os.makedirs(os.path.dirname(paths.CRON_PATH), exist_ok=True)
    tmp = paths.CRON_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        if not text.endswith("\n"):
            text += "\n"
        f.write(text)
    os.replace(tmp, paths.CRON_PATH)


def validate(cron: str) -> str | None:
    fields = cron.split()
    if len(fields) != 5:
        return "cron 表达式需要 5 个字段：分 时 日 月 周"
    for field in fields:
        if not CRON_FIELD.match(field):
            return f"字段 `{field}` 含非法字符"
    return None


def parse() -> dict:
    """读出当前的定时设置。

    没有托管标记时不直接说「未启用」—— 老用户从官方镜像迁移过来，
    crontab 里本来就只有一行 `0 9 * * * ... dailycheckin ...`，应该被识别出来。
    """
    text = read_text()
    enabled = False
    cron = DEFAULT_CRON
    block = re.search(re.escape(BEGIN) + r"(.*?)" + re.escape(END), text, re.S)
    if block:
        for line in block.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            if len(fields) >= 6:
                cron = " ".join(fields[:5])
                enabled = True
                break
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            if len(fields) >= 6 and CALL_RE.search(line) and "pip" not in line:
                cron = " ".join(fields[:5])
                enabled = True
                break
    return {
        "enabled": enabled,
        "cron": cron,
        "presets": PRESETS,
        "crontab_path": paths.CRON_PATH,
        "detected": block is None and enabled,
    }


def set_schedule(enabled: bool, cron: str) -> dict:
    err = validate(cron)
    if err:
        raise ValueError(err)
    text = read_text()
    block_re = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    if enabled:
        body = f"{BEGIN}\n{_run_line(cron)}\n{END}"
    else:
        body = f"{BEGIN}\n# 定时签到已在面板中关闭\n{END}"
    if block_re.search(text):
        text = block_re.sub(lambda _: body, text, count=1)
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += f"\n##############每日签到任务##############\n{body}\n"
    write_text(text)
    applied = apply()
    return {"enabled": enabled, "cron": cron, "applied": applied}


def apply() -> dict:
    """把 crontab 文件装进容器里的 cron 服务。非容器环境（比如本地开发）会返回 skipped。"""
    binary = shutil.which("crontab")
    if not binary:
        return {"ok": False, "skipped": True, "message": "当前环境没有 crontab 命令（本地开发模式属正常）"}
    try:
        proc = subprocess.run([binary, paths.CRON_PATH], capture_output=True, text=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"执行 crontab 失败：{exc}"}
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return {"ok": False, "message": out.strip() or f"crontab 退出码 {proc.returncode}"}
    return {"ok": True, "message": "定时任务已生效"}


def installed() -> str:
    binary = shutil.which("crontab")
    if not binary:
        return ""
    try:
        proc = subprocess.run([binary, "-l"], capture_output=True, text=True, timeout=20)
        return proc.stdout or proc.stderr or ""
    except Exception:  # noqa: BLE001
        return ""
