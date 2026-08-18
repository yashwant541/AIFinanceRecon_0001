(function () {
  "use strict";
  const api = (p) => (typeof getWebAppBackendUrl === "function" ? getWebAppBackendUrl(p) : p);
  const $ = (id) => document.getElementById(id);
  const qsa = (s, r) => [...(r || document).querySelectorAll(s)];
  const PAGES = ["overview", "upload", "mapping", "matching", "results", "admin"];
  const state = {
    sid: null, page: "overview",
    cols: { left: [], right: [] }, tables: { left: [], right: [] },
    unlocked: new Set(["overview", "upload", "admin"]), done: new Set(), lastResult: null,
    adminToken: null,
  };

  // ---------------- theme ----------------
  function setTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    qsa("[data-theme-set]").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.themeSet === t)));
    try { localStorage.setItem("frai-theme", t); } catch (e) {}
  }
  function initTheme() {
    let t = "light";
    try { t = localStorage.getItem("frai-theme") || t; } catch (e) {}
    setTheme(t);
    qsa("[data-theme-set]").forEach((b) => (b.onclick = () => setTheme(b.dataset.themeSet)));
  }

  // ---------------- toast ----------------
  let toastTimer;
  function toast(msg, err) {
    const t = $("toast");
    t.innerHTML = `<span class="ti">${err ? "!" : "✓"}</span>${msg}`;
    t.className = "toast show" + (err ? " err" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.className = "toast"), 2800);
  }

  // ---------------- routing ----------------
  function goto(page) {
    if (!state.unlocked.has(page)) return;
    state.page = page;
    qsa(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + page));
    updateNav();
    setStepbar(page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function updateNav() {
    qsa(".nav").forEach((n) => {
      const pg = n.dataset.page;
      n.setAttribute("aria-current", String(pg === state.page));
      n.classList.toggle("done", state.done.has(pg));
      n.classList.toggle("locked", !state.unlocked.has(pg));
    });
    qsa(".ms").forEach((m) =>
      m.setAttribute("aria-current", String(m.dataset.page === state.page)));
    qsa(".ms").forEach((m) => m.classList.toggle("done", state.done.has(m.dataset.page)));
    const idx = PAGES.indexOf(state.page);
    $("rail-prog").style.height = `calc(${idx / (PAGES.length - 1)} * (100% - 44px) + 0px)`;
  }
  function unlock(page) { state.unlocked.add(page); updateNav(); }
  function markDone(page) { state.done.add(page); updateNav(); }

  // sticky action bar per page
  function setStepbar(page) {
    const bar = $("stepbar"), back = $("step-back"), prim = $("step-primary"), hint = $("step-hint");
    const cfg = {
      overview: null,
      upload: { back: "overview", backLbl: "← Overview", prim: "Continue → Map fields",
        onPrim: () => goto("mapping"), primOn: () => state.cols.left.length && state.cols.right.length,
        hint: () => (state.cols.left.length && state.cols.right.length)
          ? "Both sides ready." : "Add at least one file per side." },
      mapping: { back: "upload", backLbl: "← Upload", prim: "Continue → Matching",
        onPrim: () => goto("matching"), primOn: () => true, hint: () => "" },
      matching: { back: "mapping", backLbl: "← Map fields", prim: "Run reconciliation ▶",
        onPrim: run, primOn: () => true, hint: () => "Exact keys match first; fallbacks apply after." },
      results: { back: "matching", backLbl: "← Matching", prim: "", onPrim: null,
        primOn: () => false, hint: () => "" },
      admin: null,
    }[page];
    if (!cfg) { bar.classList.remove("show"); return; }
    bar.classList.add("show");
    back.textContent = cfg.backLbl;
    back.onclick = () => goto(cfg.back);
    if (cfg.prim) {
      prim.style.display = ""; prim.textContent = cfg.prim;
      prim.disabled = !cfg.primOn(); prim.onclick = cfg.onPrim;
    } else { prim.style.display = "none"; }
    hint.textContent = cfg.hint();
  }

  // ---------------- session ----------------
  async function initSession() {
    try {
      const d = await (await fetch(api("/session"), { method: "POST" })).json();
      state.sid = d.session_id;
    } catch (e) { toast("Could not reach the engine.", true); }
    addFieldRow({ name: "", role: "key" });
    addFieldRow({ name: "amount", role: "value", dtype: "money", abstol: "0.01" });
  }

  // ---------------- upload ----------------
  const extOf = (n) => (n.split(".").pop() || "").toUpperCase();

  async function uploadSide(side, files) {
    if (!files.length) return;
    const drop = $(side + "-drop");
    drop.querySelector(".t").textContent = "Inspecting…";
    const fd = new FormData();
    fd.append("sid", state.sid); fd.append("side", side);
    for (const f of files) fd.append("files", f);
    try {
      const d = await (await fetch(api("/stage"), { method: "POST", body: fd })).json();
      if (d.error) { toast(d.error, true); return; }
      renderStage(side, d.files, d.engines);
    } catch (e) {
      toast("Could not read those files.", true);
    } finally { drop.querySelector(".t").textContent = "Drop files or browse"; }
  }

  function renderStage(side, files, engines) {
    const engs = engines && engines.length ? engines : ["native"];
    const engLabel = { native: "Native (best headers)",
      camelot: "Camelot (regions)", "camelot+native": "Camelot + native headers" };
    const box = $(side + "-stage");
    box.innerHTML = files.map((f, i) => {
      const uid = `${side}-st${i}`;
      let picker;
      if (f.kind === "excel" && f.sheets.length) {
        picker = `<label class="chk" style="margin-bottom:8px;font-size:12.5px">
            <input type="checkbox" class="sheet-all" data-uid="${uid}" checked> Select all sheets</label>
          <div class="sheetbox">` +
          f.sheets.map((s) => `<label><input type="checkbox" class="sheet-chk" data-uid="${uid}"
             value="${esc(s)}" checked> ${esc(s)}</label>`).join("") + `</div>`;
      } else if (f.count > 0) {
        picker = `<div class="row">
            <label class="chk" style="font-size:12.5px"><input type="checkbox" class="range-all"
              data-uid="${uid}" checked> All ${esc(f.units)}</label>
            <input type="text" class="range-in" data-uid="${uid}" disabled
              placeholder="e.g. 1-5, 12 (of ${f.count})"></div>`;
      } else {
        picker = `<div class="muted">Whole file will be read.</div>`;
      }
      const engSel = (f.kind === "pdf" && engs.length > 1)
        ? `<div class="row" style="margin-top:9px"><span class="muted" style="font-size:11.5px">Engine</span>
             <select class="eng-sel" data-uid="${uid}">${
               engs.map((e) => `<option value="${e}">${esc(engLabel[e] || e)}</option>`).join("")
             }</select></div>`
        : "";
      return `<div class="stage-card" data-uid="${uid}" data-sid="${esc(f.staged_id)}"
                   data-kind="${esc(f.kind)}" data-count="${f.count}">
          <div class="fn"><span class="ext">${esc((f.filename.split(".").pop() || "").toUpperCase())}</span>
            <span>${esc(f.filename)}</span>
            <span class="meta">${f.count ? f.count + " " + esc(f.units) : ""}</span></div>
          ${picker}${engSel}</div>`;
    }).join("") +
      `<div class="stage-actions"><button class="btn sm" id="${side}-stage-go">Read selected →</button>
       <button class="btn ghost sm" id="${side}-stage-cancel">Cancel</button></div>`;

    qsa(".sheet-all", box).forEach((a) => (a.onchange = () => {
      qsa(`.sheet-chk[data-uid="${a.dataset.uid}"]`, box).forEach((c) => (c.checked = a.checked));
    }));
    qsa(".range-all", box).forEach((a) => (a.onchange = () => {
      const inp = box.querySelector(`.range-in[data-uid="${a.dataset.uid}"]`);
      inp.disabled = a.checked; if (a.checked) inp.value = "";
    }));
    $(side + "-stage-go").onclick = () => commitStage(side);
    $(side + "-stage-cancel").onclick = () => (box.innerHTML = "");
  }

  async function commitStage(side) {
    const box = $(side + "-stage");
    const selections = qsa(".stage-card", box).map((card) => {
      const uid = card.dataset.uid;
      const sel = { staged_id: card.dataset.sid, count: Number(card.dataset.count || 0) };
      const allSheets = box.querySelector(`.sheet-all[data-uid="${uid}"]`);
      if (allSheets && !allSheets.checked) {
        sel.sheets = qsa(`.sheet-chk[data-uid="${uid}"]`, box)
          .filter((c) => c.checked).map((c) => c.value);
      }
      const allRange = box.querySelector(`.range-all[data-uid="${uid}"]`);
      if (allRange && !allRange.checked) {
        sel.pages = (box.querySelector(`.range-in[data-uid="${uid}"]`).value || "").trim();
      }
      const engSel = box.querySelector(`.eng-sel[data-uid="${uid}"]`);
      if (engSel) sel.engine = engSel.value;
      return sel;
    });
    const btn = $(side + "-stage-go");
    btn.disabled = true; btn.innerHTML = '<span class="sp"></span> Reading…';
    try {
      const d = await (await fetch(api("/upload_staged"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sid: state.sid, side, selections }) })).json();
      if (d.error) { toast(d.error, true); return; }
      box.innerHTML = "";
      state.cols[side] = d.side_columns;
      state.tables[side] = d.side_tables;
      const files = {};
      d.tables.forEach((t) => (files[t.file] = (files[t.file] || 0) + 1));
      const list = $(side + "-list");
      Object.keys(files).forEach((fname) => {
        if (qsa(`[data-fname="${cssEsc(fname)}"]`, list).length) return;
        const li = document.createElement("li");
        li.dataset.fname = fname;
        li.innerHTML = `<span class="ext">${extOf(fname)}</span><span>${esc(fname)}</span>
          <span class="meta">${files[fname]} table${files[fname] > 1 ? "s" : ""}</span>`;
        list.appendChild(li);
      });
      $(side + "-count").textContent = d.side_file_count + " file" + (d.side_file_count > 1 ? "s" : "");
      renderTables(side);
      renderWarnings(side, d.warnings);
      afterUpload();
      toast(`Read ${d.tables.length} table${d.tables.length === 1 ? "" : "s"}.`);
    } finally { btn.disabled = false; btn.textContent = "Read selected →"; }
  }
  function renderTables(side) {
    const box = $(side + "-tables"), rows = state.tables[side];
    if (!rows.length) { box.innerHTML = ""; return; }
    box.innerHTML = `<div class="thd" style="display:flex;align-items:center;justify-content:space-between">
        <span>Detected tables — untick to exclude</span>
        <label class="chk" style="font-size:11px;gap:6px">
          <input type="checkbox" id="${side}-all" checked> Select all</label></div>` +
      rows.map((t) => `<label class="tbl">
        <input type="checkbox" class="${side}-tchk" data-tid="${esc(t.id)}" checked>
        <span class="nm">${esc(t.table)}</span>
        <span class="cols">${esc(t.columns.join(" · "))}</span>
        <span class="rc">${t.rows} rows</span>
        <button class="view" data-view="${esc(t.id)}" data-side="${side}">View</button></label>`).join("");
    $(side + "-all").onchange = (e) => {
      qsa(`.${side}-tchk`).forEach((c) => (c.checked = e.target.checked));
      refreshColumnPickers();
    };
    qsa(`.${side}-tchk`, box).forEach((c) => (c.onchange = () => {
      const all = qsa(`.${side}-tchk`);
      $(side + "-all").checked = all.every((x) => x.checked);
      refreshColumnPickers();
    }));
    qsa("[data-view]", box).forEach((b) => (b.onclick = (ev) => {
      ev.preventDefault(); ev.stopPropagation();
      showPreview(b.dataset.side, b.dataset.view);
    }));
  }
  function renderWarnings(side, warnings) {
    const box = $(side + "-warn");
    (warnings || []).forEach((w) => {
      const el = document.createElement("div");
      el.className = "wn " + w.severity;
      el.innerHTML = `<span class="wi">${w.severity === "error" ? "×" : "!"}</span>
        <span>${esc(w.file)}: ${esc(w.message)}</span>`;
      box.appendChild(el);
    });
  }
  function includedTables(side) {
    return qsa(`.${side}-tchk`).filter((c) => c.checked).map((c) => c.dataset.tid);
  }
  // Columns offered on the Map-fields page come from the *selected* tables only,
  // so unticking a sheet/page removes its columns from the pickers.
  function selectedColumns(side) {
    const chosen = new Set(includedTables(side));
    const tables = state.tables[side] || [];
    const active = tables.filter((t) => chosen.size === 0 || chosen.has(t.id));
    const out = [];
    (active.length ? active : tables).forEach((t) =>
      (t.columns || []).forEach((c) => { if (!out.includes(c)) out.push(c); }));
    return out.length ? out : state.cols[side];
  }
  function afterUpload() {
    const ready = state.cols.left.length && state.cols.right.length;
    if (ready) { unlock("mapping"); unlock("matching"); markDone("upload"); }
    setStepbar(state.page);
  }
  function wireDrop(side) {
    const drop = $(side + "-drop"), input = $(side + "-input");
    const open = () => input.click();
    drop.onclick = open;
    drop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } };
    input.onchange = (e) => uploadSide(side, [...e.target.files]);
    ["dragover", "dragenter"].forEach((ev) => drop.addEventListener(ev, (e) => {
      e.preventDefault(); drop.classList.add("drag"); }));
    ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => {
      e.preventDefault(); drop.classList.remove("drag"); }));
    drop.addEventListener("drop", (e) => uploadSide(side, [...e.dataTransfer.files]));
  }

  // ---------------- mapping ----------------
  function colOptions(cols, sel) {
    return ['<option value="">—</option>'].concat(
      cols.map((c) => `<option ${c === sel ? "selected" : ""}>${esc(c)}</option>`)).join("");
  }
  function addFieldRow(p) {
    p = p || {};
    const tr = document.createElement("tr");
    const agg = ["sum", "mean", "first", "last", "count", "max", "min"];
    tr.innerHTML = `
      <td><input class="f-name" placeholder="e.g. invoice" value="${esc(p.name || "")}"></td>
      <td><select class="f-role">
        <option value="key" ${p.role === "key" ? "selected" : ""}>key</option>
        <option value="value" ${p.role !== "key" ? "selected" : ""}>value</option></select></td>
      <td><select class="f-dtype">
        ${["text", "money", "numeric", "date"].map((d) =>
          `<option value="${d}" ${p.dtype === d ? "selected" : ""}>${d}</option>`).join("")}</select></td>
      <td><select class="f-left">${colOptions(selectedColumns("left"), p.left)}</select></td>
      <td><select class="f-right">${colOptions(selectedColumns("right"), p.right)}</select></td>
      <td><input class="f-abstol num w-s" type="number" step="any" placeholder="0"
                 value="${p.abstol != null ? p.abstol : ""}"></td>
      <td><input class="f-reltol num w-m" type="number" step="any" placeholder="0"></td>
      <td><input class="f-fuzzy num w-m" type="number" min="0" max="100" placeholder="—"
                 value="${p.fuzzy != null ? p.fuzzy : ""}"></td>
      <td><select class="f-agg">${agg.map((a) =>
        `<option value="${a}" ${p.agg === a ? "selected" : ""}>${a}</option>`).join("")}</select></td>
      <td><button class="btn ghost sm f-del" title="Remove">✕</button></td>`;
    tr.querySelector(".f-del").onclick = () => { tr.remove(); refreshBlocking(); };
    tr.querySelector(".f-name").oninput = refreshBlocking;
    tr.querySelector(".f-role").onchange = refreshBlocking;
    $("fields-body").appendChild(tr);
  }
  function refreshColumnPickers() {
    qsa("#fields-body tr").forEach((tr) => {
      const l = tr.querySelector(".f-left"), r = tr.querySelector(".f-right");
      l.innerHTML = colOptions(selectedColumns("left"), l.value);
      r.innerHTML = colOptions(selectedColumns("right"), r.value);
    });
  }
  function refreshBlocking() {
    const keys = qsa("#fields-body tr").filter((tr) =>
      tr.querySelector(".f-role").value === "key" && tr.querySelector(".f-name").value.trim())
      .map((tr) => tr.querySelector(".f-name").value.trim());
    const sel = $("blocking-field"), cur = sel.value;
    sel.innerHTML = '<option value="">— none —</option>' +
      keys.map((k) => `<option ${k === cur ? "selected" : ""}>${esc(k)}</option>`).join("");
  }
  function collectFields() {
    return qsa("#fields-body tr").map((tr) => {
      const name = tr.querySelector(".f-name").value.trim();
      if (!name) return null;
      return {
        name, role: tr.querySelector(".f-role").value, dtype: tr.querySelector(".f-dtype").value,
        left_source: tr.querySelector(".f-left").value || null,
        right_source: tr.querySelector(".f-right").value || null,
        abs_tol: tr.querySelector(".f-abstol").value || "0",
        rel_tol: (parseFloat(tr.querySelector(".f-reltol").value) || 0) / 100,
        text_fuzzy_threshold: tr.querySelector(".f-fuzzy").value || null,
        agg: tr.querySelector(".f-agg").value,
      };
    }).filter(Boolean);
  }
  async function suggestMapping() {
    const b = $("suggest-btn");
    b.disabled = true; b.innerHTML = `<span class="sp"></span> Analyzing…`;
    try {
      const d = await (await fetch(api("/suggest_mapping"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sid: state.sid,
          included_left: includedTables("left"),
          included_right: includedTables("right") }) })).json();
      if (d.error) { toast(d.error, true); return; }
      $("fields-body").innerHTML = "";
      (d.fields || []).forEach((f) => addFieldRow({
        name: f.name, role: f.role, dtype: f.dtype, left: f.left_source, right: f.right_source,
        abstol: f.abs_tol, fuzzy: f.text_fuzzy_threshold, agg: f.agg }));
      refreshBlocking();
      toast(`Suggested ${d.fields.length} field${d.fields.length === 1 ? "" : "s"} from your data.`);
    } catch (e) { toast("Could not suggest a mapping.", true); }
    finally { b.disabled = false; b.textContent = "✨ Auto-suggest mapping"; }
  }

  // ---------------- run ----------------
  async function run() {
    const fields = collectFields();
    if (!fields.some((f) => f.role === "key")) { toast("Add at least one key field.", true); return; }
    const prim = $("step-primary");
    prim.disabled = true; prim.innerHTML = `<span class="sp"></span> Running…`;
    const body = {
      sid: state.sid, fields,
      included_left: includedTables("left"), included_right: includedTables("right"),
      matching: {
        fuzzy_enabled: $("fuzzy-enabled").checked,
        fuzzy_threshold: parseFloat($("fuzzy-threshold").value) || 90,
        semantic_enabled: $("semantic-enabled").checked,
        semantic_threshold: parseFloat($("semantic-threshold").value) || 75,
        numeric_enabled: $("numeric-enabled").checked,
        accept_threshold: parseFloat($("accept-threshold").value) || 0.6,
        blocking_field: $("blocking-field").value || null,
      },
      melt: $("melt-mode").checked,
      norm: { casefold_keys: $("casefold-keys").checked, dayfirst: $("dayfirst").checked,
              strip_non_english: $("strip-non-english").checked },
    };
    try {
      const d = await (await fetch(api("/reconcile"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) })).json();
      if (d.error) { toast(d.error, true); return; }
      state.lastResult = d;
      renderResults(d);
      markDone("mapping"); markDone("matching"); unlock("results");
      goto("results");
    } catch (e) { toast("Reconciliation failed.", true); }
    finally { prim.disabled = false; prim.textContent = "Run reconciliation ▶"; }
  }

  // ---------------- results ----------------
  const fmt = (v) => {
    if (v === null || v === undefined || v === "") return "";
    if (typeof v === "number") return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
    return v;
  };
  function metric(k, v, cls) {
    return `<div class="metric ${cls || ""}"><div class="v">${v}</div><div class="k">${k}</div></div>`;
  }
  function renderResults(d) {
    const s = d.summary;
    $("results-sub").innerHTML =
      `${s.matched_pairs} matched · ${s.matched_exact} exact, ${s.matched_fuzzy_or_semantic} fuzzy/semantic
       · fuzzy engine: <span class="num">${s.fuzzy_backend}</span>`;
    $("metrics").innerHTML =
      metric("Reconciled", s.reconciled, "tie") +
      metric("Breaks", s.breaks, "brk") +
      metric("Unmatched ◀", s.unmatched_left, "hold") +
      metric("Unmatched ▶", s.unmatched_right, "hold") +
      metric("Recon rate", s.reconciliation_rate + "%", "seam");
    $("gauge-card").innerHTML = donut(s);
    $("variance").innerHTML = varianceBars(d.field_variance);
    buildTabs(d);
  }
  function donut(s) {
    const segs = [
      ["Reconciled", s.reconciled, "var(--tie)"],
      ["Breaks", s.breaks, "var(--break)"],
      ["Unmatched", s.unmatched_left + s.unmatched_right, "var(--hold)"],
    ];
    const total = segs.reduce((a, x) => a + x[1], 0) || 1;
    const R = 54, C = 2 * Math.PI * R;
    let off = 0, arcs = "";
    segs.forEach(([, n, col]) => {
      const len = (n / total) * C;
      arcs += `<circle cx="70" cy="70" r="${R}" fill="none" stroke="${col}" stroke-width="16"
        stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-off}"
        transform="rotate(-90 70 70)" stroke-linecap="butt"></circle>`;
      off += len;
    });
    const legend = segs.map(([lbl, n, col]) =>
      `<span><span class="sw" style="background:${col}"></span>${lbl} <b class="num">${n}</b></span>`).join("");
    return `<svg viewBox="0 0 140 140" width="150" height="150" role="img" aria-label="Match breakdown">
      <circle cx="70" cy="70" r="${R}" fill="none" stroke="var(--wash)" stroke-width="16"></circle>
      ${arcs}
      <text x="70" y="66" text-anchor="middle" font-family="var(--mono)" font-size="24"
        font-weight="600" fill="var(--ink)">${s.reconciliation_rate}%</text>
      <text x="70" y="84" text-anchor="middle" font-family="var(--body)" font-size="10"
        fill="var(--muted)">reconciled</text></svg>
      <div class="gauge-legend">${legend}</div>`;
  }
  function varianceBars(fv) {
    const num = fv.filter((f) => f.sum_abs_difference !== null);
    if (!num.length) return `<div class="muted">No numeric fields to chart.</div>`;
    const max = Math.max(...num.map((f) => Math.abs(f.sum_abs_difference) || 0), 1);
    return num.map((f) => {
      const w = Math.max(2, (Math.abs(f.sum_abs_difference) / max) * 100);
      const cls = f.n_breaks > 0 ? "brk" : "tie";
      return `<div class="vbar"><span class="name">${esc(f.field)}</span>
        <span class="track"><span class="fill" style="width:${w}%"></span></span>
        <span class="val ${cls}">${fmt(f.sum_left_minus_right)}${f.n_breaks ? ` · ${f.n_breaks}✕` : ""}</span></div>`;
    }).join("");
  }
  function buildTabs(d) {
    const s = d.summary;
    const defs = [
      ["breaks", "Breaks", s.breaks], ["reconciled", "Reconciled", s.reconciled],
      ["unmatched_left", "Unmatched ◀", s.unmatched_left],
      ["unmatched_right", "Unmatched ▶", s.unmatched_right],
    ];
    const tb = $("result-tabs"); tb.innerHTML = "";
    defs.forEach(([key, label, n], i) => {
      const b = document.createElement("button");
      b.className = "tab"; b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", String(i === 0));
      b.innerHTML = `${label}<span class="cnt">${n}</span>`;
      b.onclick = () => {
        qsa(".tab").forEach((x) => x.setAttribute("aria-selected", "false"));
        b.setAttribute("aria-selected", "true");
        showPanel(d, key);
      };
      tb.appendChild(b);
    });
    showPanel(d, "breaks");
  }
  function showPanel(d, key) {
    const trunc = d.truncated && d.truncated[key];
    $("result-panel").innerHTML = dataTable(d[key]) +
      (trunc ? `<div class="muted" style="padding:10px 13px">Preview capped at 250 rows — export for the full set.</div>` : "");
  }
  function dataTable(rows) {
    if (!rows || !rows.length)
      return `<div class="empty"><div class="big">✓</div>Nothing in this bucket.</div>`;
    const cols = Object.keys(rows[0]);
    const head = cols.map((c) => `<th>${esc(c)}</th>`).join("");
    const body = rows.map((row) => "<tr>" + cols.map((c) => {
      let v = row[c];
      if (c === "match_type") return `<td><span class="badge ${v}">${esc(v)}</span></td>`;
      if (c.endsWith("__ok")) return `<td class="${v ? "ok" : "bad"}">${v ? "✓" : "✕"}</td>`;
      const numeric = typeof v === "number";
      return `<td class="${numeric ? "n" : ""}">${esc(fmt(v))}</td>`;
    }).join("") + "</tr>").join("");
    return `<table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }
  function exportWorkbook() {
    if (!state.lastResult) { toast("Run a reconciliation first.", true); return; }
    window.location = api("/export") + "?sid=" + encodeURIComponent(state.sid);
  }

  // ---------------- table preview modal ----------------
  async function showPreview(side, tid) {
    const modal = $("preview-modal");
    $("preview-title").textContent = "Loading…";
    $("preview-sub").textContent = "";
    $("preview-body").innerHTML = '<div class="empty">Fetching table…</div>';
    modal.classList.add("open"); modal.setAttribute("aria-hidden", "false");
    try {
      const d = await (await fetch(api("/table_preview"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sid: state.sid, side, table_id: tid }) })).json();
      if (d.error) { $("preview-body").innerHTML = `<div class="empty">${esc(d.error)}</div>`; return; }
      $("preview-title").textContent = d.table;
      const qc = d.qc || {};
      let qcTxt = "";
      if (qc.status === "ok") qcTxt = ` · ✓ QC ${qc.passed}/${qc.checked} subtotals foot`;
      else if (qc.status === "check") qcTxt = ` · ⚠ QC ${qc.passed}/${qc.checked} — verify totals`;
      $("preview-sub").textContent =
        `${esc(d.file)} · ${d.total_rows} rows × ${d.columns.length} columns` +
        (d.truncated ? " · showing first 500" : "") + qcTxt;
      const head = d.columns.map((c) => `<th>${esc(c)}</th>`).join("");
      const body = d.rows.map((r) => "<tr>" + r.map((v) => {
        const num = typeof v === "number";
        return `<td class="${num ? "n" : ""}">${v === null || v === undefined ? "" : esc(fmt(v))}</td>`;
      }).join("") + "</tr>").join("");
      $("preview-body").innerHTML =
        `<table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    } catch (e) {
      $("preview-body").innerHTML = '<div class="empty">Could not load this table.</div>';
    }
  }
  function closePreview() {
    const m = $("preview-modal");
    m.classList.remove("open"); m.setAttribute("aria-hidden", "true");
  }

  // ---------------- references & admin ----------------
  async function loadReferences() {
    let refs = [];
    try { refs = (await (await fetch(api("/reference/list"))).json()).references || []; }
    catch (e) { refs = []; }
    const sel = $("ref-select");
    sel.innerHTML = '<option value="">— select a reference —</option>' +
      refs.map((r) => `<option value="${esc(r.id)}">${esc(r.source)} (${r.tables} tables)</option>`).join("");
    const mng = $("ref-manage");
    mng.innerHTML = refs.length ? refs.map((r) => `<div class="ref-row">
        <span class="nm">${esc(r.source)}</span><span class="rc">${r.tables} tables · ${esc(r.id)}</span>
        <span class="grow"></span>
        <button class="btn ghost sm" data-del="${esc(r.id)}">Delete</button></div>`).join("")
      : '<div class="muted">No references yet. Upload one above.</div>';
    qsa("[data-del]", mng).forEach((b) => (b.onclick = () => deleteReference(b.dataset.del)));
  }
  async function useReference() {
    const ref = $("ref-select").value;
    if (!ref) { toast("Pick a reference first.", true); return; }
    const d = await (await fetch(api("/reference/use"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sid: state.sid, side: "right", ref_id: ref }) })).json();
    if (d.error) { toast(d.error, true); return; }
    state.cols.right = d.side_columns;
    state.tables.right = d.tables;
    renderTables("right");
    $("right-count").textContent = "reference";
    $("melt-mode").checked = true;   // references are tidy/long
    toast("Reference loaded. Tidy/long mode enabled for matching.");
    afterUpload();
  }
  function adminToken() { return state.adminToken || ""; }
  async function adminLogin() {
    const b = $("admin-login-btn"); b.disabled = true; b.textContent = "Signing in…";
    try {
      const d = await (await fetch(api("/admin/login"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: $("admin-user").value, password: $("admin-pass").value })
      })).json();
      if (d.error || !d.token) { toast(d.error || "Login failed.", true); return; }
      state.adminToken = d.token;
      $("admin-login-card").style.display = "none";
      $("admin-panels").style.display = "";
      loadReferences();
      toast("Signed in as admin.");
    } catch (e) { toast("Login failed.", true); }
    finally { b.disabled = false; b.textContent = "Log in"; }
  }
  async function uploadReference() {
    const f = $("ref-file").files[0];
    if (!adminToken()) { toast("Sign in first.", true); return; }
    if (!f) { toast("Choose a file.", true); return; }
    const fd = new FormData();
    fd.append("token", adminToken()); fd.append("file", f);
    fd.append("name", $("ref-name").value.trim() || f.name);
    fd.append("melt", String($("ref-melt").checked));
    const b = $("ref-upload"); b.disabled = true; b.textContent = "Saving…";
    try {
      const d = await (await fetch(api("/admin/reference/upload"), { method: "POST", body: fd })).json();
      if (d.error) { toast(d.error, true); return; }
      toast(`Saved reference "${d.source}" (${d.tables} tables).`);
      loadReferences();
    } finally { b.disabled = false; b.textContent = "Save to library"; }
  }
  function downloadProcessed() {
    const f = $("ref-file").files[0];
    if (!adminToken()) { toast("Sign in first.", true); return; }
    if (!f) { toast("Choose a file.", true); return; }
    const fd = new FormData();
    fd.append("token", adminToken()); fd.append("file", f);
    fd.append("name", $("ref-name").value.trim() || f.name);
    fd.append("melt", String($("ref-melt").checked));
    fetch(api("/admin/reference/download"), { method: "POST", body: fd })
      .then((r) => r.blob()).then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = "processed_tables.xlsx"; a.click();
        URL.revokeObjectURL(url);
      }).catch(() => toast("Download failed.", true));
  }
  async function uploadAdminSynonyms() {
    const f = $("syn-file").files[0];
    if (!adminToken()) { toast("Sign in first.", true); return; }
    if (!f) { toast("Choose a file.", true); return; }
    const fd = new FormData(); fd.append("token", adminToken()); fd.append("file", f);
    const d = await (await fetch(api("/admin/synonyms/save"), { method: "POST", body: fd })).json();
    if (d.error) { toast(d.error, true); return; }
    toast(`Global synonyms saved: ${d.aliases} aliases, ${d.concepts} concepts.`);
  }
  async function deleteReference(id) {
    const d = await (await fetch(api("/admin/reference/delete"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: adminToken(), ref_id: id }) })).json();
    if (d.error) { toast(d.error, true); return; }
    toast("Reference deleted."); loadReferences();
  }

  // ---------------- hero art ----------------
  function heroArt() {
    const rows = [
      ["INV-1001", "1,200.50", "1,200.50", "tie"],
      ["INV-1002", "3,400.00", "3,400.00", "tie"],
      ["INV-1003", "5,000.00", "4,999.00", "brk"],
      ["INV-1004", "880.00", "880.00", "tie"],
    ];
    const y0 = 58, h = 34, gap = 12;
    let left = "", right = "", links = "";
    rows.forEach((r, i) => {
      const y = y0 + i * (h + gap);
      const cy = y + h / 2;
      const col = r[3] === "brk" ? "var(--break)" : "var(--tie)";
      left += rowRect(16, y, r[0], r[1], "left");
      right += rowRect(244, y, r[0], r[2], "right");
      links += `<line x1="176" y1="${cy}" x2="244" y2="${cy}" stroke="${col}"
        stroke-width="2" stroke-dasharray="${r[3] === "brk" ? "3 3" : "0"}"></line>
        <circle cx="210" cy="${cy}" r="3.5" fill="${col}"></circle>`;
      if (r[3] === "brk")
        links += `<text x="210" y="${cy - 8}" text-anchor="middle" font-family="var(--mono)"
          font-size="9" fill="var(--break)">Δ 1.00</text>`;
    });
    return `<svg viewBox="0 0 420 268" width="100%" role="img" aria-label="Reconciliation illustration">
      <text x="16" y="40" font-family="var(--mono)" font-size="11" letter-spacing="1"
        fill="var(--muted)">LEFT</text>
      <text x="404" y="40" text-anchor="end" font-family="var(--mono)" font-size="11" letter-spacing="1"
        fill="var(--muted)">RIGHT</text>
      <line x1="210" y1="30" x2="210" y2="248" stroke="var(--seam)" stroke-width="1.5"
        stroke-opacity=".35"></line>
      ${links}${left}${right}</svg>`;
  }
  function rowRect(x, y, id, amt, side) {
    const w = 160;
    return `<g>
      <rect x="${x}" y="${y}" width="${w}" height="34" rx="8" fill="var(--surface-2)"
        stroke="var(--line)"></rect>
      <text x="${x + 12}" y="${y + 22}" font-family="var(--mono)" font-size="11"
        fill="var(--ink-2)">${id}</text>
      <text x="${x + w - 12}" y="${y + 22}" text-anchor="end" font-family="var(--mono)"
        font-size="11" fill="var(--ink)">${amt}</text></g>`;
  }

  // ---------------- utils ----------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  const cssEsc = (s) => String(s).replace(/["\\]/g, "\\$&");

  // ---------------- boot ----------------
  document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    $("hero-art").innerHTML = heroArt();
    ["left", "right"].forEach(wireDrop);
    qsa(".nav").forEach((n) => (n.onclick = () => goto(n.dataset.page)));
    qsa(".ms").forEach((m) => (m.onclick = () => goto(m.dataset.page)));
    $("hero-start").onclick = () => goto("upload");
    $("hero-how").onclick = () => goto("upload");
    $("add-field").onclick = () => addFieldRow();
    $("suggest-btn").onclick = suggestMapping;
    $("clear-map-btn").onclick = () => {
      $("fields-body").innerHTML = "";
      addFieldRow();                 // leave one blank row ready for manual mapping
      refreshColumnPickers();
      setStepbar(state.page);
      toast("Cleared all mappings — map fields manually.");
    };
    $("export-btn").onclick = exportWorkbook;
    $("ref-use").onclick = useReference;
    $("preview-close").onclick = closePreview;
    $("preview-modal").addEventListener("click", (e) => {
      if (e.target === $("preview-modal")) closePreview();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closePreview();
    });
    $("admin-login-btn").onclick = adminLogin;
    $("ref-upload").onclick = uploadReference;
    $("ref-download").onclick = downloadProcessed;
    $("syn-upload").onclick = uploadAdminSynonyms;
    loadReferences();

    // refresh column pickers whenever mapping opens
    const mo = new MutationObserver(() => {
      if ($("page-mapping").classList.contains("active")) refreshColumnPickers();
    });
    mo.observe($("page-mapping"), { attributes: true, attributeFilter: ["class"] });

    updateNav(); setStepbar("overview");
    initSession();
  });
})();
