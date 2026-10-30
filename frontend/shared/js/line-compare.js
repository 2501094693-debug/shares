(() => {
  const DEFAULT_INDEX = "000300";
  const PANE_DEFAULT_INDEX = "000001";
  const FACTOR_ORDER = ["open", "high", "low", "close"];
  const FACTOR_FALLBACK = {
    open: "开盘涨跌幅",
    high: "最大涨幅",
    low: "最大跌幅",
    close: "收盘涨跌幅",
  };
  const DIR_TONE = {
    同涨: "same-up",
    同跌: "same-down",
    股涨指跌: "stock-up",
    股跌指涨: "stock-down",
  };
  /** 方向四色：深绿 / 浅绿 / 浅红 / 深红 */
  const DIR_BAR_COLORS = {
    股跌指涨: "#0f7a4a", // 深绿
    同跌: "#3dd68c", // 浅绿
    同涨: "#ff8a95", // 浅红
    股涨指跌: "#d62839", // 深红
  };
  const DIR_BAR_DIM = {
    股跌指涨: "rgba(15, 122, 74, 0.38)",
    同跌: "rgba(61, 214, 140, 0.38)",
    同涨: "rgba(255, 138, 149, 0.38)",
    股涨指跌: "rgba(214, 40, 57, 0.38)",
  };

  const state = {
    visible: false,
    code: "",
    name: "",
    indices: [],
    factors: [],
    selected: new Set([DEFAULT_INDEX]),
    activeIndex: "",
    activeFactor: "close",
    pack: null,
    loading: false,
    metaLoaded: false,
    chart: null,
    abort: null,
    bound: false,
  };

  /** 四价相对基准收盘的波动统计（个股 + 指数） */
  function emptyUndulateSlot() {
    return { key: "", loading: false, error: "", pack: null, abort: null };
  }
  const undulate = {
    stock: emptyUndulateSlot(),
    index: emptyUndulateSlot(),
    rangeBeg: "",
    rangeEnd: "",
  };

  /** 某交易日四价「前低」回溯 */
  const extremum = {
    key: "",
    date: "",
    loading: false,
    error: "",
    pack: null,
    abort: null,
  };

  /** 区间四价极值位置百分比 */
  const position = {
    key: "",
    beg: "",
    end: "",
    loading: false,
    error: "",
    pack: null,
    abort: null,
  };

  /** 聪明投机者：首日低买，其后每日高卖低买 → 期末股数 / 均价 */
  const trader = {
    key: "",
    beg: "",
    end: "",
    loading: false,
    error: "",
    pack: null,
    abort: null,
  };
  let traderHeadObserver = null;

  const pane = {
    index: PANE_DEFAULT_INDEX,
    indexName: "上证指数",
    factor: "close",
    code: "",
    beg: "",
    end: "",
    loading: false,
    error: "",
    daysByDate: new Map(),
    abort: null,
  };

  function cssVar(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  function chartColors() {
    return {
      muted: cssVar("--muted", "#8494a8"),
      ink: cssVar("--ink", "#e8eef7"),
      grid: "rgba(42, 212, 184, 0.08)",
      zero: "rgba(132, 148, 168, 0.55)",
      hoverBg: "rgba(232, 238, 247, 0.06)",
    };
  }

  function dirBarColor(dir, { active = true } = {}) {
    const key = String(dir || "");
    if (active) return DIR_BAR_COLORS[key] || cssVar("--muted", "#8494a8");
    return DIR_BAR_DIM[key] || "rgba(132, 148, 168, 0.35)";
  }

  function $(id) {
    return document.getElementById(id);
  }

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtPct(n, digits = 2) {
    if (n == null || !Number.isFinite(Number(n))) return "—";
    const v = Number(n) * 100;
    const sign = v > 0 ? "+" : "";
    return `${sign}${v.toFixed(digits)}%`;
  }

  function fmtScore(n) {
    if (n == null || !Number.isFinite(Number(n))) return "—";
    return Number(n).toFixed(2);
  }

  function toDateInput(value) {
    const s = String(value || "").replace(/-/g, "");
    if (/^\d{8}$/.test(s)) return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
    if (/^\d{4}-\d{2}-\d{2}/.test(String(value || ""))) return String(value).slice(0, 10);
    return "";
  }

  function todayStr() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function shiftDays(base, days) {
    const d = new Date(`${base}T12:00:00`);
    d.setDate(d.getDate() + days);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function yearStart(base = todayStr()) {
    return `${base.slice(0, 4)}-01-01`;
  }

  function factorLabel(key) {
    const hit = (state.factors || []).find((f) => f.key === key);
    return (hit && hit.label) || FACTOR_FALLBACK[key] || key;
  }

  function showFormError(msg) {
    const el = $("lcFormError");
    if (!el) return;
    if (!msg) {
      el.textContent = "";
      el.classList.add("hidden");
      return;
    }
    el.textContent = msg;
    el.classList.remove("hidden");
  }

  function setFormMeta(text) {
    const el = $("lcFormMeta");
    if (el) el.textContent = text || "";
  }

  function setResultMeta(_text) {
    /* 精简侧栏已无独立 meta */
  }

  function syncRangeDisplay(beg, end) {
    const b = toDateInput(beg) || String($("lcBeg")?.value || "").trim() || "";
    const e = toDateInput(end) || String($("lcEnd")?.value || "").trim() || "";
    undulate.rangeBeg = b;
    undulate.rangeEnd = e;
    /* 区间文案由 renderUndulateStats 写入 lcUndulateMeta */
    if (undulate.stock.pack || undulate.index.pack || b) renderUndulateStats();
  }

  function setRangeValues(beg, end) {
    const b = toDateInput(beg);
    const e = toDateInput(end) || b;
    if ($("lcBeg")) $("lcBeg").value = b || "";
    if ($("lcEnd")) $("lcEnd").value = e || "";
    syncRangeDisplay(b, e);
    // 通知 K 线极值重新计算
    const lcBegEl = $("lcBeg");
    if (lcBegEl) lcBegEl.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function ensureDefaults() {
    syncRangeDisplay($("lcBeg")?.value, $("lcEnd")?.value);
  }

  function visibleWindowRange() {
    const range = window.CompanyLcKline?.visibleWindowRange?.();
    if (!range?.beg || !range?.end) return null;
    return { beg: toDateInput(range.beg), end: toDateInput(range.end) };
  }

  function selectedIndices() {
    return [...state.selected];
  }

  function renderIndexList() {
    const box = $("lcIndexList");
    if (!box) return;
    const list = state.indices || [];
    if (!list.length) {
      box.innerHTML = `<p class="muted">指数目录加载中…</p>`;
      return;
    }
    if (!state.selected.size) {
      const prefer = list.find((x) => x.code === DEFAULT_INDEX) || list[0];
      if (prefer) state.selected.add(prefer.code);
    }
    box.innerHTML = list
      .map((item) => {
        const code = String(item.code || "");
        const checked = state.selected.has(code) ? " checked" : "";
        return `<label class="line-compare-index-item">
          <input type="checkbox" value="${esc(code)}"${checked} />
          <span class="line-compare-index-name">${esc(item.name || code)}</span>
          <span class="line-compare-index-code muted">${esc(code)}</span>
        </label>`;
      })
      .join("");
  }

  function fillPaneIndexSelect() {
    const sel = $("lcCompareIndexSelect");
    if (!sel) return;
    const list = state.indices || [];
    if (!list.length) {
      if (![...sel.options].some((o) => o.value === PANE_DEFAULT_INDEX)) {
        sel.innerHTML = `<option value="${PANE_DEFAULT_INDEX}" selected>上证指数</option>`;
      }
      pane.index = PANE_DEFAULT_INDEX;
      pane.indexName = "上证指数";
      sel.value = PANE_DEFAULT_INDEX;
      return;
    }
    const prefer = pane.index || PANE_DEFAULT_INDEX;
    const hit = list.find((x) => x.code === prefer) || list.find((x) => x.code === PANE_DEFAULT_INDEX) || list[0];
    pane.index = String(hit?.code || PANE_DEFAULT_INDEX);
    pane.indexName = String(hit?.name || pane.index);
    sel.innerHTML = list
      .map((item) => {
        const code = String(item.code || "");
        const selected = code === pane.index ? " selected" : "";
        return `<option value="${esc(code)}"${selected}>${esc(item.name || code)}</option>`;
      })
      .join("");
    sel.value = pane.index;
  }

  async function loadMeta() {
    if (state.metaLoaded && state.indices.length) return;
    const res = await fetch("/api/stocks/line-compare/meta");
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || "指数目录加载失败");
    const data = json.data || {};
    state.indices = Array.isArray(data.indices) ? data.indices : [];
    state.factors = Array.isArray(data.factors) ? data.factors : [];
    state.metaLoaded = true;
    renderIndexList();
    fillPaneIndexSelect();
    fillPaneFactorSelect();
  }

  function paneCovers(code, index, beg, end) {
    if (!pane.daysByDate.size) return false;
    if (pane.code !== code || pane.index !== index) return false;
    if (!pane.beg || !pane.end || !beg || !end) return false;
    return pane.beg <= beg && pane.end >= end;
  }

  function unionPaneCoverage(beg, end) {
    const b = toDateInput(beg);
    const e = toDateInput(end);
    if (!b || !e) return;
    if (!pane.beg || b < pane.beg) pane.beg = b;
    if (!pane.end || e > pane.end) pane.end = e;
  }

  function normalizeFactor(key) {
    const k = String(key || "").trim();
    return FACTOR_ORDER.includes(k) ? k : "close";
  }

  function factorPairFromDay(factors, factorKey = pane.factor) {
    const key = normalizeFactor(factorKey);
    const pair = (factors && factors[key]) || {};
    const rs = Number(pair.rs);
    const rb = Number(pair.rb);
    const dif = Number.isFinite(Number(pair.dif))
      ? Number(pair.dif)
      : Number.isFinite(rs) && Number.isFinite(rb)
        ? rs - rb
        : null;
    return {
      factor: key,
      dif,
      dir: String(pair.dir || ""),
      rs: Number.isFinite(rs) ? rs : null,
      rb: Number.isFinite(rb) ? rb : null,
    };
  }

  function ingestPaneDays(cmp, { replace = false } = {}) {
    const map = replace ? new Map() : pane.daysByDate || new Map();
    const days = Array.isArray(cmp?.days) ? cmp.days : [];
    for (const day of days) {
      const date = toDateInput(day.date);
      if (!date) continue;
      const factors = day.factors && typeof day.factors === "object" ? day.factors : {};
      map.set(date, { date, factors });
    }
    pane.daysByDate = map;
    pane.indexName = String(cmp?.index?.name || pane.indexName || pane.index);
  }

  function paneSnapshot() {
    return {
      index: pane.index,
      indexName: pane.indexName,
      factor: normalizeFactor(pane.factor),
      factorLabel: factorLabel(pane.factor),
      code: pane.code,
      beg: pane.beg,
      end: pane.end,
      loading: pane.loading,
      error: pane.error,
      size: pane.daysByDate.size,
    };
  }

  function resolvePaneDay(hit, factorKey = pane.factor) {
    if (!hit) return null;
    const pair = factorPairFromDay(hit.factors, factorKey);
    return { date: hit.date, ...pair };
  }

  function paneAligned(items, factorKey = pane.factor) {
    const keyFactor = normalizeFactor(factorKey);
    return (items || []).map((d) => {
      const key = toDateInput(d?.time || d?.date);
      const hit = key ? pane.daysByDate.get(key) : null;
      if (!hit) return { time: d?.time, date: key, factor: keyFactor };
      return { time: d?.time, ...resolvePaneDay(hit, keyFactor) };
    });
  }

  function paneAtDate(timeOrDate, factorKey = pane.factor) {
    const key = toDateInput(timeOrDate);
    const hit = key ? pane.daysByDate.get(key) : null;
    return resolvePaneDay(hit, factorKey);
  }

  function fillPaneFactorSelect() {
    const sel = $("lcCompareFactorSelect");
    if (!sel) return;
    const cur = normalizeFactor(pane.factor);
    pane.factor = cur;
    const opts = FACTOR_ORDER.map((f) => {
      const selected = f === cur ? " selected" : "";
      return `<option value="${esc(f)}"${selected}>${esc(factorLabel(f))}</option>`;
    });
    sel.innerHTML = opts.join("");
    sel.value = cur;
  }

  function setPaneIndex(code) {
    const next = String(code || "").trim() || PANE_DEFAULT_INDEX;
    if (next === pane.index) return pane.index;
    pane.index = next;
    const hit = (state.indices || []).find((x) => x.code === next);
    pane.indexName = hit?.name || next;
    const sel = $("lcCompareIndexSelect");
    if (sel && sel.value !== next) sel.value = next;
    pane.daysByDate = new Map();
    pane.beg = "";
    pane.end = "";
    pane.error = "";
    return pane.index;
  }

  function setPaneFactor(factorKey) {
    const next = normalizeFactor(factorKey);
    const changed = next !== normalizeFactor(pane.factor);
    pane.factor = next;
    const sel = $("lcCompareFactorSelect");
    if (sel && sel.value !== next) sel.value = next;
    return { factor: next, changed };
  }

  /** 同步右侧口径下拉 + 左侧四项高亮 / 差值图（不重拉） */
  function setActiveFactor(factorKey) {
    syncFactorSelect(factorKey);
    if (state.pack) renderResult();
    renderUndulateStats();
    return state.activeFactor;
  }

  async function ensurePane({ code, beg, end, index, force = false } = {}) {
    const stock = String(code || state.code || "").trim();
    const idx = String(index || pane.index || PANE_DEFAULT_INDEX).trim() || PANE_DEFAULT_INDEX;
    const rangeBeg = toDateInput(beg);
    const rangeEnd = toDateInput(end) || todayStr();
    if (!stock || !rangeBeg) {
      pane.error = "缺少股票或日期";
      return paneSnapshot();
    }
    const indexChanged = pane.index && pane.index !== idx;
    const codeChanged = pane.code && pane.code !== stock;
    pane.index = idx;
    const sel = $("lcCompareIndexSelect");
    if (sel && sel.value !== idx) sel.value = idx;
    if (!force && !indexChanged && !codeChanged && paneCovers(stock, idx, rangeBeg, rangeEnd)) {
      return paneSnapshot();
    }

    // 仅缺左侧更早区间时，只补缺口，避免整段重拉冲掉已有日线对齐数据
    let fetchBeg = rangeBeg;
    let fetchEnd = rangeEnd;
    let replace = force || indexChanged || codeChanged;
    if (!replace && pane.code === stock && pane.index === idx && pane.beg && pane.end) {
      if (rangeBeg < pane.beg && rangeEnd <= pane.end) {
        fetchBeg = rangeBeg;
        fetchEnd = pane.beg;
      } else if (rangeBeg >= pane.beg && rangeEnd > pane.end) {
        fetchBeg = pane.end;
        fetchEnd = rangeEnd;
      } else if (rangeBeg < pane.beg && rangeEnd > pane.end) {
        fetchBeg = rangeBeg;
        fetchEnd = rangeEnd;
      }
    } else if (replace) {
      pane.daysByDate = new Map();
      pane.beg = "";
      pane.end = "";
    }

    if (pane.abort) pane.abort.abort();
    const ac = new AbortController();
    pane.abort = ac;
    pane.loading = true;
    pane.error = "";
    try {
      const qs = new URLSearchParams({
        code: stock,
        beg: fetchBeg,
        end: fetchEnd,
        indices: idx,
      });
      const res = await fetch(`/api/stocks/line-compare?${qs}`, {
        signal: ac.signal,
      });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "对比失败");
      if (pane.abort !== ac) return paneSnapshot();
      const cmp = (json.data?.comparisons || [])[0] || null;
      ingestPaneDays(cmp, { replace });
      pane.code = stock;
      unionPaneCoverage(rangeBeg, rangeEnd);
      if (!pane.daysByDate.size) pane.error = "暂无对比数据";
      else pane.error = "";
    } catch (err) {
      if (err?.name === "AbortError") return paneSnapshot();
      pane.error = err.message || String(err);
    } finally {
      if (pane.abort === ac) {
        pane.loading = false;
        pane.abort = null;
      }
    }
    return paneSnapshot();
  }

  /** 按日 K 已加载的全部交易日同步股指差值（随 allItems 扩长而补齐，不截可见窗口） */
  async function syncPaneWithKline({ code, items, index, force = false } = {}) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) return paneSnapshot();
    const beg = toDateInput(list[0]?.time || list[0]?.date);
    const end = toDateInput(list[list.length - 1]?.time || list[list.length - 1]?.date);
    if (!beg || !end) return paneSnapshot();
    return ensurePane({ code, beg, end, index, force });
  }

  function dirBarColorPublic(dir, active = true) {
    return dirBarColor(dir, { active });
  }

  function dirTone(dir) {
    return DIR_TONE[String(dir || "")] || "neutral";
  }

  function dirCountsHtml(dirs, factorKey = "close") {
    const pack = (dirs && dirs[factorKey]) || {};
    const keys = ["同涨", "同跌", "股涨指跌", "股跌指涨"];
    return keys
      .map((k) => {
        const n = Number(pack[k] || 0);
        return `<span class="line-compare-dir" data-tone="${dirTone(k)}"><em>${esc(k)}</em>${n}</span>`;
      })
      .join("");
  }

  function comparisonCardsHtml(comparisons) {
    return comparisons
      .map((cmp, idx) => {
        const index = cmp.index || {};
        const code = String(index.code || "");
        const total = cmp.total || {};
        const deviation = cmp.deviation || {};
        const active = (state.activeIndex || comparisons[0]?.index?.code) === code ? " is-active" : "";
        const n = Array.isArray(cmp.dates) ? cmp.dates.length : 0;
        return `<button type="button" class="line-compare-card${active}" data-lc-index="${esc(code)}" data-lc-i="${idx}">
          <div class="line-compare-card-top">
            <strong>${esc(index.name || code)}</strong>
            <span class="muted">${esc(code)}</span>
          </div>
          <div class="line-compare-card-score">
            <span class="line-compare-score">${esc(fmtScore(total.value))}</span>
            <span class="line-compare-level" data-level="${esc(total.level || "")}">${esc(total.level || "—")}</span>
            <span class="line-compare-level" data-level="${esc(deviation.level || "")}">${esc(fmtScore(deviation.value))} ${esc(deviation.level || "")}</span>
          </div>
          <div class="line-compare-card-meta muted">${n} 个交易日</div>
        </button>`;
      })
      .join("");
  }

  function normMeta(cmp) {
    return (cmp && cmp.norm) || (state.pack && state.pack.meta && state.pack.meta.norm) || {};
  }

  /** 四项强弱 + 偏离，与右侧下拉口径一致（默认波动标准化） */
  function factorScoresHtml(cmp) {
    const scores = cmp?.scores || {};
    const deviations = cmp?.deviations || {};
    const total = cmp?.total || {};
    const deviation = cmp?.deviation || {};
    const norm = normMeta(cmp);
    const unit = norm.unit === "pct_point" ? "百分点" : "σ";
    const rows = FACTOR_ORDER.map((f) => {
      const active = f === state.activeFactor ? " is-active" : "";
      return `<button type="button" class="line-compare-factor-score${active}" data-lc-factor="${esc(f)}">
        <span class="line-compare-factor-score-label">${esc(factorLabel(f))}</span>
        <span class="line-compare-factor-score-pair">
          <span class="line-compare-score" title="强弱(${unit})">${esc(fmtScore(scores[f]))}</span>
          <span class="line-compare-dev" title="偏离(${unit})">${esc(fmtScore(deviations[f]))}</span>
        </span>
      </button>`;
    }).join("");
    return `<div class="line-compare-factor-scores" aria-label="四项强弱与偏离">
      <div class="line-compare-score-legend muted">
        <span>强弱·${esc(unit)}</span><span>偏离·${esc(unit)}</span>
      </div>
      ${rows}
      <div class="line-compare-factor-score line-compare-factor-score--total">
        <span class="line-compare-factor-score-label">total</span>
        <span class="line-compare-factor-score-pair">
          <span class="line-compare-score" title="强弱">${esc(fmtScore(total.value))}</span>
          <span class="line-compare-level" data-level="${esc(total.level || "")}">${esc(total.level || "—")}</span>
        </span>
        <span class="line-compare-factor-score-pair">
          <span class="line-compare-dev" title="偏离">${esc(fmtScore(deviation.value))}</span>
          <span class="line-compare-level" data-level="${esc(deviation.level || "")}">${esc(deviation.level || "—")}</span>
        </span>
      </div>
    </div>`;
  }

  function chartIndexCode() {
    const sel = $("lcCompareIndexSelect");
    const raw = String(sel?.value || pane.index || PANE_DEFAULT_INDEX).trim();
    return raw || PANE_DEFAULT_INDEX;
  }

  function chartFactorKey() {
    const sel = $("lcCompareFactorSelect");
    const raw = String(sel?.value || pane.factor || state.activeFactor || "close").trim();
    return FACTOR_ORDER.includes(raw) ? raw : "close";
  }

  function syncFactorSelect(factor) {
    const next = FACTOR_ORDER.includes(factor) ? factor : "close";
    state.activeFactor = next;
    pane.factor = next;
    const sel = $("lcCompareFactorSelect");
    if (sel && sel.value !== next) sel.value = next;
  }

  function factorTabsHtml() {
    return FACTOR_ORDER.map((f) => {
      const active = f === state.activeFactor ? " is-active" : "";
      return `<button type="button" class="line-compare-factor-btn${active}" data-lc-factor="${esc(f)}">${esc(factorLabel(f))}</button>`;
    }).join("");
  }

  function buildSeries(cmp, factorKey = state.activeFactor) {
    const days = Array.isArray(cmp?.days) ? cmp.days : [];
    let cumS = 1;
    let cumB = 1;
    const points = [];
    for (const day of days) {
      const pair = (day.factors || {})[factorKey] || {};
      const rs = Number(pair.rs);
      const rb = Number(pair.rb);
      if (!Number.isFinite(rs) || !Number.isFinite(rb)) continue;
      cumS *= 1 + rs;
      cumB *= 1 + rb;
      points.push({
        date: String(day.date || ""),
        cumS: cumS - 1,
        cumB: cumB - 1,
        excess: cumS - cumB,
        rs,
        rb,
        dif: Number.isFinite(Number(pair.dif)) ? Number(pair.dif) : rs - rb,
        dir: String(pair.dir || ""),
      });
    }
    return points;
  }

  function niceMax(absMax) {
    const v = Math.abs(Number(absMax)) || 0.01;
    const exp = Math.floor(Math.log10(v));
    const base = 10 ** exp;
    const n = v / base;
    let nice;
    if (n <= 1) nice = 1;
    else if (n <= 2) nice = 2;
    else if (n <= 5) nice = 5;
    else nice = 10;
    return nice * base;
  }

  function destroyChart() {
    if (state.chart?.ro) {
      try {
        state.chart.ro.disconnect();
      } catch {
        /* ignore */
      }
    }
    state.chart = null;
  }

  function fillHover(points, idx) {
    const el = $("lcResultHover");
    if (!el) return;
    if (idx == null || idx < 0 || !points[idx]) {
      el.classList.add("hidden");
      el.setAttribute("aria-hidden", "true");
      return;
    }
    const p = points[idx];
    const stockName = state.name || state.code || "个股";
    const idxName =
      state.pack?.comparisons?.find((c) => c.index?.code === state.activeIndex)?.index?.name ||
      state.activeIndex ||
      "指数";
    const dirColor = dirBarColor(p.dir, { active: true });
    el.innerHTML = `
      <div class="line-compare-hover-date">${esc(p.date)}</div>
      <div class="line-compare-hover-row" data-series="excess"><em>差值</em><span>${esc(fmtPct(p.dif))}</span></div>
      <div class="line-compare-hover-row"><em>方向</em><span style="color:${esc(dirColor)}">${esc(p.dir || "—")}</span></div>
      <div class="line-compare-hover-row"><em>${esc(stockName)}</em><span>${esc(fmtPct(p.rs))}</span></div>
      <div class="line-compare-hover-row"><em>${esc(idxName)}</em><span>${esc(fmtPct(p.rb))}</span></div>`;
    el.classList.remove("hidden");
    el.setAttribute("aria-hidden", "false");
  }

  function paintCompareChart(hoverIdx = null) {
    const chart = state.chart;
    if (!chart?.canvas || !chart.wrap) return;
    const points = chart.points || [];
    const canvas = chart.canvas;
    const wrap = chart.wrap;
    const colors = chartColors();
    const cssW = Math.max(120, wrap.clientWidth || canvas.clientWidth || 320);
    const cssH = Math.max(180, wrap.clientHeight || 240);
    const dpr = Math.min(2.5, window.devicePixelRatio || 1);
    canvas.width = Math.floor(cssW * dpr);
    canvas.height = Math.floor(cssH * dpr);
    canvas.style.width = `${cssW}px`;
    canvas.style.height = `${cssH}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    const pad = { top: 14, right: 12, bottom: 24, left: 48 };
    const plot = {
      x: pad.left,
      y: pad.top,
      w: Math.max(40, cssW - pad.left - pad.right),
      h: Math.max(80, cssH - pad.top - pad.bottom),
    };

    if (!points.length) {
      ctx.fillStyle = colors.muted;
      ctx.font = "12px sans-serif";
      ctx.fillText("暂无柱状数据", plot.x + 8, plot.y + 24);
      fillHover([], null);
      return;
    }

    let absMax = 0.01;
    for (const p of points) {
      absMax = Math.max(absMax, Math.abs(p.dif));
    }
    const yMax = niceMax(absMax * 1.12);
    const n = points.length;
    const slot = plot.w / n;
    const gap = Math.min(3, slot * 0.22);
    const barW = Math.max(1, slot - gap);
    const xSlot = (i) => plot.x + i * slot;
    const xCenter = (i) => xSlot(i) + slot / 2;
    const yAt = (v) => plot.y + plot.h / 2 - (v / yMax) * (plot.h / 2);
    const zeroY = yAt(0);

    ctx.strokeStyle = colors.grid;
    ctx.lineWidth = 1;
    for (const frac of [-1, -0.5, 0, 0.5, 1]) {
      const y = yAt(frac * yMax);
      ctx.beginPath();
      ctx.moveTo(plot.x, y);
      ctx.lineTo(plot.x + plot.w, y);
      ctx.stroke();
    }
    ctx.strokeStyle = colors.zero;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(plot.x, zeroY);
    ctx.lineTo(plot.x + plot.w, zeroY);
    ctx.stroke();

    ctx.fillStyle = colors.muted;
    ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (const frac of [-1, 0, 1]) {
      const v = frac * yMax;
      ctx.fillText(fmtPct(v, 1), plot.x - 6, yAt(v));
    }

    const hi = hoverIdx == null ? n - 1 : hoverIdx;

    points.forEach((p, i) => {
      const active = i === hi;
      if (active) {
        ctx.fillStyle = colors.hoverBg;
        ctx.fillRect(xSlot(i), plot.y, slot, plot.h);
      }
      const x = xCenter(i) - barW / 2;
      const y1 = yAt(p.dif);
      const top = Math.min(zeroY, y1);
      const h = Math.max(1, Math.abs(y1 - zeroY));
      const fill = dirBarColor(p.dir, { active });
      ctx.fillStyle = fill;
      ctx.fillRect(x, top, barW, h);
      if (active) {
        ctx.strokeStyle = dirBarColor(p.dir, { active: true });
        ctx.lineWidth = 1;
        ctx.strokeRect(x + 0.5, top + 0.5, Math.max(0, barW - 1), Math.max(0, h - 1));
      }
    });

    ctx.fillStyle = colors.muted;
    ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "alphabetic";
    const labelIdx = [0, Math.floor((n - 1) / 2), n - 1].filter(
      (v, i, arr) => arr.indexOf(v) === i
    );
    for (const i of labelIdx) {
      ctx.fillText(String(points[i].date || "").slice(5), xCenter(i), cssH - 6);
    }

    if (hi >= 0 && hi < n) fillHover(points, hi);
    else fillHover(points, null);

    chart.layout = { pad, plot, slot, n };
  }

  function pointerIndex(evt) {
    const chart = state.chart;
    if (!chart?.canvas || !chart.points?.length) return null;
    const rect = chart.canvas.getBoundingClientRect();
    const padLeft = chart.layout?.pad?.left ?? 48;
    const padRight = chart.layout?.pad?.right ?? 12;
    const w = Math.max(40, rect.width - padLeft - padRight);
    const x = evt.clientX - rect.left - padLeft;
    if (x < 0 || x > w) return null;
    const n = chart.points.length;
    if (n <= 1) return 0;
    return Math.min(n - 1, Math.max(0, Math.floor((x / w) * n)));
  }

  function bindChartInteractions(canvas) {
    if (!canvas || canvas.dataset.lcBound === "1") return;
    canvas.dataset.lcBound = "1";
    canvas.addEventListener("pointermove", (evt) => {
      const idx = pointerIndex(evt);
      paintCompareChart(idx);
    });
    canvas.addEventListener("pointerleave", () => {
      paintCompareChart(null);
    });
  }

  function mountResultChart(cmp) {
    destroyChart();
    const canvas = $("lcResultChart");
    const wrap = $("lcResultChartWrap");
    if (!canvas || !wrap) return;
    const points = buildSeries(cmp, state.activeFactor);
    state.chart = { canvas, wrap, points, hoverIdx: null, ro: null };
    bindChartInteractions(canvas);
    if (typeof ResizeObserver !== "undefined") {
      let timer = 0;
      state.chart.ro = new ResizeObserver(() => {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => paintCompareChart(null), 50);
      });
      state.chart.ro.observe(wrap);
    }
    requestAnimationFrame(() => paintCompareChart(null));
  }

  /* ---------- 四价相对基准收盘的波动统计（个股 + 指数） ---------- */

  function undulateKey(kind, code, beg, end) {
    if (!code || !beg) return "";
    return `${kind}|${code}|${beg}|${end || ""}`;
  }

  function abortUndulateSlot(slot) {
    if (slot.abort) {
      slot.abort.abort();
      slot.abort = null;
    }
  }

  function clearUndulateSlot(slot) {
    abortUndulateSlot(slot);
    slot.key = "";
    slot.loading = false;
    slot.error = "";
    slot.pack = null;
  }

  function clearUndulate() {
    clearUndulateSlot(undulate.stock);
    clearUndulateSlot(undulate.index);
    undulate.rangeBeg = "";
    undulate.rangeEnd = "";
    undulateDayCache = { key: "", map: new Map() };
    renderUndulateStats();
  }

  function indexDisplayName() {
    const sel = $("lcCompareIndexSelect");
    const opt = sel?.selectedOptions?.[0];
    return (opt?.textContent || "").trim() || undulate.index.pack?.name || "指数";
  }

  function renderUndulateStats() {
    const meta = $("lcUndulateMeta");
    const stock = undulate.stock;
    const idx = undulate.index;
    const beg = undulate.rangeBeg || stock.pack?.beg || idx.pack?.beg || "";
    const end = undulate.rangeEnd || stock.pack?.end || idx.pack?.end || beg;
    const loading = stock.loading || idx.loading;
    const anyPack = Boolean(stock.pack || idx.pack);
    if (meta) {
      if (!beg && !anyPack) {
        meta.textContent = loading
          ? "加载中…"
          : "右侧点选两根日K · 滚轮缩放 / 拖动平移 · 相对基准收盘";
      } else {
        const rangeText = beg ? `选区 ${beg}${end && end !== beg ? ` ~ ${end}` : ""}` : "";
        const count = Number(stock.pack?.count || idx.pack?.count || 0);
        const countText = count ? ` · ${count} 日` : "";
        const loadText = loading ? " · 更新中…" : "";
        meta.textContent = `${rangeText}${countText}${loadText}` || "相对基准收盘";
      }
    }
    // 四张 σ 曲线卡（个股 vs 指数）与各卡统计数字由 company 侧统一渲染
    window.CompanyLcKline?.renderUndulate?.();
  }

  async function fetchUndulateSlot(slot, { kind, code, beg, end, force = false, adjust = "qfq" }) {
    const key = undulateKey(kind, code, beg, end);
    if (!code || !beg) {
      clearUndulateSlot(slot);
      return null;
    }
    if (slot.loading && slot.key === key) return slot.pack || null;
    if (!force && key === slot.key && slot.pack) return slot.pack;
    abortUndulateSlot(slot);
    const ac = new AbortController();
    slot.abort = ac;
    slot.key = key;
    slot.loading = true;
    slot.error = "";
    renderUndulateStats();
    try {
      const qs = new URLSearchParams({
        code,
        beg,
        end: end || "",
        kind,
      });
      if (kind === "stock") qs.set("adjust", adjust);
      const res = await fetch(`/api/stocks/line-undulate/volatility?${qs}`, {
        signal: ac.signal,
      });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "波动统计失败");
      if (slot.abort !== ac) return null;
      slot.pack = json.data || null;
      slot.key = key;
      slot.error = "";
      return slot.pack;
    } catch (err) {
      if (err?.name === "AbortError") return null;
      if (slot.abort !== ac) return null;
      slot.pack = null;
      slot.key = "";
      slot.error = err.message || String(err);
      return null;
    } finally {
      if (slot.abort === ac) {
        slot.loading = false;
        slot.abort = null;
        renderUndulateStats();
      }
    }
  }

  async function loadUndulate({ code, beg, end, index, force = false } = {}) {
    const stock = String(code || state.code || "").trim();
    const b = toDateInput(beg);
    const e = toDateInput(end);
    const idx = String(index || chartIndexCode() || "").trim();
    if (!stock || !b) {
      clearUndulate();
      return null;
    }
    undulate.rangeBeg = b;
    undulate.rangeEnd = e || b;
    const [stockPack] = await Promise.all([
      fetchUndulateSlot(undulate.stock, {
        kind: "stock",
        code: stock,
        beg: b,
        end: e || b,
        force,
        adjust: "qfq",
      }),
      idx
        ? fetchUndulateSlot(undulate.index, {
            kind: "index",
            code: idx,
            beg: b,
            end: e || b,
            force,
          })
        : (clearUndulateSlot(undulate.index), Promise.resolve(null)),
    ]);
    renderUndulateStats();
    return stockPack;
  }

  let undulateDayCache = { key: "", map: new Map() };

  function undulateDayMap() {
    const days = Array.isArray(undulate.stock.pack?.days) ? undulate.stock.pack.days : [];
    const cacheKey = undulate.stock.key;
    if (undulateDayCache.key === cacheKey && undulateDayCache.map.size === days.length) {
      return undulateDayCache.map;
    }
    const map = new Map();
    for (const d of days) {
      const k = toDateInput(d.date);
      if (k) map.set(k, d);
    }
    undulateDayCache = { key: cacheKey, map };
    return map;
  }

  function undulateAtDate(timeOrDate, factorKey = state.activeFactor) {
    const key = toDateInput(timeOrDate);
    if (!key || !undulate.stock.pack) return null;
    const hit = undulateDayMap().get(key);
    if (!hit) return null;
    const pct = (hit.pct || {})[factorKey];
    return {
      date: key,
      factor: factorKey,
      pct: pct == null ? null : Number(pct),
      prices: hit.prices || {},
    };
  }

  /* ---------- 四价前低回溯 ---------- */

  function extremumKey(code, date) {
    if (!code || !date) return "";
    return `${code}|${date}|qfq`;
  }

  function abortExtremum() {
    if (extremum.abort) {
      extremum.abort.abort();
      extremum.abort = null;
    }
  }

  function clearExtremum() {
    abortExtremum();
    extremum.key = "";
    extremum.date = "";
    extremum.loading = false;
    extremum.error = "";
    extremum.pack = null;
    syncExtremumDateInput("");
    renderExtremum();
  }

  function syncExtremumDateInput(date) {
    const el = $("lcExtremumDate");
    if (!el) return;
    const next = toDateInput(date) || "";
    if (el.value !== next) el.value = next;
  }

  function renderExtremum() {
    const meta = $("lcExtremumMeta");
    const date = toDateInput(extremum.date) || toDateInput(extremum.pack?.date) || "";
    if (meta) {
      if (extremum.loading && !extremum.pack) {
        meta.textContent = date ? `加载 ${date}…` : "加载中…";
      } else if (extremum.error && !extremum.pack) {
        meta.textContent = extremum.error;
      } else if (date) {
        const used = toDateInput(extremum.pack?.date) || date;
        const snapped = extremum.pack?.snapped ? " · 已对齐交易日" : "";
        const loadText = extremum.loading ? " · 更新中…" : "";
        meta.textContent = `基准日 ${used}${snapped}${loadText}`;
      } else {
        meta.textContent = "点选日K终点（或单根）· 回溯开/收/高/低各自最近更低日";
      }
    }
    window.CompanyLcKline?.renderExtremum?.();
  }

  async function loadExtremum({ code, date, force = false } = {}) {
    const stock = String(code || state.code || "").trim();
    const d = toDateInput(date);
    if (!stock || !d) {
      clearExtremum();
      return null;
    }
    const key = extremumKey(stock, d);
    if (extremum.loading && extremum.key === key) return extremum.pack || null;
    if (!force && key === extremum.key && extremum.pack) {
      extremum.date = d;
      syncExtremumDateInput(d);
      renderExtremum();
      return extremum.pack;
    }
    abortExtremum();
    const ac = new AbortController();
    extremum.abort = ac;
    extremum.key = key;
    extremum.date = d;
    extremum.loading = true;
    extremum.error = "";
    syncExtremumDateInput(d);
    renderExtremum();
    try {
      const qs = new URLSearchParams({ code: stock, date: d, adjust: "qfq" });
      const res = await fetch(`/api/stocks/line-extremum?${qs}`, { signal: ac.signal });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "四价前低失败");
      if (extremum.abort !== ac) return null;
      extremum.pack = json.data || null;
      extremum.key = key;
      extremum.error = "";
      if (extremum.pack?.date) syncExtremumDateInput(extremum.pack.date);
      return extremum.pack;
    } catch (err) {
      if (err?.name === "AbortError") return null;
      if (extremum.abort !== ac) return null;
      extremum.pack = null;
      extremum.key = "";
      extremum.error = err.message || String(err);
      return null;
    } finally {
      if (extremum.abort === ac) {
        extremum.loading = false;
        extremum.abort = null;
        renderExtremum();
      }
    }
  }

  /** 按日K点选终点（或可见窗口末日）同步四价前低 */
  async function syncExtremumWithKline({ code, date, force = false } = {}) {
    let d = toDateInput(date);
    if (!d) {
      const range = visibleWindowRange();
      d = range?.end || "";
    }
    if (!d) return null;
    return loadExtremum({ code, date: d, force });
  }

  /* ---------- 四价极值位置（区间内开/收/高/低各自的最低—最高—现价位置） ---------- */

  function positionKey(code, beg, end) {
    if (!code || !beg) return "";
    return `${code}|${beg}|${end || ""}|qfq`;
  }

  function abortPosition() {
    if (position.abort) {
      position.abort.abort();
      position.abort = null;
    }
  }

  function clearPosition() {
    abortPosition();
    position.key = "";
    position.beg = "";
    position.end = "";
    position.loading = false;
    position.error = "";
    position.pack = null;
    renderPosition();
  }

  function renderPosition() {
    window.CompanyLcKline?.renderPosition?.();
  }

  async function loadPosition({ code, beg, end, force = false } = {}) {
    const stock = String(code || state.code || "").trim();
    const b = toDateInput(beg);
    const e = toDateInput(end) || b;
    if (!stock || !b) {
      clearPosition();
      return null;
    }
    const key = positionKey(stock, b, e);
    if (position.loading && position.key === key) return position.pack || null;
    if (!force && key === position.key && position.pack) {
      renderPosition();
      return position.pack;
    }
    abortPosition();
    const ac = new AbortController();
    position.abort = ac;
    position.key = key;
    position.beg = b;
    position.end = e;
    position.loading = true;
    position.error = "";
    renderPosition();
    try {
      const qs = new URLSearchParams({ code: stock, beg: b, end: e, adjust: "qfq" });
      const res = await fetch(`/api/stocks/line-extremum/position?${qs}`, {
        signal: ac.signal,
      });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "极值位置失败");
      if (position.abort !== ac) return null;
      position.pack = json.data || null;
      position.error = "";
      return position.pack;
    } catch (err) {
      if (err?.name === "AbortError") return null;
      if (position.abort !== ac) return null;
      position.pack = null;
      position.key = "";
      position.error = err.message || String(err);
      return null;
    } finally {
      if (position.abort === ac) {
        position.loading = false;
        position.abort = null;
        renderPosition();
      }
    }
  }

  /* ---------- 聪明投机者（期末股数 / 均价） ---------- */

  function traderKey(code, beg, end) {
    if (!code || !beg) return "";
    return `${code}|${beg}|${end || ""}|0.01|qfq`;
  }

  function abortTrader() {
    if (trader.abort) {
      trader.abort.abort();
      trader.abort = null;
    }
  }

  function clearTrader() {
    abortTrader();
    trader.key = "";
    trader.beg = "";
    trader.end = "";
    trader.loading = false;
    trader.error = "";
    trader.pack = null;
    renderTrader();
  }

  function fmtTraderShares(value) {
    // 后端 shares 单位为股；前端展示换算为手（1 手 = 100 股）
    const shares = Number(value);
    if (!Number.isFinite(shares)) return "—";
    const lots = shares / 100;
    const abs = Math.abs(lots);
    if (abs >= 1e8) return `${(lots / 1e8).toFixed(2)}亿手`;
    if (abs >= 1e4) return `${(lots / 1e4).toFixed(2)}万手`;
    if (abs >= 100) return `${lots.toFixed(1)}手`;
    return `${lots.toFixed(2)}手`;
  }

  function fmtTraderPrice(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n >= 100 ? n.toFixed(2) : n.toFixed(3);
  }

  function fmtTraderPnl(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return { text: "—", tone: "" };
    const abs = Math.abs(n);
    let body;
    if (abs >= 1e8) body = `${(abs / 1e8).toFixed(2)}亿`;
    else if (abs >= 1e4) body = `${(abs / 1e4).toFixed(2)}万`;
    else body = abs.toFixed(0);
    const sign = n > 0 ? "+" : n < 0 ? "-" : "";
    const tone = n > 0 ? "is-up" : n < 0 ? "is-down" : "";
    return { text: `${sign}${body}`, tone };
  }

  function syncTraderBoxHeight() {
    const box = $("lcTraderBox");
    const head = document.querySelector("#lineCompareKline > .chart-card__head");
    if (!box || !head) return;
    const h = Math.round(head.getBoundingClientRect().height);
    // 只对齐最小高度；内容（2×2 指标格）可高于表头，避免被 overflow 裁切成「无数据」
    if (h > 0) {
      box.style.minHeight = `${h}px`;
      box.style.height = "auto";
    }
  }

  function ensureTraderHeadObserver() {
    if (traderHeadObserver) return;
    const head = document.querySelector("#lineCompareKline > .chart-card__head");
    if (!head || typeof ResizeObserver === "undefined") {
      syncTraderBoxHeight();
      return;
    }
    traderHeadObserver = new ResizeObserver(() => syncTraderBoxHeight());
    traderHeadObserver.observe(head);
    syncTraderBoxHeight();
  }

  function setTraderTone(tone) {
    const box = $("lcTraderBox");
    if (!box) return;
    box.dataset.tone = tone || "";
  }

  function renderTrader() {
    const body = $("lcTraderBody");
    const rangeEl = $("lcTraderRange");
    const beg = toDateInput(trader.pack?.beg) || toDateInput(trader.beg) || "";
    const end = toDateInput(trader.pack?.end) || toDateInput(trader.end) || beg;
    if (rangeEl) {
      const text = beg ? (end && end !== beg ? `${beg.slice(5)}~${end.slice(5)}` : beg.slice(5)) : "";
      rangeEl.textContent = text;
      rangeEl.hidden = !text;
    }
    if (!body) return;
    if (trader.loading && !trader.pack) {
      setTraderTone("");
      body.innerHTML = `<p class="muted lc-undulate-note">计算中…</p>`;
      return;
    }
    if (trader.error && !trader.pack) {
      setTraderTone("");
      body.innerHTML = `<p class="error lc-undulate-note">${esc(trader.error)}</p>`;
      return;
    }
    if (!trader.pack) {
      setTraderTone("");
      body.innerHTML = `<p class="muted lc-undulate-note">点选日K区间…</p>`;
      return;
    }
    const shares = fmtTraderShares(trader.pack.shares);
    const avg = fmtTraderPrice(trader.pack.avg_price);
    const netAvg = fmtTraderPrice(trader.pack.net_avg_price);
    const pnl = fmtTraderPnl(trader.pack.pnl);
    const tone = pnl.tone === "is-up" ? "up" : pnl.tone === "is-down" ? "down" : "";
    setTraderTone(tone);
    const loadHint = trader.loading ? `<span class="muted"> ·</span>` : "";
    const pnlClass = ["line-compare-trader-cell", "is-pnl", tone ? `is-${tone}` : ""].filter(Boolean).join(" ");
    body.innerHTML =
      `<div class="line-compare-trader-grid">` +
      `<div class="line-compare-trader-cell"><span class="k">持股</span><span class="v">${esc(shares)}${loadHint}</span></div>` +
      `<div class="line-compare-trader-cell"><span class="k">均价</span><span class="v">${esc(avg)}</span></div>` +
      `<div class="line-compare-trader-cell"><span class="k">净成本</span><span class="v">${esc(netAvg)}</span></div>` +
      `<div class="${pnlClass}"><span class="k">盈亏</span><span class="v ${pnl.tone}">${esc(pnl.text)}</span></div>` +
      `</div>`;
  }

  async function loadTrader({ code, beg, end, force = false } = {}) {
    const stock = String(code || state.code || "").trim();
    const b = toDateInput(beg);
    const e = toDateInput(end) || b;
    if (!stock || !b) {
      clearTrader();
      return null;
    }
    const key = traderKey(stock, b, e);
    if (trader.loading && trader.key === key) return trader.pack || null;
    if (!force && key === trader.key && trader.pack) {
      renderTrader();
      return trader.pack;
    }
    abortTrader();
    const ac = new AbortController();
    trader.abort = ac;
    trader.key = key;
    trader.beg = b;
    trader.end = e;
    trader.loading = true;
    trader.error = "";
    renderTrader();
    try {
      const qs = new URLSearchParams({
        code: stock,
        beg: b,
        end: e,
        ratio: "0.01",
        adjust: "qfq",
      });
      const res = await fetch(`/api/stocks/line-trader?${qs}`, { signal: ac.signal });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "投机持仓失败");
      if (trader.abort !== ac) return null;
      trader.pack = json.data || null;
      trader.error = "";
      return trader.pack;
    } catch (err) {
      if (err?.name === "AbortError") return null;
      if (trader.abort !== ac) return null;
      trader.pack = null;
      trader.key = "";
      trader.error = err.message || String(err);
      return null;
    } finally {
      if (trader.abort === ac) {
        trader.loading = false;
        trader.abort = null;
        renderTrader();
      }
    }
  }

  function renderResult() {
    /* 左侧强弱面板已移除；仍同步区间与口径，供右侧股指对比使用 */
    const pack = state.pack;
    if (!pack) {
      syncRangeDisplay($("lcBeg")?.value, $("lcEnd")?.value);
      return;
    }
    const comparisons = Array.isArray(pack.comparisons) ? pack.comparisons : [];
    if (!comparisons.length) return;
    const prefer = chartIndexCode();
    if (prefer && comparisons.some((c) => c.index?.code === prefer)) {
      state.activeIndex = prefer;
    } else if (!state.activeIndex || !comparisons.some((c) => c.index?.code === state.activeIndex)) {
      state.activeIndex = String(comparisons[0].index?.code || "");
    }
    syncFactorSelect(chartFactorKey());
    const meta = pack.meta || {};
    syncRangeDisplay(meta.beg || $("lcBeg")?.value, meta.end || $("lcEnd")?.value);
  }

  async function runCompare(opts = {}) {
    showFormError("");
    const beg = String(opts.beg || $("lcBeg")?.value || "").trim();
    const end = String(opts.end || $("lcEnd")?.value || "").trim();
    const indices = Array.isArray(opts.indices) && opts.indices.length
      ? opts.indices.map((x) => String(x).trim()).filter(Boolean)
      : [chartIndexCode()];
    if (!state.code) {
      showFormError("缺少股票代码");
      return;
    }
    if (!beg) {
      showFormError("请先在日K上点选区间");
      return;
    }
    if (end && beg > end) {
      showFormError("起始日期不能晚于结束日期");
      return;
    }
    if (!indices.length) {
      showFormError("请选择对比指数");
      return;
    }

    if (opts.factor) syncFactorSelect(opts.factor);
    else syncFactorSelect(chartFactorKey());
    setRangeValues(beg, end || beg);
    void loadUndulate({ code: state.code, beg, end: end || beg });
    void loadExtremum({ code: state.code, date: end || beg });
    void loadTrader({ code: state.code, beg, end: end || beg });

    if (state.abort) state.abort.abort();
    const ac = new AbortController();
    state.abort = ac;
    state.loading = true;
    setFormMeta("计算中…");

    try {
      const qs = new URLSearchParams({
        code: state.code,
        beg,
        end: end || "",
        indices: indices.join(","),
      });
      const res = await fetch(`/api/stocks/line-compare?${qs}`, {
        signal: ac.signal,
      });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "对比失败");
      if (state.abort !== ac) return;
      state.pack = json.data || null;
      const prefer = chartIndexCode();
      const list = state.pack?.comparisons || [];
      const hit = list.find((c) => c.index?.code === prefer) || list[0];
      state.activeIndex = hit?.index?.code ? String(hit.index.code) : "";
      renderResult();
      const name = hit?.index?.name || state.activeIndex || "";
      setFormMeta(name ? `vs ${name}` : "");
    } catch (err) {
      if (err?.name === "AbortError") return;
      showFormError(err.message || String(err));
      setFormMeta("");
    } finally {
      if (state.abort === ac) {
        state.loading = false;
        state.abort = null;
      }
    }
  }

  /** 右侧日K点选两根蜡烛后：按图表下拉指数/口径写入起止日并计算 */
  async function applyRangeAndRun({ beg, end, index, factor } = {}) {
    const a = toDateInput(beg);
    const b = toDateInput(end) || a;
    if (!a) {
      showFormError("未识别选区日期");
      return;
    }
    const lo = a <= b ? a : b;
    const hi = a <= b ? b : a;
    setRangeValues(lo, hi);
    const idx = String(index || chartIndexCode()).trim() || PANE_DEFAULT_INDEX;
    const fac = String(factor || chartFactorKey()).trim();
    if ($("lcCompareIndexSelect") && $("lcCompareIndexSelect").value !== idx) {
      $("lcCompareIndexSelect").value = idx;
    }
    setPaneIndex(idx);
    syncFactorSelect(fac);
    showFormError("");
    await runCompare({ beg: lo, end: hi, indices: [idx], factor: fac });
  }

  /** 右侧切换指数时：若已有区间，按新指数重算对比与四价波动 */
  async function rerunForPaneIndex(index) {
    const idx = String(index || chartIndexCode()).trim();
    if (!idx) return;
    setPaneIndex(idx);
    const beg = String($("lcBeg")?.value || "").trim();
    const end = String($("lcEnd")?.value || "").trim();
    if (!beg || !state.code) return;
    await runCompare({ beg, end, indices: [idx], factor: chartFactorKey() });
  }

  function bind() {
    if (state.bound) return;
    state.bound = true;
    ensureTraderHeadObserver();
    $("lcUndulateStats")?.addEventListener("click", onUndulateClick);
    $("lcUndulateRefresh")?.addEventListener("click", () => {
      const beg = toDateInput($("lcBeg")?.value) || visibleWindowRange()?.beg || "";
      const end = toDateInput($("lcEnd")?.value) || visibleWindowRange()?.end || "";
      if (!beg) return;
      void loadUndulate({
        code: state.code,
        beg,
        end,
        index: chartIndexCode(),
        force: true,
      });
    });
    $("lcExtremumRefresh")?.addEventListener("click", () => {
      const forceExt = window.CompanyLcKline?.refreshExtremum;
      if (typeof forceExt === "function") forceExt({ force: true });
      else window.CompanyLcKline?.renderExtremum?.();
    });
  }

  function onUndulateClick(ev) {
    const row = ev.target.closest?.("[data-lc-factor]");
    if (!row) return;
    const next = String(row.getAttribute("data-lc-factor") || "");
    if (!FACTOR_ORDER.includes(next) || next === state.activeFactor) return;
    syncFactorSelect(next);
    renderUndulateStats();
    renderResult();
    window.CompanyLcKline?.render?.();
  }

  function hideResultChart() {
    destroyChart();
  }

  async function show(identity = {}) {
    bind();
    state.visible = true;
    const nextCode = String(identity.code || state.code || "").trim();
    const nextName = String(identity.name || state.name || "").trim();
    const codeChanged = nextCode && nextCode !== state.code;
    state.code = nextCode || state.code;
    state.name = nextName || state.name;
    ensureDefaults();
    const page = $("lineComparePage");
    if (page) page.hidden = false;

    try {
      await loadMeta();
      fillPaneIndexSelect();
      fillPaneFactorSelect();
    } catch (err) {
      showFormError(err.message || String(err));
    }

    if (codeChanged) {
      state.pack = null;
      state.activeIndex = "";
      setRangeValues("", "");
      renderResult();
      setFormMeta("");
      pane.daysByDate = new Map();
      pane.code = "";
      pane.beg = "";
      pane.end = "";
      pane.error = "";
      clearUndulate();
      clearExtremum();
      clearPosition();
      clearTrader();
    }
    ensureTraderHeadObserver();
    if (window.CompanyLcKline?.show) {
      await window.CompanyLcKline.show({
        code: state.code,
        name: state.name,
      });
    }
  }

  function hide() {
    state.visible = false;
    if (state.abort) {
      state.abort.abort();
      state.abort = null;
    }
    if (pane.abort) {
      pane.abort.abort();
      pane.abort = null;
    }
    abortUndulateSlot(undulate.stock);
    abortUndulateSlot(undulate.index);
    abortExtremum();
    abortPosition();
    abortTrader();
    hideResultChart();
    window.CompanyLcKline?.hide?.();
    const page = $("lineComparePage");
    if (page) page.hidden = true;
  }

  function syncIdentity(next = {}) {
    const code = String(next.code || "").trim();
    const name = String(next.name || "").trim();
    const changed = code && code !== state.code;
    if (code) state.code = code;
    if (name) state.name = name;
    if (!state.visible) return;
    if (changed) {
      state.pack = null;
      state.activeIndex = "";
      setRangeValues("", "");
      pane.daysByDate = new Map();
      pane.code = "";
      pane.beg = "";
      pane.end = "";
      clearUndulate();
      clearExtremum();
      clearPosition();
      clearTrader();
      renderResult();
      window.CompanyLcKline?.sync?.()?.catch?.(() => {});
    } else {
      window.CompanyLcKline?.render?.();
    }
  }

  /** 按日K可见窗口同步四价波动统计（基准=窗口首日前一交易日收盘） */
  async function syncUndulateWithKline({ code, items, beg, end, force = false } = {}) {
    let b = toDateInput(beg);
    let e = toDateInput(end);
    if (!b) {
      const list = Array.isArray(items) ? items : [];
      if (list.length) {
        b = toDateInput(list[0]?.time || list[0]?.date);
        e = toDateInput(list[list.length - 1]?.time || list[list.length - 1]?.date);
      } else {
        const range = visibleWindowRange();
        if (range) {
          b = range.beg;
          e = range.end;
        }
      }
    }
    if (!b) return null;
    return loadUndulate({ code, beg: b, end: e, force });
  }

  window.LineCompare = {
    show,
    hide,
    syncIdentity,
    ensurePane,
    syncPaneWithKline,
    syncUndulateWithKline,
    setPaneIndex,
    setPaneFactor,
    setActiveFactor,
    paneAligned,
    paneAtDate,
    undulateAtDate,
    paneMeta: paneSnapshot,
    undulateMeta: () => ({
      key: undulate.stock.key,
      loading: undulate.stock.loading || undulate.index.loading,
      error: undulate.stock.error,
      name: undulate.stock.pack?.name || state.name || state.code || "",
      code: undulate.stock.pack?.code || state.code || "",
      beg: undulate.stock.pack?.beg || undulate.rangeBeg || "",
      end: undulate.stock.pack?.end || undulate.rangeEnd || "",
      base: undulate.stock.pack?.base || null,
      stats: undulate.stock.pack?.stats || null,
      index: {
        key: undulate.index.key,
        loading: undulate.index.loading,
        error: undulate.index.error,
        beg: undulate.index.pack?.beg || "",
        end: undulate.index.pack?.end || "",
        base: undulate.index.pack?.base || null,
        stats: undulate.index.pack?.stats || null,
        code: undulate.index.pack?.code || "",
        name: undulate.index.pack?.name || "",
      },
    }),
    syncExtremumWithKline,
    loadExtremum,
    clearExtremum,
    extremumMeta: () => ({
      key: extremum.key,
      loading: extremum.loading,
      error: extremum.error,
      date: extremum.date || extremum.pack?.date || "",
      pack: extremum.pack,
      name: extremum.pack?.name || state.name || state.code || "",
      code: extremum.pack?.code || state.code || "",
    }),
    loadPosition,
    clearPosition,
    positionMeta: () => ({
      key: position.key,
      loading: position.loading,
      error: position.error,
      beg: position.beg || position.pack?.beg || "",
      end: position.end || position.pack?.end || "",
      pack: position.pack,
      name: position.pack?.name || state.name || state.code || "",
      code: position.pack?.code || state.code || "",
    }),
    loadTrader,
    clearTrader,
    syncTraderBoxHeight,
    traderMeta: () => ({
      key: trader.key,
      loading: trader.loading,
      error: trader.error,
      beg: trader.beg || trader.pack?.beg || "",
      end: trader.end || trader.pack?.end || "",
      pack: trader.pack,
      name: trader.pack?.name || state.name || state.code || "",
      code: trader.pack?.code || state.code || "",
    }),
    fillIndexSelect: fillPaneIndexSelect,
    fillFactorSelect: fillPaneFactorSelect,
    dirBarColor: dirBarColorPublic,
    DIR_BAR_COLORS,
    FACTOR_ORDER,
    runCompare,
    applyRangeAndRun,
    rerunForPaneIndex,
    setFormMeta,
  };
})();
