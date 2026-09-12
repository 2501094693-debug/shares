(() => {
  const POLL_MS = 15000;
  const MIN_DATE = "2014-01-01";

  const state = {
    tree: [],
    l1: "",
    l2: "",
    l3: "",
    date: "",
    source: "",
    fetching: false,
    pollTimer: 0,
    pendingLoad: null,
  };

  const $ = (id) => document.getElementById(id);

  function todayISO() {
    const d = new Date();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${d.getFullYear()}-${m}-${day}`;
  }

  function parseDate(text) {
    const raw = String(text || "").trim().slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return "";
    const d = new Date(`${raw}T12:00:00`);
    if (Number.isNaN(d.getTime())) return "";
    return raw;
  }

  function toISO(d) {
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${d.getFullYear()}-${m}-${day}`;
  }

  function shiftDate(iso, dir) {
    const d = new Date(`${iso}T12:00:00`);
    if (Number.isNaN(d.getTime())) return todayISO();
    do {
      d.setDate(d.getDate() + dir);
    } while (d.getDay() === 0 || d.getDay() === 6);
    const next = toISO(d);
    if (next < MIN_DATE) return MIN_DATE;
    const today = todayISO();
    if (next > today) return today;
    return next;
  }

  function isHistory() {
    return Boolean(state.date) && state.date !== todayISO();
  }

  function isSnapshot() {
    return state.source === "snapshot";
  }

  function histOnly() {
    return isHistory() && !isSnapshot();
  }

  function colCount() {
    return histOnly() ? 6 : 7;
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

  function fmtRatio(value) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(2);
  }

  function fmtPx(value) {
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

  function byChange(items) {
    return (items || []).slice().sort((a, b) => {
      const va = Number(a.change_pct);
      const vb = Number(b.change_pct);
      const na = Number.isFinite(va) ? va : -Infinity;
      const nb = Number.isFinite(vb) ? vb : -Infinity;
      return nb - na;
    });
  }

  function find(nodes, code) {
    return (nodes || []).find((n) => n.code === code) || null;
  }

  function setLive(kind) {
    const el = $("liveDot");
    el.dataset.state = kind;
    el.textContent = kind === "live" ? "LIVE" : kind === "busy" ? "SYNC" : kind === "hist" ? "HIST" : "IDLE";
  }

  function emptyRow(text, cols) {
    return `<tr class="is-empty"><td colspan="${cols}">${text}</td></tr>`;
  }

  function fundCells(node) {
    return `
      <td class="num market-fund-cell market-col-live" data-tone="${tone(node.main_net)}">${fmtYi(node.main_net)}</td>
      <td class="num market-fund-cell market-col-live" data-tone="${tone(node.main_net_5d)}">${fmtYi(node.main_net_5d)}</td>
      <td class="num market-fund-cell market-col-live" data-tone="${tone(node.main_net_10d)}">${fmtYi(node.main_net_10d)}</td>`;
  }

  function histCells(node) {
    return `
      <td class="num market-col-hist">${fmtPx(node.price)}</td>
      <td class="num market-col-hist">${fmtPct(node.turnover)}</td>
      <td class="num market-col-hist">${fmtRatio(node.pe)}</td>
      <td class="num market-col-hist">${fmtRatio(node.pb)}</td>`;
  }

  function fmtCountPair(total, limit) {
    const up = Number(total);
    const lim = Number(limit);
    if (!Number.isFinite(up) && !Number.isFinite(lim)) return "—";
    const a = Number.isFinite(up) ? up : 0;
    const b = Number.isFinite(lim) ? lim : 0;
    return `${a}(${b})`;
  }

  function limitCells(node) {
    return `
      <td class="num market-col-live" data-tone="up">${fmtCountPair(node.up_count, node.limit_up_count)}</td>
      <td class="num market-col-live" data-tone="down">${fmtCountPair(node.down_count, node.limit_down_count)}</td>`;
  }

  function industryRows(items, selected) {
    const rows = byChange(items);
    if (!rows.length) return emptyRow("暂无数据", colCount());
    return rows
      .map((n) => {
        const active = n.code === selected ? " is-active" : "";
        return `<tr class="is-row${active}" data-code="${n.code}">
          <td class="market-name">${n.name || n.code || "—"}</td>
          <td class="num" data-tone="${tone(n.change_pct)}">${fmtPct(n.change_pct)}</td>
          ${limitCells(n)}
          ${fundCells(n)}
          ${histCells(n)}
        </tr>`;
      })
      .join("");
  }

  function stockRows(items) {
    const rows = byChange(items);
    if (!rows.length) {
      return emptyRow(histOnly() ? "历史日报只覆盖一、二级指数" : "点三级行业后展示成分股", colCount());
    }
    return rows
      .map((n) => {
        return `<tr class="is-row is-stock" data-code="${n.code}" data-industry="${n.parent_code || ""}">
          <td><span class="market-stock-name">${n.name || "—"}</span><span class="market-stock-code">${n.code}</span></td>
          <td class="num" data-tone="${tone(n.change_pct)}">${fmtPct(n.change_pct)}</td>
          <td class="num">${fmtRatio(n.pe_ttm)}</td>
          <td class="num">${fmtRatio(n.pb)}</td>
          ${fundCells(n)}
        </tr>`;
      })
      .join("");
  }

  function syncDateControls() {
    const today = todayISO();
    const input = $("dateInput");
    input.min = MIN_DATE;
    input.max = today;
    input.value = state.date || today;
    $("todayBtn").disabled = !isHistory();
    $("nextDateBtn").disabled = !isHistory();
    document.querySelector(".market-page")?.classList.toggle("is-history", histOnly());
    const sub = $("marketSub");
    if (sub) {
      sub.textContent = histOnly()
        ? "申万历史日报：一级 / 二级指数涨跌，三级无官方点位"
        : isHistory()
          ? "本地收盘快照：一级 → 二级 → 三级 → 成分股"
          : "一级 → 二级 → 三级 → 成分股，每张表按涨跌排序";
    }
  }

  function syncUrl() {
    const url = new URL(window.location.href);
    if (isHistory()) url.searchParams.set("date", state.date);
    else url.searchParams.delete("date");
    window.history.replaceState(null, "", url);
  }

  function render() {
    const l1Items = state.tree || [];
    $("l1Body").innerHTML = industryRows(l1Items, state.l1);
    $("l1Hint").textContent = `${l1Items.length} 个 · 涨跌排序`;

    const l1 = find(l1Items, state.l1);
    const l2Items = l1 ? l1.children || [] : [];
    $("l2Body").innerHTML = l1
      ? industryRows(l2Items, state.l2)
      : emptyRow("点一级行业后展示二级", colCount());
    $("l2Hint").textContent = l1 ? `${l1.name} · ${l2Items.length} 个` : "点一级后展开";

    const l2 = find(l2Items, state.l2);
    const l3Items = l2 ? l2.children || [] : [];
    $("l3Body").innerHTML = l2
      ? industryRows(l3Items, state.l3)
      : emptyRow("点二级行业后展示三级", colCount());
    $("l3Hint").textContent = l2
      ? histOnly()
        ? `${l2.name} · ${l3Items.length} 个 · 无历史点位`
        : `${l2.name} · ${l3Items.length} 个`
      : "点二级后展开";

    const l3 = find(l3Items, state.l3);
    const stocks = l3 ? l3.children || [] : [];
    $("l4Body").innerHTML = l3
      ? stockRows(stocks)
      : emptyRow(histOnly() ? "历史日报只覆盖一、二级指数" : "点三级行业后展示成分股", colCount());
    $("l4Hint").textContent = l3
      ? histOnly()
        ? `${l3.name} · 无历史成分股行情`
        : `${l3.name} · ${stocks.length} 只`
      : "点三级后展开";
  }

  function selectL1(code) {
    state.l1 = code;
    state.l2 = "";
    state.l3 = "";
    render();
  }

  function selectL2(code) {
    state.l2 = code;
    state.l3 = "";
    render();
  }

  function selectL3(code) {
    state.l3 = code;
    render();
    if (histOnly()) return;
    const l1 = find(state.tree, state.l1);
    const l2 = find(l1?.children, state.l2);
    const l3 = find(l2?.children, code);
    window.OrbitPrefetch?.intent({ industry: code, stocks: l3?.children || [] });
  }

  function renderSummary(data) {
    if (histOnly()) {
      const trade = data.trade_date || "";
      const snapped = trade && trade !== data.date ? ` · 交易日 ${trade}` : "";
      $("summaryBar").innerHTML = `
        <span><b class="is-up">${data.up ?? 0}</b> 涨</span>
        <span><b class="is-down">${data.down ?? 0}</b> 跌</span>
        <span>申万一 / 二级日报</span>
      `;
      $("marketMeta").textContent = `${data.date || ""}${snapped} · 历史`;
      return;
    }
    $("summaryBar").innerHTML = `
      <span><b class="is-up">${data.up ?? 0}</b> 涨</span>
      <span><b class="is-down">${data.down ?? 0}</b> 跌</span>
      <span>今日入 <b class="is-up">${fmtYi(data.inflow)}</b></span>
      <span>今日出 <b class="is-down">${fmtYi(data.outflow)}</b></span>
      <span>5日入 <b class="is-up">${fmtYi(data.inflow_5d)}</b></span>
      <span>5日出 <b class="is-down">${fmtYi(data.outflow_5d)}</b></span>
      <span>10日入 <b class="is-up">${fmtYi(data.inflow_10d)}</b></span>
      <span>10日出 <b class="is-down">${fmtYi(data.outflow_10d)}</b></span>
    `;
    const l1 = find(state.tree, state.l1);
    if (isSnapshot()) {
      $("marketMeta").textContent = `${data.trade_date || data.date || ""} · 收盘快照${l1 ? ` · ${l1.name}` : ""}`;
      return;
    }
    const tag = data.live ? "指数实时" : "全量";
    $("marketMeta").textContent = `${data.updated_at || ""} · ${tag}${l1 ? ` · ${l1.name}` : ""}`;
  }

  async function fetchTree({ refresh = false, live = false, lite = false } = {}) {
    const q = new URLSearchParams();
    if (refresh) q.set("refresh", "1");
    if (live) q.set("live", "1");
    if (lite) q.set("lite", "1");
    const path = `/api/market/tree${q.toString() ? `?${q}` : ""}`;
    if (window.OrbitHttp) return OrbitHttp.get(path);
    const resp = await fetch(path, { cache: "no-store" });
    const body = await resp.json();
    if (!body.ok) throw new Error(body.error || "加载失败");
    return body;
  }

  async function fetchHistory(date, refresh = false) {
    const q = new URLSearchParams({ date });
    if (refresh) q.set("refresh", "1");
    const path = `/api/market/history?${q}`;
    if (window.OrbitHttp) return OrbitHttp.get(path);
    const resp = await fetch(path, { cache: "no-store" });
    const body = await resp.json();
    if (!body.ok) throw new Error(body.error || "加载失败");
    return body;
  }

  function applyPayload(data) {
    state.tree = data.tree || [];
    state.source = data.source || (data.history ? "sw_daily" : "");
    if (state.l1 && !find(state.tree, state.l1)) {
      state.l1 = "";
      state.l2 = "";
      state.l3 = "";
    }
    syncDateControls();
    render();
    renderSummary(data);
    const errs = data.errors || [];
    if (errs.length) {
      $("errorBox").textContent = errs.join("；");
      $("errorBox").classList.remove("hidden");
    } else {
      $("errorBox").classList.add("hidden");
    }
  }

  async function load({ silent = false, refresh = false, live = false } = {}) {
    const date = state.date || todayISO();
    if (state.fetching) {
      state.pendingLoad = { silent, refresh, live };
      return;
    }
    if (!isHistory() && !silent && !refresh && !live && !state.tree.length && window.OrbitHttp) {
      const cached = await OrbitHttp.peek("/api/market/tree", { allowStale: true });
      const liteCached = cached?.data?.tree?.length
        ? null
        : await OrbitHttp.peek("/api/market/tree?lite=1", { allowStale: true });
      if (cached?.data?.tree?.length) {
        applyPayload(cached.data);
        setLive("busy");
      } else if (liteCached?.data?.tree?.length) {
        applyPayload(liteCached.data);
        setLive("busy");
      } else {
        void fetchTree({ lite: true })
          .then((json) => {
            if (!state.tree.length && json?.data?.tree?.length) {
              applyPayload(json.data);
              $("loading").classList.add("hidden");
              setLive("busy");
            }
          })
          .catch(() => {});
      }
    }
    state.fetching = true;
    if (!silent && !state.tree.length) $("loading").classList.remove("hidden");
    if (!silent) $("errorBox").classList.add("hidden");
    setLive("busy");
    try {
      const json = isHistory()
        ? await fetchHistory(date, refresh)
        : await fetchTree({ refresh, live });
      if ((state.date || todayISO()) !== date) return;
      applyPayload(json.data || {});
      setLive(isHistory() || isSnapshot() ? "hist" : "live");
    } catch (exc) {
      if (!silent && !state.tree.length) {
        $("errorBox").textContent = String(exc.message || exc);
        $("errorBox").classList.remove("hidden");
      }
      setLive(state.tree.length ? (isHistory() || isSnapshot() ? "hist" : "live") : "idle");
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

  function setDate(next, { loadNow = true } = {}) {
    const today = todayISO();
    const parsed = parseDate(next) || today;
    state.date = parsed > today ? today : parsed < MIN_DATE ? MIN_DATE : parsed;
    syncDateControls();
    syncUrl();
    if (loadNow) {
      state.tree = [];
      void load({ silent: false, refresh: false, live: false });
    }
  }

  function startPoll() {
    window.clearInterval(state.pollTimer);
    state.pollTimer = window.setInterval(() => {
      if (document.hidden || isHistory() || isSnapshot()) return;
      void load({ silent: true, live: true });
    }, POLL_MS);
  }

  function bind() {
    $("l1Body").addEventListener("click", (ev) => {
      const row = ev.target.closest("tr[data-code]");
      if (row) selectL1(row.dataset.code);
    });
    $("l2Body").addEventListener("click", (ev) => {
      const row = ev.target.closest("tr[data-code]");
      if (row) selectL2(row.dataset.code);
    });
    $("l3Body").addEventListener("click", (ev) => {
      const row = ev.target.closest("tr[data-code]");
      if (row) selectL3(row.dataset.code);
    });
    window.OrbitPrefetch?.bindHover($("l4Body"), "tr.is-stock[data-code]");
    $("l4Body").addEventListener("click", (ev) => {
      const row = ev.target.closest("tr.is-stock[data-code]");
      if (!row || histOnly()) return;
      const qs = new URLSearchParams({ code: row.dataset.code, from: "market" });
      if (row.dataset.industry) qs.set("industry", row.dataset.industry);
      window.location.href = `/company.html?${qs}`;
    });
    $("refreshBtn").addEventListener("click", () => void load({ silent: true, refresh: true, live: false }));
    $("dateInput").addEventListener("change", () => setDate($("dateInput").value));
    $("prevDateBtn").addEventListener("click", () => setDate(shiftDate(state.date || todayISO(), -1)));
    $("nextDateBtn").addEventListener("click", () => setDate(shiftDate(state.date || todayISO(), 1)));
    $("todayBtn").addEventListener("click", () => setDate(todayISO()));
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && !isHistory() && !isSnapshot()) {
        void load({ silent: true, live: true });
      }
    });
  }

  const bootDate = parseDate(new URLSearchParams(window.location.search).get("date")) || todayISO();
  state.date = bootDate > todayISO() ? todayISO() : bootDate;
  bind();
  syncDateControls();
  window.OrbitPrefetch?.boot("market");
  void load().then(startPoll);
})();
