/* 签到管理面板 —— 无框架、无构建步骤的纯前端 */
(() => {
  "use strict";

  const API = "/api";
  const S = {
    state: null,
    drafts: {},      // 站点 KEY -> 账号数组（前端草稿）
    checks: {},      // 站点 KEY -> 每账号的本地体检结果
    dirty: {},       // 站点 KEY -> 是否有未保存改动
    expanded: new Set(),
    runId: null,
    pollTimer: null,
    logTimer: null,
    token: localStorage.getItem("panel_token") || "",
  };

  const $ = (id) => document.getElementById(id);
  const esc = (v) =>
    String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /* ---------------- 网络 ---------------- */
  async function api(path, options = {}) {
    const opt = { headers: { "Content-Type": "application/json" }, ...options };
    if (S.token) opt.headers["X-Panel-Token"] = S.token;
    if (opt.body && typeof opt.body !== "string") opt.body = JSON.stringify(opt.body);
    const res = await fetch(API + path, opt);
    let data = null;
    try { data = await res.json(); } catch (_) { /* 忽略非 JSON */ }
    if (res.status === 401) {
      const input = prompt("该面板已开启口令保护，请输入访问口令：");
      if (input) {
        S.token = input;
        localStorage.setItem("panel_token", input);
        return api(path, options);
      }
      throw new Error("需要口令");
    }
    if (!res.ok) throw new Error((data && data.error) || `请求失败 (HTTP ${res.status})`);
    return data;
  }

  const toast = (() => {
    const el = $("toast");
    let timer = null;
    return (msg, ms = 2600) => {
      el.textContent = msg;
      el.classList.add("show");
      clearTimeout(timer);
      timer = setTimeout(() => el.classList.remove("show"), ms);
    };
  })();

  const fmtTime = (ts) => {
    if (!ts) return "—";
    const d = new Date(ts * 1000);
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  };
  const ago = (ts) => {
    if (!ts) return "从未";
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 60) return "刚刚";
    if (s < 3600) return `${Math.floor(s / 60)} 分钟前`;
    if (s < 86400) return `${Math.floor(s / 3600)} 小时前`;
    return `${Math.floor(s / 86400)} 天前`;
  };

  /* ---------------- 状态 ---------------- */
  async function loadState(silent = false) {
    const st = await api("/state");
    S.state = st;
    document.title = st.panel.title;
    $("panelTitle").textContent = st.panel.title;
    $("panelVersion").textContent = "v" + st.panel.version + (st.engine.version ? " · 引擎 " + st.engine.version : "");
    $("engineDot").className = "dot" + (st.engine.ok ? "" : " off");
    $("engineDot").title = st.engine.ok ? st.engine.message : "引擎不可用：" + st.engine.message;

    for (const site of st.sites) {
      if (!S.dirty[site.key]) {
        S.drafts[site.key] = site.accounts.map((a) => ({ ...a }));
        S.checks[site.key] = site.accounts.map((a) => a._check || null);
      }
    }
    render();
    if (!silent) toast("已刷新");
  }

  const currentSites = () => (S.state ? S.state.sites : []);
  const visibleSites = () => {
    const q = $("search").value.trim().toLowerCase();
    const f = $("filter").value;
    return currentSites().filter((s) => {
      if (q && !(s.label + " " + s.key + " " + s.group).toLowerCase().includes(q)) return false;
      const state = (s.status && s.status.state) || "unverified";
      if (f === "configured") return s.configured;
      if (f === "unconfigured") return !s.configured;
      if (f === "valid") return state === "valid";
      if (f === "invalid") return state === "invalid";
      if (f === "unverified") return state === "unverified";
      return true;
    });
  };

  const STATE_TEXT = { valid: ["valid", "✅ 有效"], invalid: ["invalid", "❌ 失效"], unknown: ["unknown", "❔ 无法判定"], unverified: ["unverified", "⚪ 未校验"] };
  // 标注结论是哪来的：登录态接口是强证据，签到运行只是弱证据
  const SOURCE_TEXT = { api: "依据：登录态接口", run: "依据：签到运行" };

  /* ---------------- 渲染 ---------------- */
  function render() {
    const sites = visibleSites();
    const box = $("sites");
    box.innerHTML = sites.map(cardHTML).join("");
    const total = currentSites().length;
    $("emptyHint").classList.toggle("hidden", sites.length > 0);
    $("emptyHint").textContent = total === 0 ? "没有发现任何站点" : "没有符合筛选条件的站点";

    const counts = { valid: 0, invalid: 0, unknown: 0, unverified: 0 };
    let configured = 0;
    currentSites().forEach((s) => {
      counts[((s.status && s.status.state) || "unverified")]++;
      if (s.configured) configured++;
    });
    $("statValid").textContent = counts.valid;
    $("statInvalid").textContent = counts.invalid;
    $("statUnknown").textContent = counts.unknown + counts.unverified;
    $("statConfigured").textContent = configured;
    $("statTotal").textContent = total;
    const last = (S.state.runs || [])[0];
    $("statLastRun").textContent = last ? `上次任务 ${ago(last.started_at)}` : "还没有运行过";
    document.body.classList.toggle("masked", $("maskCookie").checked);
  }

  function cardHTML(site) {
    const open = S.expanded.has(site.key);
    const accounts = S.drafts[site.key] || [];
    const [cls, text] = STATE_TEXT[(site.status && site.status.state) || "unverified"];
    const meta = [];
    meta.push(accounts.length ? `${accounts.length} 个账号` : "未配置");
    if (site.status && site.status.checked_at) meta.push(`校验于 ${ago(site.status.checked_at)}`);
    const src = site.status && SOURCE_TEXT[site.status.source];
    if (src) meta.push(src);
    if (site.status && site.status.message) meta.push(truncate(site.status.message, 60));
    if (S.dirty[site.key]) meta.push("● 有未保存的改动");

    return `
<article class="card" data-state="${cls}" data-key="${site.key}">
  <div class="card-head" data-action="toggle" data-key="${site.key}">
    <span class="emoji">${esc(site.emoji)}</span>
    <span class="names"><b>${esc(site.label)}</b><span>${esc(site.key)}</span></span>
    <span class="spacer"></span>
    <span class="badge ${cls}">${text}</span>
    <span class="chev">${open ? "▾" : "▸"}</span>
  </div>
  <div class="card-meta">${meta.map(esc).join(" · ")}</div>
  ${open ? bodyHTML(site, accounts) : ""}
</article>`;
  }

  function bodyHTML(site, accounts) {
    const req = (site.required || []).length
      ? `<span class="req">必填：${site.required.map(esc).join("、")}</span>`
      : `<span class="opt">无强制字段</span>`;
    const blocks = accounts.length
      ? accounts.map((acc, i) => accountHTML(site, acc, i)).join("")
      : `<p class="muted" style="font-size:12.5px">还没有账号，点下面的「添加账号」。</p>`;
    return `
<div class="card-body">
  ${site.howto ? `<div class="howto"><b>怎么拿 cookie：</b>${esc(site.howto)}</div>` : ""}
  <div class="row" style="margin:0 0 8px">
    <span class="muted" style="font-size:12px">凭据类型：${site.credential === "cookie" ? "Cookie" : "账号/表单"}</span>
    ${site.verify ? "" : `<span class="badge unknown">无在线校验接口</span>`}
  </div>
  ${blocks}
  <div class="row">
    <button class="tiny" data-action="add" data-key="${site.key}">＋ 添加账号</button>
    <span class="spacer"></span>
    <button class="tiny" data-action="run" data-key="${site.key}">立即签到</button>
    <button class="tiny primary" data-action="save" data-key="${site.key}">保存</button>
  </div>
</div>`;
  }

  function accountHTML(site, account, index) {
    const check = (S.checks[site.key] || [])[index];
    const extras = (site.fields || [])
      .map((f) => {
        const value = account[f.key] != null ? account[f.key] : f.default != null ? f.default : "";
        const label = `<label>${esc(f.label)}${f.required ? ' <span class="req">*</span>' : ""}${f.help ? ` <span class="opt">${esc(f.help)}</span>` : ""}</label>`;
        if (f.type === "bool") {
          return `<div><label class="switch">${label.replace(/^<label>|<\/label>$/g, "")}<input type="checkbox" data-field="${esc(f.key)}" ${value ? "checked" : ""}></label></div>`;
        }
        const type = f.type === "secret" ? "password" : "text";
        return `<div>${label}<input type="${type}" data-field="${esc(f.key)}" value="${esc(value)}" autocomplete="off"></div>`;
      })
      .join("");

    const cookieBlock =
      site.credential === "cookie"
        ? `<div class="field-label">Cookie ${reqLabel(site)}</div>
           <textarea data-field="cookie" rows="4" spellcheck="false" placeholder="在这里粘贴 cookie 原文，支持：浏览器 Cookie 面板整块复制 / name=value; ... 串 / JSON / curl 里的 Cookie 头">${esc(account.cookie || "")}</textarea>
           <div class="row">
             <button class="tiny" data-action="normalize" data-key="${site.key}" data-index="${index}">规范化</button>
             ${site.verify ? `<button class="tiny" data-action="verify" data-key="${site.key}">校验 cookie</button>` : ""}
             <span class="spacer"></span>
             <span class="muted" style="font-size:11.5px" data-role="count">${check ? check.count + " 个字段" : ""}</span>
           </div>
           <div class="check ${check ? (check.ok ? "ok" : "bad") : ""}" data-role="check">${checkHTML(check)}</div>`
        : "";

    return `
<div class="account" data-index="${index}">
  <div class="acc-head">
    <b>账号 ${index + 1}</b>
    <span class="spacer"></span>
    <button class="ghost tiny" data-action="remove" data-key="${site.key}" data-index="${index}">删除</button>
  </div>
  ${cookieBlock}
  ${extras ? `<details class="extras" ${hasNonEmpty(account, site) ? "open" : ""}><summary>其它参数（${(site.fields || []).length} 项，可选）</summary><div class="grid2">${extras}</div></details>` : ""}
</div>`;
  }

  const reqLabel = (site) =>
    (site.required || []).length ? `<span class="req">必填：${site.required.map(esc).join("、")}</span>` : "";

  function hasNonEmpty(account, site) {
    return (site.fields || []).some((f) => {
      const v = account[f.key];
      return v !== undefined && v !== "" && v !== null;
    });
  }

  function truncate(text, n) {
    text = String(text || "").replace(/\s+/g, " ");
    return text.length > n ? text.slice(0, n) + "…" : text;
  }

  function checkHTML(check) {
    if (!check) return "";
    const parts = [];
    if (check.missing && check.missing.length) parts.push(`缺少必填字段：${check.missing.join("、")}`);
    else if (check.ok) parts.push(`格式正常，共 ${check.count} 个字段`);
    else if (check.message) parts.push(check.message);
    if (check.source && check.source !== "unknown") parts.push(`识别为 ${check.source}`);
    let html = esc(parts.join("｜"));
    if (check.keys && check.keys.length) {
      const chips = check.keys.map((k) => `<span class="chip have">${esc(k)}</span>`).join("");
      const miss = (check.missing || []).map((k) => `<span class="chip miss">${esc(k)}</span>`).join("");
      html += `<div class="chips" style="margin-top:6px">${chips}${miss}</div>`;
    }
    if (check.warnings && check.warnings.length) {
      html += `<ul>${check.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>`;
    }
    if (check.needs_fix && check.ok) {
      html += `<div style="margin-top:6px"><span class="chip miss">格式不是引擎标准形态，建议点「规范化」</span></div>`;
    }
    return html;
  }

  /* ---------------- 卡片交互 ---------------- */
  function findSite(key) { return currentSites().find((s) => s.key === key); }
  function draftOf(key) {
    if (!S.drafts[key]) S.drafts[key] = [];
    return S.drafts[key];
  }

  function repaintCard(key) {
    const card = document.querySelector(`.card[data-key="${key}"]`);
    const site = findSite(key);
    if (!card || !site) return;
    const wrapper = document.createElement("div");
    wrapper.innerHTML = cardHTML(site);
    card.replaceWith(wrapper.firstElementChild);
  }

  function refreshCardFooter(key) {
    const card = document.querySelector(`.card[data-key="${key}"]`);
    if (!card) return;
    const site = findSite(key);
    const accounts = draftOf(key);
    const meta = [];
    meta.push(accounts.length ? `${accounts.length} 个账号` : "未配置");
    if (site.status && site.status.checked_at) meta.push(`校验于 ${ago(site.status.checked_at)}`);
    if (S.dirty[key]) meta.push("● 有未保存的改动");
    const el = card.querySelector(".card-meta");
    if (el) el.textContent = meta.join(" · ");
  }

  document.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-action]");
    if (!btn) return;
    const action = btn.dataset.action;
    const key = btn.dataset.key;
    const index = btn.dataset.index != null ? Number(btn.dataset.index) : null;

    if (action === "toggle") {
      if (S.expanded.has(key)) S.expanded.delete(key);
      else S.expanded.add(key);
      repaintCard(key);
      return;
    }

    if (action === "add") {
      const site = findSite(key);
      const blank = {};
      if (site.credential === "cookie") blank.cookie = "";
      S.drafts[key] = [...draftOf(key), blank];
      S.checks[key] = [...(S.checks[key] || []), null];
      S.dirty[key] = true;
      repaintCard(key);
      return;
    }

    if (action === "remove") {
      S.drafts[key] = draftOf(key).filter((_, i) => i !== index);
      S.checks[key] = (S.checks[key] || []).filter((_, i) => i !== index);
      S.dirty[key] = true;
      repaintCard(key);
      return;
    }

    if (action === "normalize") {
      const account = draftOf(key)[index];
      if (!account || !account.cookie) return toast("先粘贴 cookie");
      btn.disabled = true;
      try {
        const r = await api("/cookies/normalize", { method: "POST", body: { raw: account.cookie, site: key } });
        account.cookie = r.cookie || account.cookie;
        (S.checks[key] || [])[index] = r;
        S.dirty[key] = true;
        repaintCard(key);
        toast(`已规范化：${r.count} 个字段（来源：${r.source}）`);
      } catch (e) { toast(e.message); } finally { btn.disabled = false; }
      return;
    }

    if (action === "verify") {
      btn.disabled = true;
      btn.textContent = "校验中…";
      try {
        const r = await api(`/sites/${key}/verify`, { method: "POST", body: {} });
        const site = findSite(key);
        if (site) site.status = { state: r.state, checked_at: Date.now() / 1000, message: (r.results || []).map((x) => x.message).join("；") };
        repaintCard(key);
        const map = { valid: "✅ cookie 有效", invalid: "❌ cookie 已失效", unknown: "❔ 无法判定", unverified: "没有配置账号" };
        toast(`${site ? site.label : key}：${map[r.state] || r.state}`);
      } catch (e) { toast(e.message); } finally { btn.disabled = false; btn.textContent = "校验 cookie"; }
      return;
    }

    if (action === "save") { await saveSite(key); return; }
    if (action === "run") { await startRun([key]); return; }
    if (action === "open") { openDrawer("live"); return; }
  });

  document.addEventListener("input", (ev) => {
    const card = ev.target.closest(".card");
    if (!card) return;
    const key = card.dataset.key;
    const accEl = ev.target.closest(".account");
    if (!accEl) return;
    const index = Number(accEl.dataset.index);
    const account = draftOf(key)[index];
    if (!account) return;

    if (ev.target.dataset.field === "cookie") {
      account.cookie = ev.target.value;
      S.dirty[key] = true;
      refreshCardFooter(key);
      scheduleNormalize(key, index);
    } else if (ev.target.dataset.field) {
      const field = ev.target.dataset.field;
      account[field] = ev.target.type === "checkbox" ? ev.target.checked : ev.target.value;
      S.dirty[key] = true;
      refreshCardFooter(key);
    }
  });

  let normalizeTimers = {};
  function scheduleNormalize(key, index) {
    const id = key + ":" + index;
    clearTimeout(normalizeTimers[id]);
    normalizeTimers[id] = setTimeout(async () => {
      const account = draftOf(key)[index];
      if (!account || !account.cookie) return;
      try {
        const r = await api("/cookies/normalize", { method: "POST", body: { raw: account.cookie, site: key } });
        (S.checks[key] || [])[index] = r;
        const card = document.querySelector(`.card[data-key="${key}"]`);
        const accEl = card && card.querySelector(`.account[data-index="${index}"]`);
        if (!accEl) return;
        const box = accEl.querySelector('[data-role="check"]');
        const cnt = accEl.querySelector('[data-role="count"]');
        if (box) {
          box.className = "check " + (r.ok ? "ok" : "bad");
          box.innerHTML = checkHTML(r);
        }
        if (cnt) cnt.textContent = `${r.count} 个字段`;
      } catch (_) { /* 输入过程中的网络抖动直接忽略 */ }
    }, 400);
  }

  async function saveSite(key) {
    const site = findSite(key);
    if (!site) return;
    const accounts = draftOf(key).filter((a) => Object.values(a).some((v) => String(v == null ? "" : v).trim() !== ""));
    try {
      await api(`/sites/${key}/accounts`, { method: "POST", body: { accounts } });
      S.dirty[key] = false;
      site.accounts = accounts;
      site.configured = accounts.length > 0;
      toast(`${site.label}：已保存 ${accounts.length} 个账号`);
      await loadState(true);
    } catch (e) { toast("保存失败：" + e.message); }
  }

  /* ---------------- 运行 ---------------- */
  async function startRun(sites) {
    try {
      const r = await api("/run", { method: "POST", body: { sites } });
      S.runId = r.id;
      openDrawer("live");
      $("console").textContent = "任务已创建，等待输出…\n";
      pollRun();
    } catch (e) { toast(e.message); }
  }

  async function verifyAll() {
    try {
      const r = await api("/verify", { method: "POST", body: {} });
      S.runId = r.id;
      openDrawer("live");
      $("console").textContent = "开始批量校验…\n";
      pollRun();
    } catch (e) { toast(e.message); }
  }

  function pollRun() {
    clearTimeout(S.pollTimer);
    if (!S.runId) return;
    S.pollTimer = setTimeout(async () => {
      try {
        const run = await api("/runs/" + S.runId);
        const text = (run.lines || []).join("\n");
        const box = $("console");
        const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 40;
        box.textContent = text || "…";
        if (atBottom) box.scrollTop = box.scrollHeight;
        $("drawerTitle").textContent =
          (run.kind === "verify" ? "批量校验" : "签到任务") + " · " + ({ running: "运行中", done: "已完成", failed: "失败" }[run.status] || run.status) +
          " · " + Math.round((run.finished_at || Date.now() / 1000) - run.started_at) + "s";
        if (run.status === "running") return pollRun();
        S.runId = null;
        await loadState(true);
        if (run.kind === "verify") {
          toast(run.status === "done" ? "批量校验完成" : "校验结束但有问题，请看输出");
        } else {
          // 关键提醒：签到任务跑通 ≠ cookie 有效（部分站点模块对无效 cookie 是静默返回的）
          toast(
            run.status === "done"
              ? "签到任务完成 —— 有效性请以「校验 cookie」的结论为准"
              : "签到任务结束但有问题，请看输出",
            4200
          );
        }
      } catch (e) {
        $("console").textContent += "\n[面板] 读取任务状态失败：" + e.message;
      }
    }, 900);
  }

  async function loadHistory() {
    try {
      const r = await api("/runs");
      $("history").innerHTML = (r.runs || []).length
        ? r.runs
            .map(
              (run) => `<div class="account">
        <div class="acc-head"><b>${run.kind === "verify" ? "批量校验" : "签到任务"}</b>
        <span class="badge ${run.status === "done" ? "valid" : run.status === "running" ? "unknown" : "invalid"}">${run.status}</span>
        <span class="spacer"></span><span class="muted">${fmtTime(run.started_at)}</span></div>
        <div class="muted" style="font-size:12px">${esc((run.site_keys || []).join("、") || "全部站点")} · 用时 ${
                run.finished_at ? Math.round(run.finished_at - run.started_at) + " 秒" : "运行中"
              }</div>
        <div class="row"><button class="tiny" data-history="${run.id}">查看输出</button></div>
      </div>`
            )
            .join("")
        : `<p class="muted">还没有历史任务</p>`;
    } catch (e) { toast(e.message); }
  }

  async function loadLogs() {
    try {
      const r = await api("/logs?lines=500&name=" + encodeURIComponent($("logFile").value || "dailycheckin.log"));
      const sel = $("logFile");
      if (!sel.options.length) {
        sel.innerHTML = (r.files || []).map((f) => `<option value="${esc(f.name)}">${esc(f.name)}（${Math.round(f.size / 1024)} KB）</option>`).join("") || `<option value="dailycheckin.log">dailycheckin.log</option>`;
        sel.value = r.name;
      }
      $("logText").textContent = r.text || "（日志为空）";
    } catch (e) { $("logText").textContent = "读取失败：" + e.message; }
  }

  /* ---------------- 抽屉 / 设置 ---------------- */
  function openDrawer(tab) {
    $("drawer").classList.add("open");
    $("overlay").classList.add("open");
    if (tab) switchTab(tab);
  }
  function closeDrawer() {
    $("drawer").classList.remove("open");
    $("overlay").classList.remove("open");
  }
  function switchTab(name) {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
    document.querySelectorAll("[data-panel]").forEach((p) => p.classList.toggle("hidden", p.dataset.panel !== name));
    clearInterval(S.logTimer);
    if (name === "history") loadHistory();
    if (name === "log") { loadLogs(); S.logTimer = setInterval(loadLogs, 10000); }
  }

  async function openSettings() {
    const st = S.state;
    const sch = st.schedule;
    $("schEnabled").checked = sch.enabled;
    $("schPreset").innerHTML =
      sch.presets.map((p) => `<option value="${esc(p.cron)}">${esc(p.label)}</option>`).join("") +
      `<option value="__custom">自定义</option>`;
    $("schCron").value = sch.cron;
    $("schPreset").value = sch.presets.some((p) => p.cron === sch.cron) ? sch.cron : "__custom";
    $("schTip").textContent = `crontab 文件：${sch.crontab_path}（只改标记区块，其它行不动）`;

    $("noticeFields").innerHTML = st.notice_keys
      .map((k) => `<div><label>${esc(k.label)} <span class="opt">${esc(k.key)}</span></label>
        <input type="text" data-notice="${esc(k.key)}" value="${esc(st.notice[k.key] || "")}" autocomplete="off"></div>`)
      .join("");

    $("configTip").textContent = `路径：${st.panel.config_path}`;

    try {
      const raw = await api("/config/raw");
      $("configRaw").value = raw.text;
    } catch (e) { $("configRaw").value = "读取失败：" + e.message; }

    const bks = st.backups || [];
    $("backupSelect").innerHTML = bks.length
      ? bks.map((b) => `<option value="${esc(b.name)}">${esc(b.name)}</option>`).join("")
      : `<option value="">（暂无备份）</option>`;

    $("envInfo").textContent = [
      `面板版本   : ${st.panel.version}`,
      `引擎版本   : ${st.engine.version || "未知"}`,
      `引擎状态   : ${st.engine.ok ? "正常" : "异常"} — ${st.engine.message}`,
      `工作目录   : ${st.panel.home}`,
      `配置文件   : ${st.panel.config_path}`,
      `时区       : ${st.panel.tz}`,
      `口令保护   : ${st.panel.token_required ? "已开启" : "未开启"}`,
      `面板时间   : ${fmtTime(st.server_time)}`,
    ].join("\n");

    $("settings").showModal();
  }

  /* ---------------- 绑定 ---------------- */
  function bind() {
    $("btnRefresh").onclick = () => loadState();
    $("btnRunAll").onclick = () => startRun([]);
    $("btnVerifyAll").onclick = () => verifyAll();
    $("btnDrawer").onclick = () => openDrawer("live");
    $("btnDrawerClose").onclick = closeDrawer;
    $("overlay").onclick = closeDrawer;
    $("btnClearConsole").onclick = () => ($("console").textContent = "");
    $("btnExpandAll").onclick = () => { currentSites().forEach((s) => S.expanded.add(s.key)); render(); };
    $("btnCollapseAll").onclick = () => { S.expanded.clear(); render(); };
    $("search").oninput = render;
    $("filter").onchange = render;
    $("maskCookie").onchange = () => document.body.classList.toggle("masked", $("maskCookie").checked);
    $("btnReloadLog").onclick = loadLogs;
    $("logFile").onchange = loadLogs;

    document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => switchTab(b.dataset.tab)));

    document.addEventListener("click", (ev) => {
      const h = ev.target.closest("[data-history]");
      if (h) {
        S.runId = h.dataset.history;
        switchTab("live");
        pollRun();
      }
    });

    $("btnSettings").onclick = openSettings;
    $("btnCloseSettings").onclick = $("btnCloseSettings2").onclick = () => $("settings").close();

    $("schPreset").onchange = () => {
      if ($("schPreset").value !== "__custom") $("schCron").value = $("schPreset").value;
    };

    $("btnSaveSchedule").onclick = async () => {
      try {
        const r = await api("/schedule", { method: "PUT", body: { enabled: $("schEnabled").checked, cron: $("schCron").value.trim() } });
        toast(r.enabled ? "定时任务已生效" : "定时任务已关闭");
        if (r.applied && r.applied.skipped) toast("注意：" + r.applied.message, 4000);
        await loadState(true);
      } catch (e) { toast(e.message, 4000); }
    };

    $("btnSaveNotice").onclick = async () => {
      const notice = {};
      document.querySelectorAll("[data-notice]").forEach((el) => (notice[el.dataset.notice] = el.value));
      try {
        await api("/notice", { method: "POST", body: { notice } });
        toast("推送设置已保存");
        await loadState(true);
      } catch (e) { toast("保存失败：" + e.message); }
    };

    $("btnSaveRaw").onclick = async () => {
      try {
        await api("/config/raw", { method: "PUT", body: { text: $("configRaw").value } });
        toast("config.json 已保存");
        await loadState(true);
      } catch (e) { toast("保存失败：" + e.message, 4000); }
    };
    $("btnReloadRaw").onclick = async () => {
      try { $("configRaw").value = (await api("/config/raw")).text; toast("已重新载入"); } catch (e) { toast(e.message); }
    };
    $("btnRestore").onclick = async () => {
      const name = $("backupSelect").value;
      if (!name) return toast("没有可恢复的备份");
      if (!confirm(`确定用 ${name} 覆盖当前 config.json 吗？`)) return;
      try {
        await api(`/backups/${encodeURIComponent(name)}/restore`, { method: "POST", body: {} });
        toast("已恢复备份");
        await loadState(true);
        $("configRaw").value = (await api("/config/raw")).text;
      } catch (e) { toast(e.message); }
    };

    window.addEventListener("beforeunload", (ev) => {
      if (Object.values(S.dirty).some(Boolean)) { ev.preventDefault(); ev.returnValue = ""; }
    });
  }

  /* ---------------- 启动 ---------------- */
  bind();
  loadState(true).catch((e) => {
    document.body.insertAdjacentHTML(
      "afterbegin",
      `<div style="padding:16px 20px;color:#c9382f">加载失败：${esc(e.message)}<br>请确认服务已启动。</div>`
    );
  });
})();
