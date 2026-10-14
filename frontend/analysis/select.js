(() => {
  const $ = (id) => document.getElementById(id);
  const val = (id) => String($(id)?.value ?? "").trim();
  const num = (id) => {
    const raw = val(id);
    if (!raw) return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  };
  const esc = (v) => String(v ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  const NAMES = { open: "开盘", high: "最高", low: "最低", close: "收盘" };
  const CACHE_KEY = "orbit-select-scan-v1";
  let aborter = null;
  let passCount = 0, failCount = 0, totalCount = 0, rankSeq = 0;
  let pendingKline = [];
  let lastRows = [];
  let lastParams = null;
  let saveTimer = null;

  function saveCache() {
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({
        params: lastParams, rows: lastRows, total: totalCount, ts: Date.now(),
      }));
    } catch { /* ignore: 配额不足时放弃缓存 */ }
  }

  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveCache, 1500);
  }

  function restoreCache() {
    let c = null;
    try { c = JSON.parse(sessionStorage.getItem(CACHE_KEY) || "null"); } catch { /* ignore */ }
    if (!c || !Array.isArray(c.rows) || !c.rows.length) return false;
    lastParams = c.params || null;
    if (lastParams) {
      const set = (id, v) => { if ($(id) && v != null) $(id).value = v; };
      set("selPxStart", lastParams.start); set("selPxEnd", lastParams.end);
      set("selPxTarget", lastParams.target); set("selPxOrder", lastParams.order);
      const pm = (lastParams.filters || {}).percent_min || {};
      const px = (lastParams.filters || {}).percent_max || {};
      set("selFOpenMin", pm.open); set("selFOpenMax", px.open);
      set("selFHighMin", pm.high); set("selFHighMax", px.high);
      set("selFLowMin", pm.low); set("selFLowMax", px.low);
      set("selFCloseMin", pm.close); set("selFCloseMax", px.close);
    }
    totalCount = Number(c.total) || c.rows.length;
    lastRows = [];
    passCount = 0; failCount = 0; rankSeq = 0;
    if ($("selResultHead")) $("selResultHead").classList.remove("hidden");
    c.rows.forEach((row) => appendRow(row, true));
    mountPendingKlines();
    if ($("selMeta")) $("selMeta").textContent = `共${totalCount}只 · 通过${passCount}只（已恢复）`;
    setProgress(lastRows.length, totalCount);
    if ($("selProgressText")) $("selProgressText").textContent += lastRows.length < totalCount ? " · 可继续扫描剩余" : " · 已完成";
    if (lastRows.length < totalCount && $("selRunBtn")) $("selRunBtn").textContent = "继续扫描剩余";
    return true;
  }

  function collectPayload() {
    const pctMin = {}, pctMax = {};
    [["open", "selFOpenMin", "selFOpenMax"], ["high", "selFHighMin", "selFHighMax"],
     ["low", "selFLowMin", "selFLowMax"], ["close", "selFCloseMin", "selFCloseMax"]].forEach(([k, loId, hiId]) => {
      const lo = num(loId), hi = num(hiId);
      if (lo != null) pctMin[k] = Math.max(0, Math.min(100, lo));
      if (hi != null) pctMax[k] = Math.max(0, Math.min(100, hi));
    });
    return {
      start: val("selPxStart"),
      end: val("selPxEnd"),
      target: val("selPxTarget"),
      order: val("selPxOrder") || "desc",
      filters: { percent_min: pctMin, percent_max: pctMax },
    };
  }

  function setRange(days) {
    const end = new Date();
    const start = new Date(end.getTime() - (Number(days) - 1) * 864e5);
    const f = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    if ($("selPxStart")) $("selPxStart").value = f(start);
    if ($("selPxEnd")) $("selPxEnd").value = f(end);
    if ($("selPxTarget")) $("selPxTarget").value = f(end);
  }

  function showErr(msg) {
    const box = $("selError");
    if (!box) return;
    if (!msg) { box.classList.add("hidden"); box.textContent = ""; return; }
    box.textContent = msg;
    box.classList.remove("hidden");
  }

  function fmt(v, d = 1) {
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(d) : "—";
  }

  function pctChip(m, k) {
    const c = (m || {})[k] || {};
    const pct = Number(c.percent);
    if (!Number.isFinite(pct)) return "";
    return `<span class="screen-chip" data-tone="${pct >= 80 ? "up" : pct < 20 ? "down" : ""}" title="${NAMES[k]}价${c.value ?? ""} · 排名${c.rank ?? ""}/${c.total ?? ""}"><em>${NAMES[k]}</em>${fmt(pct)}</span>`;
  }

  function cardHtml(row) {
    const m = row.metrics || {};
    const close = Number((m.close || {}).percent);
    const href = `/company.html?code=${encodeURIComponent(row.symbol || "")}&from=analysis`;
    return `<article class="screen-card is-stock" data-code="${esc(row.symbol || "")}" data-key="${esc(row.symbol || "")}" tabindex="0">
      <a class="screen-card-head" href="${esc(href)}" title="打开公司详情">
        <span class="screen-rank">${++rankSeq}</span>
        <div class="screen-card-name">
          <strong>${esc(row.name || row.symbol || "")}</strong>
          <span>${esc(row.symbol || "")}</span>
        </div>
        <div class="screen-card-score">
          <b>${Number.isFinite(close) ? fmt(close) : "—"}</b>
          <span>收盘分位</span>
        </div>
      </a>
      <article class="chart-card chart-card--kline" data-kline-code="${esc(row.symbol || "")}">
        <header class="chart-card__head">
          <div class="chart-card__head-main">
            <div class="chart-card__title">
              <span class="chart-card__mark" aria-hidden="true"></span>
              <h3>日K</h3>
            </div>
            <div class="chart-kline-hover chart-hover-card hidden" aria-hidden="true"></div>
          </div>
          <p class="chart-card__meta muted">日K · 前复权</p>
        </header>
        <div class="chart-card__stage">
          <div class="chart-canvas-wrap">
            <canvas width="960" height="360" aria-label="个股走势图"></canvas>
            <p class="muted chart-empty hidden">暂无行情数据</p>
          </div>
        </div>
      </article>
      <footer class="screen-card-meta">
        ${["open", "high", "low", "close"].map((k) => pctChip(m, k)).join("")}
        ${((row.reasons || []).length && !row.pass) ? `<span class="screen-card-error">${esc(row.reasons.join("；"))}</span>` : ""}
      </footer>
    </article>`;
  }

  function mountPendingKlines() {
    if (!pendingKline.length || !window.OrbitKline) return;
    const batch = pendingKline.splice(0, pendingKline.length);
    requestAnimationFrame(() => batch.forEach((card) => {
      const kline = card.querySelector(".chart-card--kline");
      const code = kline && kline.dataset.klineCode;
      if (kline && code && window.OrbitKline) {
        try { window.OrbitKline.mount(kline, { code, carousel: true }); } catch { /* ignore */ }
      }
    }));
  }

  function setProgress(done, total) {
    const bar = $("selProgress"), fill = $("selProgressFill"), text = $("selProgressText");
    if (bar) bar.classList.remove("hidden");
    if (fill && total) fill.style.width = `${Math.round((done / total) * 100)}%`;
    if (text) text.textContent = `已扫描 ${done} / ${total} · 通过 ${passCount} 只`;
    if ($("selPassCount")) $("selPassCount").textContent = `通过 ${passCount} 只`;
  }

  function resetRun(keepRows = false) {
    if (!keepRows) {
      passCount = 0; failCount = 0; totalCount = 0; rankSeq = 0;
      pendingKline = [];
      lastRows = [];
      lastParams = null;
      const list = $("selResult");
      if (list) list.innerHTML = "";
    }
    if ($("selResultHead")) $("selResultHead").classList.remove("hidden");
    if ($("selPassCount")) $("selPassCount").textContent = `通过 ${passCount} 只`;
  }

  function appendRow(row, silent = false) {
    lastRows.push(row);
    if (!row.pass) {
      failCount += 1;
      if ($("selOnlyPass")?.checked !== false) return;
    } else {
      passCount += 1;
    }
    const list = $("selResult");
    if (!list) return;
    list.querySelector(".screen-empty")?.remove();
    const wrap = document.createElement("div");
    wrap.innerHTML = cardHtml(row).trim();
    const card = wrap.firstElementChild;
    if (card) {
      list.appendChild(card);
      pendingKline.push(card);
      if (!silent) scheduleSave();
      if (pendingKline.length >= 6) mountPendingKlines();
      else if (!appendRow._t) {
        appendRow._t = setTimeout(() => { appendRow._t = null; mountPendingKlines(); }, 400);
      }
    }
  }

  function applyOnlyPass() {
    const list = $("selResult");
    if (!list) return;
    const onlyPass = $("selOnlyPass")?.checked !== false;
    rankSeq = 0;
    list.innerHTML = "";
    pendingKline = [];
    lastRows.filter((r) => r.pass || !onlyPass).forEach((row) => {
      const wrap = document.createElement("div");
      if (row.pass) {
        const tmp = { ...row };
        wrap.innerHTML = cardHtml(tmp).trim();
      } else {
        wrap.innerHTML = cardHtml(row).trim();
      }
      const card = wrap.firstElementChild;
      if (card) { list.appendChild(card); pendingKline.push(card); }
    });
    // rank numbers were assigned during cardHtml; re-sequence visually
    [...list.querySelectorAll(".screen-rank")].forEach((el, i) => { el.textContent = String(i + 1); });
    mountPendingKlines();
  }

  async function run() {
    if (aborter) { aborter.abort(); aborter = null; }
    showErr("");
    const body = collectPayload();
    if (!body.start || !body.end || !body.target) { showErr("价格区间与目标日不能为空"); return; }
    const resume = lastRows.length > 0 && lastParams
      && JSON.stringify({ ...body, filters: body.filters }) === JSON.stringify({ ...lastParams, filters: lastParams.filters })
      && lastRows.length < totalCount;
    const btn = $("selRunBtn"), stop = $("selStopBtn");
    btn.disabled = true;
    btn.classList.add("is-loading");
    btn.textContent = "扫描中…";
    stop?.classList.remove("hidden");
    resetRun(resume);
    lastParams = body;
    setProgress(lastRows.length, totalCount);
    if ($("selProgressText")) $("selProgressText").textContent = resume ? "正在继续扫描剩余…" : "正在获取全市场列表…";
    aborter = new AbortController();
    const base = resume ? lastRows.length : 0;
    try {
      const payload = resume
        ? { ...body, skip: lastRows.map((r) => r.symbol) }
        : { ...body };
      const res = await fetch("/api/analysis/select/price-stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/x-ndjson" },
        body: JSON.stringify({ ...payload, max_workers: 32 }),
        signal: aborter.signal,
      });
      if (!res.ok || !res.body) {
        let msg = `请求失败(${res.status})`;
        try { const j = await res.json(); msg = j.error || msg; } catch { /* ignore */ }
        throw new Error(msg);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (value) buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, idx).trim();
          buf = buf.slice(idx + 1);
          if (!line) continue;
          let msg;
          try { msg = JSON.parse(line); } catch { continue; }
          if (msg.type === "info") {
            totalCount = base + (Number(msg.total) || 0);
            setProgress(base, totalCount);
          } else if (msg.type === "item") {
            setProgress(base + (Number(msg.done) || 0), totalCount || base + (Number(msg.total) || 0));
            totalCount = base + (Number(msg.total) || (totalCount - base) || 0);
            if (msg.row) appendRow(msg.row);
          } else if (msg.type === "done") {
            totalCount = base + (Number(msg.total) || (totalCount - base) || 0);
            setProgress(base + (Number(msg.done) || 0), totalCount);
          }
        }
        if (done) break;
      }
      mountPendingKlines();
      if ($("selProgressText")) $("selProgressText").textContent += " · 完成";
    } catch (e) {
      if (e?.name === "AbortError") {
        if ($("selProgressText")) $("selProgressText").textContent += " · 已停止";
      } else {
        showErr(e.message || String(e));
      }
    } finally {
      aborter = null;
      mountPendingKlines();
      saveCache();
      btn.disabled = false;
      btn.classList.remove("is-loading");
      btn.textContent = "开始全市场扫描";
      stop?.classList.add("hidden");
      if ($("selMeta")) $("selMeta").textContent = `共${totalCount}只 · 通过${passCount}只`;
    }
  }

  function isSelectView() {
    if (document.body?.dataset?.screenMode) return document.body.dataset.screenMode === "select";
    return new URLSearchParams(location.search).get("view") === "select";
  }

  function syncVisible() {
    const panel = $("selectPanel");
    if (!panel) return;
    panel.classList.toggle("hidden", !isSelectView());
  }

  function setQuick(kind) {
    const set = (id, v) => { if ($(id)) $(id).value = v; };
    if (kind === "high") { set("selFCloseMin", "80"); set("selFCloseMax", ""); }
    else if (kind === "mid") { set("selFCloseMin", "40"); set("selFCloseMax", "70"); }
    else if (kind === "low") { set("selFCloseMin", ""); set("selFCloseMax", "20"); }
    else { set("selFCloseMin", ""); set("selFCloseMax", ""); }
  }

  document.addEventListener("click", (e) => {
    if (e.target.closest?.("#selRunBtn")) { run(); return; }
    if (e.target.closest?.("#selStopBtn")) { aborter?.abort(); return; }
    if (e.target.closest?.("#selResetBtn")) {
      ["selFOpenMin", "selFOpenMax", "selFHighMin", "selFHighMax", "selFLowMin", "selFLowMax", "selFCloseMin", "selFCloseMax"]
        .forEach((id) => { if ($(id)) $(id).value = ""; });
      return;
    }
    const preset = e.target.closest?.(".sel-presets button");
    if (preset) {
      document.querySelectorAll(".sel-presets button").forEach((b) => b.classList.toggle("is-active", b === preset));
      setRange(preset.dataset.range || 365);
      return;
    }
    const q = e.target.closest?.(".select-quick button");
    if (q) setQuick(q.dataset.q);
  });
  document.addEventListener("change", (e) => {
    if (e.target?.id === "selOnlyPass") applyOnlyPass();
  });
  document.addEventListener("DOMContentLoaded", () => {
    if (!restoreCache() && !val("selPxStart") && !val("selPxEnd")) setRange(365);
    syncVisible();
    const list = $("selResult");
    if (list && !list.dataset.swipeBound) {
      list.dataset.swipeBound = "1";
      let sx = 0, sl = 0, down = false;
      list.addEventListener("pointerdown", (e) => {
        if (e.target.closest?.("a,button,canvas")) return;
        down = true; sx = e.clientX; sl = list.scrollLeft;
      });
      window.addEventListener("pointermove", (e) => {
        if (!down) return;
        list.scrollLeft = sl - (e.clientX - sx);
      });
      window.addEventListener("pointerup", () => { down = false; });
    }
  });
  if (!val("selPxStart") && !val("selPxEnd")) setRange(365);
  syncVisible();
})();
