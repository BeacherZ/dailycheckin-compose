"""config.json 的读写。

一个原则：**面板只是 config.json 的编辑器**，不做第二套数据源。
面板写出来的文件引擎能直接用，引擎生成的文件面板也能直接读，
用户随时可以手动编辑，两边不会打架。
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time

from . import catalog, paths

_LOCK = threading.RLock()

# 推送通知字段，来自引擎的 dailycheckin/configs.py::notice_map。
#
# 按「渠道」分组：设置页把每一组装进一个方框里，同一种通知方式的字段聚在一起，
# 不用在一大片输入框里翻找。列表顺序 = 服务端顺序 = 页面显示顺序。
#   每项：(渠道名, 该渠道的字段 [(配置键, 短标签)], 是否整行铺开)
#   短标签只写「字段名」，前缀（渠道名）由标题承担，别重复；
#   配置键会作为输入框的 placeholder 显示 —— 留空时正好告诉你这个框对应 config.json 里的哪个键。
# 标了 True 的那组字段多，整行铺开再横向排（否则它一个人把同排其它方框拉高一大截）。
#
# 顺序也是排过的：两列布局下，相邻两个方框会被拉成等高，所以把「字段数差不多」
# 的放一起（1 行的挨着 1 行的），只留一处高度差 —— 否则每个矮方框底下都会空出一块。
# 顺带也是按同类聚拢：钉钉 + 飞书（国内 IM）、Server 酱 + Server 酱³、
# Gotify + ntfy（自建推送）。
NOTICE_GROUPS = [
    (
        "企业微信",
        [
            ("QYWX_KEY", "机器人 Key"),
            ("QYWX_CORPID", "企业 ID"),
            ("QYWX_AGENTID", "应用 ID"),
            ("QYWX_CORPSECRET", "应用密钥"),
            ("QYWX_TOUSER", "接收人"),
            ("QYWX_MEDIA_ID", "素材 ID"),
            ("QYWX_ORIGIN", "代理地址"),
        ],
        True,
    ),
    ("PushPlus", [("PUSHPLUS_TOKEN", "Token"), ("PUSHPLUS_TOPIC", "群组编码")], False),
    ("Bark", [("BARK_URL", "推送地址")], False),
    ("钉钉", [("DINGTALK_ACCESS_TOKEN", "Access Token"), ("DINGTALK_SECRET", "加签密钥")], False),
    ("飞书", [("FSKEY", "机器人 Key")], False),
    ("Server 酱", [("SCKEY", "SendKey")], False),
    ("Server 酱³", [("SENDKEY", "SendKey")], False),
    (
        "Qmsg",
        [("QMSG_KEY", "钥匙"), ("QMSG_TYPE", "类型")],
        False,
    ),
    (
        "Telegram",
        [
            ("TG_BOT_TOKEN", "Bot Token"),
            ("TG_USER_ID", "用户 ID"),
            ("TG_API_HOST", "API 代理"),
            ("TG_PROXY", "代理地址"),
        ],
        False,
    ),
    (
        "Gotify",
        [("GOTIFY_URL", "服务器地址"), ("GOTIFY_TOKEN", "Token"), ("GOTIFY_PRIORITY", "优先级")],
        False,
    ),
    (
        "ntfy",
        [("NTFY_URL", "服务器地址"), ("NTFY_TOPIC", "主题"), ("NTFY_PRIORITY", "优先级")],
        False,
    ),
]

# 扁平视图（配置读写、e2e 里按键取值都用这个）。标签 = 渠道名 + 字段名，
# 所以在页面之外的场景（比如以后要做 CLI）也能一眼看出这个键属于谁。
NOTICE_KEYS = [
    (key, f"{name} {label}")
    for name, fields, _wide in NOTICE_GROUPS
    for key, label in fields
]

NOTICE_KEY_NAMES = [key for key, _ in NOTICE_KEYS]


def notice_groups() -> list[dict]:
    """给前端的渠道分组。短标签 + 完整标签都给，前端用短标签、title 用完整的。"""
    return [
        {
            "name": name,
            "wide": bool(wide),
            "fields": [{"key": key, "label": label, "full": f"{name} {label}"} for key, label in fields],
        }
        for name, fields, wide in NOTICE_GROUPS
    ]

# 已废弃的配置项。上游那套「MERGE_PUSH 合并推送」开关不再需要了 ——
# 通知恒定只发一条。但老配置里可能还留着 MERGE_PUSH=false，写文件时顺手清掉，
# 免得设置页里冒出一个没人认识、也不再起作用的键。
LEGACY_NOTICE_KEYS = ("MERGE_PUSH",)


def empty_template() -> dict:
    """生成一份空配置：所有站点都是空数组，推送字段留空。"""
    data: dict = {key: "" for key in NOTICE_KEY_NAMES}
    for site in catalog.all_sites():
        data[site["key"]] = []
    return data


def read_raw() -> str:
    if not os.path.exists(paths.CONFIG_PATH):
        return json.dumps(empty_template(), ensure_ascii=False, indent=4)
    with open(paths.CONFIG_PATH, encoding="utf-8") as f:
        return f.read()


def load() -> dict:
    """读取配置；文件不存在时用空模板初始化，文件损坏时抛 ValueError。"""
    with _LOCK:
        if not os.path.exists(paths.CONFIG_PATH):
            data = empty_template()
            write(data, backup=False)
            return data
        raw = read_raw()
        if not raw.strip():
            data = empty_template()
            write(data, backup=False)
            return data
        try:
            data = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"config.json 不是合法 JSON：{exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("config.json 顶层必须是对象")
        return data


def write(data: dict, backup: bool = True) -> dict:
    """原子写入（先写临时文件再替换），可选保留一份时间戳备份。"""
    with _LOCK:
        paths.ensure_dirs()
        for legacy in LEGACY_NOTICE_KEYS:
            data.pop(legacy, None)
        if backup and os.path.exists(paths.CONFIG_PATH):
            _backup()
        tmp = paths.CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.write("\n")
        os.replace(tmp, paths.CONFIG_PATH)
        return data


def write_raw(text: str) -> dict:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("config.json 顶层必须是对象")
    write(data)
    return data


def _backup() -> None:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(paths.BACKUP_DIR, f"config-{stamp}.json")
    try:
        shutil.copy2(paths.CONFIG_PATH, dest)
    except Exception:  # noqa: BLE001
        return
    entries = sorted(name for name in os.listdir(paths.BACKUP_DIR) if name.endswith(".json"))
    for old in entries[: max(0, len(entries) - paths.MAX_BACKUPS)]:
        try:
            os.remove(os.path.join(paths.BACKUP_DIR, old))
        except OSError:
            pass


def list_backups() -> list[dict]:
    if not os.path.isdir(paths.BACKUP_DIR):
        return []
    out = []
    for name in sorted(os.listdir(paths.BACKUP_DIR), reverse=True):
        if not name.endswith(".json"):
            continue
        full = os.path.join(paths.BACKUP_DIR, name)
        out.append({"name": name, "size": os.path.getsize(full), "mtime": os.path.getmtime(full)})
    return out[: paths.MAX_BACKUPS]


def restore_backup(name: str) -> dict:
    if os.path.sep in name or "/" in name or not name.endswith(".json"):
        raise ValueError("备份文件名不合法")
    src = os.path.join(paths.BACKUP_DIR, name)
    if not os.path.exists(src):
        raise ValueError("备份不存在")
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    write(data, backup=True)
    return data


# --------------------------------------------------------------------------- #
# 账号级别的读写
# --------------------------------------------------------------------------- #
def accounts(data: dict, key: str) -> list[dict]:
    value = data.get(key.upper())
    if value is None:
        return []
    if isinstance(value, dict):  # 容错：手写成对象也认
        return [value]
    if isinstance(value, list):
        return [one for one in value if isinstance(one, dict)]
    return []


def set_accounts(data: dict, key: str, items: list[dict]) -> dict:
    data[key.upper()] = items
    return data


def has_config(data: dict, key: str) -> bool:
    """该站点是否有可用的账号配置（cookie 类站点看 cookie，表单类看必填字段）。"""
    meta = catalog.site_meta(key)
    for account in accounts(data, key):
        if meta["credential"] == "cookie":
            if str(account.get("cookie") or "").strip():
                return True
        else:
            fields = [f for f in meta.get("fields", []) if f.get("required")]
            if fields and all(str(account.get(f["key"]) or "").strip() for f in fields):
                return True
            if not fields and any(str(v or "").strip() for v in account.values()):
                return True
    return False
