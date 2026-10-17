"""签到执行器 + 校验状态存储。

两个关键设计：

1. **运行结果也是校验依据。** 引擎每个账号成功走完会打印 `✅✅✅✅✅`，抛异常打印
   `❌❌❌❌❌`。所以「跑一次签到」本身就是最可靠的 cookie 校验 —— 面板会把结果
   回写成站点的有效/失效状态，和在线校验互相印证。

2. **任务在后台线程跑，前台靠轮询拿增量输出。** 贴吧签到可能跑好几分钟，
   不能让一个 HTTP 请求挂在那儿。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid

from . import catalog, paths, store, verify

_LOCK = threading.RLock()
_RUNS: dict[str, dict] = {}
_ORDER: list[str] = []
_STATUS: dict = {"updated": 0, "sites": {}}

PART_RE = re.compile(r"^-{5,}开始执行「(.+?)」签到-{5,}\s*$")
OK_RE = re.compile(r"✅")
FAIL_RE = re.compile(r"❌")
SUMMARY_LINE_RE = re.compile(r"^(.+?)\s*账号数\s*:\s*(\d+)\s*$")
MAX_LINES = 4000

# 引擎抛的异常原文对用户没意义，但下面这几种一看就知道该怎么办，顺手翻译一下。
# 加的时候注意：这些提示会进通知正文，**保持一句话**，别写成长篇。
ERROR_HINTS = (
    ("Expecting value",
     "目标站点返回了空响应而不是 JSON，多半被风控或限流了 —— 隔 10~30 分钟再试，别连着重跑"),
    ("unsupported operand type",
     "配置里的数字字段被存成了字符串，去该站点的配置点一次保存"),
    ("Connection aborted", "连接被目标站点断开，过一会儿再试"),
    ("HTTPSConnectionPool", "连不上目标站点（网络不通，或站点不可达）"),
    ("Max retries exceeded", "连不上目标站点（网络不通，或站点不可达）"),
    ("Read timed out", "目标站点响应超时，过一会儿再试"),
    ("SSLError", "TLS 握手失败，检查容器网络或代理设置"),
)


def explain_error(text: str) -> str:
    """把引擎的异常原文补一句人话（认不出来就原样返回）。"""
    for needle, hint in ERROR_HINTS:
        if needle in text:
            return f"{text}（{hint}）"
    return text


# --------------------------------------------------------------------------- #
# 状态持久化
# --------------------------------------------------------------------------- #
def _load_status() -> None:
    global _STATUS
    try:
        with open(paths.STATUS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("sites"), dict):
            _STATUS = data
    except Exception:  # noqa: BLE001
        _STATUS = {"updated": 0, "sites": {}}


def _save_status() -> None:
    _STATUS["updated"] = time.time()
    paths.ensure_dirs()
    tmp = paths.STATUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_STATUS, f, ensure_ascii=False, indent=2)
    os.replace(tmp, paths.STATUS_PATH)


def mark_site(
    key: str,
    state: str,
    source: str,
    accounts: list[dict] | None = None,
    message: str = "",
    user: str | None = None,
) -> None:
    """state: valid / invalid / unknown / unverified"""
    with _LOCK:
        _STATUS.setdefault("sites", {})[key.upper()] = {
            "state": state,
            "source": source,
            "message": message,
            "user": user,
            "checked_at": time.time(),
            "accounts": accounts or [],
        }
        _save_status()


def site_status(key: str) -> dict:
    return _STATUS.get("sites", {}).get(key.upper(), {"state": "unverified", "source": None, "message": "", "accounts": []})


def clear_site_status(key: str, message: str = "cookie 已更新，等待重新校验") -> None:
    """账号被改动后把状态归零。

    这一步很关键：否则会出现「改了 cookie → 状态还是旧的失效」这种困惑。
    """
    with _LOCK:
        sites = _STATUS.setdefault("sites", {})
        if key.upper() in sites:
            sites[key.upper()] = {
                "state": "unverified",
                "source": None,
                "message": message,
                "user": None,
                "checked_at": time.time(),
                "accounts": [],
            }
            _save_status()


def all_status() -> dict:
    return {"updated": _STATUS.get("updated", 0), "sites": _STATUS.get("sites", {})}


# --------------------------------------------------------------------------- #
# 运行记录
# --------------------------------------------------------------------------- #
def _load_runs() -> None:
    try:
        with open(paths.RUNS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return
    if not isinstance(data, list):
        return
    for one in data:
        if isinstance(one, dict) and one.get("id"):
            one["lines"] = one.get("lines", [])[-300:]
            _RUNS[one["id"]] = one
            _ORDER.append(one["id"])


def _save_runs() -> None:
    paths.ensure_dirs()
    items = [_RUNS[rid] for rid in _ORDER[-paths.MAX_RUNS :] if rid in _RUNS]
    payload = [{k: v for k, v in one.items() if k != "proc"} for one in items]
    tmp = paths.RUNS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, paths.RUNS_PATH)


def get_run(run_id: str) -> dict | None:
    with _LOCK:
        one = _RUNS.get(run_id)
        return json.loads(json.dumps({k: v for k, v in one.items() if k != "proc"})) if one else None


def list_runs(limit: int = 10) -> list[dict]:
    with _LOCK:
        out = []
        for rid in reversed(_ORDER[-limit:]):
            one = _RUNS.get(rid)
            if one:
                out.append({k: v for k, v in one.items() if k not in ("proc", "lines")})
        return out


def latest_run() -> dict | None:
    runs = list_runs(1)
    return runs[0] if runs else None


# --------------------------------------------------------------------------- #
# 启动任务
# --------------------------------------------------------------------------- #
def _new_run(kind: str, site_keys: list[str] | None) -> dict:
    run_id = uuid.uuid4().hex[:12]
    run = {
        "id": run_id,
        "kind": kind,
        "site_keys": site_keys or [],
        "status": "running",
        "started_at": time.time(),
        "finished_at": None,
        "lines": [],
        "results": [],
        "exit_code": None,
    }
    with _LOCK:
        _RUNS[run_id] = run
        _ORDER.append(run_id)
    return run


def _append(run: dict, text: str) -> None:
    for line in text.splitlines():
        with _LOCK:
            run["lines"].append(line)
            if len(run["lines"]) > MAX_LINES:
                del run["lines"][: len(run["lines"]) - MAX_LINES]


def _finish(run: dict, status: str, exit_code: int | None = None) -> None:
    with _LOCK:
        run["status"] = status
        run["finished_at"] = time.time()
        run["exit_code"] = exit_code
    _save_runs()


def probe_engine() -> dict:
    """探测引擎是否可用，跑签到前先自检，失败时给出可操作的提示。"""
    cmd = [sys.executable, "-c", "import dailycheckin, dailycheckin.configs as c; print(len(c.checkin_map))"]
    env = dict(os.environ, PYTHONPATH=paths.HOME + os.pathsep + os.environ.get("PYTHONPATH", ""))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=paths.HOME, env=env)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"无法执行 Python：{exc}"}
    if proc.returncode != 0:
        return {"ok": False, "message": (proc.stderr or proc.stdout or "").strip()[-400:]}
    return {"ok": True, "message": f"已加载 {proc.stdout.strip()} 个站点模块"}


def start_run(site_keys: list[str] | None = None) -> dict:
    """跑签到。site_keys 为空表示跑全部。"""
    site_keys = [k.upper() for k in (site_keys or [])]
    run = _new_run("run", site_keys)
    threading.Thread(target=_do_run, args=(run, site_keys), daemon=True).start()
    return {"id": run["id"]}


def _do_run(run: dict, site_keys: list[str]) -> None:
    cmd = [sys.executable, "-m", "dailycheckin.main"]
    if site_keys:
        cmd += ["--include", *site_keys]
    _append(run, f"$ {' '.join(cmd)}")
    _append(run, f"$ cwd={paths.HOME}")
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    env["PYTHONPATH"] = paths.HOME + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("TZ", paths.TZ)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=paths.HOME,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except Exception as exc:  # noqa: BLE001
        _append(run, f"[面板] 启动失败：{exc}")
        _finish(run, "failed", -1)
        return

    deadline = time.time() + paths.RUN_TIMEOUT
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            _append(run, line.rstrip("\n"))
            if time.time() > deadline:
                proc.kill()
                _append(run, f"[面板] 超过 {paths.RUN_TIMEOUT} 秒未结束，已终止")
                break
        code = proc.wait(timeout=30)
    except Exception as exc:  # noqa: BLE001
        proc.kill()
        _append(run, f"[面板] 执行异常：{exc}")
        code = -1

    results = parse_output(run["lines"])
    with _LOCK:
        run["results"] = results
    _apply_results(results)
    _append(run, f"[面板] 进程退出码 {code}，用时 {int(time.time() - run['started_at'])} 秒")
    _finish(run, "done" if code == 0 else "failed", code)


def parse_output(lines: list[str]) -> list[dict]:
    """把引擎输出按「站点分段」解析成结构化结果。"""
    name_to_key = {name: key for key, name in catalog.engine_sites().items()}
    results: list[dict] = []
    current: dict | None = None
    pending = False  # 上一行是 ❌，接下来的行是异常信息

    for line in lines:
        m = PART_RE.match(line.strip())
        if m:
            if current:
                results.append(current)
            name = m.group(1)
            current = {
                "name": name,
                "key": name_to_key.get(name, name.upper()),
                "ok_count": 0,
                "fail_count": 0,
                "message": "",
                "lines": [],
            }
            pending = False
            continue
        if current is None:
            continue
        current["lines"].append(line)
        if OK_RE.search(line) and FAIL_RE.search(line) is None:
            current["ok_count"] += 1
            pending = False
        elif FAIL_RE.search(line):
            current["fail_count"] += 1
            pending = True
        elif pending and line.strip():
            prefix = "；" if current["message"] else ""
            current["message"] += prefix + explain_error(line.strip())
            pending = False
        if len(current["lines"]) > 200:
            del current["lines"][:100]
    if current:
        results.append(current)

    for one in results:
        one["ok"] = one["fail_count"] == 0 and one["ok_count"] > 0
        one.pop("lines", None)
    return [one for one in results if one["ok_count"] or one["fail_count"]]


def _apply_results(results: list[dict]) -> None:
    """把运行结果回写成站点状态。

    这里有个坑：不少站点模块遇到无效 cookie 时是**静默返回**的
    （比如 bilibili 的 `if is_login:` 不成立就直接跳过，一个异常都不抛），
    引擎照样打 ✅。所以「跑一次没报错」只是弱证据，而登录态接口返回的
    ❌ 是强证据 —— 两者冲突时以接口为准，并把冲突原因写清楚。
    """
    for one in results:
        if one["ok"]:
            prev = site_status(one["key"])
            if prev.get("state") == "invalid" and prev.get("source") == "api":
                mark_site(
                    one["key"],
                    "invalid",
                    "api",
                    message=(prev.get("message") or "登录态接口判定为失效").rstrip("。")
                    + "。（签到任务本身没抛异常，但该站点模块对无效 cookie 是静默返回的，以接口判定为准）",
                )
            else:
                mark_site(one["key"], "valid", "run", message=f"{one['ok_count']} 个账号签到成功")
        else:
            mark_site(
                one["key"],
                "invalid",
                "run",
                message=one["message"][:300] or f"{one['fail_count']} 个账号签到失败",
            )


# --------------------------------------------------------------------------- #
# 批量在线校验
# --------------------------------------------------------------------------- #
def start_verify(site_keys: list[str] | None = None) -> dict:
    site_keys = [k.upper() for k in (site_keys or [])]
    run = _new_run("verify", site_keys)
    threading.Thread(target=_do_verify, args=(run, site_keys), daemon=True).start()
    return {"id": run["id"]}


def _do_verify(run: dict, site_keys: list[str]) -> None:
    try:
        data = store.load()
    except Exception as exc:  # noqa: BLE001
        _append(run, f"[面板] 读取配置失败：{exc}")
        _finish(run, "failed", 1)
        return

    metas = {one["key"]: one for one in catalog.all_sites()}
    targets = site_keys or [one["key"] for one in catalog.all_sites()]
    for key in targets:
        meta = metas.get(key) or catalog.site_meta(key)
        accounts = store.accounts(data, key)
        if not accounts:
            _append(run, f"「{meta['label']}」未配置，跳过")
            continue
        if not meta.get("verify"):
            _append(run, f"「{meta['label']}」没有公开登录态接口，需靠运行签到判断")
            mark_site(key, "unknown", "api", message=verify.NO_VERIFIER_HINT)
            continue
        _append(run, f"「{meta['label']}」校验中…")
        per_account = []
        for account in accounts:
            one = verify.verify_account(key, account)
            per_account.append(one)
            flag = {True: "✅ 有效", False: "❌ 失效", None: "❔ 无法判定"}[one["ok"]]
            user = f"｜{one['user']}" if one.get("user") else ""
            _append(run, f"  {flag}{user}  {one['message']}")
            run["results"].append({"key": key, "label": meta["label"], "ok": one["ok"], "message": one["message"]})
        states = {one["ok"] for one in per_account}
        if states == {True}:
            state = "valid"
        elif False in states:
            state = "invalid"
        else:
            state = "unknown"
        users = "、".join([one["user"] for one in per_account if one.get("user")])
        mark_site(
            key,
            state,
            "api",
            accounts=per_account,
            user=users or None,
            message="；".join([one["message"] for one in per_account])[:300],
        )
    _finish(run, "done", 0)


def bootstrap() -> None:
    paths.ensure_dirs()
    _load_status()
    _load_runs()
