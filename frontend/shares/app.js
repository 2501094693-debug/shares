(() => {
  const POLL_MS = 15000;

  const state = {
    items: [],
    industries: [],
    updatedAt: "",
    live: false,
    query: "",
    industry: "",
    tone: "",
    fetching: false,
    pendingLoad: null,
    pollTimer: 0,
    totalCount: 0,
    lite: false,
    renderFrom: 0,
  };

  const ROW_H = 37;
  const OVERSCAN = 18;

  const $ = (id) => document.getElementById(id);

  function escapeHtml(text) {
    return String(text ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtPct(value) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
  }

  function fmtYi(value) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    const abs = Math.abs(n);
    const sign = n < 0 ? "-" : n > 0 ? "+" : "";
    if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
    if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(1)}万`;
    return `${sign}${abs.toFixed(0)}`;
  }

  function fmtCap(value) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    const abs = Math.abs(n);
    if (abs >= 1e8) return `${(abs / 1e8).toFixed(2)}亿`;
    if (abs >= 1e4) return `${(abs / 1e4).toFixed(1)}万`;
    return abs.toFixed(0);
  }

  function fmtRatio(value) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(2);
  }

  function fmtPrice(value) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(2);
  }

  function tone(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n === 0) return "flat";
    return n > 0 ? "up" : "down";
  }

  function setLive(kind) {
    const el = $("liveDot");
    el.dataset.state = kind;
    el.textContent = kind === "live" ? "LIVE" : kind === "busy" ? "SYNC" : "IDLE";
  }

  function emptyRow(text) {
    return `<tr class="is-empty"><td colspan="11">${text}</td></tr>`;
  }

  function industryText(row) {
    return [row.l1_name, row.l3_name].filter(Boolean).join(" / ") || "—";
  }

  function filtered() {
    const q = state.query.trim().toLowerCase();
    return (state.items || []).filter((row) => {
      const chg = Number(row.change_pct);
      if (state.tone === "up" && !(Number.isFinite(chg) && chg > 0)) return false;
      if (state.tone === "down" && !(Number.isFinite(chg) && chg < 0)) return false;
      if (state.industry && row.l1_name !== state.industry) return false;
      if (!q) return true;
      const hay = [row.name, row.code, row.l1_name, row.l2_name, row.l3_name]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }

  function renderTone() {
    $("toneSeg").querySelectorAll("button[data-tone]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.tone === state.tone);
    });
  }

  function renderIndustries() {
    const sel = $("industrySelect");
    const current = state.industry;
    const opts = ['<option value="">全部行业</option>'].concat(
      (state.industries || []).map((item) => {
        const name = item.name || "";
        const picked = name === current ? " selected" : "";
        return `<option value="${escapeHtml(name)}"${picked}>${escapeHtml(name)} ${item.count || 0}</option>`;
      })
    );
    sel.innerHTML = opts.join("");
    if (current && !state.industries.some((item) => item.name === current)) {
      state.industry = "";
      sel.value = "";
    }
  }

  function renderSummary(visible) {
    const total = state.totalCount || state.items.length;
    const up = visible.filter((r) => Number(r.change_pct) > 0).length;
    const down = visible.filter((r) => Number(r.change_pct) < 0).length;
    $("summaryBar").innerHTML = `
      <span>显示 <b>${visible.length}</b> / ${total}</span>
      <span><b class="is-up">${up}</b> 涨</span>
      <span><b class="is-down">${down}</b> 跌</span>
    `;
    const tag = state.live ? "盘口实时" : state.lite ? "首屏" : "全量";
    $("marketMeta").textContent = `${state.updatedAt || ""} · ${tag}`;
  }

  function stockRow(row) {
    return `<tr class="is-row is-stock" data-code="${escapeHtml(row.code || "")}" data-industry="${escapeHtml(row.l3_code || "")}">
      <td class="num shares-rank">${row.rank || "—"}</td>
      <td>
        <span class="market-stock-name">${escapeHtml(row.name || "—")}</span>
        <span class="market-stock-code">${escapeHtml(row.code || "")}</span>
      </td>
      <td class="num" data-tone="${tone(row.change_pct)}">${fmtPct(row.change_pct)}</td>
      <td class="num">${fmtPrice(row.price)}</td>
      <td class="shares-industry">${escapeHtml(industryText(row))}</td>
      <td class="num">${fmtRatio(row.pe_ttm)}</td>
      <td class="num">${fmtRatio(row.pb)}</td>
      <td class="num market-fund-cell" data-tone="${tone(row.main_net)}">${fmtYi(row.main_net)}</td>
      <td class="num market-fund-cell" data-tone="${tone(row.main_net_5d)}">${fmtYi(row.main_net_5d)}</td>
      <td class="num market-fund-cell" data-tone="${tone(row.main_net_10d)}">${fmtYi(row.main_net_10d)}</td>
      <td class="num">${fmtCap(row.market_cap)}</td>
    </tr>`;
  }

  function scrollBox() {
    return document.querySelector(".shares-board-scroll");
  }

  function windowSlice(rows) {
    const box = scrollBox();
    const viewH = box ? box.clientHeight : 640;
    const scrollTop = box ? box.scrollTop : 0;
    const start = Math.max(0, Math.floor(scrollTop / ROW_H) - OVERSCAN);
    const count = Math.ceil(viewH / ROW_H) + OVERSCAN * 2;
    state.renderFrom = start;
    return {
      start,
      rows: rows.slice(start, start + count),
      top: start * ROW_H,
      bottom: Math.max(0, (rows.length - start - count) * ROW_H),
    };
  }

  function renderTable() {
    const rows = filtered();
    renderTone();
    renderSummary(rows);
    if (!rows.length) {
      $("tableBody").innerHTML = emptyRow(state.items.length ? "没有匹配的股票" : "暂无数据");
      return;
    }
    if (rows.length <= 120) {
      $("tableBody").innerHTML = rows.map(stockRow).join("");
      return;
    }
    const slice = windowSlice(rows);
    $("tableBody").innerHTML = `${
      slice.top ? `<tr class="shares-pad" aria-hidden="true"><td colspan="11" style="height:${slice.top}px;padding:0;border:0"></td></tr>` : ""
    }${slice.rows.map(stockRow).join("")}${
      slice.bottom ? `<tr class="shares-pad" aria-hidden="true"><td colspan="11" style="height:${slice.bottom}px;padding:0;border:0"></td></tr>` : ""
    }`;
  }

  function render() {
    renderIndustries();
    renderTable();
  }

  async function fetchShares({ refresh = false, live = false, lite = false } = {}) {
    const q = new URLSearchParams();
    if (refresh) q.set("refresh", "1");
    if (live) q.set("live", "1");
    if (lite) q.set("lite", "1");
    const path = `/api/market/shares${q.toString() ? `?${q}` : ""}`;
    if (window.OrbitHttp) return OrbitHttp.get(path);
    const resp = await fetch(path, { cache: "no-store" });
    const body = await resp.json();
    if (!body.ok) throw new Error(body.error || "加载失败");
    return body;
  }

  function applyPayload(data, { lite = false } = {}) {
    const items = data.items || [];
    if ((lite || data.lite) && state.items.length > items.length) return;
    state.items = items;
    state.industries = data.industries || state.industries;
    state.updatedAt = data.updated_at || "";
    state.live = !!data.live;
    state.totalCount = Number(data.count) || items.length;
    state.lite = !!(data.lite || lite);
    render();
    const errs = data.errors || [];
    if (errs.length) {
      $("errorBox").textContent = errs.join("；");
      $("errorBox").classList.remove("hidden");
    } else {
      $("errorBox").classList.add("hidden");
    }
  }

  async function paintFromCache() {
    if (!window.OrbitHttp) return false;
    const full = await OrbitHttp.peek("/api/market/shares", { allowStale: true });
    if (full?.data?.items?.length) {
      applyPayload(full.data);
      return true;
    }
    const lite = await OrbitHttp.peek("/api/market/shares?lite=1", { allowStale: true });
    if (lite?.data?.items?.length) {
      applyPayload(lite.data, { lite: true });
      return true;
    }
    return false;
  }

  async function load({ silent = false, refresh = false, live = false } = {}) {
    if (state.fetching) {
      state.pendingLoad = { silent, refresh, live };
      return;
    }
    if (!silent && !refresh && !live && !state.items.length) {
      const hit = await paintFromCache();
      if (!hit) {
        void fetchShares({ lite: true })
          .then((json) => {
            if (json?.data?.items?.length) {
              applyPayload(json.data, { lite: true });
              $("loading").classList.add("hidden");
              setLive("busy");
            }
          })
          .catch(() => {});
      }
    }
    state.fetching = true;
    if (!silent && !state.items.length) $("loading").classList.remove("hidden");
    if (!silent) $("errorBox").classList.add("hidden");
    setLive("busy");
    try {
      const json = await fetchShares({ refresh, live });
      applyPayload(json.data || {});
      setLive("live");
    } catch (exc) {
      if (!silent && !state.items.length) {
        $("errorBox").textContent = String(exc.message || exc);
        $("errorBox").classList.remove("hidden");
      }
      setLive(state.items.length ? "live" : "idle");
    } finally {
      state.fetching = false;
      $("loading").classList.add("hidden");
      if (state.pendingLoad) {
        const next = state.pendingLoad;
        state.pendingLoad = null;
        void load(next);
      }
    }
  }

  function startPoll() {
    window.clearInterval(state.pollTimer);
    state.pollTimer = window.setInterval(() => {
      if (document.hidden) return;
      void load({ silent: true, live: true });
    }, POLL_MS);
  }

  function bind() {
    $("searchInput").addEventListener("input", (ev) => {
      state.query = ev.target.value || "";
      const box = scrollBox();
      if (box) box.scrollTop = 0;
      renderTable();
    });
    $("industrySelect").addEventListener("change", (ev) => {
      state.industry = ev.target.value || "";
      const box = scrollBox();
      if (box) box.scrollTop = 0;
      renderTable();
    });
    $("toneSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-tone]");
      if (!btn) return;
      state.tone = btn.dataset.tone || "";
      const box = scrollBox();
      if (box) box.scrollTop = 0;
      renderTable();
    });
    scrollBox()?.addEventListener("scroll", () => {
      if ((state.items || []).length <= 120) return;
      renderTable();
    }, { passive: true });
    window.OrbitPrefetch?.bindHover($("tableBody"), "tr.is-stock[data-code]");
    $("tableBody").addEventListener("click", (ev) => {
      const row = ev.target.closest("tr.is-stock[data-code]");
      if (!row) return;
      const qs = new URLSearchParams({ code: row.dataset.code, from: "shares" });
      if (row.dataset.industry) qs.set("industry", row.dataset.industry);
      window.location.href = `/company.html?${qs}`;
    });
    $("refreshBtn").addEventListener("click", () => {
      void load({ silent: true, refresh: true, live: false });
    });
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) void load({ silent: true, live: true });
    });
  }

  bind();
  window.OrbitPrefetch?.boot("shares");
  void load().then(() => {
    startPoll();
    window.OrbitPrefetch?.intent({ stocks: filtered().slice(0, 3) });
  });
})();
