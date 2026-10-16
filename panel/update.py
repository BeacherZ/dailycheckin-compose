"""「当前这个容器需不需要更新」。

判断依据不是一个手写的版本号，而是**构建镜像时的那次提交**：
Dockerfile 用 build-arg 把 commit 烤进 `PANEL_BUILD.json`，本地直接跑面板时
再退回读 git HEAD。拿它去和 GitHub 上 `main` 的最新提交比 —— 两边 sha 不一致，
就说明远端已经有新提交了，该 `docker compose pull` 了。

三条克制的原则：

* **缓存 3 小时**：GitHub 匿名接口限 60 次/小时/IP，别把它当心跳打。
* **网络不通就如实说**：显示「连不上 GitHub」，绝不假装「已是最新」。
* **不认识就说不认识**：本地跑、没有构建信息时，结论是「判断不了」，同样不猜。
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request

from . import paths

REPO = paths.PROJECT_REPO
API = "https://api.github.com/repos/%s/commits/main" % REPO
CACHE_TTL = 3 * 3600
TIMEOUT = 8

_LOCK = threading.Lock()
_CACHE: dict = {"ts": 0.0, "data": None}


def _short(sha: str) -> str:
    return (sha or "")[:7]


def _git_stamp(root: str) -> dict:
    """从 git 工作区取 HEAD。没有 git / 不是仓库都直接认输，不报错。"""
    try:
        sha = subprocess.run(
            ["git", "-C", root, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if sha.returncode != 0:
            return {"commit": "", "date": "", "source": ""}
        when = subprocess.run(
            ["git", "-C", root, "log", "-1", "--format=%cI"],
            capture_output=True, text=True, timeout=5,
        )
        return {
            "commit": sha.stdout.strip(),
            "date": when.stdout.strip() if when.returncode == 0 else "",
            "source": "git",
        }
    except Exception:  # noqa: BLE001
        return {"commit": "", "date": "", "source": ""}


def build_stamp() -> dict:
    """这份代码是从哪个提交来的。

    优先级：容器里烤好的 `PANEL_BUILD.json` → 源码根目录的 `PANEL_BUILD.json` → git HEAD。
    全都拿不到就返回空 commit，页面会显示「未记录构建信息」。
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path, source in (
        (os.path.join(paths.HOME, "PANEL_BUILD.json"), "image"),
        (os.path.join(root, "PANEL_BUILD.json"), "source"),
    ):
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(raw, dict) and str(raw.get("commit") or "").strip():
            return {
                "commit": str(raw["commit"]).strip(),
                "date": str(raw.get("date") or ""),
                "source": source,
            }
    return _git_stamp(root)


def local_info(version: str) -> dict:
    """给页面首屏用的本地信息：不发网络请求，所以不拖慢 /api/state。"""
    stamp = build_stamp()
    return {
        "repo": REPO,
        "url": paths.PROJECT_URL,
        "version": version,
        "commit": stamp["commit"],
        "short": _short(stamp["commit"]),
        "date": stamp["date"],
        "source": stamp["source"],
    }


def _friendly(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (403, 429):
            return "GitHub 接口限流了（匿名每小时 60 次），过一会儿再试"
        if exc.code == 404:
            return "GitHub 上找不到这个仓库（地址或权限不对）"
        return "GitHub 返回 HTTP %s" % exc.code
    if isinstance(exc, urllib.error.URLError):
        return "连不上 GitHub —— 容器网络可能访问不了 api.github.com"
    if isinstance(exc, TimeoutError):
        return "GitHub 响应超时"
    return "检查更新失败：%s" % exc


def latest() -> dict:
    """问 GitHub：main 上最新一次提交是什么。失败就抛，由 check() 兜。"""
    req = urllib.request.Request(API, method="GET")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "dailycheckin-plus-panel")
    token = os.environ.get("PANEL_GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if token.strip():
        req.add_header("Authorization", "Bearer " + token.strip())
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = json.loads(resp.read().decode() or "{}")
    commit = raw.get("commit") or {}
    return {
        "commit": raw.get("sha") or "",
        "date": (commit.get("committer") or {}).get("date") or "",
        "message": (commit.get("message") or "").splitlines()[0][:120],
        "url": raw.get("html_url") or paths.PROJECT_URL,
    }


def check(version: str, force: bool = False) -> dict:
    """对比本地构建提交与远端最新提交。结果缓存，`force=True` 时强制重查。"""
    now = time.time()
    with _LOCK:
        cached = _CACHE["data"]
        if cached and not force and now - _CACHE["ts"] < CACHE_TTL:
            return cached

    out = dict(local_info(version), checked_at=now, ok=None, error="", remote=None, needs_update=None)
    try:
        remote = latest()
    except Exception as exc:  # noqa: BLE001
        out["ok"] = False
        out["error"] = _friendly(exc)
    else:
        remote["short"] = _short(remote["commit"])
        out["ok"] = True
        out["remote"] = remote
        mine, theirs = out["commit"], remote["commit"]
        # 两边都认得出提交才敢下结论；本地没记录（本地跑面板）就说判断不了。
        out["needs_update"] = (mine != theirs) if (mine and theirs) else None

    with _LOCK:
        _CACHE["ts"] = now
        _CACHE["data"] = out
    return out
