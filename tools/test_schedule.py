#!/usr/bin/env python3
"""crontab 托管区块自测（离线，纯标准库，不碰真实 crontab）。

重点是**改项目名之后老部署不能出问题**：
面板只维护自己那段带标记的区块，标记从 `dailycheckin-compose managed` 换成了
`dailycheckin-plus managed`。老用户的 crontab 里还是老标记，
如果不认它，面板会以为「这段不是我管的」，再追加一段新的签到任务 ——
结果就是一天跑两遍、TG 收到两条通知。这里把这条路堵死并锁进测试。

跑法：python3 tools/test_schedule.py
"""
import importlib
import os
import shutil
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 用临时目录当工作目录，别碰到真实数据；环境变量必须在导入 paths 之前设好
TMP = tempfile.mkdtemp(prefix="dc-test-schedule-")
os.makedirs(os.path.join(TMP, "cron"), exist_ok=True)
os.environ["DC_HOME"] = TMP
os.environ["DC_CRON_PATH"] = os.path.join(TMP, "cron", "crontab_list.sh")

# 只把 panel 当成一个「壳」导入，避免执行 panel/__init__.py（它会连带导入整个服务端）
sys.path.insert(0, ROOT)
pkg = types.ModuleType("panel")
pkg.__path__ = [os.path.join(ROOT, "panel")]
sys.modules["panel"] = pkg

paths = importlib.import_module("panel.paths")
schedule = importlib.import_module("panel.schedule")

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name if cond else f"{name} :: {detail}")
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else " :: " + str(detail)))


def write(text):
    with open(paths.CRON_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read():
    with open(paths.CRON_PATH, encoding="utf-8") as f:
        return f.read()


def active_calls(text):
    """真正会被 cron 执行的签到行（注释掉的不算）。"""
    return [
        line
        for line in text.splitlines()
        if not line.strip().startswith("#") and "dailycheckin " in line and "cd " in line
    ]


OLD_BEGIN = "# >>> dailycheckin-compose managed >>>"
OLD_END = "# <<< dailycheckin-compose managed <<<"
RUN_LINE = f"0 9 * * * cd {paths.HOME} && dailycheckin >> {paths.LOG_DIR}/dailycheckin.log 2>&1"

# 老部署的文件：用户自己还有一条别的定时任务，加上老名字的托管区块
LEGACY = (
    f"TZ=Asia/Shanghai\nPATH=/usr/local/bin:/usr/bin:/bin\n\n"
    f"* * * * * echo 用户自己的任务\n\n"
    f"##############每日签到任务##############\n{OLD_BEGIN}\n{RUN_LINE}\n{OLD_END}\n"
)

print("=" * 66)
print("crontab 托管区块：改名后老标记仍要认，且升级成一整段")

# 1) 新标记是 dailycheckin-plus
check("托管标记用的是新项目名", schedule.BEGIN == "# >>> dailycheckin-plus managed >>>", schedule.BEGIN)
check("老标记进了兼容清单", "dailycheckin-compose" in schedule.MANAGED_MARKERS, schedule.MANAGED_MARKERS)

# 2) 文件不存在时，默认内容就是新标记
if os.path.exists(paths.CRON_PATH):
    os.remove(paths.CRON_PATH)
default = schedule.read_text()
check("默认 crontab 用新标记", schedule.BEGIN in default and schedule.END in default, default[-120:])

# 3) 老标记文件：要能被认出来（enabled、cron 时间都对），并且认出这不是「漂移检测」
write(LEGACY)
info = schedule.parse()
check("老标记被识别为已启用", info["enabled"] is True, info)
check("老标记里的 cron 时间读得出来", info["cron"] == "0 9 * * *", info)
check("老标记不算「检测到的野任务」", info["detected"] is False, info)

# 4) 改时间保存：老区块被就地替换成新标记，不能多出一段
back = schedule.set_schedule(True, "30 7 * * *")
check("保存返回已生效状态", back["enabled"] is True and back["cron"] == "30 7 * * *", back)
text = read()
check("升级后只剩一段托管区块", text.count("managed >>>") == 1, text)
check("老标记已被清掉", "dailycheckin-compose" not in text, text)
check("区块内是新时间", "30 7 * * *" in text, text)
check("用户自己的任务没被动", "* * * * * echo 用户自己的任务" in text, text)
check("只保留一个签到调用", len(active_calls(text)) == 1, text)

# 5) 关掉定时签到：同样只替换这一段的正文，不新增区块
schedule.set_schedule(False, "30 7 * * *")
text = read()
check("关闭后仍只有一段区块", text.count("managed >>>") == 1, text)
check("关闭后正文是注释", "# 定时签到已在面板中关闭" in text, text)
check("关闭后不再有签到调用", not active_calls(text), text)

# 6) 再打开：还是那一段
schedule.set_schedule(True, "0 8,20 * * *")
text = read()
check("重新开启仍只有一段区块", text.count("managed >>>") == 1, text)
check("重新开启写回了新时间", "0 8,20 * * *" in text, text)
check("重新开启后只有一个签到调用", len(active_calls(text)) == 1, text)

# 7) 从官方镜像迁过来的 crontab（没有托管标记，只有一行裸调用）
#    这行必须被接管并注释留档，否则它和新区块并存 = 一天跑两遍
write(f"TZ=Asia/Shanghai\n{RUN_LINE}\n")
info = schedule.parse()
check("裸调用也能识别为已启用", info["enabled"] is True and info["cron"] == "0 9 * * *", info)
check("裸调用标记为「检测到的」", info["detected"] is True, info)
schedule.set_schedule(True, "0 9 * * *")
text = read()
check("裸调用被包进新的托管区块", text.count("managed >>>") == 1, text)
check("接管后只剩一个真实签到调用", len(active_calls(text)) == 1, text)
check("裸调用原文被注释留档", "# 已由 dailycheckin-plus 面板接管" in text, text)
block_body = schedule.BLOCK_RE.search(text).group(1)
check("唯一的真实调用就在托管区块里", all(l in block_body for l in active_calls(text)), text)

# 8) cron 表达式校验
check("5 字段以外拒绝", schedule.validate("0 9 * *") is not None, schedule.validate("0 9 * *"))
check("含非法字符拒绝", schedule.validate("0 9 * * 天") is not None, schedule.validate("0 9 * * 天"))
check("合法表达式通过", schedule.validate("0 */6 * * *") is None)

print("=" * 66)
print(f"通过 {len(passed)}  失败 {len(failed)}")
for one in failed:
    print("  ✗", one)

shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if failed else 0)
