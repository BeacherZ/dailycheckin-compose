#!/usr/bin/env python3
"""跟随上游更新签到引擎。

本项目的签到引擎是把 https://github.com/Sitoi/dailycheckin 的源码**整份内置**在
`dailycheckin/` 目录里（而不是从 PyPI 装），好处是构建可复现、离线能编译、补丁可控；
代价是上游更新不会自己流进来，必须显式同步一次 —— 这个脚本就是干这个的。

为什么不能手工把上游 `dailycheckin/` 目录整个盖过来？
因为本项目的引擎上有 **2 个本地补丁**（见 `patches/`），直接覆盖会把它们悄悄抹掉：

* 0001-bilibili-newlist     B 站旧接口下线，改 newlist + 空值兜底
* 0002-notice-single-message 通知默认合并成一条，并修掉 merge_push 空串的坑

本脚本会在替换引擎源码之后**自动重放这些补丁**，任何一个补丁打不上就直接回滚，
绝不留下一个「改了一半」的引擎。

用法::

    python tools/sync_upstream.py --check        # 只查上游有没有更新，不联网写文件
    python tools/sync_upstream.py                # 同步到 UPSTREAM.json 记录的 ref（默认 main）
    python tools/sync_upstream.py --ref 25.12.9  # 同步到指定 tag / 分支 / commit
    python tools/sync_upstream.py --ref main --dry-run   # 走完整流程但不落地

退出码：0 = 成功（或已是最新）；1 = 失败（补丁冲突、网络异常等）；2 = `--check` 发现上游有更新。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.join(ROOT, "dailycheckin")
PATCH_DIR = os.path.join(ROOT, "patches")
STATE_PATH = os.path.join(ROOT, "UPSTREAM.json")
CATALOG_PATH = os.path.join(ROOT, "panel", "catalog.py")

DEFAULT_REPO = "Sitoi/dailycheckin"
DEFAULT_REF = "main"

# 非引擎文件：我们改了就不自动覆盖，只提示；没改过就跟着上游走
TRACKED_FILES = ["requirements.txt", "pyproject.toml", "setup.py", "LICENSE"]
PROTECTED_FILES = {"setup.py"}  # 本地有意改动过（find_packages 排除 panel）

SKIP_NAMES = {"__pycache__", ".DS_Store"}


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def log(msg: str = "") -> None:
    print(msg, flush=True)


def step(msg: str) -> None:
    log("\n==> " + msg)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def api_get(path: str, repo: str = DEFAULT_REPO):
    url = "https://api.github.com/repos/%s%s" % (repo, path)
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "dailycheckin-compose-sync",
    })
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_tarball(ref: str, repo: str = DEFAULT_REPO) -> bytes:
    url = "https://api.github.com/repos/%s/tarball/%s" % (repo, ref)
    req = urllib.request.Request(url, headers={"User-Agent": "dailycheckin-compose-sync"})
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=600) as resp:
        return resp.read()


def extract(tar_bytes: bytes, dest: str) -> str:
    """解包，返回包内顶层目录的绝对路径。"""
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tf:
        names = tf.getnames()
        if not names:
            raise RuntimeError("源码包是空的")
        top = names[0].split("/")[0]
        try:
            tf.extractall(dest, filter="data")  # Python 3.12+
        except TypeError:
            tf.extractall(dest)
    return os.path.join(dest, top)


def copy_tree(src: str, dst: str) -> int:
    """把 src 里的内容复制进 dst（不保留旧的残留文件）。"""
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*SKIP_NAMES, "*.pyc"))
    return sum(1 for _, _, fs in os.walk(dst) for _ in fs)


# --------------------------------------------------------------------------- #
# 站点目录探测
# --------------------------------------------------------------------------- #
def site_dirs(engine_root: str) -> dict:
    """从引擎源码目录里找出所有站点模块，返回 {大写KEY: 中文名}。

    站点模块 = `dailycheckin/<name>/main.py`，中文名取 `name = "..."`。
    这与引擎自身的 `pkgutil.walk_packages` 自动发现逻辑一致。
    """
    out = {}
    if not os.path.isdir(engine_root):
        return out
    for name in sorted(os.listdir(engine_root)):
        if name.startswith(".") or name in SKIP_NAMES or name == "utils":
            continue
        main_py = os.path.join(engine_root, name, "main.py")
        if not os.path.isfile(main_py):
            continue
        label = ""
        try:
            with open(main_py, encoding="utf-8", errors="replace") as f:
                m = re.search(r'^\s{4}name\s*=\s*["\'](.+?)["\']', f.read(), re.M)
            if m:
                label = m.group(1)
        except OSError:
            pass
        out[name.upper()] = label
    return out


def site_dirs_from_api(sha: str, repo: str = DEFAULT_REPO) -> dict:
    """不下载源码，用 trees 接口列出站点模块（--check 用，秒回）。"""
    data = api_get("/git/trees/%s?recursive=1" % sha, repo)
    out = {}
    pat = re.compile(r"^dailycheckin/([^/]+)/main\.py$")
    for item in data.get("tree", []):
        m = pat.match(item.get("path", ""))
        if m and m.group(1) != "utils":
            out[m.group(1).upper()] = ""
    return out


def catalog_keys() -> set:
    """读 panel/catalog.py 里已经写了元数据的站点（避免 import 引入依赖）。"""
    if not os.path.isfile(CATALOG_PATH):
        return set()
    with open(CATALOG_PATH, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^SITE_META[^=]*=\s*\{(.*?)^\}", text, re.S | re.M)
    if not m:
        return set()
    return set(re.findall(r'^\s{4}"([A-Za-z0-9_]+)"\s*:', m.group(1), re.M))


# --------------------------------------------------------------------------- #
# unified diff 应用（自带实现，不依赖 git / patch 命令）
# --------------------------------------------------------------------------- #
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _strip_ab(path: str) -> str:
    path = path.strip().split("\t")[0].strip()
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


def parse_udiff(text: str):
    """解析 unified diff，返回 [(相对路径, [(起始行, 旧行, 新行), ...]), ...]。"""
    lines = text.splitlines()
    files, cur = [], None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            # 正常情况下一行是 +++，但补丁被人手工编辑过时可能不是，
            # 所以只在确实看到 +++ 时才跳两行，避免把紧随其后的 hunk 头吞掉。
            if i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                rel = _strip_ab(lines[i + 1][4:])
                i += 2
            else:
                rel = _strip_ab(line[4:])
                i += 1
            cur = (rel, [])
            files.append(cur)
            continue
        if line.startswith("@@ ") and cur is not None:
            m = HUNK_RE.match(line)
            if not m:
                i += 1
                continue
            start = int(m.group(1))
            i += 1
            old, new = [], []
            while i < len(lines) and not lines[i].startswith(("@@ ", "--- ")):
                raw = lines[i]
                if raw.startswith("+"):
                    new.append(raw[1:])
                elif raw.startswith("-"):
                    old.append(raw[1:])
                elif raw.startswith(" "):
                    old.append(raw[1:])
                    new.append(raw[1:])
                elif raw.startswith("\\"):
                    pass
                elif raw == "":
                    old.append("")
                    new.append("")
                else:
                    break
                i += 1
            cur[1].append((start, old, new))
            continue
        i += 1
    return [(p, h) for p, h in files if h]


def _match(lines, old, pos) -> bool:
    if pos < 0 or pos + len(old) > len(lines):
        return False
    return all(lines[pos + k] == old[k] for k in range(len(old)))


def _match_loose(lines, old, pos) -> bool:
    """忽略行尾空白的宽松匹配，用来吸收上游的格式化改动。"""
    if pos < 0 or pos + len(old) > len(lines):
        return False
    return all(lines[pos + k].rstrip() == old[k].rstrip() for k in range(len(old)))


def _locate(lines, old, hint: int) -> int:
    """定位 hunk。先试补丁给的行号，再前后扫描，最后放宽行尾空白。"""
    for matcher in (_match, _match_loose):
        if matcher(lines, old, hint):
            return hint
        for offset in range(1, len(lines) + 1):
            for pos in (hint + offset, hint - offset):
                if matcher(lines, old, pos):
                    return pos
    return -1


def apply_udiff_file(path: str, hunks) -> None:
    """把 hunks 应用到 path 上，失败抛 RuntimeError。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    had_newline = text.endswith("\n")
    lines = text.splitlines()
    offset = 0
    for start, old, new in hunks:
        pos = _locate(lines, old, max(0, start - 1 + offset))
        if pos < 0:
            preview = "\n".join("        " + l for l in old[:6])
            raise RuntimeError(
                "补丁无法应用：%s\n    补丁期望的原文找不到（上游这段代码被改过了），片段：\n%s"
                % (os.path.relpath(path, ROOT), preview)
            )
        lines[pos:pos + len(old)] = new
        offset += len(new) - len(old)
    out = "\n".join(lines) + ("\n" if had_newline else "")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(out)


def apply_patches(root: str, patch_dir: str = PATCH_DIR) -> list:
    """按文件名顺序重放 patches/*.patch，返回已应用的补丁名列表。"""
    applied = []
    if not os.path.isdir(patch_dir):
        return applied
    names = sorted(n for n in os.listdir(patch_dir) if n.endswith(".patch"))
    for name in names:
        with open(os.path.join(patch_dir, name), encoding="utf-8") as f:
            text = f.read()
        for rel, hunks in parse_udiff(text):
            target = os.path.join(root, rel)
            if not os.path.isfile(target):
                raise RuntimeError("补丁 %s 的目标文件不存在：%s" % (name, rel))
            apply_udiff_file(target, hunks)
        applied.append(name)
        log("   已重放 %s" % name)
    return applied


# --------------------------------------------------------------------------- #
# 状态文件
# --------------------------------------------------------------------------- #
def read_state() -> dict:
    if not os.path.isfile(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_state(state: dict) -> None:
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, STATE_PATH)


def engine_version(engine_dir: str) -> str:
    path = os.path.join(engine_dir, "__version__.py")
    try:
        with open(path, encoding="utf-8") as f:
            m = re.search(r'__version__\s*=\s*["\']([^"\']+)', f.read())
        return m.group(1) if m else "?"
    except OSError:
        return "?"


# --------------------------------------------------------------------------- #
# 报告
# --------------------------------------------------------------------------- #
def report_sites(old: dict, new: dict) -> bool:
    """打印站点目录变化，返回是否有变化。"""
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    if not added and not removed:
        log("   站点目录没有变化（共 %d 个）" % len(new))
        return False
    if added:
        log("   上游新增站点 %d 个：" % len(added))
        for key in added:
            log("      + %-12s %s" % (key, new.get(key) or ""))
    if removed:
        log("   上游移除站点 %d 个：" % len(removed))
        for key in removed:
            log("      - %-12s %s" % (key, old.get(key) or ""))
    return True


def report_meta_gaps(sites: dict) -> list:
    """哪些站点还没有 panel/catalog.py 元数据（会退回通用配置）。"""
    known = catalog_keys()
    gaps = sorted(k for k in sites if k not in known)
    if gaps:
        log("   ⚠ 以下 %d 个站点在 panel/catalog.py 里没有元数据：" % len(gaps))
        for key in gaps:
            log("       %-12s %s" % (key, sites.get(key) or ""))
        log("     也能正常签到，只是面板不知道它的必填 cookie 字段、没有在线校验、")
        log("     LOGO 会退回 emoji。建议照着文件里已有的写法补一段。")
    else:
        log("   所有站点都有 panel/catalog.py 元数据")
    return gaps


# --------------------------------------------------------------------------- #
# --check
# --------------------------------------------------------------------------- #
def do_check(args) -> int:
    state = read_state()
    ref = args.ref or state.get("ref") or DEFAULT_REF
    repo = args.repo or state.get("repo") or DEFAULT_REPO
    step("检查上游 %s 的 %s" % (repo, ref))

    try:
        info = api_get("/commits/" + ref, repo)
    except urllib.error.HTTPError as exc:
        log("   查询失败：HTTP %s（ref %s 不存在？）" % (exc.code, ref))
        return 1
    except Exception as exc:  # noqa: BLE001
        log("   查询失败：%s: %s" % (type(exc).__name__, exc))
        return 1

    sha = info["sha"]
    date = info["commit"]["committer"]["date"]
    recorded = state.get("commit") or ""
    log("   上游最新提交 : %s  (%s)" % (sha[:10], date))
    log("   本项目记录于 : %s" % (recorded[:10] or "(未记录)"))
    log("   内置引擎版本 : %s" % (state.get("version") or "?"))

    upstream_sites = site_dirs_from_api(sha, repo)
    local_sites = site_dirs(ENGINE_DIR)
    log("   上游站点模块 : %d 个" % len(upstream_sites))
    changed = report_sites(local_sites, upstream_sites)

    if sha == recorded and not changed:
        log("\n结论：已是最新，无需同步。")
        return 0

    if sha == recorded:
        log("\n结论：引擎提交没变，但站点目录有差异（本地可能有手工调整）。")
    else:
        log("\n结论：上游有更新，可以同步：")
    log("       python tools/sync_upstream.py --ref %s" % ref)
    return 2


# --------------------------------------------------------------------------- #
# 同步
# --------------------------------------------------------------------------- #
def do_sync(args) -> int:
    state = read_state()
    ref = args.ref or state.get("ref") or DEFAULT_REF
    repo = args.repo or state.get("repo") or DEFAULT_REPO

    step("同步 %s@%s" % (repo, ref))
    try:
        info = api_get("/commits/" + ref, repo)
        sha = info["sha"]
        commit_date = info["commit"]["committer"]["date"]
    except Exception as exc:  # noqa: BLE001
        log("   读取提交信息失败：%s: %s" % (type(exc).__name__, exc))
        return 1
    log("   提交 %s (%s)" % (sha[:10], commit_date))

    old_sites = site_dirs(ENGINE_DIR)
    old_version = engine_version(ENGINE_DIR)
    log("   当前内置引擎版本 %s，站点 %d 个" % (old_version, len(old_sites)))

    step("下载上游源码")
    t0 = time.time()
    try:
        blob = download_tarball(sha, repo)
    except Exception as exc:  # noqa: BLE001
        log("   下载失败：%s: %s" % (type(exc).__name__, exc))
        return 1
    log("   %.1f KB，用时 %.1f 秒" % (len(blob) / 1024, time.time() - t0))

    with tempfile.TemporaryDirectory(prefix="dc-sync-") as tmp:
        top = extract(blob, tmp)
        up_engine = os.path.join(top, "dailycheckin")
        if not os.path.isfile(os.path.join(up_engine, "main.py")):
            log("   源码包里找不到 dailycheckin/main.py，可能上游改了目录结构")
            return 1
        new_sites = site_dirs(up_engine)
        new_version = engine_version(up_engine)
        log("   上游引擎版本 %s，站点 %d 个" % (new_version, len(new_sites)))

        if args.dry_run:
            step("--dry-run：只比对，不落地")
            report_sites(old_sites, new_sites)
            report_meta_gaps(new_sites)
            _report_tracked(top, state)
            log("\n（没有写入任何文件）")
            return 0

        step("替换引擎源码")
        backup = os.path.join(tmp, "_backup_engine")
        if os.path.isdir(ENGINE_DIR):
            shutil.copytree(ENGINE_DIR, backup, ignore=shutil.ignore_patterns(*SKIP_NAMES, "*.pyc"))
        count = copy_tree(up_engine, ENGINE_DIR)
        log("   已写入 %d 个文件到 dailycheckin/" % count)

        step("重放本地补丁")
        try:
            if args.no_patch:
                log("   --no-patch：跳过（引擎将不带本项目补丁，仅供调试）")
                applied = []
            else:
                # 补丁里的路径是仓库相对的（dailycheckin/...），所以根目录传 ROOT 而不是 ENGINE_DIR
                applied = apply_patches(ROOT)
                if not applied:
                    log("   没有找到补丁文件，引擎为上游原样")
        except RuntimeError as exc:
            log("   ✗ " + str(exc))
            log("\n   正在回滚到同步前的引擎……")
            copy_tree(backup, ENGINE_DIR)
            log("   已回滚，dailycheckin/ 未被改动。")
            log("\n   处理办法：打开上面的补丁文件，按上游新代码重新对一遍，")
            log("   改好 patches/ 里的 diff 后重跑本脚本。")
            return 1

        step("核对非引擎文件")
        file_info = _sync_tracked_files(top, state)

        step("写入 UPSTREAM.json")
        patches = sorted(n for n in os.listdir(PATCH_DIR) if n.endswith(".patch")) if os.path.isdir(PATCH_DIR) else []
        new_state = {
            "repo": repo,
            "ref": ref,
            "commit": sha,
            "commit_date": commit_date,
            "version": new_version,
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sync_tool": "tools/sync_upstream.py",
            "patches": patches,
            "engine_sites": sorted(new_sites),
            "tracked_files": file_info,
            "note": "引擎源码来自上游，patches/ 里的补丁在同步后自动重放。不要手工覆盖 dailycheckin/。",
        }
        write_state(new_state)
        log("   已写入 %s" % os.path.relpath(STATE_PATH, ROOT).replace("\\", "/"))

    step("结果")
    report_sites(old_sites, new_sites)
    gaps = report_meta_gaps(site_dirs(ENGINE_DIR))

    log("")
    log("引擎已更新：%s → %s" % (old_version, new_version))
    log("下一步：")
    log("   1) 看一眼改了什么：git diff --stat")
    if gaps:
        log("   2) 给上面列出的新站点补 panel/catalog.py 元数据（可选，但不补体验会打折）")
        log("   3) git add -A && git commit -m \"chore: 同步上游引擎 %s\" && git push" % new_version)
    else:
        log("   2) git add -A && git commit -m \"chore: 同步上游引擎 %s\" && git push" % new_version)
    log("   推送后 CI 会自动重建并发布 ghcr.io 镜像。")
    return 0


def _report_tracked(top: str, state: dict) -> None:
    for rel in TRACKED_FILES:
        src = os.path.join(top, rel)
        if not os.path.isfile(src):
            continue
        up_hash = sha256(src)
        local = os.path.join(ROOT, rel)
        local_hash = sha256(local) if os.path.isfile(local) else ""
        recorded = (state.get("tracked_files") or {}).get(rel, {}).get("upstream_sha256")
        flag = []
        if recorded and recorded != up_hash:
            flag.append("上游已改动")
        if up_hash != local_hash:
            flag.append("本地与上游不同")
        log("   %-18s %s" % (rel, "、".join(flag) or "一致"))


def _sync_tracked_files(top: str, state: dict) -> dict:
    """上游改过的非引擎文件：本地没定制过就跟着更新，定制过的只提示。"""
    info = {}
    for rel in TRACKED_FILES:
        src = os.path.join(top, rel)
        if not os.path.isfile(src):
            continue
        up_hash = sha256(src)
        local = os.path.join(ROOT, rel)
        local_hash = sha256(local) if os.path.isfile(local) else ""
        recorded = (state.get("tracked_files") or {}).get(rel, {}).get("upstream_sha256")

        entry = {"upstream_sha256": up_hash}
        if rel in PROTECTED_FILES:
            entry["local"] = "modified"
            if recorded and recorded != up_hash:
                log("   ⚠ %s 上游也改了，但本地有定制（%s），没有自动覆盖，请人工合并"
                    % (rel, "、".join(PROTECTED_FILES_REASON.get(rel, ["本地改动"]))))
            else:
                log("   %-18s 保留本地版本（有意改动）" % rel)
        elif up_hash == local_hash:
            entry["local"] = "same"
            log("   %-18s 与上游一致" % rel)
        else:
            shutil.copyfile(src, local)
            entry["local"] = "synced"
            log("   %-18s 已更新为上游版本" % rel)
        info[rel] = entry
    return info


PROTECTED_FILES_REASON = {
    "setup.py": ["find_packages 里排除了 panel，避免把面板打进 wheel"],
}


# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(
        description="同步上游 Sitoi/dailycheckin 引擎，并自动重放本项目补丁",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--check", action="store_true", help="只检查上游有没有更新，不下载不改文件")
    parser.add_argument("--ref", default=None, help="上游 tag / 分支 / commit（默认沿用 UPSTREAM.json 里的，再默认 main）")
    parser.add_argument("--repo", default=None, help="上游仓库，默认 Sitoi/dailycheckin")
    parser.add_argument("--dry-run", action="store_true", help="下载并比对，但不写入任何文件")
    parser.add_argument("--no-patch", action="store_true", help="跳过补丁重放（调试用，引擎将不带本项目补丁）")
    args = parser.parse_args()

    if not os.path.isdir(ENGINE_DIR):
        log("找不到引擎目录：%s（请在仓库根目录运行本脚本）" % ENGINE_DIR)
        return 1

    if args.check:
        return do_check(args)
    return do_sync(args)


if __name__ == "__main__":
    sys.exit(main())
