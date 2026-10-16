#!/usr/bin/env python3
"""同步工具的离线自测：不需要网络，不碰真实引擎目录。

跑法::

    python tools/test_sync_upstream.py

验证四件事：

1. `patches/` 里的补丁能被解析成正确的目标路径与 hunk 数；
2. 补丁「反向 + 正向」一遭之后文件逐字节回到原样（说明重放是忠实的）；
3. 上游代码行号漂移时（前后插入若干行）补丁仍然打得上去；
4. 上游真的改写了补丁涉及的代码时，必须**报错而不是静默跳过**，并保证文件不被改坏。
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_upstream as S  # noqa: E402

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ %s" % name)
    else:
        FAIL += 1
        print("  ✗ %s  %s" % (name, detail))


def patch_files() -> list:
    if not os.path.isdir(S.PATCH_DIR):
        return []
    return [os.path.join(S.PATCH_DIR, n) for n in sorted(os.listdir(S.PATCH_DIR)) if n.endswith(".patch")]


def reverse(text: str) -> str:
    """把 diff 翻转成反向补丁（用于做往返测试）。

    注意两点，写错了就会得到一个「看起来像补丁、其实应用位置全错」的东西：

    * `---` / `+++` 这一对必须**成对交换且保持先后顺序**（`---` 永远在前）；
    * hunk 头的两侧行号（`-a,b +c,d`）要跟着换成 `-c,d +a,b`，
      否则加减行数不一样的 hunk 之后，行号提示会整体偏移。
    """
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
            out.append("--- " + lines[i + 1][4:])
            out.append("+++ " + line[4:])
            i += 2
            continue
        m = HUNK_RE.match(line)
        if m:
            a, alen, b, blen = m.group(1), m.group(2) or "1", m.group(3), m.group(4) or "1"
            out.append("@@ -%s,%s +%s,%s @@%s" % (b, blen, a, alen, line[m.end():]))
        elif line.startswith("+"):
            out.append("-" + line[1:])
        elif line.startswith("-"):
            out.append("+" + line[1:])
        else:
            out.append(line)
        i += 1
    return "\n".join(out) + "\n"


def main() -> int:
    print("== 1) 解析补丁 ==")
    files = patch_files()
    check("patches/ 下有补丁文件", bool(files), str(files))
    parsed_all = {}
    for path in files:
        text = open(path, encoding="utf-8").read()
        parsed = S.parse_udiff(text)
        name = os.path.basename(path)
        parsed_all[name] = (text, parsed)
        check("%s 解析出 1 个目标文件" % name, len(parsed) == 1, str([p for p, _ in parsed]))
        for rel, hunks in parsed:
            check("%s 目标是 dailycheckin/ 下的文件" % name, rel.startswith("dailycheckin/"), rel)
            check("%s 目标文件存在" % name, os.path.isfile(os.path.join(S.ROOT, rel)), rel)
            check("%s 至少 1 个 hunk" % name, len(hunks) > 0)

    print("\n== 2) 补丁往返（反向 + 正向）应逐字节还原 ==")
    work = tempfile.mkdtemp(prefix="dc-synctest-")
    try:
        for name, (text, parsed) in parsed_all.items():
            for rel, _hunks in parsed:
                src = os.path.join(S.ROOT, rel)
                dst = os.path.join(work, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)
                original = open(dst, encoding="utf-8").read()

                # 先反向，回到未打补丁的状态
                for _rel, hunks in S.parse_udiff(reverse(text)):
                    S.apply_udiff_file(dst, hunks)
                mid = open(dst, encoding="utf-8").read()
                check("%s 反向应用后内容变化" % name, mid != original)

                # 再正向，应当逐字节回到原样
                for _rel, hunks in parsed:
                    S.apply_udiff_file(dst, hunks)
                back = open(dst, encoding="utf-8").read()
                check("%s 往返后逐字节还原" % name, back == original,
                      "长度 %d -> %d" % (len(original), len(back)))

    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("\n== 3) 行号漂移仍可应用 ==")
    work = tempfile.mkdtemp(prefix="dc-synctest-")
    try:
        for name, (text, parsed) in parsed_all.items():
            for rel, hunks in parsed:
                src = os.path.join(S.ROOT, rel)
                dst = os.path.join(work, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                # 模拟上游在文件头部插入了 5 行（行号整体下移）
                body = open(src, encoding="utf-8").read()
                shifted = "# 上游新加的头几行\n" * 5 + body
                # 此时文件里已经没有补丁要加的代码了（因为它是打过补丁的版本），
                # 所以先反向回到原始状态再加漂移
                open(dst, "w", encoding="utf-8", newline="").write(body)
                for _r, hs in S.parse_udiff(reverse(text)):
                    S.apply_udiff_file(dst, hs)
                base = open(dst, encoding="utf-8").read()
                open(dst, "w", encoding="utf-8", newline="").write("# 上游新加的头几行\n" * 5 + base)
                for _r, hs in parsed:
                    S.apply_udiff_file(dst, hs)
                got = open(dst, encoding="utf-8").read()
                want = "# 上游新加的头几行\n" * 5 + body
                check("%s 行号漂移后仍能应用" % name, got == want)

    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("\n== 4) 上游改写了代码时必须报错并保持文件完好 ==")
    work = tempfile.mkdtemp(prefix="dc-synctest-")
    try:
        name, (text, parsed) = sorted(parsed_all.items())[0]
        rel, hunks = parsed[0]
        dst = os.path.join(work, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        body = open(os.path.join(S.ROOT, rel), encoding="utf-8").read()
        open(dst, "w", encoding="utf-8", newline="").write(body)
        for _r, hs in S.parse_udiff(reverse(text)):
            S.apply_udiff_file(dst, hs)
        # 把补丁期望的某一行彻底改掉，模拟上游重写
        broken = open(dst, encoding="utf-8").read()
        target_line = [l for l in hunks[0][1] if l.strip()][0]
        broken = broken.replace(target_line, target_line + "  # 上游把它改了", 1)
        open(dst, "w", encoding="utf-8", newline="").write(broken)

        raised = False
        try:
            S.apply_udiff_file(dst, hunks)
        except RuntimeError as exc:
            raised = True
            check("冲突时抛出 RuntimeError", "补丁无法应用" in str(exc), str(exc)[:80])
        check("冲突时确实报错（不是静默通过）", raised)
        after = open(dst, encoding="utf-8").read()
        check("冲突时报错后文件内容未被破坏", "# 上游把它改了" in after)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("\n== 5) 站点与元数据探测 ==")
    sites = S.site_dirs(S.ENGINE_DIR)
    check("能扫出引擎站点模块", len(sites) >= 16, str(len(sites)))
    check("站点 KEY 都是大写", all(k.isupper() for k in sites), str(sorted(sites)))
    check("utils 不被当成站点", "UTILS" not in sites)
    known = S.catalog_keys()
    check("能从 catalog.py 读出已收录站点", len(known) >= 16, str(len(known)))
    check("引擎站点都已有元数据", not (set(sites) - known), str(sorted(set(sites) - known)))

    print("\n== 6) UPSTREAM.json 结构 ==")
    state = S.read_state()
    check("UPSTREAM.json 存在且可解析", bool(state))
    for key in ("repo", "ref", "commit", "version", "patches", "engine_sites"):
        check("含字段 %s" % key, key in state, str(list(state)))
    check("记录的补丁文件都存在",
          all(os.path.isfile(os.path.join(S.PATCH_DIR, p)) for p in state.get("patches", [])))
    check("记录的站点与引擎一致", set(state.get("engine_sites", [])) == set(sites))

    print("\n== 7) 上游新增站点时，面板应当「能用但不精细」 ==")
    sys.path.insert(0, S.ROOT)
    from panel import catalog  # noqa: E402

    merged = {m["key"]: m for m in catalog.merge_sites({"BILIBILI": "哔哩哔哩", "NEWSITE": "某某新站"})}
    check("新站点出现在列表里", "NEWSITE" in merged)
    new = merged["NEWSITE"]
    check("新站点 label 取引擎里的中文名", new["label"] == "某某新站", new["label"])
    check("新站点 LOGO 退回 emoji", new["emoji"] == "🧩", new["emoji"])
    check("新站点 known=False（前端会标注通用配置）", new["known"] is False)
    check("新站点不做必填字段拦截", new["required"] == [], str(new["required"]))
    check("新站点没有在线校验按钮", new["verify"] is None, str(new["verify"]))
    check("新站点依然按 cookie 方式配置", new["credential"] == "cookie", new["credential"])
    check("已收录站点不受影响", merged["BILIBILI"]["known"] is True and merged["BILIBILI"]["verify"] == "bilibili")
    check("按引擎现状没有缺口", catalog.missing_meta() == [], str(catalog.missing_meta()))

    print("\n" + "=" * 52)
    print("通过 %d 项，失败 %d 项" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
