(() => {
  const DAY_OPTIONS = [15, 30];
  const POLL_MS = 30000;
  const WEEK = "日一二三四五六";

  const state = {
    items: [],
    updatedAt: "",
    days: 15,
    sortKey: "board",
    sortDir: "desc",
    open: new Set(),
    fetching: false,
    pendingLoad: null,
    pollTimer: 0,
    syncing: false,
  };

  const $ = (id) => document.getElementById(id);

  function paneKey(dateRaw, kind) {
    return `${dateRaw}:${kind}`;
  }

  function fmtPct(value) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
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
    return `<tr class="is-empty"><td colspan="3">${text}</td></tr>`;
  }

  function stockRow(row, kind) {
    const board = kind === "up" ? row.board_count : row.down_days;
    const boardText = board ? (kind === "up" ? `${board}板` : `${board}天`) : "—";
    const industry = [row.l1_name, row.l2_name, row.l3_name].filter(Boolean).join(" / ") || "—";
    return `<tr class="is-row is-stock" data-code="${row.code || ""}" data-industry="${row.l3_code || ""}">
      <td>
        <span class="market-stock-name">${row.name || ""}</span>
        <span class="market-stock-code">${row.code || ""}</span>
        <span class="steep-sw-line">${industry}</span>
      </td>
      <td class="num" data-tone="${tone(row.change_pct)}">${fmtPct(row.change_pct)}</td>
      <td class="num steep-board-n" data-tone="${tone(row.change_pct)}">${boardText}</td>
    </tr>`;
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
          <th class="num">涨跌</th>
          <th class="num">${boardTitle}</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>`;
  }

  function dayCard(day, kind) {
    const key = paneKey(day.date_raw, kind);
    const open = state.open.has(key);
    const count = kind === "up" ? day.limit_up_count || 0 : day.limit_down_count || 0;
    return `<article class="steep-day${open ? " is-open" : ""}" data-date="${day.date_raw}" data-kind="${kind}">
      <button type="button" class="steep-day-head" data-date="${day.date_raw}" data-kind="${kind}" aria-expanded="${open ? "true" : "false"}">
        <span class="steep-day-when">
          <b>${fmtMd(day.date)}</b>
          <em>${weekday(day.date)}</em>
        </span>
        <span class="steep-day-count" data-tone="${kind}">${count}</span>
        <span class="steep-day-caret" aria-hidden="true">${open ? "◂" : "▸"}</span>
      </button>
      <div class="steep-day-body"${open ? "" : " hidden"}>${open ? dayTable(day, kind) : ""}</div>
    </article>`;
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

  function renderRange() {
    $("rangeSeg").querySelectorAll("button[data-days]").forEach((btn) => {
      btn.classList.toggle("is-active", Number(btn.dataset.days) === state.days);
    });
  }

  function renderSummary() {
    const up = state.items.reduce((n, day) => n + (day.limit_up_count || 0), 0);
    const down = state.items.reduce((n, day) => n + (day.limit_down_count || 0), 0);
    $("summaryBar").innerHTML = `
      <span>${state.items.length} 个交易日</span>
      <span>涨停 <b class="is-up">${up}</b></span>
      <span>跌停 <b class="is-down">${down}</b></span>
    `;
    $("marketMeta").textContent = state.updatedAt || "";
  }

  function markRowOpen() {
    $("upRow").classList.toggle(
      "is-open",
      state.items.some((day) => state.open.has(paneKey(day.date_raw, "up")))
    );
    $("downRow").classList.toggle(
      "is-open",
      state.items.some((day) => state.open.has(paneKey(day.date_raw, "down")))
    );
  }

  function renderTracks() {
    const left = $("upScroll").scrollLeft || $("downScroll").scrollLeft || 0;
    $("upTrack").innerHTML = state.items.map((day) => dayCard(day, "up")).join("");
    $("downTrack").innerHTML = state.items.map((day) => dayCard(day, "down")).join("");
    $("upScroll").scrollLeft = left;
    $("downScroll").scrollLeft = left;
    markRowOpen();
  }

  function render() {
    renderRange();
    renderSort();
    renderSummary();
    renderTracks();
  }

  function togglePane(dateRaw, kind) {
    const key = paneKey(dateRaw, kind);
    if (state.open.has(key)) state.open.delete(key);
    else state.open.add(key);
    render();
    if (state.open.has(key)) {
      const card = document.querySelector(`.steep-day[data-date="${dateRaw}"][data-kind="${kind}"]`);
      card?.scrollIntoView({ inline: "nearest", block: "nearest" });
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

  function setDays(days) {
    const value = Number(days);
    if (!DAY_OPTIONS.includes(value) || value === state.days) return;
    state.days = value;
    state.open = new Set();
    renderRange();
    void load();
  }

  function pruneOpen() {
    const valid = new Set();
    for (const day of state.items) {
      valid.add(paneKey(day.date_raw, "up"));
      valid.add(paneKey(day.date_raw, "down"));
    }
    state.open = new Set([...state.open].filter((key) => valid.has(key)));
  }

  async function load({ silent = false, refresh = false } = {}) {
    if (state.fetching) {
      state.pendingLoad = { silent, refresh };
      return;
    }
    state.fetching = true;
    if (!silent) $("loading").classList.remove("hidden");
    if (!silent) $("errorBox").classList.add("hidden");
    setLive("busy");
    try {
      const q = new URLSearchParams({ days: String(state.days) });
      if (refresh) q.set("refresh", "1");
      const resp = await fetch(`/api/market/steep?${q}`, { cache: "no-store" });
      const json = await resp.json();
      if (!json.ok) throw new Error(json.error || "加载失败");
      const data = json.data || {};
      state.items = data.items || [];
      state.updatedAt = data.updated_at || "";
      pruneOpen();
      render();
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
      void load({ silent: true });
    }, POLL_MS);
  }

  function bindScroll() {
    const up = $("upScroll");
    const down = $("downScroll");
    const follow = (from, to) => {
      from.addEventListener("scroll", () => {
        if (state.syncing) return;
        state.syncing = true;
        to.scrollLeft = from.scrollLeft;
        state.syncing = false;
      });
    };
    follow(up, down);
    follow(down, up);
  }

  function bind() {
    $("upTrack").addEventListener("click", onTrackClick);
    $("downTrack").addEventListener("click", onTrackClick);
    $("sortSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-sort]");
      if (btn) setSort(btn.dataset.sort);
    });
    $("rangeSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-days]");
      if (btn) setDays(btn.dataset.days);
    });
    $("refreshBtn").addEventListener("click", () => void load({ silent: true, refresh: true }));
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) void load({ silent: true });
    });
    bindScroll();
  }

  function onTrackClick(ev) {
    const stock = ev.target.closest("tr.is-stock[data-code]");
    if (stock) {
      const qs = new URLSearchParams({ code: stock.dataset.code });
      if (stock.dataset.industry) qs.set("industry", stock.dataset.industry);
      window.location.href = `/company.html?${qs}`;
      return;
    }
    const head = ev.target.closest(".steep-day-head");
    if (head) togglePane(head.dataset.date, head.dataset.kind);
  }

  bind();
  void load().then(startPoll);
})();
