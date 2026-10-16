"""读取 UPSTREAM.json —— 面板里「当前引擎是哪一版、什么时候同步的」就来自这里。

引擎源码是本项目内置的（见 tools/sync_upstream.py），所以「上游发新版了没有」
这件事面板自己是不知道的；这里只负责把**同步那一刻记录下来的溯源信息**读出来，
让用户至少能看到当前跑的是哪一版、基于上游哪个提交、带了哪些本地补丁。
"""

from __future__ import annotations

import json
import os

from . import paths

_CACHE: dict = {"mtime": None, "data": {}}


def _candidates() -> list:
    # 容器里 UPSTREAM.json 和 panel/ 一起放在 DC_HOME；
    # 本地开发时 DC_HOME 可能是临时目录，所以再退回项目根目录找一次。
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [os.path.join(paths.HOME, "UPSTREAM.json"), os.path.join(root, "UPSTREAM.json")]


def info() -> dict:
    """返回归一化后的溯源信息；读不到就返回空字典（面板会降级显示）。"""
    for path in _candidates():
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if _CACHE["mtime"] == (path, mtime):
            return _CACHE["data"]
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict) or not raw.get("commit"):
            continue
        data = {
            "repo": raw.get("repo") or "",
            "ref": raw.get("ref") or "",
            "commit": (raw.get("commit") or "")[:10],
            "commit_date": raw.get("commit_date") or "",
            "version": raw.get("version") or "",
            "synced_at": raw.get("synced_at") or "",
            "patches": list(raw.get("patches") or []),
            "sites": list(raw.get("engine_sites") or []),
            "url": "https://github.com/%s" % raw["repo"] if raw.get("repo") else "",
            "source": path,
        }
        _CACHE["mtime"] = (path, mtime)
        _CACHE["data"] = data
        return data
    return {}
