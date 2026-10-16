#!/usr/bin/env python3
"""通知模块自测：一次签到**恒定只发一条**消息，带标题、带分隔行、结尾是项目地址。

引擎依赖 requests，这里塞一个假的进 sys.modules，只关心「发了几条、内容长什么样」。
纯标准库，CI 里直接跑：python3 tools/test_notice.py
"""
import importlib.util
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "dailycheckin", "utils", "message.py")
MAIN = os.path.join(ROOT, "dailycheckin", "main.py")

# --------------------------------------------------------------------------- #
# 假 requests：把所有出网调用记下来
# --------------------------------------------------------------------------- #
CALLS = []


class _Resp:
    status_code = 200
    text = ""

    def json(self):
        return {}


def _record(name):
    def fn(*args, **kwargs):
        url = kwargs.get("url") or (args[0] if args else "")
        CALLS.append({"fn": name, "url": url, **kwargs})
        return _Resp()

    return fn


fake = types.ModuleType("requests")
fake.post = _record("post")
fake.get = _record("get")
sys.modules["requests"] = fake

spec = importlib.util.spec_from_file_location("dc_message", MOD)
message = importlib.util.module_from_spec(spec)
spec.loader.exec_module(message)

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name if cond else f"{name} :: {detail}")
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else " :: " + str(detail)))


# --------------------------------------------------------------------------- #
# 与 dailycheckin/main.py 里 content_list 的构造方式保持一致
# --------------------------------------------------------------------------- #
TITLE = "每日签到 · 2026-10-16"
CONTENT = [
    "「V2EX 论坛」\n帐号信息: BZGOGO\n今日签到: 20261016 的每日登录奖励 13 铜币\n帐号余额: 38259.34",
    "「哔哩哔哩」\n第 1 个账号: ✅✅✅✅✅",
    f"开始时间: 2026-10-16 09:00:01\n任务用时: 0 秒\n当前版本: 25.12.9\n最新版本: 25.12.9\n项目地址: {message.PROJECT_URL}",
]

TG = {"tg_bot_token": "BOT", "tg_user_id": "123"}


def run(notice_info=None, content=None, title=TITLE):
    CALLS.clear()
    message.push_message(
        content_list=list(content if content is not None else CONTENT),
        notice_info=dict(notice_info or TG),
        title=title,
    )
    return [c for c in CALLS if "telegram" in str(c.get("url"))]


print("=" * 66)
print("通知模块：一条消息、带标题、结尾是项目地址")

# 1) 只发一条，且带标题
tg = run()
check("TG 只发一条", len(tg) == 1, f"实际 {len(tg)} 条")
body = tg[0]["data"]["text"] if tg else ""
check("正文首行是标题", body.startswith(f"【{TITLE}】"), repr(body[:60]))
check("标题与正文之间空一行", f"【{TITLE}】\n\n「V2EX 论坛」" in body, repr(body[:80]))
check("站点之间用分隔行隔开", body.count(message.SEPARATOR.strip()) == 2, body.count(message.SEPARATOR.strip()))
check("三个区块都在", all(k in body for k in ("V2EX 论坛", "哔哩哔哩", "开始时间")), body[:200])

# 2) 结尾的项目地址指向本项目，而不是上游
check("项目地址指向本项目", message.PROJECT_URL in body, message.PROJECT_URL)
check("正文里不再出现上游仓库地址", "Sitoi/dailycheckin" not in body, body[-120:])

# 3) 老配置里的 MERGE_PUSH=false 也必须被忽略 —— 它正是「还是两条」的元凶之一
for legacy in ("false", "0", "no", ""):
    tg = run({**TG, "merge_push": legacy})
    check(f"忽略旧配置 MERGE_PUSH={legacy!r}，仍是一条", len(tg) == 1, f"实际 {len(tg)} 条")

# 4) 没传标题时不该凭空冒出一对空括号
CALLS.clear()
message.push_message(content_list=["「A」\nok"], notice_info=dict(TG), title="")
plain = [c for c in CALLS if "telegram" in str(c.get("url"))][0]["data"]["text"]
check("不传标题就没有标题行", plain == "「A」\nok", repr(plain))

# 5) 空区块直接丢掉，不会留下空行
tg = run(content=["「A」\nok", "", None, "  ", "「B」\nok"])
text = tg[0]["data"]["text"]
check("空区块被丢弃，分隔行只剩一个", text.count(message.SEPARATOR.strip()) == 1, repr(text))
check("空区块不产生悬空标题", text.startswith(f"【{TITLE}】\n\n「A」"), repr(text[:60]))

# 6) 自带标题能力的渠道要收到标题
CALLS.clear()
message.push_message(
    content_list=list(CONTENT),
    notice_info={"pushplus_token": "T", "gotify_url": "https://g", "gotify_token": "gt", "ntfy_topic": "topic", "bark_url": "https://bark"},
    title=TITLE,
)
pushplus = [c for c in CALLS if "pushplus" in str(c.get("url"))]
gotify = [c for c in CALLS if "/message?token=" in str(c.get("url"))]
ntfy = [c for c in CALLS if "/topic" in str(c.get("url", ""))]
pp_title = json.loads(pushplus[0]["data"])["title"] if pushplus else None
check("PushPlus 用上了标题", pp_title == TITLE, f"实际 {pp_title!r}")
check("Gotify 用上了标题", gotify and gotify[0]["data"]["title"] == TITLE, gotify[0]["data"] if gotify else "没有调用")
check("ntfy 用上了标题", ntfy and "Title" in ntfy[0].get("headers", {}), ntfy[0].get("headers") if ntfy else "没有调用")

# 7) 企业微信应用消息里的回跳地址也必须是本项目
CALLS.clear()
message.push_message(
    content_list=list(CONTENT),
    notice_info={"qywx_corpid": "c", "qywx_agentid": "1", "qywx_corpsecret": "s", "qywx_touser": "u"},
    title=TITLE,
)
qywx = [c for c in CALLS if "qyapi.weixin.qq.com" in str(c.get("url"))]
check("企业微信卡片回跳本项目", qywx and message.PROJECT_URL in str(qywx[-1].get("data")), str(qywx[-1].get("data"))[:120] if qywx else "没有调用")

# 8) main.py 里的元信息块必须用同一个常量，别再写死上游地址
main_src = open(MAIN, encoding="utf-8").read()
check("main.py 结尾用 PROJECT_URL", "项目地址: {PROJECT_URL}" in main_src, main_src[-300:])
check("main.py 不再硬编码上游地址", "Sitoi/dailycheckin\"" not in main_src, "main.py 里还有写死的上游链接")

print("=" * 66)
print(f"通过 {len(passed)}  失败 {len(failed)}")
for one in failed:
    print("  ✗", one)
sys.exit(1 if failed else 0)
