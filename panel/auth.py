"""后台账号密码与会话。

刻意不引入任何第三方库：PBKDF2-HMAC-SHA256 来自 `hashlib`，会话票据是自己签的
HMAC，凭据文件和 config.json 一样放在 `data/` 目录里，方便整体备份与迁移。

安全取舍（写清楚，免得用户误会）：

* 密码只存「PBKDF2 派生值 + 随机盐」，既不存明文也不存可逆密文。
* 会话是**签名票据**而不是服务端 session 表 —— 面板重启不会把人踢下线。
* 票据是 Bearer 语义，所以**要用在公网就务必配 HTTPS 反代**，README 里有说明。
* 登录失败按来源 IP 计数限速，挡住最基本的爆破。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

from . import paths

ALGO = "pbkdf2_sha256"
ITERATIONS = 210_000
SALT_BYTES = 16
SESSION_TTL = 7 * 24 * 3600
COOKIE_NAME = "dc_session"

MIN_USER = 2
MAX_USER = 32
MIN_PASS = 6
MAX_PASS = 128

# 登录限速：同一来源 10 分钟内最多失败 12 次
FAIL_WINDOW = 600
FAIL_MAX = 12

_LOCK = threading.RLock()
_CACHE: dict | None = None
_FAILS: dict[str, list[float]] = {}


# --------------------------------------------------------------------------- #
# 存取
# --------------------------------------------------------------------------- #
def _path() -> str:
    return paths.AUTH_PATH


def _load() -> dict:
    global _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        try:
            with open(_path(), encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or not data.get("hash"):
                data = {}
        except Exception:  # noqa: BLE001
            data = {}
        _CACHE = data
        return _CACHE


def _save(data: dict) -> None:
    global _CACHE
    with _LOCK:
        paths.ensure_dirs()
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _path())
        try:
            os.chmod(_path(), 0o600)
        except OSError:
            pass
        _CACHE = data


def reset_cache() -> None:
    """测试与迁移用：丢掉内存缓存，下次强制重读磁盘。"""
    global _CACHE
    with _LOCK:
        _CACHE = None


# --------------------------------------------------------------------------- #
# 派生
# --------------------------------------------------------------------------- #
def _derive(password: str, salt: bytes, iterations: int = ITERATIONS) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode())


def validate_username(name: str) -> str:
    name = str(name or "").strip()
    if not (MIN_USER <= len(name) <= MAX_USER):
        raise ValueError(f"账号长度需要在 {MIN_USER}-{MAX_USER} 个字符之间")
    if any(ch.isspace() for ch in name) or any(ord(ch) < 32 for ch in name):
        raise ValueError("账号里不能有空格或控制字符")
    return name


def validate_password(password: str) -> str:
    password = str(password or "")
    if not (MIN_PASS <= len(password) <= MAX_PASS):
        raise ValueError(f"密码长度需要在 {MIN_PASS}-{MAX_PASS} 个字符之间")
    return password


# --------------------------------------------------------------------------- #
# 凭据
# --------------------------------------------------------------------------- #
def is_initialized() -> bool:
    return bool(_load().get("hash"))


def username() -> str:
    return str(_load().get("username") or "")


def created_at() -> float:
    return float(_load().get("created_at") or 0)


def setup(user: str, password: str) -> dict:
    """首次设置。已经初始化过就拒绝，避免被后来的人悄悄改掉管理员。"""
    with _LOCK:
        if is_initialized():
            raise ValueError("后台账号已经设置过了，请直接在设置里修改")
        user = validate_username(user)
        password = validate_password(password)
        salt = secrets.token_bytes(SALT_BYTES)
        now = time.time()
        data = {
            "version": 1,
            "username": user,
            "algo": ALGO,
            "iterations": ITERATIONS,
            "salt": _b64(salt),
            "hash": _b64(_derive(password, salt)),
            "session_secret": secrets.token_hex(32),
            "created_at": now,
            "updated_at": now,
        }
        _save(data)
        return data


def check(user: str, password: str) -> bool:
    data = _load()
    if not data.get("hash"):
        return False
    user = str(user or "").strip()
    if not user or user != data.get("username"):
        # 账号不对也要走一次派生，避免用响应时间区分「账号错误」和「密码错误」
        _derive(str(password or ""), b"dummy-salt-000000", int(data.get("iterations") or ITERATIONS))
        return False
    expect = _unb64(data["hash"])
    actual = _derive(str(password or ""), _unb64(data["salt"]), int(data.get("iterations") or ITERATIONS))
    return hmac.compare_digest(expect, actual)


def change_credentials(old_password: str, new_user: str | None, new_password: str | None) -> dict:
    """改账号 / 改密码。必须验旧密码；改完轮换会话密钥并返回新票据。"""
    with _LOCK:
        data = _load()
        if not is_initialized():
            raise ValueError("还没有设置后台账号")
        if not check(username(), old_password):
            raise ValueError("当前密码不正确")
        if new_user is not None:
            data["username"] = validate_username(new_user)
        if new_password:
            new_password = validate_password(new_password)
            salt = secrets.token_bytes(SALT_BYTES)
            data["salt"] = _b64(salt)
            data["hash"] = _b64(_derive(new_password, salt))
            data["iterations"] = ITERATIONS
        data["session_secret"] = secrets.token_hex(32)
        data["updated_at"] = time.time()
        _save(data)
        return data


# --------------------------------------------------------------------------- #
# 会话票据
# --------------------------------------------------------------------------- #
def _sign(payload: str) -> str:
    secret = str(_load().get("session_secret") or "")
    if not secret:
        return ""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]


def create_session(user: str | None = None) -> str:
    user = user or username()
    payload = base64.urlsafe_b64encode(
        json.dumps({"u": user, "exp": int(time.time()) + SESSION_TTL}, separators=(",", ":")).encode()
    ).decode()
    return payload + "." + _sign(payload)


def read_session(ticket: str) -> str | None:
    if not ticket or "." not in ticket:
        return None
    payload, _, sig = ticket.rpartition(".")
    if not payload or not sig:
        return None
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    except Exception:  # noqa: BLE001
        return None
    if int(data.get("exp") or 0) < time.time():
        return None
    user = str(data.get("u") or "")
    return user if user and user == username() else None


# --------------------------------------------------------------------------- #
# 登录限速
# --------------------------------------------------------------------------- #
def throttled(ip: str) -> int:
    """返回还需要等待的秒数，0 表示可以继续尝试。"""
    now = time.time()
    with _LOCK:
        hits = [t for t in _FAILS.get(ip, []) if now - t < FAIL_WINDOW]
        _FAILS[ip] = hits
        if len(hits) < FAIL_MAX:
            return 0
        return int(FAIL_WINDOW - (now - hits[0])) + 1


def note_failure(ip: str) -> None:
    with _LOCK:
        _FAILS.setdefault(ip, []).append(time.time())


def clear_failures(ip: str) -> None:
    with _LOCK:
        _FAILS.pop(ip, None)


# --------------------------------------------------------------------------- #
# 环境变量直通（给不想手点「首次设置」的人 / 自动化用）
# --------------------------------------------------------------------------- #
def bootstrap_from_env() -> str:
    """`PANEL_USERNAME` + `PANEL_PASSWORD` 都给了、且还没初始化时，直接建好账号。"""
    if is_initialized():
        return ""
    user = (os.environ.get("PANEL_USERNAME") or "").strip()
    password = os.environ.get("PANEL_PASSWORD") or ""
    if not user or not password:
        return ""
    try:
        setup(user, password)
    except ValueError as exc:
        return f"环境变量里的账号密码不合法：{exc}"
    return f"已按环境变量创建后台账号：{user}"
