(() => {
  const POLL_MS = 500;
  const WEEK = "日一二三四五六";

  const state = {
    days: 15,
    top: 30,
    status: "idle",
    dayRows: [],
    selectedDate: "",
    updatedAt: "",
    candidateCount: 0,
    resultCount: 0,
    analyzedCount: 0,
    pollTimer: 0,
    fetching: false,
  };

  const $ = (id) => document.getElementById(id);

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtNum(value, digits = 1) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(digits);
  }

  function fmtPct(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
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

  function fmtMd(date) {
    return String(date || "").slice(5) || "—";
  }

  function selectedDay() {
    return state.dayRows.find((d) => d.date === state.selectedDate) || state.dayRows[0] || null;
  }

  function setLive(kind) {
    const el = $("liveDot");
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

  function showLoading(show, text) {
    const el = $("loading");
    el.textContent = text || "正在分析…";
    el.classList.toggle("hidden", !show);
  }

  function renderSeg() {
    $("daysSeg").querySelectorAll("button[data-days]").forEach((btn) => {
      btn.classList.toggle("is-active", Number(btn.dataset.days) === state.days);
    });
    $("topSeg").querySelectorAll("button[data-top]").forEach((btn) => {
      btn.classList.toggle("is-active", Number(btn.dataset.top) === state.top);
    });
  }

  function renderSummary() {
    const day = selectedDay();
    const dayN = day ? day.candidate_count || 0 : 0;
    const dayDone = day ? day.analyzed_count || (day.items || []).length : 0;
    const analyzed = state.analyzedCount || 0;
    $("summaryBar").innerHTML = `
      <span>已分析 <b>${analyzed}</b> / ${state.candidateCount || 0}</span>
      <span>当日 <b>${dayDone}</b> / ${dayN}</span>
      <span>展示 <b>${(day && day.items && day.items.length) || 0}</b></span>
      <span>窗口 <b>${state.days}</b> 交易日</span>
    `;
    $("marketMeta").textContent = state.updatedAt || "";
  }

  function scoreChip(label, value) {
    const n = Number(value);
    if (!Number.isFinite(n)) {
      return `<span class="screen-chip"><em>${esc(label)}</em>—</span>`;
    }
    const kind = n >= 70 ? "up" : n >= 45 ? "flat" : "down";
    return `<span class="screen-chip" data-tone="${kind}"><em>${esc(label)}</em>${fmtNum(n, 0)}</span>`;
  }

  function renderDayRail() {
    const rail = $("dayRail");
    if (!state.dayRows.length) {
      rail.innerHTML = `<p class="screen-empty muted">暂无交易日</p>`;
      return;
    }
    rail.innerHTML = state.dayRows
      .map((day) => {
        const active = day.date === state.selectedDate ? " is-active" : "";
        const total = day.candidate_count || 0;
        const done = day.analyzed_count || (day.items || []).length || 0;
        const countText = state.status === "running" ? `${done}/${total}` : String(total);
        return `<button type="button" class="screen-day-chip${active}" data-date="${esc(day.date)}">
          <span class="screen-day-when">
            <b>${esc(fmtMd(day.date))}</b>
            <em>${esc(weekday(day.date))}</em>
          </span>
          <span class="screen-day-count" data-tone="up">${esc(countText)}</span>
        </button>`;
      })
      .join("");
  }

  function renderDayHead(day) {
    const head = $("dayHead");
    if (!day) {
      head.innerHTML = "";
      return;
    }
    head.innerHTML = `
      <div>
        <h2>${esc(day.date)} ${esc(weekday(day.date))}</h2>
        <p>当日涨停 <b>${day.candidate_count || 0}</b> · 已分析 <b>${day.analyzed_count || (day.items || []).length}</b> · 展示 <b>${(day.items || []).length}</b></p>
      </div>
    `;
  }

  function stockKey(row) {
    return `${row.code || ""}|${row.limit_up_date || ""}`;
  }

  function cardHtml(row) {
    const detected = row.detected || {};
    const dec = detected.decline || {};
    const cons = detected.consolidation || {};
    const scores = row.scores || {};
    const industry = [row.l1_name, row.l2_name, row.l3_name].filter(Boolean).join(" / ");
    const board = row.board_count ? `${row.board_count}板` : "—";
    const err = row.error ? `<span class="screen-card-error">${esc(row.error)}</span>` : "";
    const href = `/company.html?code=${encodeURIComponent(row.code || "")}`;
    return `<article class="screen-card is-stock" data-code="${esc(row.code || "")}" data-key="${esc(stockKey(row))}" tabindex="0">
      <a class="screen-card-head" href="${esc(href)}" title="打开公司详情">
        <span class="screen-rank">${row.rank || ""}</span>
        <div class="screen-card-name">
          <strong>${esc(row.name || "")}</strong>
          <span>${esc(row.code || "")}</span>
          ${industry ? `<em>${esc(industry)}</em>` : ""}
        </div>
        <div class="screen-card-score">
          <b>${fmtNum(scores.total, 1)}</b>
          <span>${esc(board)}</span>
        </div>
      </a>
      <article class="chart-card chart-card--kline" data-kline-code="${esc(row.code || "")}">
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
      </article>
      <footer class="screen-card-meta">
        <span>阴跌 <b>${dec.days ?? "—"}</b>天 <b data-tone="${tone(dec.total_pct)}">${fmtPct(dec.total_pct)}</b></span>
        <span>横盘 <b>${cons.days ?? "—"}</b>天 幅 <b>${fmtNum(cons.range_pct, 1)}</b>%</span>
        ${scoreChip("阴跌时长", scores.decline_duration)}
        ${scoreChip("阴跌质量", scores.decline_quality)}
        ${scoreChip("横盘时长", scores.consolidation_duration)}
        ${scoreChip("横盘质量", scores.consolidation_quality)}
        ${scoreChip("突破", scores.breakout)}
        ${scoreChip("结构", scores.structure)}
        ${err}
      </footer>
    </article>`;
  }

  function mountCardKline(card) {
    const kline = card.querySelector(".chart-card--kline");
    const code = kline && kline.dataset.klineCode;
    if (kline && code && window.OrbitKline) window.OrbitKline.mount(kline, { code, carousel: true });
  }

  function htmlToCard(row) {
    const wrap = document.createElement("div");
    wrap.innerHTML = cardHtml(row).trim();
    return wrap.firstElementChild;
  }

  function patchCard(el, row) {
    const rank = el.querySelector(".screen-rank");
    if (rank) rank.textContent = String(row.rank || "");
    const score = el.querySelector(".screen-card-score b");
    if (score) score.textContent = fmtNum((row.scores || {}).total, 1);
  }

  function renderCards() {
    const list = $("resultList");
    const day = selectedDay();
    const items = (day && day.items) || [];
    if (!items.length) {
      const text = state.status === "running" ? "正在分析，结果会逐只出现…" : "该日暂无结果";
      list.innerHTML = `<p class="screen-empty muted">${esc(text)}</p>`;
      return;
    }

    const empty = list.querySelector(".screen-empty");
    if (empty) empty.remove();

    if (list.dataset.date !== (state.selectedDate || "")) {
      list.scrollLeft = 0;
      list.dataset.date = state.selectedDate || "";
    }

    const prev = new Map();
    list.querySelectorAll("article.is-stock").forEach((el) => {
      prev.set(el.dataset.key, el);
    });
    const used = new Set();
    const fresh = [];
    items.forEach((row) => {
      const key = stockKey(row);
      used.add(key);
      let el = prev.get(key);
      if (!el) {
        el = htmlToCard(row);
        fresh.push(el);
      } else {
        patchCard(el, row);
      }
      list.appendChild(el);
    });
    prev.forEach((el, key) => {
      if (!used.has(key)) el.remove();
    });
    if (fresh.length) {
      requestAnimationFrame(() => fresh.forEach((card) => mountCardKline(card)));
    }
  }

  function renderAll() {
    renderSeg();
    renderSummary();
    renderDayRail();
    renderDayHead(selectedDay());
    renderCards();
  }

  function applyData(data) {
    state.dayRows = data.days || [];
    state.updatedAt = data.updated_at || "";
    state.candidateCount = data.candidate_count || 0;
    state.resultCount = data.result_count || 0;
    state.analyzedCount = data.analyzed_count || data.result_count || 0;
    if (!state.dayRows.some((d) => d.date === state.selectedDate)) {
      state.selectedDate = (state.dayRows[0] && state.dayRows[0].date) || "";
    }
    renderAll();
  }

  function applyPayload(payload) {
    state.status = payload.status || "idle";
    const progress = payload.progress || {};
    if (progress.total) {
      state.candidateCount = progress.total;
      state.analyzedCount = progress.done || 0;
    }

    if (payload.status === "done" && payload.data) {
      applyData(payload.data);
      showLoading(false);
      showError("");
      setLive("live");
      return;
    }

    if (payload.status === "error") {
      showLoading(false);
      showError(payload.error || "分析失败");
      setLive("idle");
      return;
    }

    if (payload.status === "running") {
      if (payload.data) applyData(payload.data);
      const elapsed = payload.elapsed_sec ? ` · ${fmtNum(payload.elapsed_sec, 0)}s` : "";
      showLoading(true, `${payload.message || "正在分析…"}${elapsed}`);
      setLive("busy");
    }
  }

  function stopPoll() {
    if (state.pollTimer) {
      clearTimeout(state.pollTimer);
      state.pollTimer = 0;
    }
  }

  function schedulePoll() {
    stopPoll();
    state.pollTimer = setTimeout(() => load(false), POLL_MS);
  }

  async function load(force) {
    if (state.fetching && !force) return;
    state.fetching = true;
    showError("");
    if (force) {
      state.dayRows = [];
      state.resultCount = 0;
      state.analyzedCount = 0;
      state.selectedDate = "";
      renderAll();
      showLoading(true, "正在拉取涨停池…");
      setLive("busy");
    }

    const qs = new URLSearchParams({
      days: String(state.days),
      top: String(state.top),
      refresh: force ? "1" : "0",
    });

    try {
      const res = await fetch(`/api/screen/yindie?${qs}`);
      const json = await res.json();
      if (!json.ok) {
        throw new Error(json.error || "请求失败");
      }
      applyPayload(json.data || {});
      if (state.status === "running") {
        schedulePoll();
      } else {
        stopPoll();
      }
    } catch (err) {
      showLoading(false);
      showError(err.message || String(err));
      setLive("idle");
      stopPoll();
    } finally {
      state.fetching = false;
    }
  }

  function openCompany(code) {
    if (!code) return;
    window.location.href = `/company.html?code=${encodeURIComponent(code)}`;
  }

  function bindEvents() {
    $("refreshBtn").addEventListener("click", () => load(true));

    $("daysSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-days]");
      if (!btn) return;
      const days = Number(btn.dataset.days);
      if (days === state.days) return;
      state.days = days;
      renderSeg();
      load(false);
    });

    $("topSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-top]");
      if (!btn) return;
      const top = Number(btn.dataset.top);
      if (top === state.top) return;
      state.top = top;
      renderSeg();
      load(false);
    });

    $("dayRail").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-date]");
      if (!btn) return;
      const date = btn.dataset.date;
      if (!date || date === state.selectedDate) return;
      state.selectedDate = date;
      renderAll();
    });

    const list = $("resultList");
    let swipe = null;
    const canScrollX = () => list.scrollWidth > list.clientWidth + 1;

    list.addEventListener(
      "wheel",
      (ev) => {
        if (ev.ctrlKey) return;
        if (ev.target.closest(".chart-canvas-wrap, canvas")) return;
        if (!canScrollX()) return;
        ev.preventDefault();
        ev.stopPropagation();
        const delta = Math.abs(ev.deltaX) > Math.abs(ev.deltaY) ? ev.deltaX : ev.deltaY;
        list.scrollLeft += delta;
      },
      { passive: false, capture: true },
    );

    list.addEventListener(
      "pointerdown",
      (ev) => {
        if (ev.button != null && ev.button !== 0) return;
        if (ev.target.closest("input, select, button, a, .chart-scroll-bar, .chart-canvas-wrap, canvas")) return;
        if (!canScrollX()) return;
        swipe = {
          id: ev.pointerId,
          x: ev.clientX,
          scroll: list.scrollLeft,
          moved: false,
        };
        list.classList.add("is-swiping");
      },
      true,
    );

    list.addEventListener("pointermove", (ev) => {
      if (!swipe || ev.pointerId !== swipe.id) return;
      const dx = ev.clientX - swipe.x;
      if (!swipe.moved && Math.abs(dx) < 6) return;
      if (!swipe.moved) {
        swipe.moved = true;
        try {
          list.setPointerCapture(ev.pointerId);
        } catch {
          /* ignore */
        }
      }
      ev.preventDefault();
      list.scrollLeft = swipe.scroll - dx;
    });

    const endSwipe = (ev) => {
      if (!swipe || (ev && ev.pointerId !== swipe.id)) return;
      const moved = swipe.moved;
      swipe = null;
      list.classList.remove("is-swiping");
      list.dataset.swiped = moved ? "1" : "";
    };
    list.addEventListener("pointerup", endSwipe);
    list.addEventListener("pointercancel", endSwipe);

    list.addEventListener("click", (ev) => {
      if (list.dataset.swiped === "1") {
        list.dataset.swiped = "";
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      const head = ev.target.closest(".screen-card-head");
      if (head) return;
      if (ev.target.closest(".chart-card")) return;
      const card = ev.target.closest("article.is-stock[data-code]");
      if (!card) return;
      openCompany(card.dataset.code);
    });

    $("resultList").addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      const card = ev.target.closest("article.is-stock[data-code]");
      if (!card) return;
      ev.preventDefault();
      openCompany(card.dataset.code);
    });
  }

  renderSeg();
  bindEvents();
  load(false);
})();
