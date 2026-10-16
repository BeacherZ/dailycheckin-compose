#!/usr/bin/env python3
"""前端「契约」自测（离线，纯标准库，不起服务）。

锁三件容易在后续改动里被悄悄改回去的事：

1. **首屏不能预置某一屏的文案**。以前 index.html 里直接写着「设置后台账号」，
   于是已经登录的人打开面板会先看到一屏登录/注册页，等 /api/auth/status 回来
   才跳走（用户报的「先闪一秒登录页」）。现在 index.html 里只允许有中性的
   「正在连接面板…」，具体那一屏必须由 app.js 判定之后再画。
2. **默认排序是「已配置优先」**，卡片一行 4 个、列表一行 2 个。
3. localStorage 一律走 lsGet/lsSet —— 隐私模式下它会抛异常，
   不能因为读不到一个本地偏好就把整个面板搞崩。
4. **同排卡片必须等高**。meta 那行文案长短差很多（B 站会多出「普通会员 |
   硬币 1223 | 等级 5」这种尾巴），一旦允许它换行，那一张就会比同排高出一截
   （用户报的「第一个站点卡片比其他的高」）。所以 meta 固定单行 + 写死高度，
   完整文案挂到 title 上。

跑法：python3 tools/test_panel_static.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "panel", "static")

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(f"  [{'OK' if cond else 'FAIL'}]   {name}" + (f"  :: {detail}" if not cond else ""))


def read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


html = read("index.html")
js = read("app.js")
css = read("style.css")

print("=" * 66)
print("1) 首屏：index.html 不许预置登录/设置屏")

gate = re.search(r'<div class="[^"]*"\s+id="gate"[^>]*>(.*?)<!-- =+ 主界面', html, re.S)
check("index.html 里有 gate 区块", bool(gate))
if gate:
    body = gate.group(1)
    check("gate 里没有「设置后台账号」", "设置后台账号" not in body)
    check("gate 里没有「登录后台」", "登录后台" not in body)
    check("gate 里没有「登录」按钮文案", ">登录<" not in body)
    check("gate 默认是中性文案「正在连接面板…」", "正在连接面板" in body)
    check("gate 的表单默认带 hidden", re.search(r'id="gateForm"[^>]*class="hidden"', body) is not None)
    check("gate 自己不默认隐藏（否则慢网络下是一片空白）",
          re.search(r'class="gate"\s+id="gate"', body) is None and 'class="gate"' in gate.group(0),
          gate.group(0)[:80])

check("app.js 的 showGate 会先把表单放出来", 'gateForm").classList.remove("hidden")' in js)
check("app.js 里有上一次登录状态的本地提示", "dc_auth_hint" in js and "readHint" in js and "writeHint" in js)
check("启动时按提示先画主界面（不等接口）", "readHint().l === true" in js and "hideGate()" in js)
check("gateCheck 会把结论写回本地", js.count("writeHint(") >= 4, js.count("writeHint("))

print("2) localStorage 走安全封装（隐私模式会抛异常）")
bare = len(re.findall(r"\blocalStorage\.(get|set|remove)Item", js))
check("除封装本身外没有裸调用", bare == 2, f"发现 {bare} 处")
check("有 lsGet / lsSet 封装", "const lsGet" in js and "const lsSet" in js)
check("读历史视图偏好走封装", 'lsGet("dc_view")' in js)

print("3) 站点排序：默认已配置优先")
check("app.js 定义了排序取值", "SORT_MODES" in js)
check("默认取值是 configured", re.search(r'SORT_MODES\.includes\(lsGet\("dc_sort"\)\)\s*\?\s*lsGet\("dc_sort"\)\s*:\s*"configured"', js) is not None)
check("过滤之后统一过一遍排序", "return sortSites(currentSites().filter(" in js)
check("「已配置优先」用的是 configured 标志", "Number(!!b.configured) - Number(!!a.configured)" in js)
check("index.html 有排序下拉且默认项是「已配置优先」",
      re.search(r'<select id="sortSelect"[\s\S]*?<option value="configured">已配置优先</option>', html) is not None)
check("排序选择会被记下来", 'lsSet("dc_sort", S.sort)' in js)

print("4) 密度：卡片一行 4 个、列表一行 2 个")


def rule(selector):
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


def media_block(width):
    """取某个断点的整段 @media 内容（到下一个 @media 为止）。"""
    i = css.find(f"@media (max-width: {width}px)")
    if i < 0:
        return ""
    j = css.find("@media ", i + 1)
    return css[i: j if j > 0 else len(css)]


grid = rule(".grid")
lst = rule(".list")
check("卡片一行 4 列", "repeat(4, minmax(0, 1fr))" in grid, grid.strip()[:90])
check("网格顶部对齐（否则展开一张会把同排其它卡片拉高）", "align-items: start" in grid, grid.strip()[:90])
check("列表一行 2 列", "repeat(2, minmax(0, 1fr))" in lst, lst.strip()[:90])
check("卡片有 3 / 2 / 1 列的降级",
      "repeat(3, minmax(0, 1fr))" in media_block(1560)
      and "repeat(2, minmax(0, 1fr))" in media_block(1180)
      and ".grid { grid-template-columns: 1fr; }" in media_block(820))
check("列表窄屏回单列", ".list { grid-template-columns: 1fr; }" in media_block(1180))
check("单列布局下取消展开卡片的跨列", "grid-column: auto" in media_block(820))
check("卡片展开时跨两列", re.search(r"\.card\.open\s*\{\s*grid-column: span 2", css) is not None)
check("app.js 给展开的卡片加 open 类", 'class="card${open ? " open" : ""}"' in js)

print("5) 同排卡片等高：meta 固定单行")
meta_css = rule(".card-meta")
check("meta 不换行", "white-space: nowrap" in meta_css, meta_css.strip()[:110])
check("meta 溢出用省略号", "overflow: hidden" in meta_css and "text-overflow: ellipsis" in meta_css, meta_css.strip()[:110])
mh = re.search(r"height:\s*(\d+(?:\.\d+)?)px", meta_css)
mlh = re.search(r"line-height:\s*(\d+(?:\.\d+)?)px", meta_css)
mpb = re.search(r"padding:\s*0\s+\d+px\s+(\d+(?:\.\d+)?)px", meta_css)
check("meta 高度写死了（不是靠内容撑）", bool(mh), meta_css.strip()[:110])
check("height 正好 = 行高 + 下间距（改 padding 时这里会红，提醒一起改）",
      bool(mh and mlh and mpb) and float(mh.group(1)) == float(mlh.group(1)) + float(mpb.group(1)),
      f"height={mh and mh.group(1)} line-height={mlh and mlh.group(1)} padding-bottom={mpb and mpb.group(1)}")
check("完整 meta 挂到 title 上（截断的部分还能看到）", 'class="card-meta" title=' in js)
check("展开/收起后 meta 的 title 也跟着更新", "el.title = el.textContent" in js)

print("6) 视觉基建：统计条 / 图标 / 状态点")
check("顶栏统计收成一条 .statbar，不再是堆 .pill", 'class="statbar"' in html and 'class="pill' not in html)
check("统计项之间有分隔线", ".stat + .stat { border-left" in css)
check("状态徽章带前置圆点", ".badge::before" in css)
check("展开箭头是自绘 SVG 而不是字符 ▶", "▶" not in js and "const CHEVRON" in js)
check("顶栏按钮带内联图标", html.count("<button") >= 4 and 'id="btnRunAll"' in html and html.count("<svg") >= 6)
check("下拉框去掉了原生箭头（自绘 chevron）", "appearance: none" in css and "background-position: right 9px center" in css)
check("开关是自绘滑块", ".switch input::after" in css)
check("统计数字用等宽数字", "font-variant-numeric: tabular-nums" in css)

print("=" * 66)
print(f"通过 {len(passed)}  失败 {len(failed)}")
for one in failed:
    print("  ✗", one)
sys.exit(1 if failed else 0)
