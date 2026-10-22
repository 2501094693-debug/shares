(() => {
  const PAGE_DAYS = 15;
  const STEP_DAYS = 15;
  // 东财涨停/跌停池大约只保留近 30 个交易日
  const MAX_DAYS = 30;
  const POLL_MS = 30000;
  const LIVE_POLL_MS = 15000;
  const WEEK = "日一二三四五六";
  const VIEW_KEY = "steep-view";
  const FOLD_KEY = "steep-row-fold";
  const DATE_KEY = "steep-selected-date";

  const state = {
    items: [],
    itemsSig: "",
    updatedAt: "",
    days: PAGE_DAYS,
    hasMore: true,
    sortKey: "board",
    sortDir: "desc",
    view: "list",
    selectedDate: "",
    collapsed: { up: false, down: false },
    fetching: false,
    loadingMore: false,
    pendingLoad: null,
    pollTimer: 0,
    liveQuoteTimer: 0,
    liveQuoteStarted: false,
    liveQuotes: {},
    pinDateScroll: false,
    dayFetching: "",
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
    const sign = n < 0 ? "-" : "";
    if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
    if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(1)}万`;
    return `${sign}${abs.toFixed(0)}`;
  }

  function fmtPrice(value) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(2);
  }

  function stockHref(row) {
    const qs = new URLSearchParams({ code: row.code || "", from: "steep" });
    if (row.l3_code) qs.set("industry", row.l3_code);
    return `/company.html?${qs}`;
  }

  function fmtMd(date) {
    return String(date || "").slice(5) || "—";
  }

  function tone(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n === 0) return "flat";
    return n > 0 ? "up" : "down";
  }

  function weekday(date) {
    const d = new Date(`${date}T00:00:00`);
    if (Number.isNaN(d.getTime())) return "";
    return `周${WEEK[d.getDay()]}`;
  }

  function cmpText(a, b) {
    const sa = String(a || "").trim();
    const sb = String(b || "").trim();
    if (!sa && !sb) return 0;
    if (!sa) return 1;
    if (!sb) return -1;
    return sa.localeCompare(sb, "zh-CN");
  }

  function boardValue(row, kind) {
    const n = Number(kind === "up" ? row.board_count : row.down_days);
    return Number.isFinite(n) ? n : 0;
  }

  function sortRows(rows, kind) {
    const dir = state.sortDir === "desc" ? -1 : 1;
    return (rows || []).slice().sort((a, b) => {
      let n = 0;
      if (state.sortKey === "l1") {
        n = cmpText(a.l1_name, b.l1_name);
        if (n) return n * dir;
        n = boardValue(b, kind) - boardValue(a, kind);
        return n || cmpText(a.code, b.code);
      }
      n = boardValue(b, kind) - boardValue(a, kind);
      if (state.sortDir === "asc") n = -n;
      return n || cmpText(a.code, b.code);
    });
  }

  function emptyRow(text) {
    return `<tr class="is-empty"><td colspan="8">${text}</td></tr>`;
  }

  function fmtTime(value) {
    const text = String(value || "").trim();
    return text || "—";
  }

  function extraCells(row, kind) {
    if (kind === "down") {
      const opens = Number(row.open_count);
      return `
      <td class="num steep-time">${fmtTime(row.last_seal)}</td>
      <td class="num steep-money">${fmtYi(row.seal_fund)}</td>
      <td class="num">${Number.isFinite(opens) ? opens : "—"}</td>
      <td class="num steep-money">${fmtYi(row.board_amount)}</td>`;
    }
    const breaks = Number(row.break_count);
    return `
      <td class="num steep-time">${fmtTime(row.first_seal)}</td>
      <td class="num steep-time">${fmtTime(row.last_seal)}</td>
      <td class="num steep-money">${fmtYi(row.seal_fund)}</td>
      <td class="num">${Number.isFinite(breaks) ? breaks : "—"}</td>`;
  }

  function extraHeads(kind) {
    if (kind === "down") {
      return `
          <th class="num steep-time">最后</th>
          <th class="num steep-money">封单</th>
          <th class="num">开板</th>
          <th class="num steep-money">板上</th>`;
    }
    return `
          <th class="num steep-time">首次</th>
          <th class="num steep-time">最后</th>
          <th class="num steep-money">封单</th>
          <th class="num">炸板</th>`;
  }

  function boardText(row, kind) {
    const board = kind === "up" ? row.board_count : row.down_days;
    if (!board) return "—";
    return kind === "up" ? `${board}板` : `${board}天`;
  }

  function industryText(row) {
    return [row.l1_name, row.l2_name, row.l3_name].filter(Boolean).join(" / ") || "—";
  }

  function stockRow(row, kind) {
    return `<tr class="is-row is-stock" data-code="${row.code || ""}" data-industry="${row.l3_code || ""}">
      <td>
        <span class="market-stock-name">${row.name || ""}</span>
        <span class="market-stock-code">${row.code || ""}</span>
        <span class="steep-sw-line">${industryText(row)}</span>
      </td>
      ${extraCells(row, kind)}
      <td class="num steep-board-n" data-tone="${tone(row.change_pct)}">${boardText(row, kind)}</td>
      <td class="num steep-money">${fmtYi(row.amount)}</td>
      <td class="num steep-money">${fmtYi(row.float_mv)}</td>
    </tr>`;
  }

  function klineBlock(code) {
    return `<article class="chart-card chart-card--kline" data-kline-code="${code || ""}">
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

  function stockMeta(row, kind) {
    if (kind === "down") {
      const opens = Number(row.open_count);
      return `
        <span>连跌 <b>${boardText(row, kind)}</b></span>
        <span>最后 <b>${fmtTime(row.last_seal)}</b></span>
        <span>封单 <b>${fmtYi(row.seal_fund)}</b></span>
        <span>开板 <b>${Number.isFinite(opens) ? opens : "—"}</b></span>
        <span>板上 <b>${fmtYi(row.board_amount)}</b></span>
        <span>成交 <b>${fmtYi(row.amount)}</b></span>
        <span>流通 <b>${fmtYi(row.float_mv)}</b></span>`;
    }
    const breaks = Number(row.break_count);
    return `
      <span>连板 <b>${boardText(row, kind)}</b></span>
      <span>首次 <b>${fmtTime(row.first_seal)}</b></span>
      <span>最后 <b>${fmtTime(row.last_seal)}</b></span>
      <span>封单 <b>${fmtYi(row.seal_fund)}</b></span>
      <span>炸板 <b>${Number.isFinite(breaks) ? breaks : "—"}</b></span>
      <span>成交 <b>${fmtYi(row.amount)}</b></span>
      <span>流通 <b>${fmtYi(row.float_mv)}</b></span>`;
  }

  function stockCard(row, kind) {
    const code = row.code || "";
    const chgTone = tone(row.change_pct);
    const addBtn = window.OrbitMineAdd?.buttonHtml({ code, name: row.name || "" }) || "";
    return `<article class="screen-card is-stock" data-code="${code}" data-industry="${row.l3_code || ""}" tabindex="0">
      <a class="screen-card-head" href="${stockHref(row)}" title="打开公司详情">
        <div class="screen-card-name">
          <strong>${row.name || "—"}</strong>
          <span>${code}</span>
          <em>${industryText(row)}</em>
        </div>
        <div class="screen-card-score">
          <b data-tone="${chgTone}">${fmtPct(row.change_pct)}</b>
          <span>${fmtPrice(row.price)}</span>
        </div>
      </a>
      ${klineBlock(code)}
      <footer class="screen-card-meta">${stockMeta(row, kind)}${addBtn}</footer>
    </article>`;
  }

  function mountCardKline(card) {
    const kline = card.querySelector(".chart-card--kline");
    const code = kline && kline.dataset.klineCode;
    if (kline && code && window.OrbitKline) window.OrbitKline.mount(kline, { code, carousel: true });
  }

  function mountOpenKlines() {
    if (state.view !== "cards" || !window.OrbitKline) return;
    document.querySelectorAll(".steep-pane-scroll .screen-card.is-stock").forEach(mountCardKline);
  }

  function dayTable(day, kind) {
    const rows = sortRows(kind === "up" ? day.limit_up || [] : day.limit_down || [], kind);
    const empty = kind === "up" ? "当日无涨停" : "当日无跌停";
    const body = rows.length ? rows.map((row) => stockRow(row, kind)).join("") : emptyRow(empty);
    const boardTitle = kind === "up" ? "连板" : "连跌";
    return `<table class="market-table steep-table steep-mini">
      <thead>
        <tr>
          <th>名称</th>
          ${extraHeads(kind)}
          <th class="num">${boardTitle}</th>
          <th class="num steep-money">成交额</th>
          <th class="num steep-money">流通</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>`;
  }

  function dayCards(day, kind) {
    const rows = sortRows(kind === "up" ? day.limit_up || [] : day.limit_down || [], kind);
    const empty = kind === "up" ? "当日无涨停" : "当日无跌停";
    if (!rows.length) return `<p class="screen-empty muted">${empty}</p>`;
    return `<div class="steep-stock-cards screen-result-list" aria-label="${kind === "up" ? "涨停" : "跌停"}卡片">${rows.map((row) => stockCard(row, kind)).join("")}</div>`;
  }

  function dayBody(day, kind) {
    if (!day) return `<p class="screen-empty muted">请选择交易日</p>`;
    return state.view === "cards" ? dayCards(day, kind) : dayTable(day, kind);
  }

  function selectedDay() {
    return state.items.find((day) => day.date_raw === state.selectedDate) || null;
  }

  function readView() {
    try {
      return localStorage.getItem(VIEW_KEY) === "cards" ? "cards" : "list";
    } catch {
      return "list";
    }
  }

  function persistView() {
    try {
      localStorage.setItem(VIEW_KEY, state.view);
    } catch {
      /* ignore */
    }
  }

  function readSavedDate() {
    try {
      return localStorage.getItem(DATE_KEY) || "";
    } catch {
      return "";
    }
  }

  function persistDate() {
    try {
      if (state.selectedDate) localStorage.setItem(DATE_KEY, state.selectedDate);
    } catch {
      /* ignore */
    }
  }

  function ensureSelectedDate() {
    if (!state.items.length) {
      state.selectedDate = "";
      return;
    }
    if (state.selectedDate && state.items.some((day) => day.date_raw === state.selectedDate)) return;
    const saved = readSavedDate();
    if (saved && state.items.some((day) => day.date_raw === saved)) {
      state.selectedDate = saved;
      return;
    }
    state.selectedDate = state.items[0].date_raw;
    persistDate();
  }

  function setSelectedDate(dateRaw) {
    if (!dateRaw || dateRaw === state.selectedDate) return;
    if (!state.items.some((day) => day.date_raw === dateRaw)) return;
    state.selectedDate = dateRaw;
    state.pinDateScroll = true;
    persistDate();
    render();
    void ensureDayDetail(dateRaw);
  }

  function renderViewSeg() {
    $("viewSeg")?.querySelectorAll("button[data-view]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.view === state.view);
    });
    $("dayPanel")?.setAttribute("data-view", state.view);
  }

  function setView(next) {
    const view = next === "cards" ? "cards" : "list";
    if (view === state.view) return;
    state.view = view;
    persistView();
    if (view === "cards") syncCardGeometry();
    render();
  }

  function measureSharesLikeCardSize() {
    const probe = document.createElement("div");
    probe.style.cssText =
      "position:absolute;left:0;top:0;visibility:hidden;pointer-events:none;width:var(--company-kline-w);height:0";
    document.body.appendChild(probe);
    const width = probe.getBoundingClientRect().width || 480;
    probe.remove();
    const toolbar = document.querySelector(".steep-page .market-toolbar");
    const top = toolbar ? toolbar.getBoundingClientRect().bottom : 120;
    const height = Math.max(180, (window.innerHeight - top - 12 - 20) / (state.collapsed.up || state.collapsed.down ? 1 : 2));
    return { width, height };
  }

  function syncCardGeometry() {
    const { width, height } = measureSharesLikeCardSize();
    if (!(width > 0) || !(height > 0)) return;
    const root = document.body;
    root.style.setProperty("--steep-card-w", `${Math.round(width)}px`);
    root.style.setProperty("--steep-card-h", `${Math.round(height)}px`);
    root.style.setProperty("--steep-card-ar", (width / height).toFixed(6));
  }

  function setLive(kind) {
    const el = $("liveDot");
    el.dataset.state = kind;
    el.textContent = kind === "live" ? "LIVE" : kind === "busy" ? "SYNC" : "IDLE";
  }

  function renderSort() {
    $("sortSeg").querySelectorAll("button[data-sort]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.sort === state.sortKey);
    });
  }

  function renderSummary() {
    const day = selectedDay();
    const upAll = state.items.reduce((n, d) => n + (d.limit_up_count || 0), 0);
    const downAll = state.items.reduce((n, d) => n + (d.limit_down_count || 0), 0);
    const dayLabel = day ? `${fmtMd(day.date)} ${weekday(day.date)}` : "—";
    const up = day ? day.limit_up_count || 0 : 0;
    const down = day ? day.limit_down_count || 0 : 0;
    $("summaryBar").innerHTML = `
      <span>${state.items.length} 个交易日</span>
      <span>当日 <b>${dayLabel}</b></span>
      <span>涨停 <b class="is-up">${up}</b></span>
      <span>跌停 <b class="is-down">${down}</b></span>
      <span class="muted">区间合计 ↑${upAll} ↓${downAll}</span>
    `;
    $("marketMeta").textContent = state.updatedAt || "";
  }

  function loadFold() {
    try {
      const data = JSON.parse(sessionStorage.getItem(FOLD_KEY) || "null");
      if (!data || typeof data !== "object") return;
      state.collapsed.up = !!data.up;
      state.collapsed.down = !!data.down;
    } catch {
      /* ignore */
    }
  }

  function saveFold() {
    try {
      sessionStorage.setItem(FOLD_KEY, JSON.stringify(state.collapsed));
    } catch {
      /* ignore */
    }
  }

  function applyRowFold() {
    for (const kind of ["up", "down"]) {
      const row = $(`${kind}Row`);
      const collapsed = !!state.collapsed[kind];
      row.classList.toggle("is-collapsed", collapsed);
      const label = row.querySelector(".steep-matrix-label");
      if (!label) continue;
      label.setAttribute("aria-expanded", collapsed ? "false" : "true");
      label.title = collapsed
        ? kind === "up"
          ? "展开涨停"
          : "展开跌停"
        : kind === "up"
          ? "折叠涨停"
          : "折叠跌停";
      const caret = label.querySelector(".steep-row-caret");
      if (caret) caret.textContent = collapsed ? "▸" : "▾";
    }
  }

  function toggleRow(kind) {
    if (kind !== "up" && kind !== "down") return;
    state.collapsed[kind] = !state.collapsed[kind];
    applyRowFold();
    saveFold();
    if (state.view === "cards") {
      syncCardGeometry();
      requestAnimationFrame(mountOpenKlines);
    }
  }

  function dateListFooter() {
    if (state.loadingMore) {
      return `<p class="steep-dates-foot muted" aria-live="polite">加载更早交易日…</p>`;
    }
    if (!state.hasMore && state.items.length) {
      return `<p class="steep-dates-foot muted">东财约保留近 ${MAX_DAYS} 个交易日</p>`;
    }
    if (state.hasMore && state.items.length) {
      return `<p class="steep-dates-foot muted">下滑加载更早</p>`;
    }
    return "";
  }

  function renderDateList() {
    const list = $("dateList");
    if (!list) return;
    const keepTop = list.scrollTop;
    if (!state.items.length) {
      list.innerHTML = `<p class="steep-dates-empty muted">暂无交易日</p>`;
      return;
    }
    list.innerHTML =
      state.items
        .map((day) => {
          const active = day.date_raw === state.selectedDate;
          return `<button type="button" class="steep-date-item${active ? " is-active" : ""}" role="option" aria-selected="${active ? "true" : "false"}" data-date="${day.date_raw}">
          <span class="steep-date-when">
            <b>${fmtMd(day.date)}</b>
            <em>${weekday(day.date)}</em>
          </span>
          <span class="steep-date-counts">
            <span data-tone="up">${day.limit_up_count || 0}</span>
            <span data-tone="down">${day.limit_down_count || 0}</span>
          </span>
        </button>`;
        })
        .join("") + dateListFooter();
    list.scrollTop = keepTop;
    if (state.pinDateScroll) {
      state.pinDateScroll = false;
      const activeBtn = list.querySelector(".steep-date-item.is-active");
      if (activeBtn) {
        const box = list.getBoundingClientRect();
        const btn = activeBtn.getBoundingClientRect();
        if (btn.top < box.top || btn.bottom > box.bottom) {
          activeBtn.scrollIntoView({ block: "nearest" });
        }
      }
    }
    requestAnimationFrame(maybeFillDates);
  }

  function captureCardScrolls() {
    const map = new Map();
    for (const kind of ["up", "down"]) {
      const el = $(`${kind}Body`)?.querySelector(".steep-stock-cards");
      if (el) map.set(kind, el.scrollLeft);
    }
    return map;
  }

  function restoreCardScrolls(map) {
    if (!map?.size) return;
    for (const [kind, left] of map) {
      const el = $(`${kind}Body`)?.querySelector(".steep-stock-cards");
      if (el) el.scrollLeft = left;
    }
  }

  function renderDayPanel() {
    const day = selectedDay();
    const cardScrolls = captureCardScrolls();
    $("upBody").innerHTML = dayBody(day, "up");
    $("downBody").innerHTML = dayBody(day, "down");
    restoreCardScrolls(cardScrolls);
    requestAnimationFrame(() => {
      restoreCardScrolls(cardScrolls);
      mountOpenKlines();
    });
  }

  function render() {
    ensureSelectedDate();
    renderSort();
    renderViewSeg();
    renderSummary();
    renderDateList();
    renderDayPanel();
    applyRowFold();
    startLiveQuotesPoll();
    if (Object.keys(state.liveQuotes || {}).length > 0) {
      requestAnimationFrame(() => patchLiveQuotes());
    }
  }

  function setSort(key) {
    if (!key) return;
    if (state.sortKey === key) {
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortKey = key;
      state.sortDir = key === "board" ? "desc" : "asc";
    }
    render();
  }

  function updateHasMore(prevCount, items) {
    const nextCount = (items || []).length;
    if (state.days >= MAX_DAYS || nextCount <= prevCount) {
      state.hasMore = false;
      return;
    }
    // 新拉到的更早交易日若涨跌停都是 0，多半已超出东财历史窗口
    const newer = (items || []).slice(prevCount);
    if (newer.length && newer.every((day) => !(day.limit_up_count || 0) && !(day.limit_down_count || 0))) {
      state.hasMore = false;
      return;
    }
    state.hasMore = true;
  }

  function dayNeedsDetail(day) {
    if (!day) return false;
    const upN = day.limit_up_count || 0;
    const downN = day.limit_down_count || 0;
    const upLen = (day.limit_up || []).length;
    const downLen = (day.limit_down || []).length;
    return (upN > 0 && upLen === 0) || (downN > 0 && downLen === 0);
  }

  async function ensureDayDetail(dateRaw) {
    const raw = String(dateRaw || "").replace(/-/g, "").slice(0, 8);
    if (!raw || state.dayFetching === raw) return;
    const day = state.items.find((item) => item.date_raw === raw);
    if (!dayNeedsDetail(day)) return;
    state.dayFetching = raw;
    try {
      const path = `/api/market/steep/day?date=${encodeURIComponent(raw)}`;
      const json = window.OrbitHttp
        ? await OrbitHttp.get(path, { bypassCache: true, writeCache: true })
        : await fetch(path, { cache: "no-store" }).then((r) => r.json());
      if (!json?.ok || !json.data) return;
      const detail = json.data;
      const idx = state.items.findIndex((item) => item.date_raw === raw);
      if (idx < 0) return;
      state.items[idx] = {
        ...state.items[idx],
        ...detail,
        limit_up: detail.limit_up || [],
        limit_down: detail.limit_down || [],
        limit_up_count: detail.limit_up_count ?? (detail.limit_up || []).length,
        limit_down_count: detail.limit_down_count ?? (detail.limit_down || []).length,
      };
      state.itemsSig = steepItemsSig(state.items);
      if (state.selectedDate === raw) {
        renderSummary();
        renderDayPanel();
        renderDateList();
        if (Object.keys(state.liveQuotes || {}).length > 0) {
          requestAnimationFrame(() => patchLiveQuotes());
        }
      }
    } catch (err) {
      console.warn("[steep] 补拉单日名单失败", err);
    } finally {
      if (state.dayFetching === raw) state.dayFetching = "";
    }
  }

  async function loadMore() {
    if (state.loadingMore || state.fetching || !state.hasMore) return;
    if (state.days >= MAX_DAYS) {
      state.hasMore = false;
      renderDateList();
      return;
    }
    const nextDays = Math.min(MAX_DAYS, state.days + STEP_DAYS);
    if (nextDays <= state.days) {
      state.hasMore = false;
      renderDateList();
      return;
    }
    const prevDays = state.days;
    const prevCount = state.items.length;
    state.loadingMore = true;
    state.days = nextDays;
    renderDateList();
    try {
      const json = await fetchSteep({ bypassCache: true });
      const items = json?.data?.items || [];
      const newer = items.slice(prevCount);
      const newerAllEmpty =
        newer.length > 0 &&
        newer.every((day) => !(day.limit_up_count || 0) && !(day.limit_down_count || 0));
      if (newerAllEmpty) {
        // 超出东财历史窗口：不追加空日期
        state.days = prevDays;
        state.hasMore = false;
      } else {
        updateHasMore(prevCount, items);
        applyPayload(json.data || {});
      }
    } catch (err) {
      console.warn("[steep] 加载更早交易日失败", err);
      state.days = prevDays;
    } finally {
      state.loadingMore = false;
      renderDateList();
      if (state.pendingLoad) {
        const next = state.pendingLoad;
        state.pendingLoad = null;
        void load(next);
      }
    }
  }

  function onDateListScroll() {
    const list = $("dateList");
    if (!list || state.loadingMore || !state.hasMore) return;
    const remain = list.scrollHeight - list.scrollTop - list.clientHeight;
    if (remain <= 48) void loadMore();
  }

  function maybeFillDates() {
    const list = $("dateList");
    if (!list || state.loadingMore || state.fetching || !state.hasMore) return;
    if (list.scrollHeight <= list.clientHeight + 8) void loadMore();
  }

  function steepPath({ refresh = false, lite = false } = {}) {
    const q = new URLSearchParams({ days: String(state.days) });
    if (refresh) q.set("refresh", "1");
    if (lite) q.set("lite", "1");
    return `/api/market/steep?${q}`;
  }

  async function fetchSteep({ refresh = false, lite = false, bypassCache = false } = {}) {
    const path = steepPath({ refresh, lite });
    if (window.OrbitHttp) {
      return OrbitHttp.get(path, bypassCache ? { bypassCache: true, writeCache: true } : {});
    }
    const resp = await fetch(path, { cache: "no-store" });
    const body = await resp.json();
    if (!body.ok) throw new Error(body.error || "加载失败");
    return body;
  }

  function steepItemsSig(items) {
    return (items || [])
      .map((day) => {
        const up = (day.limit_up || [])
          .map((r) => [r.code, r.board_count, r.seal_fund, r.amount, r.break_count, r.first_seal, r.last_seal, r.float_mv].join(":"))
          .join(",");
        const down = (day.limit_down || [])
          .map((r) => [r.code, r.down_days, r.seal_fund, r.amount, r.open_count, r.last_seal, r.board_amount, r.float_mv].join(":"))
          .join(",");
        return [day.date_raw, day.limit_up_count, day.limit_down_count, up, down].join("|");
      })
      .join(";");
  }

  function applyPayload(data, { lite = false } = {}) {
    const items = data.items || [];
    if ((lite || data.lite) && state.items.some((day) => (day.limit_up || []).length || (day.limit_down || []).length) && items.length <= state.items.length) {
      const currentFull = state.items.reduce((n, day) => n + (day.limit_up || []).length + (day.limit_down || []).length, 0);
      const nextFull = items.reduce((n, day) => n + (day.limit_up || []).length + (day.limit_down || []).length, 0);
      if (nextFull < currentFull) return;
    }
    const prevCount = state.items.length;
    const nextSig = steepItemsSig(items);
    const sameList = nextSig === state.itemsSig && state.items.length > 0;
    state.items = items;
    state.itemsSig = nextSig;
    state.updatedAt = data.updated_at || "";
    if (typeof data.days === "number" && data.days > state.days) {
      state.days = data.days;
    }
    // hasMore：首屏开启；触底加载由 loadMore 判定；静默刷新不改
    if (state.days >= MAX_DAYS) {
      state.hasMore = false;
    } else if (!state.loadingMore && prevCount === 0) {
      state.hasMore = items.length > 0;
    }
    ensureSelectedDate();
    if (sameList) {
      renderSummary();
      renderDateList();
    } else {
      render();
    }
    void ensureDayDetail(state.selectedDate);
    window.OrbitPrefetch?.intent({ stocks: visibleSteepStocks() });
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
    const full = await OrbitHttp.peek(steepPath(), { allowStale: true });
    if (full?.data?.items?.length) {
      applyPayload(full.data);
      return true;
    }
    const lite = await OrbitHttp.peek(steepPath({ lite: true }), { allowStale: true });
    if (lite?.data?.items?.length) {
      applyPayload(lite.data, { lite: true });
      return true;
    }
    return false;
  }

  async function load({ silent = false, refresh = false } = {}) {
    if (state.loadingMore) {
      state.pendingLoad = { silent, refresh };
      return;
    }
    if (state.fetching) {
      state.pendingLoad = { silent, refresh };
      return;
    }
    if (!silent && !refresh && !state.items.length) {
      const hit = await paintFromCache();
      if (!hit) {
        void fetchSteep({ lite: true })
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
      const json = await fetchSteep({ refresh, bypassCache: silent });
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
      void load({ silent: true });
    }, POLL_MS);
  }

  function onPaneClick(ev) {
    if (ev.target.closest(".screen-card-head")) return;
    if (ev.target.closest(".chart-card")) return;
    if (ev.target.closest("[data-add-group]")) return;
    const stock = ev.target.closest(".is-stock[data-code]");
    if (stock) {
      window.location.href = stockHref({
        code: stock.dataset.code,
        l3_code: stock.dataset.industry,
      });
    }
  }

  function bind() {
    $("dateList").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-date]");
      if (btn) setSelectedDate(btn.dataset.date);
    });
    $("dateList").addEventListener("scroll", onDateListScroll, { passive: true });
    $("upBody").addEventListener("click", onPaneClick);
    $("downBody").addEventListener("click", onPaneClick);
    window.OrbitMineAdd?.bindRoot($("upBody"));
    window.OrbitMineAdd?.bindRoot($("downBody"));
    $("viewSeg")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-view]");
      if (btn) setView(btn.dataset.view);
    });
    $("sortSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-sort]");
      if (btn) setSort(btn.dataset.sort);
    });
    $("upRow").querySelector(".steep-matrix-label")?.addEventListener("click", () => toggleRow("up"));
    $("downRow").querySelector(".steep-matrix-label")?.addEventListener("click", () => toggleRow("down"));
    $("refreshBtn").addEventListener("click", () => void load({ silent: true, refresh: true }));
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) void load({ silent: true });
    });
    window.addEventListener("resize", () => {
      syncCardGeometry();
      if (state.view === "cards") requestAnimationFrame(mountOpenKlines);
    });
  }

  function visibleSteepStocks() {
    const day = selectedDay() || state.items[0] || {};
    return [...(day.limit_up || []), ...(day.limit_down || [])].slice(0, 6);
  }

  function getSelectedCodes() {
    const day = selectedDay();
    if (!day) return [];
    const codes = new Set();
    for (const row of day.limit_up || []) {
      if (row.code) codes.add(row.code);
    }
    for (const row of day.limit_down || []) {
      if (row.code) codes.add(row.code);
    }
    return [...codes];
  }

  async function fetchLiveQuotes() {
    const codes = getSelectedCodes();
    if (!codes.length) {
      state.liveQuoteTimer = setTimeout(fetchLiveQuotes, LIVE_POLL_MS);
      return;
    }
    try {
      const res = await fetch(`/api/stocks/quotes?codes=${codes.join(",")}`);
      const json = await res.json();
      if (json.ok && json.data) {
        state.liveQuotes = json.data;
        patchLiveQuotes();
      }
    } catch (err) {
      console.warn("[steep] 实时行情获取失败", err);
    }
    state.liveQuoteTimer = setTimeout(fetchLiveQuotes, LIVE_POLL_MS);
  }

  function patchLiveQuotes() {
    for (const bodyId of ["upBody", "downBody"]) {
      const track = $(bodyId);
      if (!track) continue;
      track.querySelectorAll("article.is-stock[data-code]").forEach((card) => {
        const code = card.dataset.code;
        const quote = state.liveQuotes[code];
        if (!quote) return;
        const scoreDiv = card.querySelector(".screen-card-score");
        if (!scoreDiv) return;
        const priceEl = scoreDiv.querySelector("span:last-child");
        if (priceEl && quote.price) {
          priceEl.textContent = quote.price;
        }
        const chgEl = scoreDiv.querySelector("b[data-tone]");
        if (chgEl && quote.change_pct) {
          const n = parseFloat(quote.change_pct);
          chgEl.textContent = quote.change_pct;
          chgEl.dataset.tone = !Number.isFinite(n) || n === 0 ? "flat" : n > 0 ? "up" : "down";
        }
      });
    }
  }

  function startLiveQuotesPoll() {
    if (state.liveQuoteStarted) return;
    state.liveQuoteStarted = true;
    state.liveQuoteTimer = setTimeout(fetchLiveQuotes, 2000);
  }

  state.view = readView();
  loadFold();
  applyRowFold();
  syncCardGeometry();
  renderViewSeg();
  bind();
  window.OrbitPrefetch?.bindHover($("upBody"), ".is-stock[data-code]");
  window.OrbitPrefetch?.bindHover($("downBody"), ".is-stock[data-code]");
  window.OrbitPrefetch?.boot("steep");
  void load().then(() => {
    startPoll();
    window.OrbitPrefetch?.intent({ stocks: visibleSteepStocks() });
  });
})();
