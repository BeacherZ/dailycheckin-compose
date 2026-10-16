"""面板 HTTP 服务。

刻意只用标准库 `http.server`：容器里除了引擎自己的 4 个依赖之外，
不再引入 flask/fastapi/uvicorn 之类的框架，任何架构（x86 / arm64 / armv7）
都能直接跑起来，也不会因为依赖装不上而白折腾。
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import auth, catalog, cookies as ck, paths, runner, schedule, store, upstream, verify

PANEL_VERSION = "2.1.0"
MAX_BODY = 4 * 1024 * 1024

# 不需要登录就能访问的接口：健康检查（给容器 healthcheck 用）与登录/首次设置本身
PUBLIC_ROUTES = {"h_health", "h_auth_status", "h_auth_setup", "h_auth_login"}

ROUTES: list[tuple[str, re.Pattern, str]] = []


def route(method: str, pattern: str):
    def deco(func):
        ROUTES.append((method, re.compile("^" + pattern + "$"), func.__name__))
        return func

    return deco


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def engine_version() -> str:
    path = os.path.join(paths.HOME, "dailycheckin", "__version__.py")
    try:
        with open(path, encoding="utf-8") as f:
            m = re.search(r'__version__\s*=\s*["\']([^"\']+)', f.read())
        if m:
            return m.group(1)
    except Exception:  # noqa: BLE001
        pass
    try:
        from importlib.metadata import version

        return version("dailycheckin")
    except Exception:  # noqa: BLE001
        return ""


def tail_log(name: str = "dailycheckin.log", lines: int = 300) -> str:
    path = os.path.join(paths.LOG_DIR, os.path.basename(name))
    if not os.path.exists(path):
        return ""
    lines = max(1, min(int(lines), 3000))
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = min(size, lines * 400)
            f.seek(size - block)
            data = f.read().decode("utf-8", errors="replace")
        return "\n".join(data.splitlines()[-lines:])
    except Exception as exc:  # noqa: BLE001
        return f"读取日志失败：{exc}"


def log_files() -> list[dict]:
    if not os.path.isdir(paths.LOG_DIR):
        return []
    out = []
    for name in sorted(os.listdir(paths.LOG_DIR)):
        full = os.path.join(paths.LOG_DIR, name)
        if os.path.isfile(full):
            out.append({"name": name, "size": os.path.getsize(full), "mtime": os.path.getmtime(full)})
    return out


def build_state() -> dict:
    data = store.load()
    status = runner.all_status()
    sites = []
    for meta in catalog.all_sites():
        key = meta["key"]
        accounts = store.accounts(data, key)
        # 逐账号做一次本地格式体检（不联网），前端直接显示
        for account in accounts:
            account["_check"] = local_check(key, account)
        sites.append(
            {
                **meta,
                "accounts": accounts,
                "configured": store.has_config(data, key),
                "status": status["sites"].get(key, {"state": "unverified", "source": None, "message": "", "accounts": []}),
            }
        )
    notice = {key: data.get(key, "") for key in store.NOTICE_KEY_NAMES}
    # 上游新加了站点、但 panel/catalog.py 还没给它写元数据时，面板仍然能配置和签到，
    # 只是没有必填字段提示、没有在线校验。把这类站点列出来，前端会打个「通用配置」标记。
    without_meta = [s["key"] for s in sites if not s.get("known")]
    return {
        "panel": {
            "title": paths.TITLE,
            "version": PANEL_VERSION,
            "home": paths.HOME,
            "config_path": paths.CONFIG_PATH,
            "tz": paths.TZ,
            "token_bypass": bool(paths.TOKEN),
            "user": auth.username(),
            "auth_since": auth.created_at(),
        },
        "engine": {
            **runner.probe_engine(),
            "version": engine_version(),
            "upstream": upstream.info(),
            "sites_without_meta": without_meta,
        },
        "sites": sites,
        "notice_keys": [{"key": k, "label": v} for k, v in store.NOTICE_KEYS],
        "notice": notice,
        "schedule": schedule.parse(),
        "status_updated": status.get("updated", 0),
        "runs": runner.list_runs(8),
        "backups": store.list_backups()[:8],
        "server_time": time.time(),
    }


def local_check(key: str, account: dict) -> dict:
    """纯本地格式体检：不发任何网络请求。"""
    meta = catalog.site_meta(key)
    if meta["credential"] == "cookie":
        raw = str(account.get("cookie") or "")
        if not raw.strip():
            return {"ok": None, "message": "未填写 cookie", "warnings": [], "missing": [], "keys": [], "count": 0}
        result = ck.normalize(raw, required=meta.get("required") or [])
        return {
            "ok": result.ok,
            "message": result.cookie if result.ok else "；".join(result.errors) or "缺少必填字段",
            "warnings": result.warnings,
            "missing": result.missing,
            "keys": [k for k, _ in result.items],
            "count": result.count,
            "needs_fix": result.needs_fix(raw),
            "normalized": result.cookie,
            "source": result.source,
        }
    missing = []
    for field in meta.get("fields", []):
        if field.get("required") and not str(account.get(field["key"]) or "").strip():
            missing.append(field["label"])
    return {"ok": not missing, "message": "" if not missing else "缺少：" + "、".join(missing), "warnings": [], "missing": missing, "keys": [], "count": 0}


# --------------------------------------------------------------------------- #
# 路由处理
# --------------------------------------------------------------------------- #
@route("GET", r"/api/health")
def h_health(h):
    return {"ok": True, "time": time.time(), "version": PANEL_VERSION}


# --------------------------------------------------------------------------- #
# 后台账号密码
# --------------------------------------------------------------------------- #
@route("GET", r"/api/auth/status")
def h_auth_status(h):
    return {
        "initialized": auth.is_initialized(),
        "logged_in": bool(h.session_user()),
        "username": auth.username(),
        "min_user": auth.MIN_USER,
        "max_user": auth.MAX_USER,
        "min_pass": auth.MIN_PASS,
        "max_pass": auth.MAX_PASS,
        "auth_path": paths.AUTH_PATH,
        "token_bypass": bool(paths.TOKEN),
    }


@route("POST", r"/api/auth/setup")
def h_auth_setup(h):
    body = h.body()
    try:
        auth.setup(str(body.get("username") or ""), str(body.get("password") or ""))
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    h.set_session(auth.create_session())
    return {"ok": True, "username": auth.username()}


@route("POST", r"/api/auth/login")
def h_auth_login(h):
    ip = h.client_ip()
    wait = auth.throttled(ip)
    if wait:
        raise HttpError(429, f"尝试过于频繁，请 {wait} 秒后再试")
    body = h.body()
    if not auth.is_initialized():
        raise HttpError(400, "后台还没有设置账号密码")
    if not auth.check(str(body.get("username") or ""), str(body.get("password") or "")):
        auth.note_failure(ip)
        raise HttpError(401, "账号或密码不正确")
    auth.clear_failures(ip)
    h.set_session(auth.create_session())
    return {"ok": True, "username": auth.username()}


@route("POST", r"/api/auth/logout")
def h_auth_logout(h):
    h.set_session("", clear=True)
    return {"ok": True}


@route("POST", r"/api/auth/credentials")
def h_auth_credentials(h):
    body = h.body()
    new_user = body.get("username")
    new_password = str(body.get("new_password") or "")
    if not new_password and body.get("confirm_password"):
        new_password = str(body.get("confirm_password"))
    try:
        auth.change_credentials(
            str(body.get("old_password") or ""),
            None if new_user is None else str(new_user),
            new_password or None,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    h.set_session(auth.create_session())
    return {"ok": True, "username": auth.username(), "password_changed": bool(new_password)}


@route("GET", r"/api/state")
def h_state(h):
    return build_state()


@route("GET", r"/api/config/raw")
def h_config_raw(h):
    return {"text": store.read_raw(), "path": paths.CONFIG_PATH}


@route("PUT", r"/api/config/raw")
def h_config_put(h):
    body = h.body()
    text = body.get("text", "")
    if not isinstance(text, str) or not text.strip():
        raise HttpError(400, "内容为空")
    try:
        data = store.write_raw(text)
    except json.JSONDecodeError as exc:
        raise HttpError(400, f"JSON 语法错误：{exc}") from exc
    return {"ok": True, "sites": len([k for k, v in data.items() if isinstance(v, list)])}


@route("POST", r"/api/cookies/normalize")
def h_normalize(h):
    body = h.body()
    raw = body.get("raw", "")
    key = str(body.get("site", "")).upper()
    required = catalog.required_of(key) if key else []
    result = ck.normalize(raw, required=required)
    out = result.as_dict()
    out["required"] = required
    out["recommended"] = catalog.site_meta(key).get("recommended", []) if key else []
    return out


@route("POST", r"/api/sites/(?P<key>[A-Za-z0-9_]+)/accounts")
def h_save_accounts(h):
    key = h.params["key"].upper()
    body = h.body()
    accounts = body.get("accounts")
    if not isinstance(accounts, list):
        raise HttpError(400, "accounts 必须是数组")
    cleaned: list[dict] = []
    for one in accounts:
        if not isinstance(one, dict):
            continue
        account = {}
        for field_key, value in one.items():
            if str(field_key).startswith("_"):
                continue
            if field_key == "cookie":
                result = ck.normalize(str(value or ""), required=catalog.required_of(key))
                account["cookie"] = result.cookie
                account["_normalized"] = result.ok
            else:
                account[field_key] = value
        if any(str(v or "").strip() for k, v in account.items() if not str(k).startswith("_")):
            cleaned.append({k: v for k, v in account.items() if not str(k).startswith("_")})
    data = store.load()
    before = store.accounts(data, key)
    store.set_accounts(data, key, cleaned)
    store.write(data)
    # 账号被改动 → 旧的有效性标记立刻作废，避免「改了 cookie 还显示失效」的困惑
    changed = before != cleaned
    if changed:
        runner.clear_site_status(key)
    return {"ok": True, "count": len(cleaned), "changed": changed}


@route("POST", r"/api/notice")
def h_notice(h):
    body = h.body()
    notice = body.get("notice")
    if not isinstance(notice, dict):
        raise HttpError(400, "notice 必须是对象")
    data = store.load()
    changed = 0
    for notice_key in store.NOTICE_KEY_NAMES:
        if notice_key in notice:
            data[notice_key] = notice[notice_key]
            changed += 1
    store.write(data)
    return {"ok": True, "changed": changed}


@route("POST", r"/api/sites/(?P<key>[A-Za-z0-9_]+)/verify")
def h_verify_site(h):
    key = h.params["key"].upper()
    data = store.load()
    accounts = store.accounts(data, key)
    if not accounts:
        return {"ok": True, "state": "unverified", "results": [], "message": "该站点还没有配置账号"}
    meta = catalog.site_meta(key)
    results = [verify.verify_account(key, one) for one in accounts]
    states = {one["ok"] for one in results}
    state = "valid" if states == {True} else ("invalid" if False in states else "unknown")
    users = "、".join([one["user"] for one in results if one.get("user")])
    runner.mark_site(
        key,
        state,
        "api",
        accounts=results,
        user=users or None,
        message="；".join([one["message"] for one in results])[:300],
    )
    return {"ok": True, "state": state, "results": results, "label": meta["label"]}


@route("POST", r"/api/run")
def h_run(h):
    body = h.body()
    sites = body.get("sites") or []
    if not isinstance(sites, list):
        raise HttpError(400, "sites 必须是数组")
    return runner.start_run([str(s) for s in sites])


@route("POST", r"/api/verify")
def h_verify(h):
    body = h.body()
    sites = body.get("sites") or []
    if not isinstance(sites, list):
        raise HttpError(400, "sites 必须是数组")
    return runner.start_verify([str(s) for s in sites])


@route("GET", r"/api/runs")
def h_runs(h):
    return {"runs": runner.list_runs(20)}


@route("GET", r"/api/runs/(?P<id>[A-Za-z0-9]+)")
def h_run_get(h):
    one = runner.get_run(h.params["id"])
    if not one:
        raise HttpError(404, "找不到该任务")
    return one


@route("GET", r"/api/logs")
def h_logs(h):
    query = h.query
    name = query.get("name", ["dailycheckin.log"])[0]
    lines = int(query.get("lines", ["400"])[0])
    return {"files": log_files(), "name": os.path.basename(name), "text": tail_log(name, lines)}


@route("GET", r"/api/schedule")
def h_schedule_get(h):
    return schedule.parse()


@route("PUT", r"/api/schedule")
def h_schedule_put(h):
    body = h.body()
    enabled = bool(body.get("enabled", True))
    cron = str(body.get("cron") or schedule.DEFAULT_CRON)
    try:
        out = schedule.set_schedule(enabled, cron)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return out


@route("GET", r"/api/crontab")
def h_crontab_get(h):
    return {"text": schedule.read_text(), "installed": schedule.installed()}


@route("PUT", r"/api/crontab")
def h_crontab_put(h):
    body = h.body()
    text = body.get("text", "")
    if not isinstance(text, str) or not text.strip():
        raise HttpError(400, "内容为空")
    schedule.write_text(text)
    return {"ok": True, "applied": schedule.apply()}


@route("GET", r"/api/backups")
def h_backups(h):
    return {"backups": store.list_backups()}


@route("POST", r"/api/backups/(?P<name>[A-Za-z0-9._\-]+)/restore")
def h_restore(h):
    try:
        store.restore_backup(h.params["name"])
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"ok": True}


# --------------------------------------------------------------------------- #
# HTTP 层
# --------------------------------------------------------------------------- #
class HttpError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


HANDLERS = {}


class Handler(BaseHTTPRequestHandler):
    server_version = "dailycheckin-plus-panel/" + PANEL_VERSION
    protocol_version = "HTTP/1.1"

    # ----- 基础 -----
    def log_message(self, fmt, *args):  # noqa: A003 - 覆盖父类，降低噪音
        if os.environ.get("PANEL_VERBOSE"):
            super().log_message(fmt, *args)

    def _send(self, status: int, payload: bytes, content_type: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _json(self, status: int, data, extra: dict | None = None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", extra)

    def body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise HttpError(413, "请求体过大")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise HttpError(400, f"请求体不是合法 JSON：{exc}") from exc
        return data if isinstance(data, dict) else {"_": data}

    # ----- 认证 -----
    def client_ip(self) -> str:
        fwd = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return fwd or (self.client_address[0] if self.client_address else "?")

    def cookie(self, name: str) -> str:
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            key, _, value = part.strip().partition("=")
            if key == name:
                return value
        return ""

    def session_user(self) -> str | None:
        return auth.read_session(self.cookie(auth.COOKIE_NAME))

    def _secure_cookie(self) -> bool:
        proto = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
        return proto == "https"

    def set_session(self, ticket: str, clear: bool = False) -> None:
        parts = [f"{auth.COOKIE_NAME}={ticket}", "Path=/", "HttpOnly", "SameSite=Lax"]
        parts.append("Max-Age=0" if clear else f"Max-Age={auth.SESSION_TTL}")
        if self._secure_cookie():
            parts.append("Secure")
        self._pending_cookie = "; ".join(parts)

    def _token_ok(self) -> bool:
        if not paths.TOKEN:
            return False
        if (self.headers.get("X-Panel-Token") or "") == paths.TOKEN:
            return True
        return self.query.get("token", [""])[0] == paths.TOKEN

    def _deny(self) -> dict | None:
        """返回 None 表示放行；否则返回要回给前端的 401 载荷。"""
        if self._token_ok():
            return None
        if not auth.is_initialized():
            return {"error": "后台还没有设置账号密码", "need_setup": True}
        if self.session_user():
            return None
        return {"error": "请先登录", "need_login": True}

    def _dispatch(self, method: str):
        parsed = urllib.parse.urlparse(self.path)
        self.path_only = urllib.parse.unquote(parsed.path)
        self.query = urllib.parse.parse_qs(parsed.query)
        self._pending_cookie = ""

        for route_method, pattern, name in ROUTES:
            m = pattern.match(self.path_only)
            if not m:
                continue
            if route_method != method:
                continue
            self.params = m.groupdict()
            if name not in PUBLIC_ROUTES:
                denied = self._deny()
                if denied:
                    return self._json(401, denied)
            try:
                result = globals()[name](self)
            except HttpError as exc:
                return self._json(exc.status, {"error": exc.message}, self._cookie_header())
            except ValueError as exc:
                return self._json(400, {"error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return self._json(200, result, self._cookie_header())

        if method == "GET":
            return self._static(self.path_only)
        return self._json(404, {"error": f"未知接口 {method} {self.path_only}"})

    def _cookie_header(self) -> dict | None:
        return {"Set-Cookie": self._pending_cookie} if self._pending_cookie else None

    def do_GET(self):  # noqa: N802
        self._dispatch("GET")

    def do_POST(self):  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self):  # noqa: N802
        self._dispatch("PUT")

    # ----- 静态文件 -----
    def _static(self, path: str):
        if path in ("/", "/index.html"):
            return self._file(os.path.join(paths.STATIC_DIR, "index.html"))
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if path.startswith("/static/"):
            name = os.path.normpath(path[len("/static/") :]).replace("\\", "/")
            if name.startswith("..") or name.startswith("/"):
                return self._json(400, {"error": "非法路径"})
            return self._file(os.path.join(paths.STATIC_DIR, name))
        return self._json(404, {"error": "not found"})

    def _file(self, full: str):
        if not os.path.isfile(full):
            return self._json(404, {"error": "文件不存在"})
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


def serve() -> None:
    paths.ensure_dirs()
    runner.bootstrap()
    note = auth.bootstrap_from_env()
    httpd = ThreadingHTTPServer((paths.HOST, paths.PORT), Handler)
    httpd.daemon_threads = True
    shown = "127.0.0.1" if paths.HOST == "0.0.0.0" else paths.HOST
    print(f"{paths.TITLE} 已启动：http://{shown}:{paths.PORT}", flush=True)
    print(f"  工作目录   : {paths.HOME}")
    print(f"  配置文件   : {paths.CONFIG_PATH}")
    if note:
        print(f"  后台账号   : {note}")
    if not auth.is_initialized():
        print("  后台账号   : 还没设置 —— 打开网页会引导你设置账号密码", flush=True)
    else:
        print(f"  后台账号   : {auth.username()}（凭据文件 {paths.AUTH_PATH}）")
    if paths.TOKEN:
        print("  脚本口令   : 已启用 PANEL_TOKEN（供脚本/自动化调用，不能替代登录）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止", flush=True)
    finally:
        httpd.server_close()
