(() => {
  const POLL_MS = 15000;

  const state = {
    tree: [],
    l1: "",
    l2: "",
    l3: "",
    fetching: false,
    pollTimer: 0,
    pendingLoad: null,
  };

  const $ = (id) => document.getElementById(id);

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
    el.textContent = kind === "live" ? "LIVE" : kind === "busy" ? "SYNC" : "IDLE";
  }

  function emptyRow(text, cols) {
    return `<tr class="is-empty"><td colspan="${cols}">${text}</td></tr>`;
  }

  function fundCells(node) {
    return `
      <td class="num market-fund-cell" data-tone="${tone(node.main_net)}">${fmtYi(node.main_net)}</td>
      <td class="num market-fund-cell" data-tone="${tone(node.main_net_5d)}">${fmtYi(node.main_net_5d)}</td>
      <td class="num market-fund-cell" data-tone="${tone(node.main_net_10d)}">${fmtYi(node.main_net_10d)}</td>`;
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
      <td class="num" data-tone="up">${fmtCountPair(node.up_count, node.limit_up_count)}</td>
      <td class="num" data-tone="down">${fmtCountPair(node.down_count, node.limit_down_count)}</td>`;
  }

  function industryRows(items, selected) {
    const rows = byChange(items);
    if (!rows.length) return emptyRow("暂无数据", 7);
    return rows
      .map((n) => {
        const active = n.code === selected ? " is-active" : "";
        return `<tr class="is-row${active}" data-code="${n.code}">
          <td>${n.name}</td>
          <td class="num" data-tone="${tone(n.change_pct)}">${fmtPct(n.change_pct)}</td>
          ${limitCells(n)}
          ${fundCells(n)}
        </tr>`;
      })
      .join("");
  }

  function stockRows(items) {
    const rows = byChange(items);
    if (!rows.length) return emptyRow("点三级行业后展示成分股", 7);
    return rows
      .map((n) => {
        return `<tr class="is-row is-stock" data-code="${n.code}" data-industry="${n.parent_code || ""}">
          <td><span class="market-stock-name">${n.name}</span><span class="market-stock-code">${n.code}</span></td>
          <td class="num" data-tone="${tone(n.change_pct)}">${fmtPct(n.change_pct)}</td>
          <td class="num">${fmtRatio(n.pe_ttm)}</td>
          <td class="num">${fmtRatio(n.pb)}</td>
          ${fundCells(n)}
        </tr>`;
      })
      .join("");
  }

  function render() {
    const l1Items = state.tree || [];
    $("l1Body").innerHTML = industryRows(l1Items, state.l1);
    $("l1Hint").textContent = `${l1Items.length} 个 · 涨跌排序`;

    const l1 = find(l1Items, state.l1);
    const l2Items = l1 ? l1.children || [] : [];
    $("l2Body").innerHTML = l1
      ? industryRows(l2Items, state.l2)
      : emptyRow("点一级行业后展示二级", 7);
    $("l2Hint").textContent = l1 ? `${l1.name} · ${l2Items.length} 个` : "点一级后展开";

    const l2 = find(l2Items, state.l2);
    const l3Items = l2 ? l2.children || [] : [];
    $("l3Body").innerHTML = l2
      ? industryRows(l3Items, state.l3)
      : emptyRow("点二级行业后展示三级", 7);
    $("l3Hint").textContent = l2 ? `${l2.name} · ${l3Items.length} 个` : "点二级后展开";

    const l3 = find(l3Items, state.l3);
    const stocks = l3 ? l3.children || [] : [];
    $("l4Body").innerHTML = l3 ? stockRows(stocks) : emptyRow("点三级行业后展示成分股", 7);
    $("l4Hint").textContent = l3 ? `${l3.name} · ${stocks.length} 只` : "点三级后展开";
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
  }

  function renderSummary(data) {
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
    const tag = data.live ? "指数实时" : "全量";
    $("marketMeta").textContent = `${data.updated_at || ""} · ${tag}${l1 ? ` · ${l1.name}` : ""}`;
  }

  async function load({ silent = false, refresh = false, live = false } = {}) {
    if (state.fetching) {
      state.pendingLoad = { silent, refresh, live };
      return;
    }
    state.fetching = true;
    if (!silent) $("loading").classList.remove("hidden");
    if (!silent) $("errorBox").classList.add("hidden");
    setLive("busy");
    try {
      const q = new URLSearchParams();
      if (refresh) q.set("refresh", "1");
      if (live) q.set("live", "1");
      const resp = await fetch(`/api/market/tree?${q}`, { cache: "no-store" });
      const json = await resp.json();
      if (!json.ok) throw new Error(json.error || "加载失败");
      const data = json.data || {};
      state.tree = data.tree || [];
      if (state.l1 && !find(state.tree, state.l1)) {
        state.l1 = "";
        state.l2 = "";
        state.l3 = "";
      }
      render();
      renderSummary(data);
      const errs = data.errors || [];
      if (errs.length) {
        $("errorBox").textContent = errs.join("；");
        $("errorBox").classList.remove("hidden");
      } else if (silent) {
        $("errorBox").classList.add("hidden");
      }
      setLive("live");
    } catch (exc) {
      if (!silent) {
        $("errorBox").textContent = String(exc.message || exc);
        $("errorBox").classList.remove("hidden");
      }
      setLive("idle");
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
    $("l4Body").addEventListener("click", (ev) => {
      const row = ev.target.closest("tr.is-stock[data-code]");
      if (!row) return;
      const qs = new URLSearchParams({ code: row.dataset.code });
      if (row.dataset.industry) qs.set("industry", row.dataset.industry);
      window.location.href = `/company.html?${qs}`;
    });
    $("refreshBtn").addEventListener("click", () => void load({ silent: true, refresh: true, live: false }));
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        void load({ silent: true, live: true });
      }
    });
  }

  bind();
  void load().then(startPoll);
})();
