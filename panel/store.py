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

# 推送通知相关字段，来自引擎的 dailycheckin/configs.py::notice_map
NOTICE_KEYS = [
    ("PUSHPLUS_TOKEN", "PushPlus Token"),
    ("PUSHPLUS_TOPIC", "PushPlus 群组编码"),
    ("QYWX_KEY", "企业微信机器人 Key"),
    ("QYWX_CORPID", "企业微信 企业 ID"),
    ("QYWX_AGENTID", "企业微信 应用 ID"),
    ("QYWX_CORPSECRET", "企业微信 应用密钥"),
    ("QYWX_TOUSER", "企业微信 接收人"),
    ("QYWX_MEDIA_ID", "企业微信 素材 ID"),
    ("QYWX_ORIGIN", "企业微信 代理地址"),
    ("TG_BOT_TOKEN", "Telegram Bot Token"),
    ("TG_USER_ID", "Telegram 用户 ID"),
    ("TG_API_HOST", "Telegram API 代理"),
    ("TG_PROXY", "Telegram 代理地址"),
    ("BARK_URL", "Bark 推送地址"),
    ("DINGTALK_ACCESS_TOKEN", "钉钉 Access Token"),
    ("DINGTALK_SECRET", "钉钉加签密钥"),
    ("FSKEY", "飞书机器人 Key"),
    ("GOTIFY_URL", "Gotify 服务器地址"),
    ("GOTIFY_TOKEN", "Gotify Token"),
    ("GOTIFY_PRIORITY", "Gotify 优先级"),
    ("NTFY_URL", "ntfy 服务器地址"),
    ("NTFY_TOPIC", "ntfy 主题"),
    ("NTFY_PRIORITY", "ntfy 优先级"),
    ("SCKEY", "Server 酱 SendKey"),
    ("SENDKEY", "Server 酱³ SendKey"),
    ("QMSG_KEY", "Qmsg 钥匙"),
    ("QMSG_TYPE", "Qmsg 类型"),
    ("MERGE_PUSH", "合并推送"),
]

NOTICE_KEY_NAMES = [key for key, _ in NOTICE_KEYS]


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
