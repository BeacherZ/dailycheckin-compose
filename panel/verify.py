"""Cookie 在线有效性校验。

设计原则：**宁可说「无法判定」，也不误报「已失效」。**
网络不通、接口改版、返回结构不认识 —— 这些情况一律返回 `ok=None`，
只有站点接口明确回了「未登录 / 已过期」才判定为失效，避免把好 cookie 标成坏的。

另外所有请求都是独立的 12 秒超时，不会卡住面板。
"""

from __future__ import annotations

import gzip
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

from . import cookies as ck

__all__ = ["verify_account", "VERIFIERS", "verify_site"]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT = 12

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


class Resp:
    def __init__(self, status: int, text: str, url: str, headers=None) -> None:
        self.status = status
        self.text = text
        self.url = url
        self.headers = headers or {}


def http(
    url: str,
    cookie: str | None = None,
    headers: dict | None = None,
    data: bytes | None = None,
    method: str | None = None,
    timeout: int = TIMEOUT,
) -> Resp:
    """极简 GET/POST。只用标准库，容器里没有任何额外依赖。

    HTTP 4xx/5xx **不抛异常**，而是把状态码和响应体一起返回 —— 有些站点
    （比如有道）恰恰是用 500 + 一段 JSON 来表达「登录已失效」的。
    """
    hdr = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "identity",
    }
    if headers:
        hdr.update(headers)
    if cookie:
        hdr["Cookie"] = cookie
    if data is not None and "Content-Type" not in hdr:
        hdr["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    req = urllib.request.Request(url, data=data, headers=hdr, method=method)

    def _read(resp) -> Resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        charset = resp.headers.get_content_charset() or "utf-8"
        try:
            text = raw.decode(charset, errors="replace")
        except LookupError:
            text = raw.decode("utf-8", errors="replace")
        return Resp(resp.status, text, resp.url, dict(resp.headers))

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
            return _read(resp)
    except urllib.error.HTTPError as exc:
        return _read(exc)


def _json(resp: Resp):
    try:
        return json.loads(resp.text)
    except Exception:  # noqa: BLE001
        return None


def ok(message: str, user: str | None = None, **extra) -> dict:
    out = {"ok": True, "user": user, "message": message}
    out.update(extra)
    return out


def bad(message: str, **extra) -> dict:
    out = {"ok": False, "user": None, "message": message}
    out.update(extra)
    return out


def unknown(message: str, **extra) -> dict:
    out = {"ok": None, "user": None, "message": message}
    out.update(extra)
    return out


# --------------------------------------------------------------------------- #
# 各站点校验器
# --------------------------------------------------------------------------- #
def v_bilibili(cookie: str, account: dict) -> dict:
    try:
        resp = http(
            "https://api.bilibili.com/x/web-interface/nav",
            cookie=cookie,
            headers={"Referer": "https://www.bilibili.com/"},
        )
    except Exception as exc:  # noqa: BLE001
        return unknown(f"请求 B 站接口失败：{exc}")
    data = _json(resp)
    if not isinstance(data, dict):
        return unknown("B 站接口返回了非 JSON 内容，可能被风控拦截")
    code = data.get("code")
    if code == -101:
        return bad("B 站返回「账号未登录」，cookie 已失效或复制不完整")
    if code != 0:
        return unknown(f"B 站接口返回 code={code}：{data.get('message')}")
    inner = data.get("data") or {}
    if not inner.get("isLogin"):
        return bad("B 站接口显示未登录")
    money = inner.get("money")
    vip = "大会员" if inner.get("vipStatus") else "普通会员"
    msg = f"{vip}｜硬币 {money}｜等级 {inner.get('level_info', {}).get('current_level')}"
    return ok(msg, user=inner.get("uname"))


def v_tieba(cookie: str, account: dict) -> dict:
    try:
        resp = http("https://tieba.baidu.com/dc/common/tbs", cookie=cookie)
    except Exception as exc:  # noqa: BLE001
        return unknown(f"请求贴吧接口失败：{exc}")
    data = _json(resp)
    if not isinstance(data, dict):
        return unknown("贴吧接口返回了非 JSON 内容")
    if not data.get("is_login"):
        return bad("贴吧返回未登录，BDUSS 已失效")
    user = None
    try:
        info = _json(http("https://zhidao.baidu.com/api/loginInfo", cookie=cookie))
        if isinstance(info, dict) and info.get("userName"):
            user = info.get("userName")
    except Exception:  # noqa: BLE001
        pass
    return ok("登录态正常", user=user)


def v_youdao(cookie: str, account: dict) -> dict:
    """有道失效时接口会返回 HTTP 500 + {"error":"207","message":"AUTHENTICATION_FAILURE..."}。"""
    user = None
    try:
        pairs = dict(ck.items_from_cookie(cookie))
        parts = pairs.get("YNOTE_PERS", "").split("||")
        if len(parts) >= 2:
            user = parts[-2] or None
    except Exception:  # noqa: BLE001
        pass
    try:
        resp = http(
            "https://note.youdao.com/yws/api/daupromotion?method=sync",
            cookie=cookie,
            data=b"",
            method="POST",
            headers={"Referer": "https://note.youdao.com/web/"},
        )
    except Exception as exc:  # noqa: BLE001
        return unknown(f"请求有道接口失败：{exc}")
    body = resp.text or ""
    if "AUTHENTICATION_FAILURE" in body or ("207" in body and '"error"' in body):
        return bad("有道返回未认证，YNOTE_PERS / YNOTE_SESS 已失效")
    if "rewardSpace" in body or "space" in body.lower():
        return ok("登录态正常", user=user)
    return unknown(f"有道返回了预期之外的内容（HTTP {resp.status}），无法判定")


def v_iqiyi(cookie: str, account: dict) -> dict:
    pairs = dict(ck.items_from_cookie(cookie))
    p00001 = pairs.get("P00001", "")
    if not p00001:
        return bad("cookie 里没有 P00001，无法校验")
    user = None
    raw_p2 = pairs.get("P00002", "")
    if raw_p2:
        try:
            info = json.loads(urllib.parse.unquote(raw_p2))
            user = info.get("nickname") or info.get("user_name")
        except Exception:  # noqa: BLE001
            pass
    try:
        resp = http(
            "http://serv.vip.iqiyi.com/vipgrowth/query.action?P00001=" + urllib.parse.quote(p00001),
            headers={"Referer": "https://www.iqiyi.com/"},
        )
    except Exception as exc:  # noqa: BLE001
        return unknown(f"请求爱奇艺接口失败：{exc}")
    data = _json(resp)
    if not isinstance(data, dict):
        return unknown("爱奇艺接口返回了非 JSON 内容")
    if data.get("code") == "A00000":
        inner = data.get("data") or {}
        return ok(f"VIP 等级 {inner.get('level')}｜成长值 {inner.get('growthvalue')}", user=user)
    return bad(f"爱奇艺返回：{data.get('msg') or data.get('code')}")


def v_v2ex(cookie: str, account: dict) -> dict:
    try:
        resp = http(
            "https://www.v2ex.com/settings",
            cookie=cookie,
            headers={"Referer": "https://www.v2ex.com/"},
        )
    except Exception as exc:  # noqa: BLE001
        return unknown(f"请求 V2EX 失败：{exc}")
    if resp.status != 200:
        return unknown(f"V2EX 返回 HTTP {resp.status}，无法判定（可能被风控拦截）")
    if "/signin" in (resp.url or ""):
        return bad("V2EX 跳转到了登录页，A2 已失效")
    text = resp.text
    if "需要先登录" in text or "请输入用户名" in text or "请先登录" in text:
        return bad("V2EX 提示需要登录，A2 已失效")
    m = re.search(r'href="/member/([^"/?]+)"', text)
    return ok("登录态正常", user=m.group(1) if m else None)


def v_smzdm(cookie: str, account: dict) -> dict:
    try:
        resp = http(
            "https://zhiyou.smzdm.com/user/",
            cookie=cookie,
            headers={"Referer": "https://m.smzdm.com/"},
        )
    except Exception as exc:  # noqa: BLE001
        return unknown(f"请求什么值得买失败：{exc}")
    if "/user/login" in resp.url or "passport.smzdm.com" in resp.url:
        return bad("被重定向到登录页，cookie 已失效")
    m = re.search(r'<a href="https://zhiyou\.smzdm\.com/user">\s*(.*?)\s*</a>', resp.text, re.S)
    name = (m.group(1).strip() if m else "") or None
    if name:
        return ok("登录态正常", user=name)
    return unknown("页面结构与预期不同，未能确认登录态")


def v_baidupan(cookie: str, account: dict) -> dict:
    """未登录时返回 {"errno":-6,"errmsg":"Invalid Bduss"}。"""
    try:
        resp = http(
            "https://pan.baidu.com/rest/2.0/xpan/nas?method=uinfo&clienttype=0&app_id=250528&web=1",
            cookie=cookie,
            headers={"Referer": "https://pan.baidu.com/"},
        )
    except Exception as exc:  # noqa: BLE001
        return unknown(f"请求百度网盘失败：{exc}")
    data = _json(resp)
    if not isinstance(data, dict):
        return unknown(f"百度网盘返回了非 JSON 内容（HTTP {resp.status}）")
    errno = data.get("errno")
    if errno == 0:
        return ok("登录态正常", user=data.get("baidu_name") or data.get("netdisk_name"))
    if data.get("errmsg") or errno in (-6, 2):
        return bad(f"百度网盘返回 {data.get('errmsg') or ('errno=' + str(errno))}，BDUSS 已失效")
    return unknown(f"百度网盘返回 errno={errno}，无法判定")


def v_aolaxing(cookie: str, account: dict) -> dict:
    try:
        resp = http(
            "http://service.100bt.com/creditmall/my/user_info.jsonp",
            cookie=cookie,
            headers={"Referer": "http://www.100bt.com/"},
        )
    except Exception as exc:  # noqa: BLE001
        return unknown(f"请求百田接口失败：{exc}")
    data = _json(resp)
    if not isinstance(data, dict):
        return unknown("百田接口返回了非 JSON 内容")
    result = data.get("jsonResult") or {}
    inner = result.get("data") if isinstance(result, dict) else None
    if not isinstance(inner, dict):
        return bad("百田接口未返回用户信息，登录态已失效")
    return ok(f"积分 {inner.get('credit')}｜累计 {inner.get('creditHistory')}", user=inner.get("phoneNum"))


def _discuz(forum: str, name: str):
    def _verify(cookie: str, account: dict) -> dict:
        try:
            resp = http(
                forum + "/home.php?mod=spacecp",
                cookie=cookie,
                headers={"Referer": forum + "/forum.php"},
            )
        except Exception as exc:  # noqa: BLE001
            return unknown(f"请求{name}失败：{exc}")
        text = resp.text
        if re.search(r"需要先登录|还没有登录|尚未登录|请先登录|立即登录", text):
            return bad(f"{name}提示需要登录，cookie 已失效")
        user = None
        for pattern in (
            r'<a href="home\.php\?mod=space&uid=\d+"[^>]*>([^<]{1,24})</a>',
            r'class="dropmenu"[^>]*>\s*<a[^>]*>([^<]{1,24})</a>',
            r'id="loginuser"[^>]*>([^<]{1,24})<',
        ):
            m = re.search(pattern, text)
            if m and m.group(1).strip():
                user = m.group(1).strip()
                break
        return ok("登录态正常", user=user)

    return _verify


VERIFIERS = {
    "bilibili": v_bilibili,
    "tieba": v_tieba,
    "youdao": v_youdao,
    "iqiyi": v_iqiyi,
    "v2ex": v_v2ex,
    "smzdm": v_smzdm,
    "baidupan": v_baidupan,
    "aolaxing": v_aolaxing,
    "enshan": _discuz("https://www.right.com.cn/forum", "恩山论坛"),
    "fnnasclub": _discuz("https://club.fnnas.com", "飞牛论坛"),
}

NO_VERIFIER_HINT = "该站点没有公开的登录态接口，点「立即签到」用运行结果来判断更准确"


def verify_account(site_key: str, account: dict, verifier: str | None = None) -> dict:
    """校验单个账号；返回 {ok, user, message}。`ok=None` 表示无法判定。"""
    meta_verifier = verifier
    if meta_verifier is None:
        from . import catalog

        meta_verifier = catalog.site_meta(site_key).get("verify")
    if not meta_verifier:
        return unknown(NO_VERIFIER_HINT)
    func = VERIFIERS.get(meta_verifier)
    if func is None:
        return unknown(NO_VERIFIER_HINT)
    cookie = str(account.get("cookie") or "")
    if not cookie.strip():
        return bad("没有填写 cookie")
    return func(cookie, account)


def verify_site(site_key: str, accounts: list[dict], verifier: str | None = None) -> list[dict]:
    return [verify_account(site_key, account, verifier) for account in accounts]
