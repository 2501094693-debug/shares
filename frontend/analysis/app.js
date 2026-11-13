(() => {
  const POLL_MS = 1200;
  const WEEK = "日一二三四五六";
  const VIEW_KEY = "orbit-judgment-view";
  const VIEW_META = {
    limit: {
      title: "ORBIT · 行情研判",
      sub: "按每日涨停池分批排名：阴跌 → 横盘 → 涨停，软评分排序并附日 K",
      from: "screen",
    },
    industry: {
      title: "ORBIT · 行情研判",
      sub: "按交易日复盘申万三级行业轮动：上涨/待涨/领涨均按所选交易日切片；行情与主力净流入（当日/5日/10日）回溯至该日。点击行业进入行情树",
      from: "analysis",
    },
    stock: {
      title: "ORBIT · 行情研判",
      sub: "非创业板、非科创板、非 ST · ±band 区间内个股/指数四价走势、股指偏离、低点评分；点列头切换排序，点击行进入个股",
      from: "analysis",
    },
    select: {
      title: "ORBIT · 行情研判",
      sub: "非创业板、非科创板、非 ST、非退市 · 最新收盘/最低两价各自「最近最低」交易日数与间隔；默认按间隔升序，点列头切换排序，点击行进入个股",
      from: "analysis",
    },
  };

  const STOCK_SORT_KEYS = [
    "code",
    "name",
    "beg",
    "end",
    "count",
    "stock_path",
    "index_path",
    "divergence",
    "low_score",
    "low_date",
  ];
  const STOCK_SORT_LABELS = {
    code: "代码",
    name: "名称",
    beg: "起始",
    end: "结束",
    count: "天数",
    stock_path: "个股收盘",
    index_path: "指数收盘",
    divergence: "偏离",
    low_score: "低点分",
    low_date: "低点日",
  };
  const STOCK_INDEX_CODES = ["000001", "399001", "000300"];

  const SELECT_SORT_KEYS = [
    "code",
    "name",
    "date",
    "close_price",
    "low_price",
    "close_days",
    "low_days",
    "gap",
    "close_since",
    "low_since",
  ];
  const SELECT_SORT_LABELS = {
    code: "代码",
    name: "名称",
    date: "交易日",
    close_price: "收盘",
    low_price: "最低",
    close_days: "收盘天数",
    low_days: "最低天数",
    gap: "间隔",
    close_since: "收盘自",
    low_since: "最低自",
  };

  const limit = {
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
    started: false,
    error: "",
    message: "",
  };

  const industry = {
    days: 20,
    top: 0,
    status: "idle",
    dayRows: [],
    selectedDate: "",
    untouched: [],
    ranking: [],
    universe: 0,
    coveredCount: 0,
    untouchedCount: 0,
    note: "",
    updatedAt: "",
    errors: [],
    pollTimer: 0,
    fetching: false,
    started: false,
    error: "",
    message: "",
  };

  const stock = {
    band: 0.09,
    index: "000001",
    factor: "close",
    status: "idle",
    items: [],
    candidateCount: 0,
    analyzedCount: 0,
    foundCount: 0,
    errorCount: 0,
    updatedAt: "",
    params: null,
    sortKey: "divergence",
    sortDir: "desc",
    pollTimer: 0,
    fetching: false,
    started: false,
    error: "",
    message: "",
  };

  const select = {
    adjust: "qfq",
    status: "idle",
    items: [],
    candidateCount: 0,
    analyzedCount: 0,
    foundCount: 0,
    errorCount: 0,
    updatedAt: "",
    params: null,
    sortKey: "gap",
    sortDir: "asc",
    pollTimer: 0,
    fetching: false,
    started: false,
    error: "",
    message: "",
  };

  let view = "industry";

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

  function fmtScore(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(0);
  }

  function scoreTone(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "flat";
    if (n >= 70) return "up";
    if (n <= 60) return "down";
    return "flat";
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

  function parseView(raw) {
    const value = String(raw || "").toLowerCase();
    if (["limit", "screen", "decline", "zt"].includes(value)) return "limit";
    if (["industry", "rotation", "rot", "l3", "hy"].includes(value)) return "industry";
    if (["stock", "evaluate", "eval", "gg"].includes(value)) return "stock";
    if (["select", "recent-low", "recent_low", "rl", "sx"].includes(value)) return "select";
    return "";
  }

  function parseSortKey(raw) {
    const value = String(raw || "").toLowerCase();
    if (value === "stock_path_close") return "stock_path";
    if (value === "index_path_close") return "index_path";
    return STOCK_SORT_KEYS.includes(value) ? value : "divergence";
  }

  function parseSelectSortKey(raw) {
    const value = String(raw || "").toLowerCase();
    return SELECT_SORT_KEYS.includes(value) ? value : "gap";
  }

  function pathLabelOf(row, which) {
    const pack = row && typeof row === "object" ? row[which] : null;
    if (!pack || typeof pack !== "object") return "";
    return String(pack.close || "");
  }

  function fmtPathCell(paths) {
    const pack = paths && typeof paths === "object" ? paths : {};
    const text = pack.close || "—";
    return `<span class="stock-path-chip" data-path="${esc(text)}">${esc(text)}</span>`;
  }

  function parseSortDir(raw) {
    return String(raw || "").toLowerCase() === "asc" ? "asc" : "desc";
  }

  function current() {
    if (view === "industry") return industry;
    if (view === "stock") return stock;
    if (view === "select") return select;
    return limit;
  }

  function selectedLimitDay() {
    return limit.dayRows.find((d) => d.date === limit.selectedDate) || limit.dayRows[0] || null;
  }

  function selectedIndustryDay() {
    return (
      industry.dayRows.find((d) => d.date === industry.selectedDate) || industry.dayRows[0] || null
    );
  }

  function resultItems() {
    const day = selectedLimitDay();
    return (day && day.items) || [];
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

  function syncStatusUi() {
    const st = current();
    showError(st.error || "");
    if (st.status === "running") {
      showLoading(true, st.message || "正在分析…");
      setLive("busy");
      return;
    }
    showLoading(false);
    if (st.status === "done") setLive("live");
    else if (st.status === "error") setLive("idle");
    else setLive(st.started ? "live" : "idle");
  }

  function persistView() {
    try {
      sessionStorage.setItem(VIEW_KEY, view);
    } catch {
      /* ignore */
    }
  }

  function syncUrl() {
    const url = new URL(location.href);
    url.searchParams.set("view", view);
    url.searchParams.delete("code");
    if (view === "stock") {
      url.searchParams.set("sort", stock.sortKey);
      url.searchParams.set("order", stock.sortDir);
      url.searchParams.set("band", String(stock.band));
      url.searchParams.set("index", stock.index);
      url.searchParams.delete("adjust");
    } else if (view === "select") {
      url.searchParams.set("sort", select.sortKey);
      url.searchParams.set("order", select.sortDir);
      url.searchParams.set("adjust", select.adjust);
      url.searchParams.delete("band");
      url.searchParams.delete("index");
      url.searchParams.delete("factor");
      url.searchParams.delete("path");
    } else {
      url.searchParams.delete("sort");
      url.searchParams.delete("order");
      url.searchParams.delete("band");
      url.searchParams.delete("index");
      url.searchParams.delete("factor");
      url.searchParams.delete("path");
      url.searchParams.delete("adjust");
    }
    history.replaceState({}, "", url);
  }

  function applyChrome() {
    const meta = VIEW_META[view] || VIEW_META.industry;
    document.title = meta.title;
    $("pageSub").textContent = meta.sub;
    document.body.dataset.screenMode = view;
    persistView();
    syncUrl();
    renderSeg();
  }

  function markSeg(rootId, key, value) {
    const root = $(rootId);
    if (!root) return;
    root.querySelectorAll(`button[data-${key}]`).forEach((btn) => {
      const raw = btn.dataset[key];
      const active = typeof value === "number" ? Number(raw) === value : raw === value;
      btn.classList.toggle("is-active", active);
    });
  }

  function renderSeg() {
    $("viewSeg").querySelectorAll("button[data-view]").forEach((btn) => {
      const active = btn.dataset.view === view;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    markSeg("limitDaysSeg", "days", limit.days);
    markSeg("limitTopSeg", "top", limit.top);
    markSeg("industryDaysSeg", "days", industry.days);
    markSeg("stockBandSeg", "band", stock.band);
    markSeg("stockIndexSeg", "index", stock.index);
  }

  function scoreChip(label, value) {
    const n = Number(value);
    if (!Number.isFinite(n)) {
      return `<span class="screen-chip"><em>${esc(label)}</em>—</span>`;
    }
    const kind = n >= 70 ? "up" : n >= 45 ? "flat" : "down";
    return `<span class="screen-chip" data-tone="${kind}"><em>${esc(label)}</em>${fmtNum(n, 0)}</span>`;
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

  function fromHref(code) {
    return `/company.html?code=${encodeURIComponent(code || "")}&from=${encodeURIComponent(VIEW_META[view].from)}`;
  }

  function renderLimitSummary() {
    const analyzed = limit.analyzedCount || 0;
    const day = selectedLimitDay();
    const dayN = day ? day.candidate_count || 0 : 0;
    const dayDone = day ? day.analyzed_count || (day.items || []).length : 0;
    $("summaryBar").innerHTML = `
      <span>已分析 <b>${analyzed}</b> / ${limit.candidateCount || 0}</span>
      <span>当日 <b>${dayDone}</b> / ${dayN}</span>
      <span>展示 <b>${(day && day.items && day.items.length) || 0}</b></span>
      <span>窗口 <b>${limit.days}</b> 交易日</span>
    `;
    $("marketMeta").textContent = limit.updatedAt || "";
  }

  function windowLabel(days) {
    const n = Number(days);
    if (n >= 400) return "两年";
    if (n >= 180) return "一年";
    if (n >= 90) return "近半年";
    if (n >= 40) return "近三个月";
    if (n >= 15) return "近一个月";
    return `${n}日`;
  }

  const WATCH_CHANGE_PCT = 2.0;

  function industryChrono() {
    return [...(industry.dayRows || [])].reverse();
  }

  function paintDayQuote(row, quotes, hasQuotes) {
    if (!row) return row;
    if (!hasQuotes) return row;
    const q = row.code && quotes && quotes[row.code];
    const merged = { ...row };
    if (q) {
      Object.assign(merged, q);
    }
    for (const key of ["main_net", "main_net_5d", "main_net_10d"]) {
      merged[key] = q && Object.prototype.hasOwnProperty.call(q, key) ? q[key] : null;
    }
    return merged;
  }

  function updateWaitTableHeaders(day) {
    const table = $("indWaitBody")?.closest("table");
    const ths = table?.querySelectorAll("thead th");
    if (!ths || ths.length < 9) return;
    const latest = industry.dayRows[0]?.date;
    const hist = day && day.date && day.date !== latest;
    ths[3].textContent = hist ? "当日涨跌" : "涨跌";
    ths[6].textContent = hist ? "当日" : "今日";
    ths[7].textContent = hist ? "近5日" : "5日";
    ths[8].textContent = hist ? "近10日" : "10日";
  }

  function untouchedTag(row) {
    const flow5 = row.main_net_5d;
    const flow10 = row.main_net_10d;
    const d5 = row.change_5d;
    const money =
      flow5 != null && Number(flow5) > 0 && flow10 != null && Number(flow10) > 0;
    if (money && (d5 == null || Number(d5) < WATCH_CHANGE_PCT)) {
      return { tag: "资金先行", reason: "窗口内没被点名，但5日和10日资金都在进" };
    }
    if (d5 != null && Number(d5) >= WATCH_CHANGE_PCT) {
      return { tag: "近5日跟上", reason: "窗口内没被点名，近5日已经转强" };
    }
    return { tag: "", reason: "窗口内从未达到轮动分数线" };
  }

  function industryBoardsAsOf(selectedDate) {
    const chrono = industryChrono();
    if (!chrono.length) {
      return { wait: [], ranking: [], coveredCount: 0, untouchedCount: 0 };
    }
    const date = selectedDate || chrono[chrono.length - 1]?.date || "";
    const datePos = {};
    chrono.forEach((d, i) => {
      if (d.date) datePos[d.date] = i;
    });
    const endPos = datePos[date];
    if (endPos === undefined) {
      return { wait: [], ranking: [], coveredCount: 0, untouchedCount: 0 };
    }

    const hitsMap = {};
    for (let i = 0; i <= endPos; i++) {
      const day = chrono[i];
      const risen = [...(day.first || []), ...(day.again || [])];
      for (const item of risen) {
        const code = item.code;
        if (!code) continue;
        if (!hitsMap[code]) hitsMap[code] = [];
        hitsMap[code].push(day.date);
      }
    }

    const selectedDay = chrono[endPos];
    const hasQuotes =
      selectedDay && Object.prototype.hasOwnProperty.call(selectedDay, "quotes");
    const dayQuotes = hasQuotes ? selectedDay.quotes || {} : null;
    const risenToday = new Set(
      [...(selectedDay.first || []), ...(selectedDay.again || [])]
        .map((r) => r.code)
        .filter(Boolean),
    );

    const base =
      industry.ranking && industry.ranking.length
        ? industry.ranking
        : [...(industry.untouched || [])];

    const ranking = base
      .map((row) => {
        const hitDates = hitsMap[row.code] || [];
        return paintDayQuote(
          {
            ...row,
            hits: hitDates.length,
            first_date: hitDates[0] || "",
            last_date: hitDates[hitDates.length - 1] || "",
          },
          dayQuotes,
          hasQuotes,
        );
      })
      .sort((a, b) => {
        const ah = Number(a.hits) || 0;
        const bh = Number(b.hits) || 0;
        if (bh !== ah) return bh - ah;
        const ad = String(a.last_date || "");
        const bd = String(b.last_date || "");
        if (ad !== bd) return bd.localeCompare(ad);
        return String(a.name || "").localeCompare(String(b.name || ""), "zh");
      });

    const coveredCount = ranking.filter((r) => Number(r.hits) > 0).length;

    const wait = ranking
      .filter((row) => !risenToday.has(row.code))
      .map((row) => {
        const last = row.last_date || "";
        let idleDays;
        if (last) {
          idleDays = endPos - (datePos[last] ?? endPos);
        } else {
          idleDays = endPos + 1;
        }
        const { tag, reason } = untouchedTag(row);
        const item = {
          ...row,
          idle_days: idleDays,
          tag: tag || "待涨",
        };
        if (last) {
          item.reason = `距上次上榜 ${idleDays} 个交易日（${last}）${tag ? `；${reason}` : ""}`;
        } else if (!tag) {
          item.reason = "窗口内从未上榜";
        } else {
          item.reason = reason;
        }
        return item;
      })
      .sort((a, b) => {
        const ai = Number(a.idle_days) || 0;
        const bi = Number(b.idle_days) || 0;
        if (bi !== ai) return bi - ai;
        return String(a.last_date || "").localeCompare(String(b.last_date || ""));
      });

    return { wait, ranking, coveredCount, untouchedCount: wait.length };
  }

  function renderIndustrySummary() {
    const boards = industryBoardsAsOf(industry.selectedDate);
    const coveredN = boards.coveredCount || 0;
    const leftN = boards.untouchedCount || 0;
    $("summaryBar").innerHTML = `
      <span>扫描 <b>${industry.universe || 0}</b> 个三级</span>
      <span><b class="is-up">${coveredN}</b> 已上榜</span>
      <span>待涨 <b>${leftN}</b></span>
      <span>窗口 <b>${windowLabel(industry.days)}</b></span>
    `;
    $("marketMeta").textContent = "";
  }

  function renderDayRail() {
    const rail = $("dayRail");
    if (!limit.dayRows.length) {
      rail.innerHTML = `<p class="screen-empty muted">暂无交易日</p>`;
      return;
    }
    rail.innerHTML = limit.dayRows
      .map((day) => {
        const active = day.date === limit.selectedDate ? " is-active" : "";
        const total = day.candidate_count || 0;
        const done = day.analyzed_count || (day.items || []).length || 0;
        const countText = limit.status === "running" ? `${done}/${total}` : String(total);
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

  function renderRotDays() {
    const rail = $("rotDayRail");
    const hint = $("rotDaysHint");
    if (hint) hint.textContent = industry.dayRows.length ? `${industry.dayRows.length} 天` : "";
    if (!rail) return;
    if (!industry.dayRows.length) {
      rail.innerHTML = `<div class="rot-empty">暂无交易日</div>`;
      return;
    }
    rail.innerHTML = industry.dayRows
      .map((day) => {
        const active = day.date === industry.selectedDate ? " is-active" : "";
        const n =
          day.risen_count ||
          ((day.first || []).length + (day.again || []).length) ||
          0;
        return `<button type="button" class="rot-day${active}" data-date="${esc(day.date)}">
          <span class="rot-day-when">
            <b>${esc(fmtMd(day.date))}</b>
            <em>${esc(weekday(day.date))}</em>
          </span>
          <span class="rot-day-n">${n}</span>
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

  function renderIndustryHead(day) {
    const boards = industryBoardsAsOf(industry.selectedDate || day?.date);
    const waitN = boards.untouchedCount;
    const againN = risenList(day).length;
    const rankN = boards.ranking.length;
    const when = day ? `${fmtMd(day.date)} ${weekday(day.date)}` : "";
    const waitHint = $("rotWaitHint");
    const againHint = $("rotAgainHint");
    const rankHint = $("indRankHint");
    if (waitHint) waitHint.textContent = waitN ? `${waitN}` : "";
    if (againHint) againHint.textContent = day ? `${when} · ${againN}` : "";
    if (rankHint) rankHint.textContent = rankN ? `${rankN} 个` : "";
  }

  function tagTone(bucket, tag) {
    const key = String(bucket || tag || "");
    if (key === "首次" || key === "新轮到" || key === "近5日跟上" || key === "may_rotate" || key === "may_turn") return "up";
    if (key === "上涨" || key === "续涨" || key === "risen_hot") return "up";
    if (key === "待涨") return "down";
    if (key === "资金先行" || key === "watch") return "flat";
    if (key === "risen_cool") return "down";
    return "flat";
  }

  function fmtIdle(days, lastDate) {
    if (!lastDate) return "从未";
    const n = Number(days);
    if (!Number.isFinite(n)) return "—";
    return `${n}日`;
  }

  function fmtCountPair(total, limit) {
    const up = Number(total);
    const lim = Number(limit);
    if (!Number.isFinite(up) && !Number.isFinite(lim)) return "—";
    const a = Number.isFinite(up) ? up : 0;
    const b = Number.isFinite(lim) ? lim : 0;
    return `${a}(${b})`;
  }

  function fmtBreadth(up, sample) {
    const a = Number(up);
    const b = Number(sample);
    if (!Number.isFinite(a) || !Number.isFinite(b) || b <= 0) return "—";
    return `${a}/${b}`;
  }

  function breadthTone(up, sample, pct) {
    const a = Number(up);
    const b = Number(sample);
    const ratio = Number.isFinite(a) && Number.isFinite(b) && b > 0 ? a / b : Number(pct) / 100;
    if (!Number.isFinite(ratio)) return "flat";
    if (ratio >= 0.7) return "up";
    if (ratio <= 0.4) return "down";
    return "flat";
  }

  function fmtHits(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "0";
    return String(n);
  }

  function risenList(day) {
    const first = ((day && day.first) || []).map((row) => ({
      ...row,
      tag: "首次",
    }));
    const again = (day && day.again) || [];
    return first.concat(again);
  }

  function industryRows(items, kind) {
    if (!items.length) {
      const cols = kind === "wait" ? 9 : kind === "again" ? 6 : 3;
      const empty =
        kind === "rank"
          ? "还没有领涨行业"
          : kind === "wait"
            ? "没有待涨行业"
            : "这一天没有上涨行业";
      return `<tr class="is-empty"><td colspan="${cols}">${empty}</td></tr>`;
    }
    return items
      .map((n) => {
        const tag = String(n.tag || "").trim() === "续涨" ? "上涨" : String(n.tag || "").trim();
        const showTag = tag === "首次" || (kind === "wait" && tag);
        const tagHtml = showTag
          ? `<span class="rot-tag" data-tone="${tagTone(n.bucket, tag)}">${esc(tag)}</span>`
          : "";
        const tier = kind === "wait" ? "" : String(n.cap_tier || "").trim();
        const tierHtml = tier
          ? `<span class="rot-tag" data-tone="flat">${esc(tier)}</span>`
          : "";
        const sub = [n.l2_name, n.leader].filter(Boolean).join(" · ");
        const strong = n.strong_1d == null ? n.limit_up_1d : n.strong_1d;
        const extra =
          kind === "wait"
            ? `<td class="num">${esc(fmtHits(n.hits))}</td>
          <td class="num" data-tone="${n.tag === "首次" ? "up" : n.last_date ? "flat" : "down"}">${
              n.tag === "首次" ? "当天" : esc(fmtIdle(n.idle_days, n.last_date))
            }</td>
          <td class="num" data-tone="${tone(n.change_1d)}">${fmtPct(n.change_1d)}</td>
          <td class="num" data-tone="up">${esc(fmtCountPair(n.up_1d, n.limit_up_1d))}</td>
          <td class="num" data-tone="down">${esc(fmtCountPair(n.down_1d, n.limit_down_1d))}</td>
          <td class="num" data-tone="${tone(n.main_net)}">${fmtYi(n.main_net)}</td>
          <td class="num" data-tone="${tone(n.main_net_5d)}">${fmtYi(n.main_net_5d)}</td>
          <td class="num" data-tone="${tone(n.main_net_10d)}">${fmtYi(n.main_net_10d)}</td>`
            : kind === "rank"
              ? `<td class="num" data-tone="${Number(n.hits) > 0 ? "up" : "flat"}">${esc(fmtHits(n.hits))}</td>
          <td class="num">${esc(n.last_date ? fmtMd(n.last_date) : "从未")}</td>`
              : `<td class="num">${esc(fmtHits(n.hits))}</td>
          <td class="num" data-tone="${scoreTone(n.score)}">${fmtScore(n.score)}</td>
          <td class="num" data-tone="${tone(n.change_1d)}">${fmtPct(n.change_1d)}</td>
          <td class="num" data-tone="${breadthTone(n.up_1d, n.sample_count, n.breadth)}" title="${esc(
            n.breadth == null ? "上涨家数/样本" : `上涨 ${fmtBreadth(n.up_1d, n.sample_count)} · ${Number(n.breadth).toFixed(0)}%`
          )}">${esc(fmtBreadth(n.up_1d, n.sample_count))}</td>
          <td class="num" data-tone="${Number(strong) > 0 ? "up" : "flat"}">${strong == null ? "—" : esc(strong)}</td>`;
        return `<tr class="is-row" data-code="${esc(n.code || "")}" data-l1="${esc(n.l1_code || "")}" data-l2="${esc(n.l2_code || "")}" title="${esc(n.reason || "")}">
          <td>
            <div class="rot-name"><strong>${esc(n.name || n.code || "—")}</strong>${tagHtml}${tierHtml}</div>
            <div class="rot-sub">${esc(sub)}</div>
          </td>
          ${extra}
        </tr>`;
      })
      .join("");
  }

  function renderIndustry() {
    const day = selectedIndustryDay();
    const boards = industryBoardsAsOf(industry.selectedDate || day?.date);
    const wait = boards.wait;
    const again = risenList(day);
    const ranking = boards.ranking;
    updateWaitTableHeaders(day);
    const waitBody = $("indWaitBody");
    const againBody = $("indAgainBody");
    const rankBody = $("indRankBody");
    if (waitBody) waitBody.innerHTML = industryRows(wait, "wait");
    if (againBody) againBody.innerHTML = industryRows(again, "again");
    if (rankBody) rankBody.innerHTML = industryRows(ranking, "rank");
  }

  function stockKey(row) {
    return `${row.code || ""}|${row.limit_up_date || ""}`;
  }

  function limitCardHtml(row) {
    const detected = row.detected || {};
    const dec = detected.decline || {};
    const cons = detected.consolidation || {};
    const scores = row.scores || {};
    const industry = [row.l1_name, row.l2_name, row.l3_name].filter(Boolean).join(" / ");
    const badge = row.board_count ? `${row.board_count}板` : "—";
    const err = row.error ? `<span class="screen-card-error">${esc(row.error)}</span>` : "";
    const href = fromHref(row.code || "");
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
          <span>${esc(badge)}</span>
        </div>
      </a>
      ${klineBlock(row.code || "")}
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

  function htmlToCard(html) {
    const wrap = document.createElement("div");
    wrap.innerHTML = html.trim();
    return wrap.firstElementChild;
  }

  function renderCards(items, keyOf, htmlOf, patchOf, emptyText, viewKey) {
    const list = $("resultList");
    if (!items.length) {
      list.innerHTML = `<p class="screen-empty muted">${esc(emptyText)}</p>`;
      return;
    }

    const empty = list.querySelector(".screen-empty");
    if (empty) empty.remove();

    if (list.dataset.date !== viewKey) {
      list.scrollLeft = 0;
      list.dataset.date = viewKey;
    }

    const prev = new Map();
    list.querySelectorAll("article.is-stock").forEach((el) => {
      prev.set(el.dataset.key, el);
    });
    const used = new Set();
    const fresh = [];
    items.forEach((row) => {
      const key = keyOf(row);
      used.add(key);
      let el = prev.get(key);
      if (!el) {
        el = htmlToCard(htmlOf(row));
        fresh.push(el);
      } else {
        patchOf(el, row);
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

  function patchLimitCard(el, row) {
    const rank = el.querySelector(".screen-rank");
    if (rank) rank.textContent = String(row.rank || "");
    const score = el.querySelector(".screen-card-score b");
    if (score) score.textContent = fmtNum((row.scores || {}).total, 1);
  }

  function emptyHint(st, noneText) {
    if (!st.started || st.status === "running") return "正在分析，结果会逐只出现…";
    return noneText;
  }

  function renderLimitCards() {
    renderCards(
      resultItems(),
      stockKey,
      limitCardHtml,
      patchLimitCard,
      emptyHint(limit, "该日暂无结果"),
      limit.selectedDate || "",
    );
  }

  function sortedStockItems() {
    const key = stock.sortKey;
    const dir = stock.sortDir === "asc" ? 1 : -1;
    const rows = [...(stock.items || [])];
    rows.sort((a, b) => {
      let av = a?.[key];
      let bv = b?.[key];
      if (key === "stock_path") {
        av = pathLabelOf(a, "stock_path");
        bv = pathLabelOf(b, "stock_path");
      } else if (key === "index_path") {
        av = pathLabelOf(a, "index_path");
        bv = pathLabelOf(b, "index_path");
      }
      const aNil = av == null || av === "";
      const bNil = bv == null || bv === "";
      if (aNil && bNil) return String(a?.code || "").localeCompare(String(b?.code || ""));
      if (aNil) return 1;
      if (bNil) return -1;
      if (typeof av === "number" || typeof bv === "number") {
        const an = Number(av);
        const bn = Number(bv);
        if (Number.isFinite(an) && Number.isFinite(bn) && an !== bn) return (an - bn) * dir;
      }
      const cmp = String(av).localeCompare(String(bv), "zh-CN");
      if (cmp) return cmp * dir;
      return String(a?.code || "").localeCompare(String(b?.code || ""));
    });
    return rows;
  }

  function renderStockSortHeaders() {
    const table = $("stockEvalTable");
    if (!table) return;
    table.querySelectorAll("th[data-sort]").forEach((th) => {
      const key = th.dataset.sort;
      const active = key === stock.sortKey;
      th.classList.toggle("is-sorted", active);
      th.dataset.order = active ? stock.sortDir : "";
      const base = STOCK_SORT_LABELS[key] || key;
      th.textContent = active ? `${base}${stock.sortDir === "asc" ? " ↑" : " ↓"}` : base;
    });
  }

  function renderStockSummary() {
    const sortLabel = STOCK_SORT_LABELS[stock.sortKey] || stock.sortKey;
    const orderLabel = stock.sortDir === "asc" ? "升序" : "降序";
    const bandPct = `${Math.round(stock.band * 100)}%`;
    $("summaryBar").innerHTML = `
      <span>已分析 <b>${stock.analyzedCount || 0}</b> / ${stock.candidateCount || 0}</span>
      <span>命中 <b>${stock.foundCount || 0}</b></span>
      <span>失败 <b>${stock.errorCount || 0}</b></span>
      <span>排序 <b>${esc(sortLabel)} · ${orderLabel}</b></span>
      <span>带 <b>±${bandPct}</b></span>
    `;
    $("marketMeta").textContent = stock.message || stock.updatedAt || "";
  }

  function toneClass(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n === 0) return "flat";
    return n > 0 ? "up" : "down";
  }

  function renderStockTable() {
    const body = $("stockEvalBody");
    const hint = $("stockEvalHint");
    if (!body) return;
    renderStockSortHeaders();
    const rows = sortedStockItems();
    if (hint) {
      hint.textContent = rows.length
        ? `${rows.length} 只 · ${STOCK_SORT_LABELS[stock.sortKey] || stock.sortKey}${stock.sortDir === "asc" ? "↑" : "↓"}`
        : stock.started
          ? "暂无命中"
          : "";
    }
    if (!rows.length) {
      const msg = stock.error
        ? esc(stock.error)
        : stock.status === "running"
          ? esc(stock.message || "正在分析…")
          : stock.started
            ? "暂无命中区间的标的"
            : "点击「重新分析」开始全市场扫描";
      body.innerHTML = `<tr><td colspan="10" class="muted">${msg}</td></tr>`;
      return;
    }
    body.innerHTML = rows
      .map((row) => {
        const code = esc(row.code || "");
        return `<tr class="is-row" data-code="${code}" tabindex="0">
          <td class="mono">${code}</td>
          <td>${esc(row.name || "—")}</td>
          <td class="num">${esc(fmtMd(row.beg))}</td>
          <td class="num">${esc(fmtMd(row.end))}</td>
          <td class="num">${esc(row.count ?? "—")}</td>
          <td class="stock-path-cell">${fmtPathCell(row.stock_path)}</td>
          <td class="stock-path-cell">${fmtPathCell(row.index_path)}</td>
          <td class="num">${esc(fmtNum(row.divergence, 1))}</td>
          <td class="num">${esc(fmtNum(row.low_score, 1))}</td>
          <td class="num">${esc(fmtMd(row.low_date))}</td>
        </tr>`;
      })
      .join("");
  }

  function sortedSelectItems() {
    const key = select.sortKey;
    const dir = select.sortDir === "asc" ? 1 : -1;
    const rows = [...(select.items || [])];
    rows.sort((a, b) => {
      const av = a?.[key];
      const bv = b?.[key];
      const aNil = av == null || av === "";
      const bNil = bv == null || bv === "";
      if (aNil && bNil) return String(a?.code || "").localeCompare(String(b?.code || ""));
      if (aNil) return 1;
      if (bNil) return -1;
      if (typeof av === "number" || typeof bv === "number") {
        const an = Number(av);
        const bn = Number(bv);
        if (Number.isFinite(an) && Number.isFinite(bn) && an !== bn) return (an - bn) * dir;
      }
      const cmp = String(av).localeCompare(String(bv), "zh-CN");
      if (cmp) return cmp * dir;
      return String(a?.code || "").localeCompare(String(b?.code || ""));
    });
    return rows;
  }

  function renderSelectSortHeaders() {
    const table = $("selectTable");
    if (!table) return;
    table.querySelectorAll("th[data-sort]").forEach((th) => {
      const key = th.dataset.sort;
      const active = key === select.sortKey;
      th.classList.toggle("is-sorted", active);
      th.dataset.order = active ? select.sortDir : "";
      const base = SELECT_SORT_LABELS[key] || key;
      th.textContent = active ? `${base}${select.sortDir === "asc" ? " ↑" : " ↓"}` : base;
    });
  }

  function renderSelectSummary() {
    const sortLabel = SELECT_SORT_LABELS[select.sortKey] || select.sortKey;
    const orderLabel = select.sortDir === "asc" ? "升序" : "降序";
    $("summaryBar").innerHTML = `
      <span>已分析 <b>${select.analyzedCount || 0}</b> / ${select.candidateCount || 0}</span>
      <span>命中 <b>${select.foundCount || 0}</b></span>
      <span>失败 <b>${select.errorCount || 0}</b></span>
      <span>排序 <b>${esc(sortLabel)} · ${orderLabel}</b></span>
      <span>排除 <b>创业/科创/ST/退市</b></span>
    `;
    $("marketMeta").textContent = select.message || select.updatedAt || "";
  }

  function fmtDays(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return String(Math.round(n));
  }

  function renderSelectTable() {
    const body = $("selectBody");
    const hint = $("selectHint");
    if (!body) return;
    renderSelectSortHeaders();
    const rows = sortedSelectItems();
    if (hint) {
      hint.textContent = rows.length
        ? `${rows.length} 只 · ${SELECT_SORT_LABELS[select.sortKey] || select.sortKey}${select.sortDir === "asc" ? "↑" : "↓"}`
        : select.started
          ? "暂无命中"
          : "";
    }
    if (!rows.length) {
      const msg = select.error
        ? esc(select.error)
        : select.status === "running"
          ? esc(select.message || "正在分析…")
          : select.started
            ? "暂无有效回溯结果"
            : "点击「重新分析」开始全市场扫描";
      body.innerHTML = `<tr><td colspan="10" class="muted">${msg}</td></tr>`;
      return;
    }
    body.innerHTML = rows
      .map((row) => {
        const code = esc(row.code || "");
        return `<tr class="is-row" data-code="${code}" tabindex="0">
          <td class="mono">${code}</td>
          <td>${esc(row.name || "—")}</td>
          <td class="num">${esc(fmtMd(row.date))}</td>
          <td class="num">${esc(fmtNum(row.close_price, 2))}</td>
          <td class="num">${esc(fmtNum(row.low_price, 2))}</td>
          <td class="num">${esc(fmtDays(row.close_days))}</td>
          <td class="num">${esc(fmtDays(row.low_days))}</td>
          <td class="num">${esc(fmtDays(row.gap))}</td>
          <td class="num">${esc(fmtMd(row.close_since))}</td>
          <td class="num">${esc(fmtMd(row.low_since))}</td>
        </tr>`;
      })
      .join("");
  }

  function renderAll() {
    renderSeg();
    if (view === "limit") {
      renderLimitSummary();
      renderDayRail();
      renderDayHead(selectedLimitDay());
      renderLimitCards();
      window.OrbitPrefetch?.intent({ stocks: resultItems() });
      return;
    }
    if (view === "industry") {
      renderIndustrySummary();
      renderRotDays();
      renderIndustryHead(selectedIndustryDay());
      renderIndustry();
      return;
    }
    if (view === "stock") {
      renderStockSummary();
      renderStockTable();
      return;
    }
    if (view === "select") {
      renderSelectSummary();
      renderSelectTable();
    }
  }

  function applyLimitData(data) {
    limit.dayRows = data.days || [];
    if (!limit.dayRows.some((d) => d.date === limit.selectedDate)) {
      limit.selectedDate = (limit.dayRows[0] && limit.dayRows[0].date) || "";
    }
    limit.updatedAt = data.updated_at || "";
    limit.candidateCount = data.candidate_count || 0;
    limit.resultCount = data.result_count || 0;
    limit.analyzedCount = data.analyzed_count || data.result_count || 0;
    if (view === "limit") renderAll();
  }

  function applyIndustryData(data) {
    industry.dayRows = data.days || [];
    if (!industry.dayRows.some((d) => d.date === industry.selectedDate)) {
      industry.selectedDate = (industry.dayRows[0] && industry.dayRows[0].date) || "";
    }
    industry.untouched = data.untouched || [];
    industry.ranking = data.ranking || data.covered || [];
    industry.universe = data.universe_count || 0;
    industry.coveredCount = data.covered_count || 0;
    industry.untouchedCount = data.untouched_count || industry.untouched.length;
    industry.note = data.note || "";
    industry.updatedAt = data.updated_at || "";
    industry.errors = data.errors || [];
    industry.error = industry.errors.join("；");
    if (view === "industry") renderAll();
  }

  function applyPayload(st, payload, applyData) {
    st.status = payload.status || "idle";
    const progress = payload.progress || {};
    if (progress.total) {
      st.candidateCount = progress.total;
      st.analyzedCount = progress.done || 0;
    }

    if (payload.status === "done" && payload.data) {
      st.error = "";
      st.message = "";
      applyData(payload.data);
      if (st === current()) {
        showLoading(false);
        showError(st.error || "");
        setLive("live");
      }
      return;
    }

    if (payload.status === "error") {
      st.error = payload.error || "分析失败";
      st.message = "";
      if (st === current()) {
        showLoading(false);
        showError(st.error);
        setLive("idle");
      }
      return;
    }

    if (payload.status === "running") {
      if (payload.data) applyData(payload.data);
      const elapsed = payload.elapsed_sec ? ` · ${fmtNum(payload.elapsed_sec, 0)}s` : "";
      st.message = `${payload.message || "正在分析…"}${elapsed}`;
      st.error = "";
      if (st === current()) {
        const partialIndustry =
          view === "industry" && (industry.dayRows || []).length > 0;
        const partialStock =
          view === "stock" && (stock.items || []).length > 0;
        const partialSelect =
          view === "select" && (select.items || []).length > 0;
        const partial = partialIndustry || partialStock || partialSelect;
        showLoading(!partial, st.message);
        setLive(partial ? "live" : "busy");
        if (partial) {
          $("marketMeta").textContent = st.message;
        }
      }
    }
  }

  function stopPoll(st) {
    if (st.pollTimer) {
      clearTimeout(st.pollTimer);
      st.pollTimer = 0;
    }
  }

  function schedulePoll(st, loader) {
    stopPoll(st);
    st.pollTimer = setTimeout(() => loader(false), POLL_MS);
  }

  async function loadLimit(force) {
    if (limit.fetching && !force) return;
    limit.fetching = true;
    limit.started = true;
    limit.error = "";
    if (view === "limit") showError("");
    if (force) {
      limit.dayRows = [];
      limit.resultCount = 0;
      limit.analyzedCount = 0;
      limit.selectedDate = "";
      if (view === "limit") renderAll();
      limit.message = "正在拉取涨停池…";
      if (view === "limit") {
        showLoading(true, limit.message);
        setLive("busy");
      }
    }

    const qs = new URLSearchParams({
      days: String(limit.days),
      top: String(limit.top),
      refresh: force ? "1" : "0",
    });

    try {
      const res = await fetch(`/api/screen/decline?${qs}`);
      const json = await res.json();
      if (!json.ok) {
        throw new Error(json.error || "请求失败");
      }
      applyPayload(limit, json.data || {}, applyLimitData);
      if (limit.status === "running") schedulePoll(limit, loadLimit);
      else stopPoll(limit);
    } catch (err) {
      limit.error = err.message || String(err);
      limit.status = "error";
      if (view === "limit") {
        showLoading(false);
        showError(limit.error);
        setLive("idle");
      }
      stopPoll(limit);
    } finally {
      limit.fetching = false;
    }
  }


  async function loadIndustry(force) {
    if (industry.fetching && !force) return;
    industry.fetching = true;
    industry.started = true;
    industry.error = "";
    if (view === "industry") showError("");
    if (force) {
      industry.dayRows = [];
      industry.untouched = [];
      industry.ranking = [];
      industry.coveredCount = 0;
      industry.untouchedCount = 0;
      industry.selectedDate = "";
      if (view === "industry") renderAll();
      industry.message = "正在统计每天哪些三级轮到了…";
      if (view === "industry") {
        showLoading(true, industry.message);
        setLive("busy");
      }
    }

    const qs = new URLSearchParams({
      days: String(industry.days),
      refresh: force ? "1" : "0",
    });

    try {
      const res = await fetch(`/api/screen/rotation?${qs}`, { cache: "no-store" });
      const json = await res.json();
      if (!json.ok) {
        throw new Error(json.error || "请求失败");
      }
      applyPayload(industry, json.data || {}, applyIndustryData);
      if (industry.status === "running") schedulePoll(industry, loadIndustry);
      else stopPoll(industry);
    } catch (err) {
      industry.error = err.message || String(err);
      industry.status = "error";
      if (view === "industry") {
        showLoading(false);
        showError(industry.error);
        setLive("idle");
      }
      stopPoll(industry);
    } finally {
      industry.fetching = false;
    }
  }

  function applyStockData(data) {
    stock.items = Array.isArray(data.items) ? data.items : [];
    stock.candidateCount = data.candidate_count || 0;
    stock.analyzedCount = data.analyzed_count || 0;
    stock.foundCount = data.found_count || stock.items.length;
    stock.errorCount = data.error_count || 0;
    stock.updatedAt = data.updated_at || "";
    stock.params = data.params || null;
    if (view === "stock") renderAll();
  }

  async function loadStock(force) {
    if (stock.fetching && !force) return;
    stock.fetching = true;
    stock.started = true;
    stock.error = "";
    if (view === "stock") showError("");
    if (force) {
      stock.items = [];
      stock.analyzedCount = 0;
      stock.foundCount = 0;
      stock.errorCount = 0;
      if (view === "stock") renderAll();
      stock.message = "正在加载股票索引…";
      if (view === "stock") {
        showLoading(true, stock.message);
        setLive("busy");
      }
    }

    const qs = new URLSearchParams({
      band: String(stock.band),
      index: stock.index,
      factor: stock.factor,
      refresh: force ? "1" : "0",
    });

    try {
      const res = await fetch(`/api/screen/evaluate?${qs}`, { cache: "no-store" });
      const json = await res.json();
      if (!json.ok) {
        throw new Error(json.error || "请求失败");
      }
      applyPayload(stock, json.data || {}, applyStockData);
      if (stock.status === "running") schedulePoll(stock, loadStock);
      else stopPoll(stock);
    } catch (err) {
      stock.error = err.message || String(err);
      stock.status = "error";
      if (view === "stock") {
        showLoading(false);
        showError(stock.error);
        setLive("idle");
      }
      stopPoll(stock);
    } finally {
      stock.fetching = false;
    }
  }

  function applySelectData(data) {
    select.items = Array.isArray(data.items) ? data.items : [];
    select.candidateCount = data.candidate_count || 0;
    select.analyzedCount = data.analyzed_count || 0;
    select.foundCount = data.found_count || select.items.length;
    select.errorCount = data.error_count || 0;
    select.updatedAt = data.updated_at || "";
    select.params = data.params || null;
    if (view === "select") renderAll();
  }

  async function loadSelect(force) {
    if (select.fetching && !force) return;
    select.fetching = true;
    select.started = true;
    select.error = "";
    if (view === "select") showError("");
    if (force) {
      select.items = [];
      select.analyzedCount = 0;
      select.foundCount = 0;
      select.errorCount = 0;
      if (view === "select") renderAll();
      select.message = "正在加载股票索引…";
      if (view === "select") {
        showLoading(true, select.message);
        setLive("busy");
      }
    }

    const qs = new URLSearchParams({
      adjust: select.adjust || "qfq",
      refresh: force ? "1" : "0",
    });

    try {
      const res = await fetch(`/api/screen/recent-low?${qs}`, { cache: "no-store" });
      const json = await res.json();
      if (!json.ok) {
        throw new Error(json.error || "请求失败");
      }
      applyPayload(select, json.data || {}, applySelectData);
      if (select.status === "running") schedulePoll(select, loadSelect);
      else stopPoll(select);
    } catch (err) {
      select.error = err.message || String(err);
      select.status = "error";
      if (view === "select") {
        showLoading(false);
        showError(select.error);
        setLive("idle");
      }
      stopPoll(select);
    } finally {
      select.fetching = false;
    }
  }

  function load(force) {
    if (view === "limit") return loadLimit(force);
    if (view === "industry") return loadIndustry(force);
    if (view === "stock") return loadStock(force);
    if (view === "select") return loadSelect(force);
  }

  function openCompany(code) {
    if (!code) return;
    window.location.href = fromHref(code);
  }

  function resetList() {
    const list = $("resultList");
    list.innerHTML = `<p class="screen-empty muted">加载中…</p>`;
    list.dataset.date = "";
  }

  function switchView(next) {
    if (next !== "limit" && next !== "industry" && next !== "stock" && next !== "select") {
      return;
    }
    if (next === view) return;
    stopPoll(current());
    view = next;
    resetList();
    applyChrome();
    renderAll();
    syncStatusUi();
    const st = current();
    if (!st.started) load(false);
    else if (st.status === "running") load(false);
  }

  function bindListGestures(list) {
    let swipe = null;
    const canScrollX = () => list.scrollWidth > list.clientWidth + 1;

    list.addEventListener(
      "wheel",
      (ev) => {
        if (document.body.dataset.screenMode === "industry") return;
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
        if (document.body.dataset.screenMode === "industry") return;
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

    list.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      const card = ev.target.closest("article.is-stock[data-code]");
      if (!card) return;
      ev.preventDefault();
      openCompany(card.dataset.code);
    });
  }

  function bindEvents() {
    $("viewSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-view]");
      if (!btn) return;
      switchView(btn.dataset.view);
    });

    $("refreshBtn").addEventListener("click", () => {
      load(true);
    });

    $("limitDaysSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-days]");
      if (!btn) return;
      const days = Number(btn.dataset.days);
      if (days === limit.days) return;
      limit.days = days;
      renderSeg();
      if (view === "limit") loadLimit(false);
    });

    $("limitTopSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-top]");
      if (!btn) return;
      const top = Number(btn.dataset.top);
      if (top === limit.top) return;
      limit.top = top;
      renderSeg();
      if (view === "limit") loadLimit(false);
    });

    $("industryDaysSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-days]");
      if (!btn) return;
      const days = Number(btn.dataset.days);
      if (days === industry.days) return;
      industry.days = days;
      renderSeg();
      if (view === "industry") loadIndustry(true);
    });

    $("stockBandSeg")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-band]");
      if (!btn) return;
      const band = Number(btn.dataset.band);
      if (!Number.isFinite(band) || band === stock.band) return;
      stock.band = band;
      renderSeg();
      syncUrl();
      if (view === "stock") renderStockSummary();
    });

    $("stockIndexSeg")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-index]");
      if (!btn) return;
      const index = String(btn.dataset.index || "");
      if (!index || index === stock.index) return;
      stock.index = index;
      renderSeg();
      syncUrl();
      if (view === "stock") renderStockSummary();
    });

    $("stockEvalTable")?.addEventListener("click", (ev) => {
      const th = ev.target.closest("th[data-sort]");
      if (th && $("stockEvalTable").contains(th)) {
        const key = parseSortKey(th.dataset.sort);
        if (key === stock.sortKey) {
          stock.sortDir = stock.sortDir === "asc" ? "desc" : "asc";
        } else {
          stock.sortKey = key;
          stock.sortDir =
            key === "code" ||
            key === "name" ||
            key === "beg" ||
            key === "end" ||
            key === "low_date" ||
            key === "stock_path" ||
            key === "index_path"
              ? "asc"
              : "desc";
        }
        syncUrl();
        if (view === "stock") renderStockTable();
        renderStockSummary();
        return;
      }
      const row = ev.target.closest("tr.is-row[data-code]");
      if (row) openCompany(row.dataset.code);
    });

    $("stockEvalBody")?.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      const row = ev.target.closest("tr.is-row[data-code]");
      if (!row) return;
      ev.preventDefault();
      openCompany(row.dataset.code);
    });

    $("selectTable")?.addEventListener("click", (ev) => {
      const th = ev.target.closest("th[data-sort]");
      if (th && $("selectTable").contains(th)) {
        const key = parseSelectSortKey(th.dataset.sort);
        if (key === select.sortKey) {
          select.sortDir = select.sortDir === "asc" ? "desc" : "asc";
        } else {
          select.sortKey = key;
          select.sortDir =
            key === "code" ||
            key === "name" ||
            key === "date" ||
            key === "close_since" ||
            key === "low_since" ||
            key === "gap"
              ? "asc"
              : "desc";
        }
        syncUrl();
        if (view === "select") renderSelectTable();
        renderSelectSummary();
        return;
      }
      const row = ev.target.closest("tr.is-row[data-code]");
      if (row) openCompany(row.dataset.code);
    });

    $("selectBody")?.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      const row = ev.target.closest("tr.is-row[data-code]");
      if (!row) return;
      ev.preventDefault();
      openCompany(row.dataset.code);
    });

    function openIndustry(row) {
      const l1 = row.dataset.l1 || "";
      const l2 = row.dataset.l2 || "";
      const l3 = row.dataset.code || "";
      const qs = new URLSearchParams();
      if (l1) qs.set("l1", l1);
      if (l2) qs.set("l2", l2);
      if (l3) qs.set("l3", l3);
      const suffix = qs.toString();
      window.location.href = suffix ? `/market?${suffix}` : "/market";
    }

    function onIndustryRowClick(ev) {
      const row = ev.target.closest("tr.is-row[data-code]");
      if (row) openIndustry(row);
    }

    $("indWaitBody").addEventListener("click", onIndustryRowClick);
    $("indAgainBody").addEventListener("click", onIndustryRowClick);
    $("indRankBody").addEventListener("click", onIndustryRowClick);

    $("rotDayRail").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-date]");
      if (!btn) return;
      const date = btn.dataset.date;
      if (!date || date === industry.selectedDate) return;
      industry.selectedDate = date;
      if (view === "industry") renderAll();
    });

    $("dayRail").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-date]");
      if (!btn) return;
      const date = btn.dataset.date;
      if (!date) return;
      if (date === limit.selectedDate) return;
      limit.selectedDate = date;
      if (view === "limit") renderAll();
    });

    bindListGestures($("resultList"));
  }

  function initialView() {
    const params = new URLSearchParams(location.search);
    const fromQuery = parseView(params.get("view") || params.get("mode"));
    if (fromQuery) return fromQuery;
    try {
      const saved = parseView(sessionStorage.getItem(VIEW_KEY));
      if (saved) return saved;
    } catch {
      /* ignore */
    }
    return "industry";
  }

  function hydrateStockParams() {
    const params = new URLSearchParams(location.search);
    const band = Number(params.get("band"));
    if ([0.05, 0.09, 0.12].includes(band)) stock.band = band;
    const index = String(params.get("index") || "");
    if (STOCK_INDEX_CODES.includes(index)) stock.index = index;
    stock.factor = "close";
    stock.sortKey = parseSortKey(params.get("sort"));
    stock.sortDir = parseSortDir(params.get("order"));
  }

  function hydrateSelectParams() {
    const params = new URLSearchParams(location.search);
    const adjust = String(params.get("adjust") || "").toLowerCase();
    if (["qfq", "hfq", "none"].includes(adjust)) select.adjust = adjust;
    select.sortKey = parseSelectSortKey(params.get("sort"));
    const order = params.get("order");
    if (order) {
      select.sortDir = parseSortDir(order);
    } else {
      select.sortDir = select.sortKey === "gap" ? "asc" : "desc";
    }
  }

  view = initialView();
  hydrateStockParams();
  hydrateSelectParams();
  applyChrome();
  bindEvents();
  window.OrbitPrefetch?.bindHover($("resultList"), "article.is-stock[data-code]");
  window.OrbitPrefetch?.boot("analysis");
  load(false);
})();
