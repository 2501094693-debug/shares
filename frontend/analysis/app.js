(() => {
  const POLL_MS = 1200;
  const WEEK = "日一二三四五六";
  const VIEW_KEY = "orbit-judgment-view";
  const VIEW_META = {
    limit: {
      title: "ORBIT · 研判",
      sub: "按每日涨停池分批排名：阴跌 → 横盘 → 涨停，软评分排序并附日 K",
      from: "screen",
    },
    stock: {
      title: "ORBIT · 研判",
      sub: "全市场软评分：找出仍在阴跌或横盘的股票，无硬门槛，按分排序",
      from: "analysis",
    },
    industry: {
      title: "ORBIT · 研判",
      sub: "按交易日复盘申万三级行业轮动：上涨为当天上榜（含首次），待涨为窗口内尚未轮到，不随交易日切换；领涨按上榜次数排序。点击行业进入行情树",
      from: "analysis",
    },
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

  const stock = {
    kind: "all",
    days: 60,
    top: 50,
    code: "",
    status: "idle",
    items: [],
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
    days: 245,
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
    if (["stock", "grind", "analysis", "gx"].includes(value)) return "stock";
    if (["industry", "rotation", "rot", "l3", "hy"].includes(value)) return "industry";
    return "";
  }

  function current() {
    if (view === "stock") return stock;
    if (view === "industry") return industry;
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

  function readCode() {
    const raw = String($("codeInput")?.value || "").trim();
    const digits = raw.replace(/\D/g, "");
    if (digits.length >= 6) return digits.slice(-6);
    return "";
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
    if (view === "stock" && stock.code) url.searchParams.set("code", stock.code);
    else url.searchParams.delete("code");
    history.replaceState({}, "", url);
  }

  function applyChrome() {
    const meta = VIEW_META[view];
    document.title = meta.title;
    $("pageSub").textContent = meta.sub;
    document.body.dataset.screenMode = view;
    document.body.classList.toggle("analysis-page-root", view === "stock");
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
    markSeg("stockDaysSeg", "days", stock.days);
    markSeg("stockTopSeg", "top", stock.top);
    markSeg("kindSeg", "kind", stock.kind);
    markSeg("industryDaysSeg", "days", industry.days);
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

  function renderStockSummary() {
    $("summaryBar").innerHTML = `
      <span>已分析 <b>${stock.analyzedCount || 0}</b> / ${stock.candidateCount || 0}</span>
      <span>展示 <b>${(stock.items || []).length}</b></span>
      <span>窗口 <b>${stock.days}</b> 交易日</span>
    `;
    $("marketMeta").textContent = stock.updatedAt || "";
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

  function renderIndustrySummary() {
    const coveredN = industry.coveredCount || 0;
    const leftN = industry.untouchedCount || (industry.untouched || []).length;
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
    const waitN = (industry.untouched || []).length;
    const againN = risenList(day).length;
    const rankN = (industry.ranking || []).length;
    const when = day ? `${fmtMd(day.date)} ${weekday(day.date)}` : "";
    const waitHint = $("rotWaitHint");
    const againHint = $("rotAgainHint");
    const rankHint = $("indRankHint");
    if (waitHint) waitHint.textContent = waitN ? `${waitN}` : "";
    if (againHint) againHint.textContent = day ? `${when} · ${againN}` : "";
    if (rankHint) rankHint.textContent = rankN ? `${rankN} 个` : "";
  }

  function kindTitle() {
    if (stock.kind === "decline") return "阴跌";
    if (stock.kind === "consolidation") return "横盘";
    return "阴跌 / 横盘";
  }

  function renderStockHead() {
    const scope = stock.code ? `代码 ${stock.code}` : "全市场软评分";
    $("dayHead").innerHTML = `
      <div>
        <h2>${esc(kindTitle())}</h2>
        <p>${esc(scope)} · 已分析 <b>${stock.analyzedCount || 0}</b> · 展示 <b>${(stock.items || []).length}</b></p>
      </div>
    `;
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

  function waitList() {
    return (industry.untouched || []).map((row) => ({
      ...row,
      tag: row.tag || "待涨",
    }));
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
    const wait = waitList();
    const again = risenList(day);
    const ranking = industry.ranking || [];
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

  function grindCardHtml(row) {
    const detected = row.detected || {};
    const dec = detected.decline || {};
    const cons = detected.consolidation || {};
    const windowStats = detected.window || {};
    const scores = row.scores || {};
    const industry = [row.l1_name, row.l2_name, row.l3_name].filter(Boolean).join(" / ");
    const err = row.error ? `<span class="screen-card-error">${esc(row.error)}</span>` : "";
    const href = fromHref(row.code || "");
    return `<article class="screen-card is-stock" data-code="${esc(row.code || "")}" data-key="${esc(row.code || "")}" tabindex="0">
      <a class="screen-card-head" href="${esc(href)}" title="打开公司详情">
        <span class="screen-rank">${row.rank || ""}</span>
        <div class="screen-card-name">
          <strong>${esc(row.name || "")}</strong>
          <span>${esc(row.code || "")}</span>
          ${industry ? `<em>${esc(industry)}</em>` : ""}
        </div>
        <div class="screen-card-score">
          <b>${fmtNum(scores.total, 1)}</b>
          <span>${esc(row.kind_label || "—")}</span>
        </div>
      </a>
      ${klineBlock(row.code || "")}
      <footer class="screen-card-meta">
        <span>阴跌 <b>${dec.days ?? "—"}</b>天 <b data-tone="${tone(dec.total_pct)}">${fmtPct(dec.total_pct)}</b></span>
        <span>横盘 <b>${cons.days ?? "—"}</b>天 幅 <b>${fmtNum(cons.range_pct, 1)}</b>%</span>
        <span>窗口 <b data-tone="${tone(windowStats.total_pct)}">${fmtPct(windowStats.total_pct)}</b></span>
        ${scoreChip("阴跌", scores.decline)}
        ${scoreChip("横盘", scores.consolidation)}
        ${scoreChip("阴跌时长", scores.decline_duration)}
        ${scoreChip("阴跌质量", scores.decline_quality)}
        ${scoreChip("横盘时长", scores.consolidation_duration)}
        ${scoreChip("横盘质量", scores.consolidation_quality)}
        ${scoreChip("持续", scores.persistence)}
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

  function patchStockCard(el, row) {
    patchLimitCard(el, row);
    const badge = el.querySelector(".screen-card-score span");
    if (badge) badge.textContent = row.kind_label || "—";
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

  function renderStockCards() {
    const viewKey = `${stock.kind}:${stock.code || "-"}`;
    renderCards(
      stock.items || [],
      (row) => String(row.code || ""),
      grindCardHtml,
      patchStockCard,
      emptyHint(stock, "暂无结果"),
      viewKey,
    );
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
    renderStockSummary();
    renderStockHead();
    renderStockCards();
    window.OrbitPrefetch?.intent({ stocks: stock.items });
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

  function applyStockData(data) {
    stock.items = data.items || [];
    stock.updatedAt = data.updated_at || "";
    stock.candidateCount = data.candidate_count || 0;
    stock.resultCount = data.result_count || 0;
    stock.analyzedCount = data.analyzed_count || data.result_count || 0;
    if (view === "stock") renderAll();
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
        showLoading(true, st.message);
        setLive("busy");
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

  async function loadStock(force) {
    if (stock.fetching && !force) return;
    stock.fetching = true;
    stock.started = true;
    stock.error = "";
    if (view === "stock") showError("");
    if (force) {
      stock.items = [];
      stock.resultCount = 0;
      stock.analyzedCount = 0;
      if (view === "stock") renderAll();
      stock.message = stock.code ? `正在分析 ${stock.code}…` : "正在准备股票池…";
      if (view === "stock") {
        showLoading(true, stock.message);
        setLive("busy");
      }
    }

    const qs = new URLSearchParams({
      days: String(stock.days),
      top: String(stock.top),
      kind: stock.kind,
      refresh: force ? "1" : "0",
    });
    if (stock.code) qs.set("code", stock.code);

    try {
      const res = await fetch(`/api/screen/grind?${qs}`);
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

  function load(force) {
    if (view === "limit") return loadLimit(force);
    if (view === "industry") return loadIndustry(force);
    return loadStock(force);
  }

  function openCompany(code) {
    if (!code) return;
    window.location.href = fromHref(code);
  }

  function submitCode(force) {
    const next = readCode();
    if (next === stock.code && !force) return;
    stopPoll(stock);
    stock.code = next;
    if (view === "stock") syncUrl();
    loadStock(true);
  }

  function resetList() {
    const list = $("resultList");
    list.innerHTML = `<p class="screen-empty muted">加载中…</p>`;
    list.dataset.date = "";
  }

  function switchView(next) {
    if (next !== "limit" && next !== "stock" && next !== "industry") return;
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
      if (view === "stock") stock.code = readCode();
      load(true);
    });

    $("codeInput").addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter") return;
      ev.preventDefault();
      if (view !== "stock") return;
      submitCode(true);
    });
    $("codeInput").addEventListener("change", () => {
      if (view !== "stock") return;
      submitCode(false);
    });

    $("kindSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-kind]");
      if (!btn) return;
      const kind = btn.dataset.kind;
      if (kind === stock.kind) return;
      stock.kind = kind;
      renderSeg();
      if (view === "stock") loadStock(false);
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

    $("stockDaysSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-days]");
      if (!btn) return;
      const days = Number(btn.dataset.days);
      if (days === stock.days) return;
      stock.days = days;
      renderSeg();
      if (view === "stock") loadStock(true);
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

    $("stockTopSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-top]");
      if (!btn) return;
      const top = Number(btn.dataset.top);
      if (top === stock.top) return;
      stock.top = top;
      renderSeg();
      if (view === "stock") loadStock(false);
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
      if (!date || date === limit.selectedDate) return;
      limit.selectedDate = date;
      if (view === "limit") renderAll();
    });

    bindListGestures($("resultList"));
  }

  function initialView() {
    const params = new URLSearchParams(location.search);
    const fromQuery = parseView(params.get("view") || params.get("mode"));
    if (fromQuery) return fromQuery;
    const startCode = String(params.get("code") || "").replace(/\D/g, "").slice(-6);
    if (startCode.length === 6) return "stock";
    try {
      const saved = parseView(sessionStorage.getItem(VIEW_KEY));
      if (saved) return saved;
    } catch {
      /* ignore */
    }
    return "industry";
  }

  const params = new URLSearchParams(location.search);
  const startCode = String(params.get("code") || "").replace(/\D/g, "").slice(-6);
  if (startCode.length === 6) {
    stock.code = startCode;
    $("codeInput").value = startCode;
  }

  view = initialView();
  applyChrome();
  bindEvents();
  window.OrbitPrefetch?.bindHover($("resultList"), "article.is-stock[data-code]");
  window.OrbitPrefetch?.boot("analysis");
  load(false);
})();
