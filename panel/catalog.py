"""站点元数据。

这里的 `required` 是从引擎源码里逐站点读出来的必填 cookie 字段：

* bilibili/main.py   `bilibili_cookie = {item.split("=")[0]: item.split("=")[1] for ...}`
* tieba/main.py      取 `BDUSS`，没有就直接 `raise ValueError`
* iqiyi/main.py      `parse_cookie()` 取 `P00001 / P00002 / P00003`
* youdao/main.py     取 `YNOTE_PERS` 解析 uid
* v2ex/main.py       取 `A2`
* ...

有了这张表，面板就能在**不发任何网络请求**的前提下抓出「cookie 复制不全」这类最常见的问题。
"""

from __future__ import annotations

from . import cookies as ck

# --------------------------------------------------------------------------- #
# 站点元数据
# --------------------------------------------------------------------------- #
SITE_META: dict[str, dict] = {
    "BILIBILI": {
        "label": "哔哩哔哩",
        "emoji": "📺",
        "group": "视频",
        "required": ["SESSDATA", "bili_jct"],
        "recommended": ["DedeUserID", "buvid3"],
        "verify": "bilibili",
        "howto": "登录 bilibili.com → F12 → 应用/Application → Cookies → bilibili.com，"
        "复制 SESSDATA、bili_jct、DedeUserID（直接全选整块复制更省事）",
        "fields": [
            {"key": "coin_num", "label": "投币数量", "type": "int", "default": 0, "help": "0 = 不投币，最多 5"},
            {"key": "coin_type", "label": "投币方式", "type": "int", "default": 1, "help": "1 = 投给同时点赞的视频"},
            {"key": "silver2coin", "label": "银瓜子兑硬币", "type": "bool", "default": False},
        ],
    },
    "TIEBA": {
        "label": "百度贴吧",
        "emoji": "💬",
        "group": "论坛",
        "required": ["BDUSS"],
        "recommended": ["STOKEN"],
        "verify": "tieba",
        "howto": "登录 tieba.baidu.com → F12 → Application → Cookies，至少复制 BDUSS（建议整块复制）",
    },
    "YOUDAO": {
        "label": "有道云笔记",
        "emoji": "📝",
        "group": "工具",
        "required": ["YNOTE_PERS"],
        "recommended": ["YNOTE_SESS", "YNOTE_CSTK"],
        "verify": "youdao",
        "howto": "登录 note.youdao.com → F12 → Application → Cookies，重点是 YNOTE_PERS 与 YNOTE_SESS",
    },
    "IQIYI": {
        "label": "爱奇艺",
        "emoji": "🎬",
        "group": "视频",
        "required": ["P00001"],
        "recommended": ["P00002", "P00003", "QC005", "__dfp"],
        "verify": "iqiyi",
        "howto": "登录 iqiyi.com → F12 → Application → Cookies，P00001 是登录票据，P00002 里含昵称",
    },
    "V2EX": {
        "label": "V2EX",
        "emoji": "🔷",
        "group": "论坛",
        "required": ["A2"],
        "recommended": ["PB3_SESSION"],
        "verify": "v2ex",
        "howto": "登录 v2ex.com → F12 → Application → Cookies，重点是 A2",
        "fields": [
            {
                "key": "proxy",
                "label": "代理地址",
                "type": "str",
                "default": "",
                "help": "可选。例：http://127.0.0.1:1080",
            }
        ],
    },
    "SMZDM": {
        "label": "什么值得买",
        "emoji": "🛒",
        "group": "电商",
        "required": [],
        "recommended": ["s", "__ckguid"],
        "verify": "smzdm",
        "howto": "登录 smzdm.com → F12 → Application → Cookies，整块复制（关键是 s 会话字段）",
    },
    "BAIDUWP": {
        "label": "百度网盘",
        "emoji": "☁️",
        "group": "云盘",
        "required": ["BDUSS"],
        "recommended": ["STOKEN", "BAIDUID"],
        "verify": "baidupan",
        "howto": "登录 pan.baidu.com → F12 → Application → Cookies，至少 BDUSS + STOKEN",
    },
    "AOLAXING": {
        "label": "奥拉星",
        "emoji": "🐉",
        "group": "游戏",
        "required": ["BT_LOGIN_tt_common"],
        "recommended": ["BT_AUTO_tt_common"],
        "verify": "aolaxing",
        "howto": "登录 www.100bt.com → F12 → Application → Cookies，BT_LOGIN_tt_common 是登录标记",
    },
    "ENSHAN": {
        "label": "恩山无线论坛",
        "emoji": "📡",
        "group": "论坛",
        "required": ["TWcq_2132_auth"],
        "recommended": ["TWcq_2132_saltkey"],
        "verify": "enshan",
        "howto": "登录 right.com.cn → F12 → Application → Cookies，Discuz 论坛需要 TWcq_2132_* 那几个字段",
    },
    "FNNASCLUB": {
        "label": "飞牛 NAS 论坛",
        "emoji": "🐮",
        "group": "论坛",
        "required": ["pvRK_2132_auth"],
        "recommended": ["pvRK_2132_saltkey"],
        "verify": "fnnasclub",
        "howto": "登录 club.fnnas.com → F12 → Application → Cookies，Discuz 论坛需要 pvRK_2132_* 那几个字段",
    },
    "KGQQ": {
        "label": "全民 K 歌",
        "emoji": "🎤",
        "group": "音乐",
        "required": ["uid", "openid", "openkey"],
        "recommended": ["muid"],
        "verify": None,
        "howto": "登录 kg.qq.com → F12 → Application → Cookies，uid / openid / openkey 三个都要",
    },
    "ALIYUN": {
        "label": "阿里云盘",
        "emoji": "🗄️",
        "group": "云盘",
        "required": [],
        "credential": "form",
        "verify": None,
        "howto": "refresh_token 通过 aliyun 开放接口获取，本项目不提供自动化抓取，请参考原项目文档",
        "fields": [
            {"key": "refresh_token", "label": "refresh_token", "type": "secret", "required": True},
        ],
    },
    "IMAOTAI": {
        "label": "i 茅台",
        "emoji": "🍶",
        "group": "生活",
        "required": [],
        "credential": "form",
        "verify": None,
        "howto": "需手机抓包获取 token / userid，并在网页里填写预约省市与经纬度",
        "fields": [
            {"key": "mobile", "label": "手机号", "type": "str", "required": True},
            {"key": "token", "label": "token", "type": "secret", "required": True},
            {"key": "userid", "label": "userid", "type": "secret", "required": True},
            {"key": "province", "label": "省份", "type": "str", "required": True},
            {"key": "city", "label": "城市", "type": "str", "required": True},
            {"key": "lat", "label": "纬度 lat", "type": "str", "required": True},
            {"key": "lng", "label": "经度 lng", "type": "str", "required": True},
            {"key": "reserve_rule", "label": "预约规则", "type": "int", "default": 0},
        ],
    },
    "ACFUN": {
        "label": "AcFun",
        "emoji": "🎯",
        "group": "视频",
        "required": [],
        "credential": "form",
        "verify": None,
        "howto": "AcFun 使用的是账号密码登录，没有 cookie",
        "fields": [
            {"key": "phone", "label": "手机号", "type": "str", "required": True},
            {"key": "password", "label": "密码", "type": "secret", "required": True},
        ],
    },
    "MIMOTION": {
        "label": "小米运动",
        "emoji": "👟",
        "group": "运动",
        "required": [],
        "credential": "form",
        "verify": None,
        "howto": "小米运动使用账号密码登录，可选设置刷步区间",
        "fields": [
            {"key": "phone", "label": "手机号/账号", "type": "str", "required": True},
            {"key": "password", "label": "密码", "type": "secret", "required": True},
            {"key": "min_step", "label": "最小步数", "type": "int", "default": 10000},
            {"key": "max_step", "label": "最大步数", "type": "int", "default": 19999},
        ],
    },
    "BAIDU": {
        "label": "百度站点提交",
        "emoji": "🔎",
        "group": "工具",
        "required": [],
        "credential": "form",
        "verify": None,
        "howto": "提交 sitemap 到百度搜索资源平台，不需要 cookie",
        "fields": [
            {"key": "data_url", "label": "URL 列表地址", "type": "str", "required": True},
            {"key": "submit_url", "label": "提交接口", "type": "secret", "required": True},
            {"key": "times", "label": "提交条数", "type": "int", "default": 100},
        ],
    },
}

DEFAULT_META = {
    "label": None,  # 用 checkin_map 里的中文名
    "emoji": "🧩",
    "group": "其它",
    "required": [],
    "recommended": [],
    "verify": None,
    "credential": "cookie",
    "howto": "整块复制该站点登录后的 cookie 即可",
    "site": "",
    "logo": "",
}

# --------------------------------------------------------------------------- #
# 官网地址与 LOGO
# --------------------------------------------------------------------------- #
# LOGO 直接引用**各站官网自己的 favicon**：
#   * 不依赖任何第三方图标服务（Google 的 favicon 接口在国内不可达）
#   * 前端一律带 `referrerpolicy="no-referrer"`，绕开部分 CDN 的防盗链判断
#   * 加载不出来会自动回退成 emoji，不会出现破图
# 这里每个地址都实测过能返回图片；V2EX 在国内需要代理才能访问，
# 所以它的 LOGO 在无代理环境下会自然回退成 emoji。
SITE_LINKS: dict[str, dict[str, str]] = {
    "BILIBILI": {"site": "https://www.bilibili.com/", "logo": "https://www.bilibili.com/favicon.ico"},
    "TIEBA": {"site": "https://tieba.baidu.com/", "logo": "https://tieba.baidu.com/favicon.ico"},
    "YOUDAO": {"site": "https://note.youdao.com/", "logo": "https://note.youdao.com/favicon.ico"},
    "IQIYI": {"site": "https://www.iqiyi.com/", "logo": "https://www.iqiyi.com/favicon.ico"},
    "V2EX": {"site": "https://www.v2ex.com/", "logo": "https://www.v2ex.com/favicon.ico"},
    "SMZDM": {"site": "https://www.smzdm.com/", "logo": "https://www.smzdm.com/favicon.ico"},
    "BAIDUWP": {"site": "https://pan.baidu.com/", "logo": "https://www.baidu.com/favicon.ico"},
    "AOLAXING": {"site": "https://www.100bt.com/", "logo": "https://www.100bt.com/favicon.ico"},
    "ENSHAN": {"site": "https://www.right.com.cn/forum/", "logo": "https://www.right.com.cn/forum/favicon.ico"},
    "FNNASCLUB": {"site": "https://club.fnnas.com/", "logo": "https://club.fnnas.com/favicon.ico"},
    "KGQQ": {"site": "https://kg.qq.com/", "logo": "https://kg.qq.com/favicon.ico"},
    "ALIYUN": {"site": "https://www.alipan.com/", "logo": "https://www.alipan.com/favicon.ico"},
    "IMAOTAI": {"site": "https://www.moutai519.com.cn/", "logo": "https://www.moutai519.com.cn/favicon.ico"},
    "ACFUN": {"site": "https://www.acfun.cn/", "logo": "https://www.acfun.cn/favicon.ico"},
    "MIMOTION": {"site": "https://www.mi.com/", "logo": "https://www.mi.com/favicon.ico"},
    "BAIDU": {"site": "https://ziyuan.baidu.com/", "logo": "https://ziyuan.baidu.com/favicon.ico"},
}


def scan_source() -> dict[str, str]:
    """不导入引擎、直接扫源码拿站点名。

    引擎的 `__init__.py` 会 `walk_packages` 导入所有站点模块，而每个站点模块都
    `import requests`。在某些精简环境里 requests 还没装好，这时导入会失败 ——
    但站点清单本身只写在 `class X(CheckIn): name = "中文名"` 里，扫一遍源码就能拿到。
    """
    import os
    import re

    from . import paths

    root = os.path.join(paths.HOME, "dailycheckin")
    if not os.path.isdir(root):
        return {}
    pattern = re.compile(r"class\s+(\w+)\s*\(\s*CheckIn\s*\)\s*:\s*\n(?:\s*\"\"\"[\s\S]*?\"\"\"\s*\n)?\s*name\s*=\s*[\"']([^\"']+)")
    found: dict[str, str] = {}
    for entry in sorted(os.listdir(root)):
        main_py = os.path.join(root, entry, "main.py")
        if not os.path.isfile(main_py):
            continue
        try:
            with open(main_py, encoding="utf-8") as f:
                source = f.read()
        except OSError:
            continue
        for match in pattern.finditer(source):
            found[match.group(1).upper()] = match.group(2)
    return found


def engine_sites() -> dict[str, str]:
    """从引擎里读出「站点 KEY -> 中文名」，失败时退回源码扫描，再失败返回空字典。

    引擎的 `dailycheckin.configs.checkin_map` 由 `CheckIn.__subclasses__()` 动态生成，
    所以上游新增站点时面板会自动带上，不需要改代码。
    """
    try:
        from dailycheckin.configs import checkin_map

        found = {key.upper(): value[0] for key, value in checkin_map.items()}
        if found:
            return found
    except Exception:  # noqa: BLE001 - 缺少依赖时降级，不影响面板启动
        pass
    return scan_source()


def merge_sites(discovered: dict) -> list[dict]:
    """把「引擎发现的站点」与「手工元数据」合并成前端要的结构。

    抽成独立函数是为了能脱离真实引擎直接测试：上游新加站点时，它会走到
    「元数据缺失」那条分支 —— label 取引擎里的中文名、LOGO 退回 emoji、
    `required` 为空（不做格式拦截）、`verify` 为空（没有在线校验按钮）、
    `known` 为 False（前端标注「通用配置」），其余能力照旧可用。
    """
    keys = sorted(set(discovered) | set(SITE_META))
    out: list[dict] = []
    for key in keys:
        meta = dict(DEFAULT_META)
        known = SITE_META.get(key, {})
        meta.update({k: v for k, v in known.items() if v is not None})
        links = SITE_LINKS.get(key, {})
        out.append(
            {
                "key": key,
                "label": meta.get("label") or discovered.get(key) or key,
                "emoji": meta.get("emoji", "🧩"),
                "group": meta.get("group", "其它"),
                "credential": meta.get("credential") or "cookie",
                "required": list(meta.get("required") or []),
                "recommended": list(meta.get("recommended") or []),
                "fields": list(meta.get("fields") or []),
                "verify": meta.get("verify"),
                "howto": meta.get("howto", ""),
                "site": links.get("site", ""),
                "logo": links.get("logo", ""),
                "known": key in SITE_META,
            }
        )
    return out


def all_sites() -> list[dict]:
    """合并「引擎发现的站点」与「手工元数据」，返回给前端。"""
    return merge_sites(engine_sites())


def missing_meta() -> list[str]:
    """引擎里有、但 panel/catalog.py 还没写元数据的站点。"""
    return sorted(k for k in engine_sites() if k not in SITE_META)


def site_meta(key: str) -> dict:
    for one in all_sites():
        if one["key"] == key.upper():
            return one
    meta = dict(DEFAULT_META)
    meta["key"] = key.upper()
    meta["label"] = key.upper()
    return meta


def required_of(key: str) -> list[str]:
    return list(site_meta(key).get("required") or [])


def has_required(items, key: str) -> list[str]:
    return ck.missing_required(items, required_of(key))


def coerce_field(key: str, field_key: str, value):
    """按 catalog 里声明的字段类型转换表单值（目前只有 int / bool 真的会转）。

    **为什么非转不可**：引擎会直接拿这些值做算术 —— B 站模块是
    `coin_num = coin_num - 今天已投的个数`。面板的输入框一律是 text，
    原样写回就是字符串 "5"，于是引擎抛
    `TypeError: unsupported operand type(s) for -: 'str' and 'int'`，
    **整个站点任务在投币那一步之前就断了**（日志表现为「第 1 个账号: ❌❌❌❌❌」
    后面跟一行 TypeError，投币 / 观看 / 分享全都没跑）。
    所以类型转换必须发生在写 config.json 之前，且以后端为准（不管前端怎么传）。

    空值退回该字段的 default；填了非整数就抛 ValueError（由调用方转成 400），
    绝不静默写成 0 —— 那样用户会以为配好了，实际是把功能关了。
    """
    meta = next(
        (f for f in (site_meta(key).get("fields") or []) if f.get("key") == field_key),
        None,
    )
    if not meta:
        return value
    kind = meta.get("type")
    label = meta.get("label") or field_key

    if kind == "int":
        if isinstance(value, bool):          # bool 是 int 的子类，必须先挡掉
            raise ValueError("「%s」要填整数" % label)
        if isinstance(value, int):
            return value
        text = str(value if value is not None else "").strip()
        if text == "":
            return meta.get("default", 0)
        try:
            return int(text, 10)
        except (TypeError, ValueError):
            raise ValueError("「%s」要填整数（现在是「%s」）" % (label, text))

    if kind == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    return value
