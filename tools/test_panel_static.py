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
5. **站点配置是弹窗，不是在卡片里就地展开**。就地展开那张卡会横跨两列，把一排
   四个的节奏打乱、右边空出一大片（用户就是这么反馈的）。点卡片 = 打开
   `#siteDlg`，卡片本身只有「logo + 站名 + 分类 + 状态 + 一行概况」。

跑法：python3 tools/test_panel_static.py
"""
import os
import re
import sys
import tempfile

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
check("卡片不再就地展开（没有 .card.open 跨列）", ".card.open" not in css)

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

print("7) 站点配置走弹窗，不再就地展开卡片")
check("index.html 里有站点配置弹窗", re.search(r'<dialog id="siteDlg"', html) is not None)
check("弹窗内容区带 data-key（表单事件靠它认站点）", re.search(r'id="siteDlgBody"[^>]*data-key', html) is not None)
check("弹窗底栏有 添加 / 立即签到 / 保存 三个动作",
      all(f'id="{i}"' in html for i in ("siteDlgAdd", "siteDlgRun", "siteDlgSave")))
check("卡片整块可点（data-action=open + role=button，键盘也能进）",
      'data-action="open" role="button" tabindex="0"' in js)
check("列表行的「配置」按钮还在", 'data-action="open" data-key="${site.key}"' in js)
check("就地展开的痕迹清干净了（.card.open / .card-body / S.expanded / toggle）",
      ".card-body" not in css and "S.expanded" not in js and 'data-action="toggle"' not in js)
check("工具条去掉了「展开全部 / 收起全部」", "btnExpandAll" not in html and "btnCollapseAll" not in html)
check("用 showModal 打开、close 事件统一收尾",
      "dlg.showModal()" in js and '.addEventListener("close", onSiteDialogClosed)' in js)
check("弹窗的三段式布局必须限定 [open]（无条件 display:flex 会盖掉浏览器默认的 dialog:not([open]){display:none}，弹窗关不掉）",
      re.search(r"#siteDlg\[open\]\s*\{[^}]*display:\s*flex", css) is not None)
check("打开弹窗不再强制切回卡片视图（列表视图里也能直接配）", 'S.view = "card";' not in js)
check("操作按钮在弹窗底栏而不是滚动的编辑区里（改 cookie 时「保存」始终看得见）",
      re.search(r'class="dlg-foot">[\s\S]{0,600}?data-action="save"', html) is not None)
check("提示会搬进打开的弹窗里（原生 dialog 在顶层，页面上的提示会被盖住）",
      'document.querySelector("dialog[open]")' in js)
check("「立即签到」先关弹窗再开日志抽屉（抽屉排在弹窗下面，不关就看不见）",
      re.search(r'action === "run"\)\s*\{\s*closeSite\(\)', js) is not None)
check("卡片右侧箭头表示「进入」而不是「展开」（没有旋转态）", ".chev.open" not in css)
check("表单类站点的字段直接摊开（不再藏进「其它参数（可选）」折叠条里，"
      "否则新建账号后连账号密码框都找不到）",
      re.search(r'site\.credential === "cookie"\s*\?\s*`<details class="extras"', js) is not None)
check("cookie 类站点的可选参数仍然收在折叠条里",
      "其它参数（${(site.fields || []).length} 项，可选）" in js)

print("8) 推送通知：按渠道分组装进方框")
check("index.html 用分组容器（不再是 27 个输入框平铺）",
      re.search(r'class="notices"\s+id="noticeGroups"', html) is not None and "noticeFields" not in html)
check("app.js 渲染到 #noticeGroups", '$("noticeGroups").innerHTML = noticeHTML(st)' in js)
check("方框是「头 / 字段 / 状态」三段", 'class="nbox-head"' in js and 'class="nbox-fields"' in js and 'class="nbox-foot"' in js)
check("字段多的渠道整行铺开（跟后端 wide 标志联动）", 'nbox${g.wide ? " wide" : ""}' in js)
check("分组数据来自后端，不在前端写死渠道名", "st.notice_groups" in js and "notice_keys" in js)
# 同排等高：靠 grid 拉伸 + 状态行钉底，而不是给写死的高度（写死的话内容一多就溢出）
notices_css = rule(".notices")
check("方框网格同排等高（align-items: stretch）", "align-items: stretch" in notices_css, notices_css.strip()[:110])
nbox_css = rule(".nbox")
check("方框自身不写死高度（内容多的渠道会溢出）", "height:" not in nbox_css, nbox_css.strip()[:110])
check("方框是纵向 flex（状态行才能钉到底）", "display: flex" in nbox_css and "flex-direction: column" in nbox_css, nbox_css.strip()[:110])
check("状态行钉在方框底部（拉高时空白落在字段与状态之间，不会看着错位）",
      re.search(r"\.nbox-foot\s*\{[^}]*margin:\s*auto\s+0\s+0", css) is not None)
check("整行铺开用 1 / -1（窄屏只剩一列时 span 2 会凭空多出一列）",
      re.search(r"\.nbox\.wide\s*\{\s*grid-column:\s*1\s*/\s*-1", css) is not None)
check("字段网格自适应列数（宽方框自然排更多列）",
      "grid-template-columns: repeat(auto-fit, minmax(146px, 1fr))" in rule(".nbox-fields"))
check("配置键放不下时省略号截断，完整值挂 title", "text-overflow: ellipsis" in rule(".nf-key") and 'title="${esc((full || label)' in js)
check("表单事件仍按 data-notice 取值（保存逻辑没被改坏）",
      'document.querySelectorAll("[data-notice]")' in js and 'data-notice="${esc(key)}"' in js)
check("保存按钮还在", 'id="btnSaveNotice"' in html)

print("9) 更新提示：只在设置页最下方（首页不再有那块）")
# 首页右下角曾有一处常驻小牌，用户嫌挤让删掉了 —— 这组断言就是防止它被加回来
# （也防止删的时候把设置页那一块一起删掉）。
check("首页没有页脚区块了", 'app-foot' not in html and '<footer' not in html)
check("首页也不再有那套页脚 id", not any(i in html for i in ("footRepo", "footUpdate", "footDot", "btnFootCheck")))
check("页脚专属的样式也清干净了（不留死代码）",
      not any(s in css for s in (".app-foot {", ".foot-box {", ".foot-line {", "#footRepoName")))
check("首页引用的 app.js 也不再去找那些 id", "footUpdate" not in js and "footDot" not in js)
check("设置页最下方有「关于本项目」", "关于本项目" in html and 'id="aboutRepo"' in html)
check("「关于本项目」里有项目仓库链接（新窗口打开，别把面板顶掉）",
      re.search(r'class="foot-repo" id="aboutRepo"[^>]*target="_blank"[^>]*rel="noopener', html) is not None)
check("仓库名用 <b>（.foot-repo b 的省略号样式靠它）", '<b id="aboutRepoName">' in html)
check("更新状态和「检查更新」按钮都在那一块里",
      'id="aboutUpdate"' in html and 'class="ghost tiny js-check-update"' in html)
check("全页只剩一个「检查更新」按钮（首页那个已经删掉）",
      html.count('class="ghost tiny js-check-update"') == 1, html.count('class="ghost tiny js-check-update"'))
check("app.js 用同一个处理器接住那个按钮",
      'document.querySelectorAll(".js-check-update").forEach' in js)
check("先画本地版本、再异步问 /api/update（首屏不等网络）",
      "paintUpdate(st.update)" in js and 'api("/update"' in js)
check("/api/update 只在点按钮时带 force=1（否则吃后端的 3 小时缓存）",
      'api("/update" + (force ? "?force=1" : ""))' in js)
check("四种结论都画到了（有新版本 / 已是最新 / 判断不了 / 检查失败）",
      all(t in js for t in ("有新版本（", "已是最新（", "判断不了", "检查更新失败")))
# 结论文字要短（细节挂 title），别把那一行撑得很难看。
check("结论文案是短句（细节挂 title）",
      "有新版本（${remote.short" in js and "已是最新（${info.short}）" in js
      and "`判断不了${remote.short" in js)
check("有新版本时给出更新命令", "docker compose pull" in js)
check("简版的 /api/state 不会把已查到的结论抹掉", "info.checked_at === undefined" in js)

print("10) 更新检查的后端契约（离线，只读源码）")
sys.path.insert(0, ROOT)
from panel import store, update  # noqa: E402

groups = store.notice_groups()
keys = [f["key"] for g in groups for f in g["fields"]]
check("渠道分组和扁平列表用的是同一份数据", keys == [k for k, _ in store.NOTICE_KEYS], f"{len(keys)} 个键")
check("27 个推送字段不多不少、没有重复", len(keys) == 27 and len(set(keys)) == 27, f"{len(keys)} / {len(set(keys))}")
check("只有字段最多的那一组整行铺开", sum(1 for g in groups if g["wide"]) == 1, [g["name"] for g in groups if g["wide"]])
check("每组都给得出短标签和完整标签（title 要用）",
      all(f["label"] and f["full"] for g in groups for f in g["fields"]))
update_src = open(os.path.join(ROOT, "panel", "update.py"), encoding="utf-8").read()
# 注意：别断言 build_stamp() 在本仓库里返回空 —— CI 是带 .git 的 checkout，
# 那里它读得到 HEAD（本地没 .git 才读不到）。要断言「拿不到就别编」，
# 得指一个确定不是仓库的目录。
check("构建溯源在非仓库目录下返回空提交（不编造）",
      update._git_stamp(tempfile.mkdtemp())["commit"] == "")
check("页脚与更新检查用的是同一个锚点（local_info 与 build_stamp 一致）",
      update.local_info("9.9.9")["commit"] == update.build_stamp()["commit"])
check("远端提交和本地提交都认得出才敢下「要不要更新」的结论",
      "(mine != theirs) if (mine and theirs) else None" in update_src)
check("检查结果有缓存（GitHub 匿名接口 60 次/小时，不能当心跳打）",
      "CACHE_TTL = 3 * 3600" in update_src)

print("=" * 66)
print(f"通过 {len(passed)}  失败 {len(failed)}")
for one in failed:
    print("  ✗", one)
sys.exit(1 if failed else 0)
