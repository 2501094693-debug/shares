(() => {
  const PAGE_SIZE_KEY = "mine-stock-page-size";
  const PAGE_SIZES = new Set([20, 50, 100]);

  function readPageSize() {
    try {
      const n = Number(localStorage.getItem(PAGE_SIZE_KEY));
      if (PAGE_SIZES.has(n)) return n;
    } catch {
      /* ignore */
    }
    return 20;
  }

  const KLINE_MOUNT_CONCURRENCY = 2;
  const SORT_KEYS = new Set(["rank", "change_pct", "price", "pe_ttm", "pb", "market_cap"]);
  const SORT_LABELS = {
    rank: "加入顺序",
    change_pct: "涨跌",
    price: "现价",
    pe_ttm: "PE",
    pb: "PB",
    market_cap: "市值",
  };

  const state = {
    groups: [],
    selectedId: "",
    group: null,
    filter: "",
    page: 1,
    pageSize: readPageSize(),
    pageByGroup: {},
    sortKey: "rank",
    sortDir: "asc",
    sortByGroup: {},
    fetching: false,
    syncing: false,
    selectSeq: 0,
    suggestTimer: 0,
    suggestItems: [],
    suggestOpen: false,
    klineObserver: null,
    klineMountQueue: [],
    klineMountActive: 0,
    view: (() => {
      try {
        return localStorage.getItem("mine-stock-view") === "card" ? "card" : "list";
      } catch {
        return "list";
      }
    })(),
  };

  const $ = (id) => document.getElementById(id);

  function esc(value) {
    return String(value ?? "")
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

  function industryText(row) {
    return [row.l1_name, row.l3_name].filter(Boolean).join(" / ") || "—";
  }

  function setLive(kind) {
    const el = $("liveDot");
    if (!el) return;
    el.dataset.state = kind;
    el.textContent = kind === "live" ? "LIVE" : kind === "busy" ? "SYNC" : "IDLE";
  }

  function showError(message) {
    const box = $("errorBox");
    if (!message) {
      box.classList.add("hidden");
      box.textContent = "";
      return;
    }
    box.textContent = message;
    box.classList.remove("hidden");
  }

  function setLoading(on) {
    $("loading").classList.toggle("hidden", !on);
    if (on) showError("");
  }

  async function api(path, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    if (window.OrbitHttp && method === "GET") return OrbitHttp.get(path, options);
    const headers = { ...(options.headers || {}) };
    if (options.body && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    const res = await fetch(path, { ...options, headers, cache: "no-store" });
    const json = await res.json();
    if (!res.ok || json.ok === false) {
      throw new Error(json.error || `请求失败 (${res.status})`);
    }
    return json;
  }

  function readGroupFromUrl() {
    try {
      return new URLSearchParams(location.search).get("group") || "";
    } catch {
      return "";
    }
  }

  function writeGroupToUrl(groupId) {
    const url = new URL(location.href);
    if (groupId) url.searchParams.set("group", groupId);
    else url.searchParams.delete("group");
    history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }

  function stockHref(row) {
    const qs = new URLSearchParams({ code: row.code || "", from: "mine" });
    if (row.l3_code) qs.set("industry", row.l3_code);
    return `/company.html?${qs}`;
  }

  function parseCodes(text) {
    return String(text || "")
      .split(/[,，\s;；|]+/)
      .map((part) => part.trim())
      .filter(Boolean);
  }

  function sortValue(row, key) {
    if (key === "rank") {
      const n = Number(row?.rank);
      return Number.isFinite(n) ? n : Number.POSITIVE_INFINITY;
    }
    const n = Number(row?.[key]);
    return Number.isFinite(n) ? n : null;
  }

  function sortedStocks(rows) {
    const list = Array.isArray(rows) ? rows.slice() : [];
    const key = SORT_KEYS.has(state.sortKey) ? state.sortKey : "rank";
    const dir = state.sortDir === "asc" ? 1 : -1;
    list.sort((a, b) => {
      const av = sortValue(a, key);
      const bv = sortValue(b, key);
      if (av == null && bv == null) {
        return (Number(a.rank) || 0) - (Number(b.rank) || 0);
      }
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av !== bv) return av > bv ? dir : -dir;
      const ar = Number(a.rank) || 0;
      const br = Number(b.rank) || 0;
      if (ar !== br) return ar - br;
      return String(a.code || "").localeCompare(String(b.code || ""));
    });
    return list;
  }

  function filteredStocks() {
    const stocks = state.group?.stocks || [];
    const kw = state.filter.trim().toLowerCase();
    const filtered = !kw
      ? stocks
      : stocks.filter((row) => {
          const hay = [row.name, row.code, row.l1_name, row.l2_name, row.l3_name]
            .join(" ")
            .toLowerCase();
          return hay.includes(kw);
        });
    return sortedStocks(filtered);
  }

  function rememberSort() {
    if (!state.selectedId) return;
    state.sortByGroup[state.selectedId] = {
      key: state.sortKey,
      dir: state.sortDir,
    };
  }

  function restoreSort(groupId) {
    const saved = state.sortByGroup[groupId];
    if (saved && SORT_KEYS.has(saved.key)) {
      state.sortKey = saved.key;
      state.sortDir = saved.dir === "asc" ? "asc" : "desc";
      return;
    }
    state.sortKey = "rank";
    state.sortDir = "asc";
  }

  function setSort(key) {
    const next = SORT_KEYS.has(key) ? key : "rank";
    if (next === "rank") {
      state.sortKey = "rank";
      state.sortDir = "asc";
    } else if (next === state.sortKey) {
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortKey = next;
      // 涨跌/现价/市值默认降序，估值默认升序
      state.sortDir = next === "pe_ttm" || next === "pb" ? "asc" : "desc";
    }
    rememberSort();
    state.page = 1;
    rememberPage();
    renderStocks();
  }

  function syncSortButtons() {
    const key = SORT_KEYS.has(state.sortKey) ? state.sortKey : "rank";
    const asc = state.sortDir === "asc";
    document.querySelectorAll("[data-mine-sort]").forEach((btn) => {
      const btnKey = btn.getAttribute("data-mine-sort") || "";
      // 工具栏无「加入顺序」：仅在选中 PE/PB/涨跌等时高亮；表头 # 在 rank 时高亮
      const isSeg = Boolean(btn.closest("#sortSeg"));
      const on = isSeg ? btnKey === key && key !== "rank" : btnKey === key;
      btn.classList.toggle("is-active", on);
      btn.classList.toggle("is-asc", on && asc);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function totalPages(total) {
    return Math.max(1, Math.ceil(Math.max(0, Number(total) || 0) / state.pageSize));
  }

  function rememberPage() {
    if (!state.selectedId) return;
    state.pageByGroup[state.selectedId] = state.page;
  }

  function restorePage(groupId) {
    const saved = Number(state.pageByGroup[groupId] || 1);
    state.page = Number.isFinite(saved) && saved >= 1 ? saved : 1;
  }

  function clampPage(total) {
    const pages = totalPages(total);
    if (state.page > pages) state.page = pages;
    if (state.page < 1) state.page = 1;
    rememberPage();
    return pages;
  }

  function pagedStocks(rows) {
    clampPage(rows.length);
    const start = (state.page - 1) * state.pageSize;
    return rows.slice(start, start + state.pageSize);
  }

  function renderPager(total) {
    const pager = $("stockPager");
    const info = $("pageInfo");
    const prev = $("prevPage");
    const next = $("nextPage");
    const sizeSel = $("pageSize");
    if (!pager || !info || !prev || !next) return;
    if (!state.selectedId || !state.group || total <= 0) {
      pager.hidden = true;
      return;
    }
    const pages = clampPage(total);
    pager.hidden = false;
    if (sizeSel && Number(sizeSel.value) !== state.pageSize) {
      sizeSel.value = String(state.pageSize);
    }
    const start = (state.page - 1) * state.pageSize + 1;
    const end = Math.min(total, state.page * state.pageSize);
    info.textContent = `${start}-${end} / ${total} · 第 ${state.page}/${pages} 页`;
    prev.disabled = state.page <= 1;
    next.disabled = state.page >= pages;
  }

  function turnPage(nextPage) {
    if (nextPage < 1) return;
    const total = filteredStocks().length;
    const pages = totalPages(total);
    if (nextPage > pages) return;
    state.page = nextPage;
    rememberPage();
    renderStocks();
    const board = document.querySelector(".mine-stock-scroll") || $("stockCards");
    if (board && typeof board.scrollTo === "function") {
      try {
        board.scrollTo({ top: 0, left: 0 });
      } catch {
        board.scrollTop = 0;
        board.scrollLeft = 0;
      }
    }
  }

  function renderSummary() {
    const bar = $("summaryBar");
    const meta = $("marketMeta");
    const totalGroups = state.groups.length;
    const totalStocks = state.groups.reduce((sum, g) => sum + Number(g.count || 0), 0);
    const current = state.group ? Number(state.group.count || 0) : 0;
    const stocks = state.group?.stocks || [];
    const up = stocks.filter((r) => Number(r.change_pct) > 0).length;
    const down = stocks.filter((r) => Number(r.change_pct) < 0).length;
    if (bar) {
      bar.innerHTML = `
        <span>分组 <b>${totalGroups}</b></span>
        <span>合计 <b>${totalStocks}</b></span>
        <span>当前 <b>${current}</b></span>
        ${
          state.group
            ? `<span><b class="is-up">${up}</b> 涨</span><span><b class="is-down">${down}</b> 跌</span>`
            : ""
        }
      `;
    }
    if (meta) {
      const quoteAt = state.group?.quote_updated_at || "";
      meta.textContent = state.group
        ? `${state.group.name} · 行情 ${quoteAt || state.group.updated_at || "—"}`
        : "未选择分组";
    }
    $("groupMeta").textContent = `${totalGroups} 个`;
  }

  function needThsLogin(message) {
    return String(message || "").indexOf("THS_NEED_QRCODE") >= 0;
  }

  function handleSyncError(err) {
    const message = err && err.message ? err.message : String(err);
    if (needThsLogin(message)) {
      showError("同花顺未登录，已弹出扫码框，扫码成功后请重试同步");
      if (window.ThsAuth && typeof window.ThsAuth.openModal === "function") {
        window.ThsAuth.openModal();
      } else {
        window.dispatchEvent(new CustomEvent("ths:need-auth"));
      }
    } else {
      showError(message);
    }
  }

  async function syncGroup(groupId, btn) {
    if (!groupId || state.syncing) return null;
    state.syncing = true;
    setLive("busy");
    if (btn) {
      btn.disabled = true;
      btn.dataset.busy = "1";
    }
    try {
      const json = await api(`/api/mine/synchro/ths/push/${encodeURIComponent(groupId)}`, {
        method: "POST",
      });
      const d = json.data || {};
      if (d.result === "skipped_empty") {
        showError(`分组「${d.name || groupId}」为空，已跳过（同花顺不支持空分组）`);
      } else {
        showError("");
      }
      setLive("live");
      return d;
    } catch (err) {
      handleSyncError(err);
      setLive("idle");
      return null;
    } finally {
      state.syncing = false;
      if (btn) {
        btn.disabled = false;
        delete btn.dataset.busy;
      }
      paint();
    }
  }

  async function syncAll() {
    if (state.syncing) return;
    state.syncing = true;
    setLive("busy");
    const btn = $("syncAllBtn");
    if (btn) btn.disabled = true;
    try {
      const json = await api("/api/mine/synchro/ths/push", { method: "POST" });
      const d = json.data || {};
      const items = d.items || [];
      const failed = items.filter((i) => i.result !== "ok" && i.result !== "skipped_empty");
      if (!items.length) {
        showError("没有可同步的分组");
      } else if (failed.length) {
        showError(`同步完成：${d.ok || 0}/${d.total || items.length} 成功，失败：${failed.map((i) => i.name || i.group_id).join("、")}`);
      } else {
        showError("");
      }
      setLive("live");
    } catch (err) {
      handleSyncError(err);
      setLive("idle");
    } finally {
      state.syncing = false;
      if (btn) btn.disabled = false;
      paint();
    }
  }

  function renderGroups() {
    const root = $("groupList");
    if (!state.groups.length) {
      root.innerHTML = `<p class="mine-empty muted">还没有分组</p>`;
      return;
    }
    root.innerHTML = state.groups
      .map((g) => {
        const active = g.id === state.selectedId ? " is-active" : "";
        return `<div class="mine-group-row${active}" role="option" aria-selected="${
          g.id === state.selectedId ? "true" : "false"
        }" data-group-id="${esc(g.id)}">
          <button type="button" class="mine-group-item" data-select="${esc(g.id)}" title="查看分组">
            <span class="mine-group-name">${esc(g.name)}</span>
            <span class="mine-group-count">${Number(g.count || 0)}</span>
          </button>
          <button type="button" class="btn ghost sm mine-sync-btn" data-sync="${esc(g.id)}" title="同步「${esc(g.name)}」到同花顺账号">同步</button>
        </div>`;
      })
      .join("");
  }

  function setStockPaneEnabled(on) {
    $("filterInput").disabled = !on;
    $("addInput").disabled = !on;
    $("addStockBtn").disabled = !on;
    $("deleteGroupBtn").disabled = !on;
    const syncBtn = $("syncGroupBtn");
    if (syncBtn) syncBtn.disabled = !on;
  }

  function applyView() {
    const isCard = state.view === "card";
    const scroll = document.querySelector(".mine-stock-scroll");
    const cards = $("stockCards");
    if (scroll) scroll.hidden = isCard;
    if (cards) cards.hidden = !isCard;
    const listBtn = $("viewListBtn");
    const cardBtn = $("viewCardBtn");
    if (listBtn) listBtn.classList.toggle("is-on", !isCard);
    if (cardBtn) cardBtn.classList.toggle("is-on", isCard);
  }

  function setView(view) {
    state.view = view === "card" ? "card" : "list";
    try {
      localStorage.setItem("mine-stock-view", state.view);
    } catch {
      /* 忽略无痕模式等写入失败 */
    }
    applyView();
    renderStocks();
  }

  function klineBlock(code) {
    return `<article class="chart-card chart-card--kline" data-kline-code="${esc(code)}">
      <header class="chart-card__head">
        <div class="chart-card__head-main">
          <div class="chart-card__title">
            <span class="chart-card__mark" aria-hidden="true"></span>
            <h3>走势</h3>
          </div>
          <div class="chart-kline-hover chart-hover-card hidden" aria-hidden="true"></div>
        </div>
        <p class="chart-card__meta muted">日K · 前复权</p>
        <div class="chart-card__controls">
          <div class="chart-select-group">
            <label class="chart-select-wrap" aria-label="周期">
              <select class="chart-select" disabled>
                <option selected>日K</option>
              </select>
            </label>
            <label class="chart-select-wrap" aria-label="复权">
              <select class="chart-select" disabled>
                <option selected>前复权</option>
              </select>
            </label>
          </div>
        </div>
      </header>
      <div class="chart-card__stage">
        <div class="chart-canvas-wrap">
          <canvas width="960" height="360" aria-label="行情走势图"></canvas>
          <p class="muted chart-empty hidden">暂无走势数据</p>
        </div>
      </div>
      <footer class="chart-card__foot">
        <div class="chart-axis-scroll is-disabled">
          <input class="chart-scroll-bar" type="range" min="0" max="0" value="0" step="1" aria-label="时间轴滑动" disabled />
        </div>
      </footer>
    </article>`;
  }

  function clearKlineMountQueue() {
    state.klineMountQueue.length = 0;
  }

  function pumpKlineMount() {
    while (state.klineMountActive < KLINE_MOUNT_CONCURRENCY && state.klineMountQueue.length) {
      const job = state.klineMountQueue.shift();
      state.klineMountActive += 1;
      Promise.resolve()
        .then(() => job && job())
        .finally(() => {
          state.klineMountActive = Math.max(0, state.klineMountActive - 1);
          pumpKlineMount();
        });
    }
  }

  function enqueueKlineMount(job) {
    state.klineMountQueue.push(job);
    pumpKlineMount();
  }

  function mountCardKline(card) {
    const kline = card.querySelector(".chart-card--kline");
    const code = kline && kline.dataset.klineCode;
    if (!kline || !code || !window.OrbitKline) return;
    enqueueKlineMount(() => {
      if (!card.isConnected || !kline.isConnected) return;
      window.OrbitKline.mount(kline, { code, carousel: true });
    });
  }

  function observeCardKlines() {
    const cards = $("stockCards");
    if (!cards) return;
    if (state.klineObserver) state.klineObserver.disconnect();
    clearKlineMountQueue();
    if (state.view !== "card" || !window.OrbitKline) return;
    const pending = new Set(cards.querySelectorAll(".screen-card[data-kline-new]"));
    if (!pending.size) return;
    state.klineObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const card = entry.target;
          state.klineObserver.unobserve(card);
          card.removeAttribute("data-kline-new");
          mountCardKline(card);
        }
      },
      { root: cards, rootMargin: "120px" }
    );
    pending.forEach((card) => state.klineObserver.observe(card));
  }

  function clearCards() {
    const cards = $("stockCards");
    if (state.klineObserver) {
      state.klineObserver.disconnect();
      state.klineObserver = null;
    }
    clearKlineMountQueue();
    if (cards) cards.innerHTML = "";
  }

  function renderCards(rows) {
    const cards = $("stockCards");
    if (!cards) return;
    if (state.view !== "card") {
      clearCards();
      return;
    }
    cards.innerHTML = rows
      .map((row) => {
        const code = esc(row.code);
        const chgTone = tone(row.change_pct);
        return `<article class="screen-card is-stock" data-code="${code}" data-industry="${esc(row.l3_code || "")}" data-kline-new="1" tabindex="0">
      <a class="screen-card-head" href="${esc(stockHref(row))}" title="打开公司详情">
        <span class="screen-rank">${row.rank || ""}</span>
        <div class="screen-card-name">
          <strong>${esc(row.name || "—")}</strong>
          <span>${code}</span>
          <em>${esc(industryText(row))}</em>
        </div>
        <div class="screen-card-score">
          <b data-tone="${chgTone}">${fmtPct(row.change_pct)}</b>
          <span>${fmtPrice(row.price)}</span>
        </div>
      </a>
      ${klineBlock(row.code || "")}
      <footer class="screen-card-meta">
        <span>PE <b>${fmtRatio(row.pe_ttm)}</b></span>
        <span>PB <b>${fmtRatio(row.pb)}</b></span>
        <span>市值 <b>${fmtCap(row.market_cap)}</b></span>
        <span>今日 <b data-tone="${tone(row.main_net)}">${fmtYi(row.main_net)}</b></span>
        <span>5日 <b data-tone="${tone(row.main_net_5d)}">${fmtYi(row.main_net_5d)}</b></span>
        <span>10日 <b data-tone="${tone(row.main_net_10d)}">${fmtYi(row.main_net_10d)}</b></span>
        <button type="button" class="btn ghost sm mine-danger" data-remove="${code}" title="移出分组">移除</button>
      </footer>
    </article>`;
      })
      .join("");
    observeCardKlines();
  }

  function renderStocks() {
    const body = $("stockBody");
    const empty = $("stockEmpty");
    const title = $("stockTitle");
    const meta = $("stockMeta");
    syncSortButtons();

    if (!state.selectedId || !state.group) {
      title.textContent = "股票";
      meta.textContent = "选择左侧分组";
      body.innerHTML = "";
      clearCards();
      empty.textContent = state.groups.length ? "选择左侧分组查看成分" : "暂无分组，先在左侧新建一个";
      empty.hidden = false;
      setStockPaneEnabled(false);
      renderPager(0);
      applyView();
      return;
    }

    setStockPaneEnabled(true);
    title.textContent = state.group.name || "股票";
    const all = state.group.stocks || [];
    const rows = filteredStocks();
    const pages = totalPages(rows.length);
    clampPage(rows.length);
    const pageRows = pagedStocks(rows);
    const startRank = (state.page - 1) * state.pageSize;
    const loading = Boolean(state.group._loading);
    const sortHint =
      state.sortKey && state.sortKey !== "rank"
        ? ` · ${SORT_LABELS[state.sortKey] || state.sortKey}${state.sortDir === "asc" ? "↑" : "↓"}`
        : "";
    meta.textContent = loading
      ? "加载中…"
      : state.filter.trim()
        ? `显示 ${rows.length} / ${all.length} · 第 ${state.page}/${pages} 页${sortHint}`
        : `${all.length} 只 · 第 ${state.page}/${pages} 页${sortHint}`;

    if (loading) {
      body.innerHTML = "";
      clearCards();
      empty.textContent = "正在加载分组…";
      empty.hidden = false;
      renderPager(0);
      applyView();
      return;
    }

    if (!all.length) {
      body.innerHTML = "";
      clearCards();
      empty.textContent = "分组为空，在上方搜索并添加股票";
      empty.hidden = false;
      renderPager(0);
      applyView();
      return;
    }
    if (!rows.length) {
      body.innerHTML = "";
      clearCards();
      empty.textContent = "没有匹配的股票";
      empty.hidden = false;
      renderPager(0);
      applyView();
      return;
    }

    empty.hidden = true;
    applyView();
    renderPager(rows.length);
    if (state.view === "card") {
      body.innerHTML = "";
      renderCards(pageRows);
      return;
    }
    clearCards();
    body.innerHTML = pageRows
      .map((row, index) => {
        const code = esc(row.code);
        return `<tr class="is-row is-stock" data-code="${code}" data-industry="${esc(row.l3_code || "")}">
          <td class="num shares-rank">${row.rank || startRank + index + 1}</td>
          <td>
            <a class="mine-stock-link" href="${esc(stockHref(row))}" title="打开公司详情">
              <span class="market-stock-name">${esc(row.name || "—")}</span>
              <span class="market-stock-code">${code}</span>
            </a>
          </td>
          <td class="num" data-tone="${tone(row.change_pct)}">${fmtPct(row.change_pct)}</td>
          <td class="num">${fmtPrice(row.price)}</td>
          <td class="shares-industry">${esc(industryText(row))}</td>
          <td class="num">${fmtRatio(row.pe_ttm)}</td>
          <td class="num">${fmtRatio(row.pb)}</td>
          <td class="num market-fund-cell" data-tone="${tone(row.main_net)}">${fmtYi(row.main_net)}</td>
          <td class="num market-fund-cell" data-tone="${tone(row.main_net_5d)}">${fmtYi(row.main_net_5d)}</td>
          <td class="num market-fund-cell" data-tone="${tone(row.main_net_10d)}">${fmtYi(row.main_net_10d)}</td>
          <td class="num">${fmtCap(row.market_cap)}</td>
          <td class="num">
            <button type="button" class="btn ghost mine-row-btn" data-remove="${code}" title="移出分组">移除</button>
          </td>
        </tr>`;
      })
      .join("");
  }

  function renderSuggest() {
    const box = $("suggestBox");
    if (!state.suggestOpen || !state.suggestItems.length) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }
    box.hidden = false;
    box.innerHTML = state.suggestItems
      .map((item) => {
        const code = esc(item.code || "");
        const name = esc(item.name || "");
        const industry = esc(item.l3_name || item.l2_name || "");
        return `<button type="button" class="mine-suggest-item" role="option" data-code="${code}" data-name="${name}">
          <span class="mine-suggest-main"><b>${name || code}</b><span class="mono">${code}</span></span>
          <span class="muted">${industry}</span>
        </button>`;
      })
      .join("");
  }

  function closeSuggest() {
    state.suggestOpen = false;
    state.suggestItems = [];
    renderSuggest();
  }

  function paint() {
    renderGroups();
    renderStocks();
    renderSummary();
  }

  async function loadGroups({ keepSelection = true } = {}) {
    const json = await api("/api/mine/groups", { bypassCache: true });
    state.groups = json.data?.groups || [];
    const prefer = keepSelection ? state.selectedId || readGroupFromUrl() : readGroupFromUrl();
    if (prefer && state.groups.some((g) => g.id === prefer)) {
      state.selectedId = prefer;
    } else if (state.groups.length) {
      state.selectedId = state.groups[0].id;
    } else {
      state.selectedId = "";
      state.group = null;
    }
    writeGroupToUrl(state.selectedId);
  }

  async function loadGroupDetail(groupId, { live = false, force = false, seq = null } = {}) {
    if (!groupId) {
      state.group = null;
      return null;
    }
    const qs = live ? "?live=1" : "";
    const json = await api(`/api/mine/groups/${encodeURIComponent(groupId)}${qs}`, {
      bypassCache: force || live,
    });
    if (seq != null && seq !== state.selectSeq) return null;
    state.group = json.data || null;
    state.selectedId = state.group?.id || "";
    writeGroupToUrl(state.selectedId);
    return state.group;
  }

  async function refreshAll() {
    if (state.fetching) return;
    state.fetching = true;
    const seq = ++state.selectSeq;
    setLoading(true);
    setLive("busy");
    try {
      await loadGroups();
      if (seq !== state.selectSeq) return;
      if (state.selectedId) await loadGroupDetail(state.selectedId, { live: true, force: true, seq });
      if (seq !== state.selectSeq) return;
      paint();
      showError("");
      setLive("live");
      window.OrbitPrefetch?.boot("mine", {
        stocks: (state.group?.stocks || []).slice(0, 8),
        from: "mine",
      });
    } catch (err) {
      if (seq !== state.selectSeq) return;
      showError(err.message || String(err));
      setLive("idle");
      paint();
    } finally {
      // 即使被后续切换抢占，也要放下锁/遮罩，否则刷新会永久无响应
      state.fetching = false;
      setLoading(false);
    }
  }

  async function selectGroup(groupId) {
    if (!groupId) return;
    if (groupId === state.selectedId && state.group && !state.group._loading) {
      paint();
      return;
    }
    rememberPage();
    rememberSort();
    const seq = ++state.selectSeq;
    state.selectedId = groupId;
    restorePage(groupId);
    restoreSort(groupId);
    writeGroupToUrl(groupId);
    const meta = state.groups.find((g) => g.id === groupId);
    state.group = {
      id: groupId,
      name: meta?.name || "",
      count: Number(meta?.count || 0),
      stocks: [],
      _loading: true,
    };
    paint();
    setLive("busy");
    try {
      const detail = await loadGroupDetail(groupId, { seq });
      if (seq !== state.selectSeq) return;
      if (!detail) throw new Error("分组加载失败");
      showError("");
      setLive("live");
      paint();
      window.OrbitPrefetch?.boot("mine", {
        stocks: (state.group?.stocks || []).slice(0, 8),
        from: "mine",
      });
    } catch (err) {
      if (seq !== state.selectSeq) return;
      showError(err.message || String(err));
      setLive("idle");
      if (state.group && state.group.id === groupId) {
        delete state.group._loading;
      }
      paint();
    }
  }

  async function createGroup(name) {
    const json = await api("/api/mine/groups", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    const group = json.data;
    rememberPage();
    rememberSort();
    state.selectedId = group.id;
    state.page = 1;
    state.sortKey = "rank";
    state.sortDir = "asc";
    rememberPage();
    rememberSort();
    state.group = group;
    await loadGroups({ keepSelection: true });
    writeGroupToUrl(state.selectedId);
    paint();
  }

  async function deleteSelectedGroup() {
    if (!state.selectedId || !state.group) return;
    const name = state.group.name || state.selectedId;
    if (!window.confirm(`确定删除分组「${name}」？其中股票也会一并移除。`)) return;
    const removedId = state.selectedId;
    await api(`/api/mine/groups/${encodeURIComponent(state.selectedId)}`, {
      method: "DELETE",
    });
    delete state.pageByGroup[removedId];
    delete state.sortByGroup[removedId];
    state.selectedId = "";
    state.group = null;
    await loadGroups({ keepSelection: false });
    if (state.selectedId) {
      restorePage(state.selectedId);
      restoreSort(state.selectedId);
      await loadGroupDetail(state.selectedId);
    } else {
      state.sortKey = "rank";
      state.sortDir = "asc";
    }
    paint();
  }

  async function addCodes(codes, names) {
    if (!state.selectedId) throw new Error("请先选择分组");
    const payload = { codes };
    if (names && Object.keys(names).length) payload.names = names;
    const json = await api(`/api/mine/groups/${encodeURIComponent(state.selectedId)}/stocks`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.group = json.data?.group || state.group;
    await loadGroups({ keepSelection: true });
    paint();
    return json.data;
  }

  async function removeCode(code) {
    if (!state.selectedId) return;
    const json = await api(`/api/mine/groups/${encodeURIComponent(state.selectedId)}/stocks`, {
      method: "DELETE",
      body: JSON.stringify({ codes: [code] }),
    });
    state.group = json.data?.group || state.group;
    await loadGroups({ keepSelection: true });
    paint();
  }

  async function searchSuggest(q) {
    const text = String(q || "").trim();
    if (!text || parseCodes(text).length > 1) {
      closeSuggest();
      return;
    }
    const params = new URLSearchParams();
    if (/^\d{1,6}$/.test(text) || /^[a-z]{0,2}\d{4,6}$/i.test(text)) {
      params.set("code", text);
    } else {
      params.set("name", text);
    }
    try {
      const json = await api(`/api/stocks/search?${params.toString()}`);
      state.suggestItems = (json.data || []).slice(0, 12);
      state.suggestOpen = state.suggestItems.length > 0;
      renderSuggest();
    } catch {
      closeSuggest();
    }
  }

  function bind() {
    $("refreshBtn").addEventListener("click", () => {
      void refreshAll();
    });

    $("createForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = $("groupNameInput");
      const name = input.value.trim();
      if (!name) return;
      setLive("busy");
      try {
        await createGroup(name);
        input.value = "";
        showError("");
        setLive("live");
      } catch (err) {
        showError(err.message || String(err));
        setLive("idle");
      }
    });

    $("groupList").addEventListener("click", (event) => {
      const syncBtn = event.target.closest("[data-sync]");
      if (syncBtn) {
        event.preventDefault();
        event.stopPropagation();
        void syncGroup(syncBtn.dataset.sync, syncBtn);
        return;
      }
      const sel = event.target.closest("[data-select]");
      const row = sel || event.target.closest("[data-group-id]");
      if (!row) return;
      void selectGroup(sel ? sel.dataset.select : row.dataset.groupId);
    });

    $("syncGroupBtn").addEventListener("click", async (event) => {
      await syncGroup(state.selectedId, event.currentTarget);
    });

    $("syncAllBtn").addEventListener("click", () => {
      void syncAll();
    });

    $("deleteGroupBtn").addEventListener("click", async () => {
      setLive("busy");
      try {
        await deleteSelectedGroup();
        showError("");
        setLive("live");
      } catch (err) {
        showError(err.message || String(err));
        setLive("idle");
      }
    });

    $("filterInput").addEventListener("input", () => {
      state.filter = $("filterInput").value;
      state.page = 1;
      rememberPage();
      renderStocks();
    });

    $("pageSize")?.addEventListener("change", () => {
      const n = Number($("pageSize").value) || 20;
      state.pageSize = PAGE_SIZES.has(n) ? n : 20;
      state.page = 1;
      rememberPage();
      try {
        localStorage.setItem(PAGE_SIZE_KEY, String(state.pageSize));
      } catch {
        /* ignore */
      }
      renderStocks();
    });

    $("prevPage")?.addEventListener("click", () => turnPage(state.page - 1));
    $("nextPage")?.addEventListener("click", () => turnPage(state.page + 1));

    $("viewListBtn").addEventListener("click", () => setView("list"));
    $("viewCardBtn").addEventListener("click", () => setView("card"));

    const onSortClick = (event) => {
      const btn = event.target.closest("[data-mine-sort]");
      if (!btn) return;
      event.preventDefault();
      setSort(btn.getAttribute("data-mine-sort") || "rank");
    };
    $("sortSeg")?.addEventListener("click", onSortClick);
    $("stockHead")?.addEventListener("click", onSortClick);

    $("addInput").addEventListener("input", () => {
      const value = $("addInput").value;
      window.clearTimeout(state.suggestTimer);
      state.suggestTimer = window.setTimeout(() => {
        void searchSuggest(value);
      }, 220);
    });

    $("addInput").addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeSuggest();
    });

    $("addInput").addEventListener("blur", () => {
      window.setTimeout(closeSuggest, 150);
    });

    $("suggestBox").addEventListener("mousedown", (event) => {
      event.preventDefault();
    });

    $("suggestBox").addEventListener("click", async (event) => {
      const item = event.target.closest("[data-code]");
      if (!item) return;
      const code = item.dataset.code;
      const name = item.dataset.name || "";
      closeSuggest();
      $("addInput").value = "";
      setLive("busy");
      try {
        await addCodes([code], name ? { [code]: name } : undefined);
        showError("");
        setLive("live");
      } catch (err) {
        showError(err.message || String(err));
        setLive("idle");
      }
    });

    $("addForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = $("addInput");
      const codes = parseCodes(input.value);
      if (!codes.length) return;
      closeSuggest();
      setLive("busy");
      try {
        await addCodes(codes);
        input.value = "";
        showError("");
        setLive("live");
      } catch (err) {
        showError(err.message || String(err));
        setLive("idle");
      }
    });

    $("stockBody").addEventListener("click", async (event) => {
      const btn = event.target.closest("[data-remove]");
      if (btn) {
        event.preventDefault();
        event.stopPropagation();
        const code = btn.dataset.remove;
        setLive("busy");
        try {
          await removeCode(code);
          showError("");
          setLive("live");
        } catch (err) {
          showError(err.message || String(err));
          setLive("idle");
        }
        return;
      }
      if (event.target.closest("a")) return;
      const row = event.target.closest("tr.is-stock[data-code]");
      if (!row) return;
      const qs = new URLSearchParams({ code: row.dataset.code, from: "mine" });
      if (row.dataset.industry) qs.set("industry", row.dataset.industry);
      window.location.href = `/company.html?${qs}`;
    });

    $("stockCards").addEventListener("click", async (event) => {
      const btn = event.target.closest("[data-remove]");
      if (btn) {
        event.preventDefault();
        event.stopPropagation();
        const code = btn.dataset.remove;
        setLive("busy");
        try {
          await removeCode(code);
          showError("");
          setLive("live");
        } catch (err) {
          showError(err.message || String(err));
          setLive("idle");
        }
        return;
      }
      if (event.target.closest("a,button,select,input")) return;
      if (event.target.closest(".chart-card")) return;
      const card = event.target.closest(".screen-card[data-code]");
      if (!card) return;
      const qs = new URLSearchParams({ code: card.dataset.code, from: "mine" });
      if (card.dataset.industry) qs.set("industry", card.dataset.industry);
      window.location.href = `/company.html?${qs}`;
    });

    $("stockCards").addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const card = event.target.closest(".screen-card[data-code]");
      if (!card || event.target.closest("a,button")) return;
      event.preventDefault();
      const qs = new URLSearchParams({ code: card.dataset.code, from: "mine" });
      if (card.dataset.industry) qs.set("industry", card.dataset.industry);
      window.location.href = `/company.html?${qs}`;
    });

    window.OrbitPrefetch?.bindHover($("stockBody"), "tr.is-stock[data-code]");
  }

  bind();
  applyView();
  const sizeSel = $("pageSize");
  if (sizeSel) sizeSel.value = String(state.pageSize);
  state.selectedId = readGroupFromUrl();
  if (state.selectedId) {
    restorePage(state.selectedId);
    restoreSort(state.selectedId);
  }
  void refreshAll();
})();
