"""Cookie 解析与规范化。

为什么需要这个模块
------------------
dailycheckin 引擎里几乎所有站点都这样解析 cookie：

    {item.split("=")[0]: item.split("=")[1] for item in cookie.split("; ")}

也就是说它**硬依赖 `"; "`（分号 + 空格）**作为分隔符。从浏览器里复制出来的
cookie 常见的几种形态都会把它打挂：

* `a=1;b=2`            —— 没有空格，整条会被当成一个字段
* 每行一个 `name=value` —— 换行不会被识别
* `{"a":"1"}` / `[{"name":"a","value":"1"}]` —— JSON 导出格式
* `Cookie: a=1; b=2`   —— 带前缀
* curl 的 `-H 'Cookie: ...'` —— 整段命令

本模块把这些形态统一转成引擎要的格式，并在转不了 / 有隐患时给出明确提示，
而不是让用户面对一句 `AttributeError` 或者静默的签到失败。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

__all__ = [
    "CookieResult",
    "normalize",
    "build",
    "missing_required",
    "items_from_cookie",
    "parse_pairs",
]

SEP = "; "

# 值里出现这些字符时，引擎的 split 解析会出问题，需要提醒用户
_WS_RE = re.compile(r"\s")


@dataclass
class CookieResult:
    """规范化结果。"""

    ok: bool = False
    cookie: str = ""
    items: list[tuple[str, str]] = field(default_factory=list)
    source: str = "unknown"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.items)

    def needs_fix(self, raw: str) -> bool:
        """判断粘贴内容和引擎标准形态是否**实质**不同。

        只看分隔符风格，不纠结结尾那个分号 —— 引擎对
        `a=1; b=2` 和 `a=1; b=2;` 都能正确解析，都提示「需要规范化」会太吵。
        """
        if not self.ok or not raw:
            return False
        return raw.strip().rstrip(";").strip() != self.cookie.rstrip(";").strip()

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "cookie": self.cookie,
            "count": self.count,
            "keys": [k for k, _ in self.items],
            "source": self.source,
            "warnings": self.warnings,
            "errors": self.errors,
            "missing": self.missing,
            "duplicates": self.duplicates,
        }


# --------------------------------------------------------------------------- #
# 输入形态识别
# --------------------------------------------------------------------------- #
def _unwrap_quotes(text: str) -> str:
    for quote in ('"', "'", "`"):
        if len(text) >= 2 and text.startswith(quote) and text.endswith(quote):
            return text[1:-1].strip()
    return text


def _extract_from_command(raw: str) -> tuple[str, str] | None:
    """从 curl / DevTools 的请求头片段里抠出 cookie 串。"""
    # curl -H 'Cookie: a=b; c=d'
    m = re.search(r"(?:-H|--header)\s*(['\"])\s*cookie\s*:\s*(.*?)\1", raw, re.S | re.I)
    if m:
        return m.group(2), "curl -H"
    # curl -b 'a=b; c=d'
    m = re.search(r"(?:^|\s)(?:-b|--cookie)\s+(['\"])(.*?)\1", raw, re.S | re.I)
    if m:
        return m.group(2), "curl -b"
    # 形如 "Cookie: a=b; c=d" 的一行（可能夹在其它请求头中间）
    m = re.search(r"^[ \t]*cookie\s*:\s*(.+?)[ \t]*$", raw, re.M | re.I)
    if m:
        return m.group(1), "Cookie 头"
    return None


def _from_name_value_list(data: list) -> list[tuple[str, str]] | None:
    """[{"name": "a", "value": "1"}, ...] 这类结构。"""
    out: list[tuple[str, str]] = []
    for one in data:
        if isinstance(one, dict):
            name = one.get("name") or one.get("key") or one.get("Name")
            value = one.get("value")
            if value is None:
                value = one.get("val") or one.get("content")
            if name is None or value is None:
                return None
            out.append((str(name).strip(), str(value)))
        elif isinstance(one, str):
            if "=" not in one:
                return None
            key, _, value = one.partition("=")
            out.append((key.strip(), value.strip()))
        else:
            return None
    return out or None


def _try_json(raw: str) -> tuple[list[tuple[str, str]], str] | None:
    text = raw.strip()
    if not text or text[0] not in "[{":
        return None
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(data, dict):
        for key in ("cookies", "Cookies", "cookie"):
            inner = data.get(key)
            if isinstance(inner, list):
                items = _from_name_value_list(inner)
                if items:
                    return items, "JSON(cookies)"
        items = [(str(k), "" if v is None else str(v)) for k, v in data.items()]
        return (items, "JSON(对象)") if items else None
    if isinstance(data, list):
        items = _from_name_value_list(data)
        if items:
            return items, "JSON(数组)"
    return None


def _try_table(raw: str) -> tuple[list[tuple[str, str]], str] | None:
    """DevTools「Cookies」表格整块复制：name<TAB>value<TAB>domain...

    表格里每行至少要有「名称 + 值」两列。名称列不会含 `=`，
    含 `:` 的说明粘的是请求头而不是 cookie 表格，直接放弃交给后面的解析器。
    """
    lines = [line for line in raw.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    out: list[tuple[str, str]] = []
    for line in lines:
        if "\t" not in line and not re.search(r"\S {2,}\S", line):
            return None
        cols = [c.strip() for c in re.split(r"\t+|\s{2,}", line.strip())]
        if len(cols) < 2:
            return None
        if ":" in cols[0]:
            return None
        if "=" in cols[0]:
            # 第一列本身就是 `名称=值` 的写法，按键值对取，值到制表符为止
            name, _, value = cols[0].partition("=")
        else:
            name, value = cols[0], cols[1]
        if not name.strip():
            return None
        out.append((name.strip(), value))
    return (out, "表格粘贴") if out else None


def parse_pairs(raw: str) -> tuple[list[tuple[str, str]], list[str]]:
    """把 `k=v; k2=v2` 形态的串解析成键值对。"""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n+", SEP, text)  # 每行一个 cookie 的情况
    text = text.replace(";", SEP)  # 统一成 "; " 再切
    items: list[tuple[str, str]] = []
    skipped: list[str] = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            skipped.append(part[:60])
            continue
        key, _, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if not key:
            continue
        items.append((key, value))
    return items, skipped


def items_from_cookie(cookie: str) -> list[tuple[str, str]]:
    items, _ = parse_pairs(cookie or "")
    return items


# --------------------------------------------------------------------------- #
# 去重与体检
# --------------------------------------------------------------------------- #
def _dedupe(items: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[str]]:
    seen: dict[str, str] = {}
    order: list[str] = []
    duplicated: list[str] = []
    for key, value in items:
        if key in seen:
            if seen[key] != value:
                duplicated.append(key)
            seen[key] = value  # 后出现的覆盖先出现的，与浏览器行为一致
            continue
        seen[key] = value
        order.append(key)
    return [(k, seen[k]) for k in order], duplicated


def _inspect(items: list[tuple[str, str]]) -> list[str]:
    warnings: list[str] = []
    empty = [k for k, v in items if v == ""]
    if empty:
        warnings.append("以下字段的值为空，引擎会读到空字符串：" + "、".join(empty))
    truncated = [k for k, v in items if "=" in v]
    if truncated:
        warnings.append(
            "以下字段的值里含 `=`（常见于 Base64 结尾的填充符）："
            + "、".join(truncated)
            + "。引擎用 `split(\"=\")[1]` 取值，这类值会被截断到第一个 `=` 之前，可能造成校验失败"
        )
    semicolon = [k for k, v in items if ";" in v]
    if semicolon:
        warnings.append("以下字段的值里含 `;`，会被引擎误当成字段分隔：" + "、".join(semicolon))
    blank = [k for k, v in items if _WS_RE.search(v)]
    if blank:
        warnings.append("以下字段的值里含空白字符，请确认是否复制完整：" + "、".join(blank))
    return warnings


# --------------------------------------------------------------------------- #
# 对外接口
# --------------------------------------------------------------------------- #
def build(items: list[tuple[str, str]]) -> str:
    """按引擎要求拼回 cookie 串：`; ` 分隔，结尾一个 `;`（后面不带空格）。"""
    if not items:
        return ""
    return SEP.join(f"{k}={v}" for k, v in items) + ";"


def missing_required(items: list[tuple[str, str]], required) -> list[str]:
    have = {k.lower() for k, _ in items}
    return [k for k in required if k.lower() not in have]


def normalize(raw: str, required=(), site: str | None = None) -> CookieResult:
    """把任意粘贴形态的 cookie 规范化成引擎可用格式。"""
    result = CookieResult()

    if not raw or not raw.strip():
        result.errors.append("内容为空")
        return result

    text = _unwrap_quotes(raw.strip())

    items: list[tuple[str, str]] | None = None

    extracted = _extract_from_command(text)
    if extracted:
        text, result.source = extracted[0], extracted[1]
        text = _unwrap_quotes(text.strip())

    parsed = _try_json(text)
    if parsed:
        items, result.source = parsed

    if items is None:
        parsed = _try_table(text)
        if parsed:
            items, result.source = parsed

    if items is None:
        items, skipped = parse_pairs(text)
        result.source = result.source if result.source != "unknown" else "键值对"
        if skipped:
            result.warnings.append("已忽略无法解析的片段：" + "；".join(skipped))
        if not items:
            result.errors.append("没有解析出任何 `名称=值` 片段，请检查是不是复制到了别的内容")
            # 哪怕整体解析失败，也把「这个站点缺哪些必填字段」告诉用户
            result.missing = list(missing_required([], required))
            return result

    items, duplicated = _dedupe(items)
    if duplicated:
        result.duplicates = duplicated

    result.items = items
    result.warnings.extend(_inspect(items))
    result.missing = list(missing_required(items, required))
    result.cookie = build(items)
    result.ok = bool(items) and not result.missing
    return result


def _self_test() -> None:  # pragma: no cover - 手工自检用
    samples = {
        "标准": "SESSDATA=abc; bili_jct=def; DedeUserID=1",
        "无空格": "SESSDATA=abc;bili_jct=def",
        "换行": "SESSDATA=abc\nbili_jct=def",
        "带前缀": "Cookie: SESSDATA=abc; bili_jct=def",
        "JSON 对象": '{"SESSDATA":"abc","bili_jct":"def"}',
        "JSON 数组": '[{"name":"SESSDATA","value":"abc"},{"name":"bili_jct","value":"def"}]',
        "curl": "curl 'https://x' -H 'Cookie: SESSDATA=abc; bili_jct=def'",
        "表格": "SESSDATA\tabc\t.bilibili.com\t/\nbili_jct\tdef\t.bilibili.com\t/",
        "带引号": '"SESSDATA=abc; bili_jct=def"',
    }
    for name, raw in samples.items():
        r = normalize(raw, required=["SESSDATA", "bili_jct"])
        print(f"{name:10s} ok={r.ok!s:5s} src={r.source:10s} -> {r.cookie}")
    bad = normalize("hello world", required=["SESSDATA"])
    print("垃圾输入  ok=", bad.ok, bad.errors)
    warn = normalize("SESSDATA=a=b; bili_jct=def; empty=", required=["SESSDATA", "bili_jct"])
    print("隐患输入  warnings=", warn.warnings)


if __name__ == "__main__":  # pragma: no cover
    _self_test()
