(() => {
  const POLL_MS = 1200;
  const WEEK = "日一二三四五六";
  const VIEW_KEY = "orbit-judgment-view";
  const SHARES_SPEC_KEY = "orbit-judgment-shares-specs";
  const SHARES_LOGIC_KEY = "orbit-judgment-shares-logic";
  const SHARES_PRESET_KEY = "orbit-judgment-shares-presets";
  const VIEW_META = {
    limit: {
      title: "ORBIT · 研判",
      sub: "按每日涨停池分批排名：阴跌 → 横盘 → 涨停，软评分排序并附日 K",
      from: "screen",
    },
    industry: {
      title: "ORBIT · 研判",
      sub: "按交易日复盘申万三级行业轮动：上涨/待涨/领涨均按所选交易日切片；行情与主力净流入（当日/5日/10日）回溯至该日。点击行业进入行情树",
      from: "analysis",
    },
    shares: {
      title: "ORBIT · 研判",
      sub: "筛选式工作台：从近月加点组成日子链，相邻日自选且/或，点节点编辑当日条件后开始筛选",
      from: "analysis",
    },
  };

  /** 供「导入 JSON」一键填入的示例方案 */
  const SHARES_SCHEME_EXAMPLE = {
    id: "lower_shadow_or_quiet",
    name: "收下影或缩实体",
    brief: "T0下影 OR 近5日≥3日|实体|≤1.2%",
    logic: "or",
    top: 50,
    groups: [
      {
        id: "lower_shadow",
        label: "最新一日收下影",
        logic: "and",
        days: [{ offset: 0, lower_ratio_min: 0.35, lower_ge_body: true }],
      },
      {
        id: "quiet_body",
        label: "近五日缩实体",
        min_hits: 3,
        days: [
          { offset: 0, body_abs_pct_max: 1.2 },
          { offset: 1, body_abs_pct_max: 1.2 },
          { offset: 2, body_abs_pct_max: 1.2 },
          { offset: 3, body_abs_pct_max: 1.2 },
          { offset: 4, body_abs_pct_max: 1.2 },
        ],
      },
    ],
  };

  const SHARES_PRIMARY_FIELDS = ["pct_chg", "body_pct", "lower_ratio", "vol_ratio"];

  const SHARES_FIELDS = [
    {
      key: "pct_chg",
      label: "涨跌幅 %",
      unit: "%",
      formula: "(C / Cprev − 1) × 100",
    },
    {
      key: "max_gain",
      label: "最大涨幅 %",
      unit: "%",
      formula: "(H / Cprev − 1) × 100",
    },
    {
      key: "max_drop",
      label: "最大跌幅 %",
      unit: "%",
      formula: "(L / Cprev − 1) × 100",
    },
    {
      key: "body_pct",
      label: "实体幅度 %",
      unit: "%",
      formula: "(C − O) / O × 100",
    },
    {
      key: "lower_ratio",
      label: "下影占比",
      unit: "",
      formula: "lower / span",
    },
    {
      key: "upper_ratio",
      label: "上影占比",
      unit: "",
      formula: "upper / span",
    },
    {
      key: "body_ratio",
      label: "实体占比",
      unit: "",
      formula: "body / span",
    },
    {
      key: "vol_ratio",
      label: "量比",
      unit: "×",
      formula: "V / mean(Vprev5)",
    },
    {
      key: "vol_chg",
      label: "量增幅 %",
      unit: "%",
      formula: "(V / Vprev − 1) × 100",
    },
  ];

  const SHARES_FORMULA_LEGEND = `
    <aside class="shares-formula-legend" aria-label="日线几何定义">
      <div class="shares-formula-legend__syms">
        <span><b>O</b> 开</span>
        <span><b>H</b> 高</span>
        <span><b>L</b> 低</span>
        <span><b>C</b> 收</span>
        <span><b>Cprev</b> 昨收</span>
        <span><b>V</b> 量</span>
      </div>
      <div class="shares-formula-legend__defs">
        <code>body = |C − O|</code>
        <code>span = H − L</code>
        <code>lower = min(O, C) − L</code>
        <code>upper = H − max(O, C)</code>
        <code>量比 = V / 前5日均量</code>
      </div>
    </aside>
  `;

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

  const shares = {
    top: 50,
    code: "",
    lookback: 22,
    logic: "and",
    status: "idle",
    dayRows: [],
    selectedDate: "",
    specsByDate: {},
    fields: {},
    fieldsMoreOpen: false,
    formulaOpen: false,
    presetMenuOpen: false,
    extraFields: [],
    items: [],
    updatedAt: "",
    candidateCount: 0,
    resultCount: 0,
    analyzedCount: 0,
    fingerprint: "",
    specSummary: [],
    note: "",
    pollTimer: 0,
    fetching: false,
    daysLoaded: false,
    started: false,
    error: "",
    message: "",
    presets: [],
    presetHint: "",
    presetImportOpen: false,
    presetImportDraft: "",
    /** 导入的形态方案（groups） */
    patternId: "",
    patternScheme: null,
    /** 未填字段时暂存的日内且/或/非，填入后写入 spec */
    fieldLogicDraft: {},
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
    if (["shares", "stock", "day", "kline", "个股", "日线"].includes(value)) return "shares";
    return "";
  }

  function current() {
    if (view === "industry") return industry;
    if (view === "shares") return shares;
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
    if (view === "shares" && current().code) {
      url.searchParams.set("code", current().code);
    } else {
      url.searchParams.delete("code");
    }
    history.replaceState({}, "", url);
  }

  function applyChrome() {
    const meta = VIEW_META[view] || VIEW_META.industry;
    document.title = meta.title;
    $("pageSub").textContent = meta.sub;
    document.body.dataset.screenMode = view;
    const workbench = $("sharesWorkbench");
    const benchBody = $("sharesBenchBody");
    if (workbench) workbench.classList.toggle("hidden", view !== "shares");
    if (benchBody) benchBody.classList.toggle("hidden", view !== "shares");
    const layout = document.querySelector(".screen-layout");
    if (layout && view !== "shares") {
      layout.classList.remove("is-editor-open", "is-editor-collapsed");
    }
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
    markSeg("sharesTopSeg", "top", shares.top);
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

  function sharesActiveSpecs() {
    return Object.keys(shares.specsByDate || {})
      .sort()
      .map((date) => ({ date, ...(shares.specsByDate[date] || {}) }))
      .filter((spec) => {
        return SHARES_FIELDS.some(
          (f) =>
            Number.isFinite(Number(spec[`${f.key}_min`])) ||
            Number.isFinite(Number(spec[`${f.key}_max`])),
        );
      });
  }

  function sharesSpecCount() {
    return sharesActiveSpecs().length;
  }

  function sharesDayHasSpec(date) {
    const spec = shares.specsByDate[date];
    if (!spec) return false;
    return SHARES_FIELDS.some(
      (f) =>
        Number.isFinite(Number(spec[`${f.key}_min`])) ||
        Number.isFinite(Number(spec[`${f.key}_max`])),
    );
  }

  function sharesSpecBrief(date) {
    const spec = shares.specsByDate[date];
    if (!spec || !sharesDayHasSpec(date)) return "";
    const parts = [];
    const fields = [];
    for (const f of SHARES_FIELDS) {
      const lo = spec[`${f.key}_min`];
      const hi = spec[`${f.key}_max`];
      if (lo == null && hi == null) continue;
      let text = "";
      if (lo != null && hi != null) text = `${f.label}${lo}~${hi}`;
      else if (lo != null) text = `${f.label}≥${lo}`;
      else text = `${f.label}≤${hi}`;
      if (spec[`${f.key}_not`]) text = `¬${text}`;
      parts.push(text);
      fields.push(f.key);
    }
    let body = "";
    const hasJoins = fields.slice(1).some((key) => spec[`${key}_join`] != null);
    if (hasJoins) {
      body = parts[0] || "";
      for (let i = 1; i < parts.length; i += 1) {
        const join = normalizeSharesJoin(spec[`${fields[i]}_join`]);
        body += (join === "or" ? " ∨ " : " ∧ ") + parts[i];
      }
    } else {
      const fieldLogic = normalizeSharesLogic(spec.logic);
      body =
        fieldLogic === "or"
          ? parts.join(" ∨ ")
          : fieldLogic === "not"
            ? `¬(${parts.join(" ∨ ")})`
            : parts.join(" ∧ ");
    }
    if (spec.not) body = `¬(${body})`;
    return body;
  }

  function readNumInput(value) {
    const text = String(value ?? "").trim();
    if (!text) return null;
    const n = Number(text);
    return Number.isFinite(n) ? n : null;
  }

  function normalizeSharesJoin(raw) {
    const v = String(raw || "").toLowerCase();
    if (v === "or" || v === "any") return "or";
    return "and";
  }

  function sharesJoinLabel(join) {
    return normalizeSharesJoin(join) === "or" ? "或" : "且";
  }

  function sharesActiveFieldKeys(spec) {
    if (!spec) return [];
    return SHARES_FIELDS.filter(
      (f) =>
        Number.isFinite(Number(spec[`${f.key}_min`])) ||
        Number.isFinite(Number(spec[`${f.key}_max`])),
    ).map((f) => f.key);
  }

  function syncFieldJoins(spec) {
    if (!spec || typeof spec !== "object") return;
    const keys = sharesActiveFieldKeys(spec);
    const mode = normalizeSharesLogic(spec.logic);
    for (const f of SHARES_FIELDS) {
      if (!keys.includes(f.key)) delete spec[`${f.key}_join`];
    }
    if (keys.length < 2 || mode === "not") {
      for (const key of keys) delete spec[`${key}_join`];
      return;
    }
    const fallback = mode === "or" ? "or" : "and";
    delete spec.logic;
    for (let i = 1; i < keys.length; i += 1) {
      const key = keys[i];
      if (spec[`${key}_join`] == null) spec[`${key}_join`] = fallback;
      else spec[`${key}_join`] = normalizeSharesJoin(spec[`${key}_join`]);
    }
    delete spec[`${keys[0]}_join`];
  }

  function syncDayJoins() {
    const dates = Object.keys(shares.specsByDate || {})
      .filter((date) => sharesDayHasSpec(date))
      .sort();
    const mode = normalizeSharesLogic(shares.logic);
    dates.forEach((date, idx) => {
      const spec = shares.specsByDate[date];
      if (!spec) return;
      if (idx === 0 || mode === "not" || dates.length < 2) {
        delete spec.join;
        return;
      }
      // 默认且；已有选择（且/或）一律保留，保证相邻日可各自不同
      if (spec.join == null) spec.join = "and";
      else spec.join = normalizeSharesJoin(spec.join);
    });
  }

  function applyUniformDayLogic(next) {
    const mode = normalizeSharesLogic(next);
    shares.logic = mode;
    const dates = Object.keys(shares.specsByDate || {})
      .filter((date) => sharesDayHasSpec(date))
      .sort();
    dates.forEach((date, idx) => {
      const spec = shares.specsByDate[date];
      if (!spec) return;
      if (idx === 0 || mode === "not" || dates.length < 2) delete spec.join;
      else spec.join = mode === "or" ? "or" : "and";
    });
  }

  function applyUniformFieldLogic(spec, next) {
    if (!spec) return;
    const mode = normalizeSharesLogic(next);
    const keys = sharesActiveFieldKeys(spec);
    if (mode === "not") {
      spec.logic = "not";
      for (const key of keys) delete spec[`${key}_join`];
      return;
    }
    if (keys.length < 2) {
      if (mode === "and") delete spec.logic;
      else spec.logic = mode;
      for (const key of keys) delete spec[`${key}_join`];
      return;
    }
    delete spec.logic;
    for (let i = 0; i < keys.length; i += 1) {
      const key = keys[i];
      if (i === 0) delete spec[`${key}_join`];
      else spec[`${key}_join`] = mode === "or" ? "or" : "and";
    }
  }

  function dayChainSummary() {
    const specs = sharesActiveSpecs();
    if (!specs.length) return "未设条件日";
    const mode = normalizeSharesLogic(shares.logic);
    if (mode === "not") {
      return `¬(${specs.map((s) => offsetLabel(sharesDateOffset(s.date)) || fmtMd(s.date)).join(" ∨ ")})`;
    }
    let text = offsetLabel(sharesDateOffset(specs[0].date)) || fmtMd(specs[0].date);
    for (let i = 1; i < specs.length; i += 1) {
      const join = normalizeSharesJoin(specs[i].join || "and");
      const tag = offsetLabel(sharesDateOffset(specs[i].date)) || fmtMd(specs[i].date);
      text += (join === "or" ? " ∨ " : " ∧ ") + tag;
    }
    return text;
  }

  function collectSharesForm(panel, opts = {}) {
    if (!panel || !shares.selectedDate) return;
    const date = shares.selectedDate;
    const next = {};
    const forced =
      opts.forceDayLogic != null ? normalizeSharesLogic(opts.forceDayLogic) : null;
    const dayLogicBtn = panel.querySelector("button[data-day-logic].is-active");
    const draft = shares.fieldLogicDraft[date];
    const dayLogic =
      forced ??
      (dayLogicBtn
        ? normalizeSharesLogic(dayLogicBtn.dataset.dayLogic)
        : draft
          ? normalizeSharesLogic(draft)
          : "and");
    if (panel.querySelector("button[data-day-negate].is-active")) next.not = true;
    const activeKeys = [];
    for (const f of SHARES_FIELDS) {
      const lo = readNumInput(panel.querySelector(`[data-field="${f.key}"][data-bound="min"]`)?.value);
      const hi = readNumInput(panel.querySelector(`[data-field="${f.key}"][data-bound="max"]`)?.value);
      if (lo != null) next[`${f.key}_min`] = lo;
      if (hi != null) next[`${f.key}_max`] = hi;
      if (lo != null || hi != null) {
        activeKeys.push(f.key);
        if (panel.querySelector(`button[data-field-not="${f.key}"].is-active`)) {
          next[`${f.key}_not`] = true;
        }
      }
    }
    if (activeKeys.length >= 2 && dayLogic === "not") {
      next.logic = "not";
    } else if (activeKeys.length >= 2) {
      const fallback = dayLogic === "or" ? "or" : "and";
      for (let i = 1; i < activeKeys.length; i += 1) {
        const key = activeKeys[i];
        if (forced != null) {
          next[`${key}_join`] = fallback;
        } else {
          const joinBtn = panel.querySelector(`button[data-field-join="${key}"].is-active`);
          next[`${key}_join`] = normalizeSharesJoin(joinBtn?.dataset.join || fallback);
        }
      }
    } else if (dayLogic !== "and") {
      next.logic = dayLogic;
    }
    const prev = shares.specsByDate[date] || {};
    if (prev.join != null && normalizeSharesLogic(shares.logic) !== "not") {
      next.join = normalizeSharesJoin(prev.join);
    }
    if (Object.keys(next).some((k) => k.endsWith("_min") || k.endsWith("_max"))) {
      if (forced != null) {
        applyUniformFieldLogic(next, forced);
        delete shares.fieldLogicDraft[date];
      } else if (draft) {
        applyUniformFieldLogic(next, draft);
        delete shares.fieldLogicDraft[date];
      } else syncFieldJoins(next);
      shares.specsByDate[date] = next;
    } else {
      delete shares.specsByDate[date];
      if (forced != null) shares.fieldLogicDraft[date] = forced;
    }
    syncDayJoins();
    persistSharesSpecs();
  }

  function sharesLogicLabel(logic) {
    const v = normalizeSharesLogic(logic);
    if (v === "or") return "OR（任一满足）";
    if (v === "not") return "NOT（全部不满足）";
    return "AND（全部满足）";
  }

  function normalizeSharesLogic(raw) {
    const v = String(raw || "").toLowerCase();
    if (v === "or" || v === "any") return "or";
    if (v === "not" || v === "nor" || v === "none") return "not";
    return "and";
  }

  function persistSharesSpecs() {
    try {
      sessionStorage.setItem(SHARES_SPEC_KEY, JSON.stringify(shares.specsByDate || {}));
      sessionStorage.setItem(SHARES_LOGIC_KEY, normalizeSharesLogic(shares.logic));
    } catch {
      /* ignore */
    }
  }

  function restoreSharesSpecs() {
    try {
      const logicRaw = sessionStorage.getItem(SHARES_LOGIC_KEY);
      if (logicRaw != null) shares.logic = normalizeSharesLogic(logicRaw);
    } catch {
      /* ignore */
    }
    try {
      const raw = sessionStorage.getItem(SHARES_SPEC_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        const cleaned = {};
        for (const [date, spec] of Object.entries(parsed)) {
          if (!spec || typeof spec !== "object") continue;
          const next = { ...spec };
          delete next.direction;
          for (const dead of [
            "amplitude_min",
            "amplitude_max",
            "body_abs_pct_min",
            "body_abs_pct_max",
            "lower_pct_min",
            "lower_pct_max",
            "upper_pct_min",
            "upper_pct_max",
          ]) {
            delete next[dead];
          }
          const has = SHARES_FIELDS.some(
            (f) =>
              Number.isFinite(Number(next[`${f.key}_min`])) ||
              Number.isFinite(Number(next[`${f.key}_max`])),
          );
          if (has) cleaned[date] = next;
        }
        shares.specsByDate = cleaned;
        syncDayJoins();
        for (const spec of Object.values(shares.specsByDate)) syncFieldJoins(spec);
        persistSharesSpecs();
      }
    } catch {
      /* ignore */
    }
  }

  function cleanSpecBounds(raw) {
    if (!raw || typeof raw !== "object") return null;
    const next = {};
    for (const f of SHARES_FIELDS) {
      const lo = Number(raw[`${f.key}_min`]);
      const hi = Number(raw[`${f.key}_max`]);
      if (Number.isFinite(lo)) next[`${f.key}_min`] = lo;
      if (Number.isFinite(hi)) next[`${f.key}_max`] = hi;
      if (
        (Number.isFinite(lo) || Number.isFinite(hi)) &&
        (raw[`${f.key}_not`] === true || raw[`${f.key}_not`] === 1 || raw[`${f.key}_not`] === "1")
      ) {
        next[`${f.key}_not`] = true;
      }
      if (
        (Number.isFinite(lo) || Number.isFinite(hi)) &&
        raw[`${f.key}_join`] != null
      ) {
        next[`${f.key}_join`] = normalizeSharesJoin(raw[`${f.key}_join`]);
      }
    }
    if (!Object.keys(next).some((k) => k.endsWith("_min") || k.endsWith("_max"))) return null;
    const logic = normalizeSharesLogic(raw.logic);
    if (logic === "not") next.logic = "not";
    else if (logic !== "and" && !sharesActiveFieldKeys(next).slice(1).some((k) => next[`${k}_join`] != null)) {
      next.logic = logic;
    }
    if (raw.not === true || raw.not === 1 || raw.not === "1") next.not = true;
    if (raw.join != null) next.join = normalizeSharesJoin(raw.join);
    syncFieldJoins(next);
    return next;
  }

  function sharesDateOffset(date) {
    return shares.dayRows.findIndex((d) => d.date === date);
  }

  function offsetLabel(offset) {
    const n = Number(offset);
    if (!Number.isFinite(n) || n < 0) return "?";
    return n === 0 ? "T0" : `T-${n}`;
  }

  function specsToRelativeDays() {
    const days = [];
    for (const spec of sharesActiveSpecs()) {
      const offset = sharesDateOffset(spec.date);
      if (offset < 0) continue;
      const bounds = cleanSpecBounds(spec);
      if (!bounds) continue;
      days.push({ offset, ...bounds });
    }
    days.sort((a, b) => a.offset - b.offset);
    return days;
  }

  function relativeDaysToSpecs(days) {
    const specs = {};
    let skipped = 0;
    const list = Array.isArray(days) ? days : [];
    for (const row of list) {
      const offset = Number(row && row.offset);
      if (!Number.isFinite(offset) || offset < 0) {
        skipped += 1;
        continue;
      }
      const day = shares.dayRows[offset];
      if (!day || !day.date) {
        skipped += 1;
        continue;
      }
      const bounds = cleanSpecBounds(row);
      if (!bounds) {
        skipped += 1;
        continue;
      }
      specs[day.date] = bounds;
    }
    return { specs, skipped };
  }

  function normalizeSharesPresetDays(rawDays) {
    if (!Array.isArray(rawDays)) return [];
    return rawDays
      .map((d) => {
        const offset = Number(d && d.offset);
        if (!Number.isFinite(offset) || offset < 0) return null;
        const bounds = cleanSpecBounds(d);
        if (!bounds) return null;
        return { offset, ...bounds };
      })
      .filter(Boolean);
  }

  function normalizeSchemeDay(raw) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    const offset = Number(raw.offset);
    if (!Number.isFinite(offset) || offset < 0) return null;
    const day = { offset };
    const bounds = cleanSpecBounds(raw);
    if (bounds) Object.assign(day, bounds);
    if (raw.lower_ge_body != null) day.lower_ge_body = Boolean(raw.lower_ge_body);
    const absMax = Number(raw.body_abs_pct_max);
    if (Number.isFinite(absMax) && absMax >= 0) day.body_abs_pct_max = absMax;
    const keys = Object.keys(day).filter((k) => k !== "offset");
    if (!keys.length) return null;
    return day;
  }

  function normalizeSchemeGroup(raw, index) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    const days = (Array.isArray(raw.days) ? raw.days : [])
      .map((d) => normalizeSchemeDay(d))
      .filter(Boolean);
    if (!days.length) return null;
    const minHits = Number(raw.min_hits);
    const id =
      String(raw.id || raw.name || `g${index}`)
        .trim()
        .slice(0, 48) || `g${index}`;
    const group = {
      id,
      label: String(raw.label || raw.name || id)
        .trim()
        .slice(0, 48),
      logic: normalizeSharesLogic(raw.logic),
      days,
    };
    if (Number.isFinite(minHits) && minHits >= 1) {
      group.min_hits = Math.min(days.length, Math.floor(minHits));
    }
    return group;
  }

  function isSchemeLike(raw) {
    return Boolean(raw && typeof raw === "object" && Array.isArray(raw.groups) && raw.groups.length);
  }

  function schemeGroupsToBranches(groups) {
    return (groups || []).map((g) => {
      const days = g.days || [];
      const rules = [];
      if (g.min_hits != null) {
        rules.push(`至少 ${g.min_hits}/${days.length} 日命中`);
      }
      for (const d of days) {
        const parts = [`${offsetLabel(d.offset)}`];
        for (const f of SHARES_FIELDS) {
          const lo = d[`${f.key}_min`];
          const hi = d[`${f.key}_max`];
          if (lo != null && hi != null) parts.push(`${f.key}[${lo},${hi}]`);
          else if (lo != null) parts.push(`${f.key}≥${lo}`);
          else if (hi != null) parts.push(`${f.key}≤${hi}`);
        }
        if (d.body_abs_pct_max != null) parts.push(`|实体|≤${d.body_abs_pct_max}%`);
        if (d.lower_ge_body) parts.push("下影≥实体");
        rules.push(parts.join(" · "));
      }
      return {
        id: g.id,
        label: g.label || g.id,
        rules,
      };
    });
  }

  function normalizeSharesPreset(raw, fallbackName) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    const name = String(raw.name || fallbackName || raw.id || "")
      .trim()
      .slice(0, 32);
    if (!name) return null;
    const id =
      String(raw.id || "").trim() ||
      `p_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
    const top = Number(raw.top);
    const brief = String(raw.brief || "").trim().slice(0, 80);

    if (isSchemeLike(raw)) {
      const groups = raw.groups
        .map((g, i) => normalizeSchemeGroup(g, i))
        .filter(Boolean);
      if (!groups.length) return null;
      const logic = normalizeSharesLogic(raw.logic || "or");
      return {
        id,
        name,
        kind: "scheme",
        brief,
        updatedAt: String(raw.updatedAt || new Date().toISOString()),
        top: Number.isFinite(top) ? top : undefined,
        logic,
        groups,
        scheme: {
          id,
          name,
          brief,
          logic,
          top: Number.isFinite(top) ? top : undefined,
          groups,
        },
      };
    }

    const days = normalizeSharesPresetDays(raw.days);
    if (!days.length) return null;
    return {
      id,
      name,
      kind: "days",
      brief,
      updatedAt: String(raw.updatedAt || new Date().toISOString()),
      top: Number.isFinite(top) ? top : undefined,
      logic: normalizeSharesLogic(raw.logic),
      days,
    };
  }

  function loadSharesPresets() {
    try {
      const raw = localStorage.getItem(SHARES_PRESET_KEY);
      if (!raw) {
        shares.presets = [];
        return;
      }
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        shares.presets = [];
        return;
      }
      shares.presets = parsed
        .map((p) => {
          const preset = normalizeSharesPreset(p);
          if (!preset || !String(preset.id || "").trim()) return null;
          return preset;
        })
        .filter(Boolean);
    } catch {
      shares.presets = [];
    }
  }

  function upsertSharesPreset(preset) {
    const existing = shares.presets.find((p) => p.name === preset.name);
    if (existing) {
      existing.days = preset.days;
      existing.groups = preset.groups;
      existing.scheme = preset.scheme;
      existing.kind = preset.kind || (preset.groups ? "scheme" : "days");
      existing.brief = preset.brief;
      existing.top = preset.top;
      existing.logic = normalizeSharesLogic(preset.logic);
      existing.updatedAt = new Date().toISOString();
      if (preset.id && !String(existing.id || "").startsWith("p_")) {
        /* keep stable id */
      } else if (preset.id) {
        existing.id = preset.id;
      }
      return existing;
    }
    const next = {
      ...preset,
      kind: preset.kind || (preset.groups ? "scheme" : "days"),
      logic: normalizeSharesLogic(preset.logic),
      id:
        String(preset.id || "").trim() ||
        `p_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
      updatedAt: new Date().toISOString(),
    };
    shares.presets.unshift(next);
    return next;
  }

  function parseSharesPresetImportPayload(rawText, fallbackName) {
    let data;
    try {
      data = JSON.parse(String(rawText || "").trim());
    } catch {
      return { error: "JSON 解析失败，请检查格式" };
    }

    let candidates = [];
    if (Array.isArray(data)) {
      const looksLikeDays =
        data.length > 0 &&
        data.every(
          (d) =>
            d &&
            typeof d === "object" &&
            !Array.isArray(d) &&
            Number.isFinite(Number(d.offset)) &&
            !Array.isArray(d.days) &&
            !Array.isArray(d.groups),
        );
      candidates = looksLikeDays ? [{ name: fallbackName, days: data }] : data;
    } else if (data && typeof data === "object") {
      if (Array.isArray(data.presets)) candidates = data.presets;
      else if (isSchemeLike(data)) candidates = [data];
      else if (Array.isArray(data.days)) candidates = [data];
      else return { error: "缺少 days / groups 字段（或 presets 数组）" };
    } else {
      return { error: "JSON 须为对象或数组" };
    }

    const presets = [];
    for (const item of candidates) {
      const preset = normalizeSharesPreset(item, fallbackName);
      if (preset) presets.push(preset);
    }
    if (!presets.length) {
      return {
        error:
          "未识别到有效方案（需 name + days，或含 groups 的形态方案；仅 days 数组时请先填方案名称）",
      };
    }
    return { presets };
  }

  function fillSharesSchemeExample() {
    const sample = SHARES_SCHEME_EXAMPLE;
    shares.presetImportOpen = true;
    shares.presetImportDraft = JSON.stringify(sample, null, 2);
    shares.presetHint = "已填入「收下影或缩实体」示例，确认后导入并套用";
    renderSharesPresetBar();
    const ta = $("sharesPresetImportText");
    if (ta) {
      ta.focus();
      try {
        ta.setSelectionRange(0, ta.value.length);
      } catch {
        /* ignore */
      }
    }
  }

  function importSharesPresetsFromText(rawText) {
    const fallbackName = ($("sharesPresetName")?.value || "").trim() || "导入方案";
    const parsed = parseSharesPresetImportPayload(rawText, fallbackName);
    if (parsed.error) {
      shares.presetHint = parsed.error;
      renderSharesPresetBar();
      return false;
    }
    const saved = parsed.presets.map((p) => upsertSharesPreset(p));
    persistSharesPresets();
    shares.presetImportOpen = false;
    shares.presetImportDraft = "";
    applySharesPreset(saved[0].id);
    shares.presetHint =
      saved.length === 1
        ? `已导入并套用「${saved[0].name}」，点「开始筛选」运行`
        : `已导入 ${saved.length} 个方案，已套用「${saved[0].name}」`;
    renderSharesPresetBar();
    return true;
  }

  function persistSharesPresets() {
    try {
      localStorage.setItem(SHARES_PRESET_KEY, JSON.stringify(shares.presets || []));
    } catch {
      /* ignore */
    }
  }

  function presetBrief(preset) {
    if (preset && (preset.kind === "scheme" || isSchemeLike(preset))) {
      const groups = preset.groups || [];
      const labels = groups.map((g) => g.label || g.id).filter(Boolean);
      const logic = normalizeSharesLogic(preset.logic || "or").toUpperCase();
      return `${groups.length}组 · ${logic}${labels.length ? ` · ${labels.join("/")}` : ""}`;
    }
    const days = (preset && preset.days) || [];
    if (!days.length) return "空";
    const labels = days
      .slice()
      .sort((a, b) => a.offset - b.offset)
      .map((d) => offsetLabel(d.offset));
    const logic = normalizeSharesLogic(preset && preset.logic).toUpperCase();
    return `${days.length}日 · ${logic} · ${labels.join("/")}`;
  }

  function saveSharesPreset(rawName) {
    collectSharesForm($("sharesCondPanel"));
    const name = String(rawName || "").trim();
    if (!name) {
      shares.presetHint = "请输入方案名称";
      renderSharesPresetBar();
      return false;
    }

    if (shares.patternScheme && isSchemeLike(shares.patternScheme)) {
      const existing = shares.presets.find((p) => p.name === name);
      upsertSharesPreset({
        id: existing?.id || shares.patternScheme.id || `p_${Date.now().toString(36)}`,
        name,
        kind: "scheme",
        brief: shares.patternScheme.brief || "",
        updatedAt: new Date().toISOString(),
        top: shares.top,
        logic: normalizeSharesLogic(shares.patternScheme.logic || "or"),
        groups: shares.patternScheme.groups,
        scheme: {
          ...shares.patternScheme,
          name,
          top: shares.top,
        },
      });
      persistSharesPresets();
      shares.presetHint = existing ? `已覆盖方案「${name}」` : `已保存形态方案「${name}」`;
      renderSharesPresetBar();
      return true;
    }

    const days = specsToRelativeDays();
    if (!days.length) {
      shares.presetHint = "请先为至少一个交易日设置条件，或导入含 groups 的 JSON";
      renderSharesPresetBar();
      return false;
    }
    const existing = shares.presets.find((p) => p.name === name);
    upsertSharesPreset({
      id: existing?.id || `p_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
      name,
      kind: "days",
      updatedAt: new Date().toISOString(),
      top: shares.top,
      logic: normalizeSharesLogic(shares.logic),
      days,
    });
    persistSharesPresets();
    shares.presetHint = existing ? `已覆盖方案「${name}」` : `已保存方案「${name}」`;
    renderSharesPresetBar();
    return true;
  }

  function applyImportedScheme(preset) {
    const scheme = preset.scheme || {
      id: preset.id,
      name: preset.name,
      brief: preset.brief || "",
      logic: preset.logic || "or",
      top: preset.top,
      groups: preset.groups,
    };
    shares.patternId = String(scheme.id || preset.id || "imported");
    shares.patternScheme = {
      id: shares.patternId,
      name: String(scheme.name || preset.name || shares.patternId),
      brief: String(scheme.brief || preset.brief || ""),
      logic: normalizeSharesLogic(scheme.logic || "or"),
      top: scheme.top,
      groups: scheme.groups,
    };
    shares.specsByDate = {};
    persistSharesSpecs();
    if (Number.isFinite(Number(preset.top))) {
      shares.top = Number(preset.top);
      renderSeg();
    } else if (Number.isFinite(Number(scheme.top))) {
      shares.top = Number(scheme.top);
      renderSeg();
    }
    stopPoll(shares);
    shares.started = false;
    shares.status = "idle";
    shares.items = [];
    shares.resultCount = 0;
    shares.analyzedCount = 0;
    shares.message = "";
    const panel = $("sharesCondPanel");
    if (panel) panel.dataset.date = "";
    shares.presetHint = `已套用形态「${shares.patternScheme.name}」（导入 JSON，点开始筛选）`;
    shares.presetMenuOpen = false;
    shares.presetImportOpen = false;
    renderAll();
    showError("");
    setLive("idle");
  }

  function applySharesPreset(id) {
    const preset = shares.presets.find((p) => p.id === id);
    if (!preset) return;
    if (preset.kind === "scheme" || isSchemeLike(preset)) {
      applyImportedScheme(preset);
      return;
    }
    if (!shares.dayRows.length) {
      shares.presetHint = "交易日尚未加载，请稍后重试";
      renderSharesPresetBar();
      return;
    }
    const { specs, skipped } = relativeDaysToSpecs(preset.days);
    if (!Object.keys(specs).length) {
      shares.presetHint = "方案中的相对日均超出当前窗口";
      renderSharesPresetBar();
      return;
    }
    clearSharesPatternMode();
    shares.specsByDate = specs;
    shares.logic = normalizeSharesLogic(preset.logic);
    syncDayJoins();
    persistSharesSpecs();
    if (Number.isFinite(Number(preset.top))) {
      shares.top = Number(preset.top);
      renderSeg();
    }
    const dates = Object.keys(specs).sort();
    if (!dates.includes(shares.selectedDate)) {
      shares.selectedDate = dates[0] || shares.selectedDate;
    }
    stopPoll(shares);
    shares.started = false;
    shares.status = "idle";
    shares.items = [];
    shares.resultCount = 0;
    shares.analyzedCount = 0;
    shares.message = "";
    const panel = $("sharesCondPanel");
    if (panel) panel.dataset.date = "";
    shares.presetHint = skipped
      ? `已套用「${preset.name}」（${skipped} 个相对日超出窗口已跳过）`
      : `已套用「${preset.name}」，点「开始筛选」运行`;
    shares.presetMenuOpen = false;
    shares.presetImportOpen = false;
    renderAll();
    showError("");
    setLive("idle");
  }


  function activePatternMeta() {
    if (shares.patternScheme && isSchemeLike(shares.patternScheme)) {
      return {
        id: shares.patternScheme.id,
        name: shares.patternScheme.name || shares.patternId,
        brief: shares.patternScheme.brief || "",
        branches: schemeGroupsToBranches(shares.patternScheme.groups),
        fromImport: true,
      };
    }
    return shares.patternId
      ? { id: shares.patternId, name: shares.patternId, brief: "", branches: [] }
      : null;
  }


  function clearSharesPatternMode() {
    shares.patternId = "";
    shares.patternScheme = null;
  }

  function deleteSharesPreset(id) {
    const before = shares.presets.length;
    shares.presets = shares.presets.filter((p) => p.id !== id);
    if (shares.presets.length === before) return;
    persistSharesPresets();
    shares.presetHint = "已删除方案";
    renderSharesPresetBar();
  }

  function renderSharesPresetBar() {
    const bar = $("sharesPresetBar");
    if (!bar) return;
    if (view !== "shares") {
      bar.innerHTML = "";
      bar.hidden = true;
      return;
    }
    bar.hidden = !shares.presetMenuOpen;
    if (!shares.presetMenuOpen) return;

    const active = document.activeElement;
    const keepNameFocus = active && active.id === "sharesPresetName";
    const keepImportFocus = active && active.id === "sharesPresetImportText";
    const prevName = keepNameFocus ? active.value : $("sharesPresetName")?.value ?? "";
    const importDraft = keepImportFocus
      ? active.value
      : $("sharesPresetImportText")?.value ?? shares.presetImportDraft ?? "";
    const importSel =
      keepImportFocus && typeof active.selectionStart === "number"
        ? { start: active.selectionStart, end: active.selectionEnd }
        : null;
    shares.presetImportDraft = importDraft;

    const saved = (shares.presets || [])
      .map((p) => {
        const kind = p.kind === "scheme" || isSchemeLike(p) ? "形态" : "多日";
        return `<li class="shares-preset-row">
          <button type="button" class="shares-preset-row__main" data-preset-apply="${esc(p.id)}">
            <span class="shares-preset-row__name">${esc(p.name)}</span>
            <span class="shares-preset-row__meta">${esc(kind)} · ${esc(presetBrief(p))}</span>
          </button>
          <button type="button" class="shares-preset-row__del" data-preset-del="${esc(p.id)}" title="删除" aria-label="删除 ${esc(p.name)}">×</button>
        </li>`;
      })
      .join("");


    bar.innerHTML = `
      <div class="shares-preset-pop__card">
        <header class="shares-preset-pop__head">
          <strong>方案</strong>
          <button type="button" class="shares-preset-pop__close" data-close-preset="1" aria-label="关闭">×</button>
        </header>
        <section class="shares-preset-pop__save">
          <input id="sharesPresetName" type="text" maxlength="32" placeholder="名称，保存当前筛选式" autocomplete="off" value="${esc(prevName)}" />
          <button type="button" class="btn" id="sharesPresetSaveBtn">保存</button>
        </section>
        <section class="shares-preset-pop__block">
          <h3>已存</h3>
          ${
            saved
              ? `<ul class="shares-preset-list">${saved}</ul>`
              : `<p class="shares-preset-pop__empty">还没有方案。设好筛选式后填写名称保存。</p>`
          }
        </section>
        <section class="shares-preset-pop__block">
          <div class="shares-preset-pop__import-head">
            <h3>导入</h3>
            <button type="button" class="btn ghost" id="sharesPresetImportBtn" aria-expanded="${shares.presetImportOpen ? "true" : "false"}">${shares.presetImportOpen ? "收起" : "粘贴 JSON"}</button>
          </div>
          ${
            shares.presetImportOpen
              ? `<div class="shares-preset-import">
                  <textarea id="sharesPresetImportText" rows="7" spellcheck="false" placeholder="粘贴 days 或多组 groups 方案 JSON">${esc(importDraft)}</textarea>
                  <div class="shares-preset-import__actions">
                    <button type="button" class="btn" id="sharesPresetImportConfirm">导入并套用</button>
                    <button type="button" class="btn ghost" id="sharesPresetImportExample">示例</button>
                    <button type="button" class="btn ghost" id="sharesPresetImportCancel">取消</button>
                  </div>
                </div>`
              : ""
          }
        </section>
        ${shares.presetHint ? `<p class="shares-preset-pop__hint">${esc(shares.presetHint)}</p>` : ""}
      </div>
    `;

    if (keepNameFocus) {
      const input = $("sharesPresetName");
      if (input) {
        input.focus();
        const len = input.value.length;
        try {
          input.setSelectionRange(len, len);
        } catch {
          /* ignore */
        }
      }
    } else if (keepImportFocus) {
      const ta = $("sharesPresetImportText");
      if (ta) {
        ta.focus();
        try {
          const start = importSel ? importSel.start : ta.value.length;
          const end = importSel ? importSel.end : ta.value.length;
          ta.setSelectionRange(start, end);
        } catch {
          /* ignore */
        }
      }
    }
  }

  function inferFieldLogic(spec, date) {
    const keys = sharesActiveFieldKeys(spec);
    if (!keys.length) {
      const draft = date && shares.fieldLogicDraft[date];
      return draft ? normalizeSharesLogic(draft) : "and";
    }
    if (!spec) return "and";
    if (normalizeSharesLogic(spec.logic) === "not") return "not";
    if (keys.length < 2) return normalizeSharesLogic(spec.logic);
    const joins = keys.slice(1).map((key) => normalizeSharesJoin(spec[`${key}_join`] || "and"));
    if (joins.every((j) => j === "or")) return "or";
    if (joins.every((j) => j === "and")) return "and";
    return "mixed";
  }

  function inferDayLogic() {
    const mode = normalizeSharesLogic(shares.logic);
    if (mode === "not") return "not";
    const specs = sharesActiveSpecs();
    if (specs.length < 2) return mode === "or" ? "or" : "and";
    const joins = specs.slice(1).map((s) => normalizeSharesJoin(s.join || "and"));
    if (joins.every((j) => j === "or")) return "or";
    if (joins.every((j) => j === "and")) return "and";
    return "mixed";
  }

  function fieldChainHtml(spec) {
    const keys = sharesActiveFieldKeys(spec);
    if (keys.length < 2) {
      return `<p class="shares-join-empty">再填一个字段后，可在字段间选且/或</p>`;
    }
    if (normalizeSharesLogic(spec.logic) === "not") {
      const labels = keys
        .map((key) => SHARES_FIELDS.find((f) => f.key === key)?.label || key)
        .join(" ∨ ");
      return `<p class="shares-join-empty">字段全部非：¬(${esc(labels)})</p>`;
    }
    const bits = [];
    keys.forEach((key, idx) => {
      const meta = SHARES_FIELDS.find((f) => f.key === key);
      const label = meta?.label || key;
      if (idx > 0) {
        const join = normalizeSharesJoin(spec[`${key}_join`] || "and");
        bits.push(`<span class="shares-join-seg" role="group" aria-label="与上一字段连接">
          <button type="button" data-field-join="${esc(key)}" data-join="and" class="${join === "and" ? "is-active" : ""}">且</button>
          <button type="button" data-field-join="${esc(key)}" data-join="or" class="${join === "or" ? "is-active" : ""}">或</button>
        </span>`);
      }
      bits.push(`<span class="shares-join-node">${esc(label)}</span>`);
    });
    return `<div class="shares-join-chain" aria-label="日内字段连接">${bits.join("")}</div>`;
  }

  function sharesExprDates() {
    const dates = new Set(
      Object.keys(shares.specsByDate || {}).filter((d) => sharesDayHasSpec(d)),
    );
    if (shares.selectedDate && !shares.patternId) dates.add(shares.selectedDate);
    return [...dates].sort();
  }

  function syncSharesEditorLayout() {
    const layout = document.querySelector(".screen-page-root[data-screen-mode='shares'] .screen-layout");
    if (!layout) return;
    const open = Boolean(shares.selectedDate || shares.patternId);
    layout.classList.toggle("is-editor-open", open);
    layout.classList.toggle("is-editor-collapsed", !open);
  }

  function renderSharesExprBar() {
    const bar = $("sharesExprBar");
    if (!bar || view !== "shares") return;
    syncDayJoins();

    if (shares.patternId) {
      const meta = activePatternMeta();
      const name = (meta && meta.name) || shares.patternId;
      const brief = (meta && meta.brief) || "";
      bar.innerHTML = `
        <div class="shares-expr-bar__main">
          <span class="shares-expr-bar__label">形态</span>
          <div class="shares-expr-chain">
            <div class="shares-expr-node is-pattern">
              <b>${esc(name)}</b>
              <span>${esc(brief)}</span>
            </div>
          </div>
        </div>
        <div class="shares-expr-bar__actions">
          <button type="button" class="btn" id="sharesRunBtn">开始筛选</button>
          <button type="button" class="btn ghost" id="sharesClearPatternBtn">退出形态</button>
          <button type="button" class="btn ghost" id="sharesPresetMenuBtn" aria-expanded="${shares.presetMenuOpen ? "true" : "false"}">方案</button>
        </div>
      `;
      return;
    }

    const dates = sharesExprDates();
    const mode = normalizeSharesLogic(shares.logic);
    let chain = "";
    if (!dates.length) {
      chain = `<p class="shares-expr-empty">从下方近月交易日加点，组成筛选式</p>`;
    } else if (mode === "not") {
      const labels = dates
        .map((d) => `${offsetLabel(sharesDateOffset(d))} ${fmtMd(d)}`)
        .join(" ∨ ");
      chain = `<p class="shares-expr-empty">全部非 ¬(${esc(labels)}) · <button type="button" class="shares-expr-text-btn" data-logic="and" data-exit-nor="1">退出全部非</button></p>`;
    } else {
      const bits = [];
      dates.forEach((date, idx) => {
        const has = sharesDayHasSpec(date);
        const brief = sharesSpecBrief(date) || "点此填写条件";
        const off = offsetLabel(sharesDateOffset(date));
        const active = date === shares.selectedDate ? " is-active" : "";
        const draft = has ? "" : " is-draft";
        if (idx > 0) {
          const spec = shares.specsByDate[date] || {};
          const join = normalizeSharesJoin(spec.join || "and");
          const canJoin = has && sharesDayHasSpec(dates[idx - 1]);
          bits.push(`<span class="shares-join-seg shares-join-seg--lg${canJoin ? "" : " is-disabled"}" role="group">
            <button type="button" data-day-join="${esc(date)}" data-join="and" class="${join === "and" ? "is-active" : ""}" ${canJoin ? "" : "disabled"}>且</button>
            <button type="button" data-day-join="${esc(date)}" data-join="or" class="${join === "or" ? "is-active" : ""}" ${canJoin ? "" : "disabled"}>或</button>
          </span>`);
        }
        bits.push(`<div class="shares-expr-node${active}${draft}" data-jump-date="${esc(date)}">
          <button type="button" class="shares-expr-node__hit" data-jump-date="${esc(date)}" title="${esc(brief)}">
            <span class="shares-expr-node__when"><b>${esc(off)}</b><em>${esc(fmtMd(date))}</em></span>
            <span class="shares-expr-node__brief">${esc(brief)}</span>
            ${has && (shares.specsByDate[date] || {}).not ? `<span class="shares-expr-node__neg">¬</span>` : ""}
          </button>
          <button type="button" class="shares-expr-node__x" data-remove-date="${esc(date)}" title="移出筛选式" aria-label="移出">×</button>
        </div>`);
      });
      chain = `<div class="shares-expr-chain" aria-label="筛选式日子链">${bits.join("")}</div>`;
    }

    bar.innerHTML = `
      <div class="shares-expr-bar__main">
        <span class="shares-expr-bar__label">筛选式</span>
        ${chain}
      </div>
      <div class="shares-expr-bar__actions">
        <button type="button" class="btn" id="sharesRunBtn" ${sharesSpecCount() || shares.patternId ? "" : "disabled"}>开始筛选</button>
        <button type="button" class="btn ghost" id="sharesPresetMenuBtn" aria-expanded="${shares.presetMenuOpen ? "true" : "false"}">方案</button>
        <div class="shares-expr-quick" title="一键统一相邻日连接">
          <button type="button" data-logic="and">统一且</button>
          <button type="button" data-logic="or">统一或</button>
          <button type="button" data-logic="not">全部非</button>
        </div>
      </div>
    `;
  }

  function refreshSharesChipsOnly() {
    renderSharesExprBar();
    renderSharesDayRail();
    renderSharesHead();
    renderSharesSummary();
  }

  function renderSharesSummary() {
    const n = sharesSpecCount();
    $("summaryBar").innerHTML = `
      <span>条件日 <b>${n}</b></span>
      <span>式 <b>${esc(dayChainSummary())}</b></span>
      <span>已分析 <b>${shares.analyzedCount || 0}</b> / ${shares.candidateCount || 0}</span>
      <span>入选 <b>${shares.resultCount || (shares.items || []).length}</b></span>
    `;
    $("marketMeta").textContent = shares.message || shares.updatedAt || "";
  }

  function renderSharesDayRail() {
    const rail = $("dayRail");
    if (!rail) return;
    if (!shares.dayRows.length) {
      rail.innerHTML = `<p class="screen-empty muted">暂无交易日</p>`;
      return;
    }
    const inExpr = new Set(sharesExprDates());
    rail.innerHTML = `
      <span class="shares-day-pool__label">近月加点</span>
      <div class="shares-day-pool__list">
        ${shares.dayRows
          .map((day, idx) => {
            const active = day.date === shares.selectedDate ? " is-active" : "";
            const has = sharesDayHasSpec(day.date);
            const pinned = inExpr.has(day.date) ? " is-pinned" : "";
            return `<button type="button" class="shares-day-pool-chip${active}${has ? " has-spec" : ""}${pinned}" data-date="${esc(day.date)}" title="${esc(sharesSpecBrief(day.date) || `${offsetLabel(idx)} · ${day.date}`)}">
              <b>${esc(offsetLabel(idx))}</b>
              <span>${esc(fmtMd(day.date))}</span>
            </button>`;
          })
          .join("")}
      </div>
    `;
  }

  function renderSharesHead() {
    if (shares.patternId) {
      const meta = activePatternMeta();
      const name = (meta && meta.name) || shares.patternId;
      $("dayHead").innerHTML = `
        <div class="shares-result-head">
          <div>
            <h2>结果</h2>
            <p>形态 · ${esc(name)} · 入选 <b>${shares.resultCount || (shares.items || []).length}</b></p>
          </div>
        </div>
      `;
      return;
    }
    $("dayHead").innerHTML = `
      <div class="shares-result-head">
        <div>
          <h2>结果</h2>
          <p>${esc(dayChainSummary())} · 入选 <b>${shares.resultCount || (shares.items || []).length}</b> · 已分析 <b>${shares.analyzedCount || 0}</b> / ${shares.candidateCount || 0}</p>
        </div>
      </div>
    `;
  }

  function sharesVisibleFieldKeys(spec) {
    const active = new Set(sharesActiveFieldKeys(spec));
    const extras = new Set(shares.extraFields || []);
    const keys = [];
    for (const f of SHARES_FIELDS) {
      if (SHARES_PRIMARY_FIELDS.includes(f.key) || active.has(f.key) || extras.has(f.key)) {
        keys.push(f.key);
      }
    }
    return keys;
  }

  function sharesFieldStackHtml(spec) {
    const keys = sharesVisibleFieldKeys(spec);
    const filled = sharesActiveFieldKeys(spec);
    const nor = normalizeSharesLogic(spec.logic) === "not";
    const parts = [];
    let filledIndex = 0;
    keys.forEach((key) => {
      const f = SHARES_FIELDS.find((x) => x.key === key);
      if (!f) return;
      const lo = spec[`${key}_min`];
      const hi = spec[`${key}_max`];
      const has = lo != null || hi != null || Number.isFinite(Number(lo)) || Number.isFinite(Number(hi));
      const reallyFilled = filled.includes(key);
      if (reallyFilled && filledIndex > 0 && !nor) {
        const join = normalizeSharesJoin(spec[`${key}_join`] || "and");
        parts.push(`<div class="shares-field-join" role="group" aria-label="与上一条件连接">
          <span class="shares-field-join__line" aria-hidden="true"></span>
          <button type="button" data-field-join="${esc(key)}" data-join="and" class="${join === "and" ? "is-active" : ""}">且</button>
          <button type="button" data-field-join="${esc(key)}" data-join="or" class="${join === "or" ? "is-active" : ""}">或</button>
          <span class="shares-field-join__line" aria-hidden="true"></span>
        </div>`);
      }
      if (reallyFilled) filledIndex += 1;
      const fieldNot = !!spec[`${key}_not`];
      parts.push(`<div class="shares-field-row${reallyFilled ? " is-filled" : ""}" data-field-row="${esc(key)}">
        <div class="shares-field-row__top">
          <span class="shares-field-row__name" title="${esc(f.formula || "")}">${esc(f.label)}</span>
          <button type="button" class="shares-field-not${fieldNot ? " is-active" : ""}" data-field-not="${esc(key)}" title="该字段取反" aria-pressed="${fieldNot ? "true" : "false"}">¬</button>
        </div>
        <div class="shares-cond-range">
          <input type="number" step="any" inputmode="decimal" data-field="${esc(key)}" data-bound="min" placeholder="最小" value="${lo == null || lo === "" ? "" : esc(lo)}" />
          <em>~</em>
          <input type="number" step="any" inputmode="decimal" data-field="${esc(key)}" data-bound="max" placeholder="最大" value="${hi == null || hi === "" ? "" : esc(hi)}" />
        </div>
      </div>`);
    });

    const unused = SHARES_FIELDS.filter((f) => !keys.includes(f.key));
    if (unused.length) {
      parts.push(`<div class="shares-field-add">
        <label class="shares-field-add__label">
          <span>添加指标</span>
          <select data-add-field="1">
            <option value="">选择…</option>
            ${unused.map((f) => `<option value="${esc(f.key)}">${esc(f.label)}</option>`).join("")}
          </select>
        </label>
      </div>`);
    }
    return parts.join("");
  }

  function renderSharesCondPanel(force) {
    const panel = $("sharesCondPanel");
    if (!panel) return;
    if (view !== "shares") return;
    syncSharesEditorLayout();

    if (shares.patternId) {
      const meta = activePatternMeta();
      const branches = (meta && meta.branches) || [];
      const branchHtml = branches
        .map((b) => {
          const rules = (b.rules || []).map((r) => `<li>${esc(r)}</li>`).join("");
          return `<div class="shares-pattern-branch">
            <p><b>${esc(b.label || b.id || "")}</b></p>
            ${rules ? `<ul>${rules}</ul>` : ""}
          </div>`;
        })
        .join("");
      panel.dataset.date = "__pattern__";
      panel.innerHTML = `
        <div class="shares-inspector">
          <header class="shares-inspector__head">
            <div>
              <strong>形态规则</strong>
              <span>${esc((meta && meta.name) || shares.patternId)}</span>
            </div>
          </header>
          <div class="shares-pattern-summary">
            ${branchHtml || `<p>${esc((meta && meta.brief) || "")}</p>`}
          </div>
        </div>
      `;
      return;
    }

    const date = shares.selectedDate;
    if (!date) {
      panel.innerHTML = `<div class="shares-inspector shares-inspector--empty">
        <p>从筛选式点节点，或从近月轨加点，开始编辑当日条件</p>
      </div>`;
      panel.dataset.date = "";
      return;
    }

    const editing =
      !force &&
      panel.dataset.date === date &&
      panel.querySelector("input, select") &&
      document.activeElement &&
      panel.contains(document.activeElement);
    if (editing) {
      refreshSharesChipsOnly();
      return;
    }
    if (!force && panel.dataset.date === date && panel.querySelector("[data-field]")) {
      refreshSharesChipsOnly();
      return;
    }

    const spec = shares.specsByDate[date] || {};
    syncFieldJoins(spec);
    syncDayJoins();
    const dayLogic = inferFieldLogic(spec, date);
    const dayNegated = !!spec.not;
    const off = sharesDateOffset(date);
    const brief = sharesSpecBrief(date);

    panel.dataset.date = date;
    panel.dataset.activeFields = sharesActiveFieldKeys(spec).join(",");
    panel.dataset.dayCount = String(sharesSpecCount());
    panel.innerHTML = `
      <div class="shares-inspector">
        <header class="shares-inspector__head">
          <div>
            <strong>${esc(offsetLabel(off))}</strong>
            <span>${esc(fmtMd(date))} ${esc(weekday(date))}</span>
          </div>
          <div class="shares-inspector__tools">
            <button type="button" class="shares-tool-btn${dayNegated ? " is-active" : ""}" data-day-negate="1" aria-pressed="${dayNegated ? "true" : "false"}" title="本日结果取反">本日¬</button>
            <button type="button" class="shares-tool-btn" id="sharesClearDayBtn" title="清空本日条件">清空</button>
            <button type="button" class="shares-tool-btn" data-close-editor="1" title="收起">收起</button>
          </div>
        </header>
        <div class="shares-inspector__mode" role="group" aria-label="字段组合">
          <span>字段</span>
          <button type="button" data-day-logic="and" class="${dayLogic === "and" ? "is-active" : ""}">且</button>
          <button type="button" data-day-logic="or" class="${dayLogic === "or" ? "is-active" : ""}">或</button>
          <button type="button" data-day-logic="not" class="${dayLogic === "not" ? "is-active" : ""}">非</button>
          ${dayLogic === "mixed" ? `<em class="shares-inspector__mixed">逐段</em>` : ""}
        </div>
        <div class="shares-inspector__fields">
          ${sharesFieldStackHtml(spec)}
        </div>
        <footer class="shares-inspector__foot">
          <code>${esc(brief || "填写区间后进入筛选式")}</code>
        </footer>
      </div>
    `;
  }
  function sharesCardHtml(row) {
    const industry = [row.l1_name, row.l2_name, row.l3_name].filter(Boolean).join(" / ");
    const err = row.error ? `<span class="screen-card-error">${esc(row.error)}</span>` : "";
    const href = fromHref(row.code || "");
    const days = row.days || [];
    const windowDays = row.window_days || [];
    const last = days[days.length - 1] || {};
    const m = last.metrics || row.latest || {};
    const fmtVolRatio = (v) => {
      const n = Number(v);
      return Number.isFinite(n) ? `${n.toFixed(2)}×` : "—";
    };
    const branchChips = (row.branches || [])
      .map((b) => {
        const label = b === "lower_shadow" ? "收下影" : b === "quiet_body" ? "缩实体" : b;
        return `<span class="screen-chip" data-tone="up"><em>命中</em>${esc(label)}</span>`;
      })
      .join("");
    const dayChips = (days.length ? days : windowDays)
      .map((d) => {
        const mm = d.metrics || d;
        const tip = [
          `涨跌 ${fmtPct(mm.pct_chg)}`,
          `最大涨 ${fmtPct(mm.max_gain)}`,
          `最大跌 ${fmtPct(mm.max_drop)}`,
          `实体 ${fmtPct(mm.body_pct)}`,
          d.body_abs_pct != null ? `|实体| ${fmtNum(d.body_abs_pct, 2)}%` : "",
          `下影比 ${fmtNum((mm.lower_ratio || 0) * 100, 0)}%`,
          `上影比 ${fmtNum((mm.upper_ratio || 0) * 100, 0)}%`,
          `实体比 ${fmtNum((mm.body_ratio || 0) * 100, 0)}%`,
          `量比 ${fmtVolRatio(mm.vol_ratio)}`,
          `量增幅 ${fmtPct(mm.vol_chg)}`,
          d.spec_text || "",
          d.is_quiet_body ? "小实体" : "",
          d.is_lower_shadow ? "收下影" : "",
        ]
          .filter(Boolean)
          .join(" · ");
        const mark = d.is_quiet_body || d.is_lower_shadow ? "up" : tone(mm.pct_chg);
        return `<span class="screen-chip" data-tone="${mark}" title="${esc(tip)}"><em>${esc(fmtMd(d.date))}</em>${fmtPct(mm.pct_chg)}</span>`;
      })
      .join("");
    const scoreLabel = row.branches
      ? row.quiet_count != null
        ? `${row.quiet_count}日缩`
        : "形态"
      : "命中日";
    const scoreValue = row.branches
      ? fmtNum(row.score, 2)
      : row.matched_days || days.length || 0;
    return `<article class="screen-card is-stock" data-code="${esc(row.code || "")}" data-key="${esc(row.code || "")}" tabindex="0">
      <a class="screen-card-head" href="${esc(href)}" title="打开公司详情">
        <span class="screen-rank">${row.rank || ""}</span>
        <div class="screen-card-name">
          <strong>${esc(row.name || "")}</strong>
          <span>${esc(row.code || "")}</span>
          ${industry ? `<em>${esc(industry)}</em>` : ""}
        </div>
        <div class="screen-card-score">
          <b>${scoreValue}</b>
          <span>${esc(scoreLabel)}</span>
        </div>
      </a>
      ${klineBlock(row.code || "")}
      <footer class="screen-card-meta">
        <span>涨跌 <b data-tone="${tone(m.pct_chg)}">${fmtPct(m.pct_chg)}</b></span>
        <span>最大涨 <b data-tone="${tone(m.max_gain)}">${fmtPct(m.max_gain)}</b></span>
        <span>最大跌 <b data-tone="${tone(m.max_drop)}">${fmtPct(m.max_drop)}</b></span>
        <span>实体 <b data-tone="${tone(m.body_pct)}">${fmtPct(m.body_pct)}</b></span>
        <span>下影比 <b>${fmtNum((m.lower_ratio || 0) * 100, 0)}</b>%</span>
        <span>上影比 <b>${fmtNum((m.upper_ratio || 0) * 100, 0)}</b>%</span>
        <span>实体比 <b>${fmtNum((m.body_ratio || 0) * 100, 0)}</b>%</span>
        <span>量比 <b data-tone="${tone((Number(m.vol_ratio) || 0) - 1)}">${fmtVolRatio(m.vol_ratio)}</b></span>
        <span>量增幅 <b data-tone="${tone(m.vol_chg)}">${fmtPct(m.vol_chg)}</b></span>
        ${branchChips}
        ${dayChips}
        ${err}
      </footer>
    </article>`;
  }

  function patchSharesCard(el, row) {
    const rank = el.querySelector(".screen-rank");
    if (rank) rank.textContent = String(row.rank || "");
    const score = el.querySelector(".screen-card-score b");
    if (score) score.textContent = String(row.matched_days || (row.days || []).length || 0);
  }

  function renderSharesCards() {
    const viewKey = `shares:${shares.fingerprint || shares.patternId || sharesSpecCount()}:${shares.code || "-"}`;
    let empty = "暂无符合条件的股票";
    if (shares.status === "running") empty = "正在分析，结果会逐只出现…";
    else if (shares.patternId) {
      if (!shares.started) empty = "形态方案已就绪，点「开始筛选」或右上角「重新分析」";
    } else if (!sharesSpecCount()) empty = "请先为至少一个交易日设置条件，再点重新分析";
    else if (!shares.started) empty = "条件已就绪，点右上角「重新分析」开始筛选";
    renderCards(
      shares.items || [],
      (row) => String(row.code || ""),
      sharesCardHtml,
      patchSharesCard,
      empty,
      viewKey,
    );
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
    if (view === "shares") {
      renderSharesSummary();
      renderSharesExprBar();
      renderSharesDayRail();
      renderSharesHead();
      renderSharesCondPanel();
      renderSharesPresetBar();
      renderSharesCards();
      window.OrbitPrefetch?.intent({ stocks: shares.items });
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

  function applySharesData(data) {
    shares.items = data.items || [];
    shares.updatedAt = data.updated_at || "";
    shares.candidateCount = data.candidate_count || 0;
    shares.resultCount = data.result_count || 0;
    shares.analyzedCount = data.analyzed_count || data.result_count || 0;
    shares.fingerprint = data.fingerprint || "";
    shares.specSummary = data.spec_summary || [];
    shares.note = data.note || "";
    if (data.logic && data.logic !== "chain") shares.logic = normalizeSharesLogic(data.logic);
    if (view === "shares") renderAll();
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
        showLoading(!partialIndustry, st.message);
        setLive(partialIndustry ? "live" : "busy");
        if (partialIndustry) {
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


  async function loadSharesDays() {
    try {
      const res = await fetch(`/api/screen/shares/days?days=${shares.lookback}`, {
        cache: "no-store",
      });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "交易日加载失败");
      const data = json.data || {};
      shares.dayRows = data.items || [];
      shares.fields = data.fields || {};
      shares.daysLoaded = true;
      const valid = new Set(shares.dayRows.map((d) => d.date));
      for (const date of Object.keys(shares.specsByDate || {})) {
        if (!valid.has(date)) delete shares.specsByDate[date];
      }
      persistSharesSpecs();
      if (!shares.dayRows.some((d) => d.date === shares.selectedDate)) {
        shares.selectedDate = (shares.dayRows[0] && shares.dayRows[0].date) || "";
      }
      if (view === "shares") renderAll();
    } catch (err) {
      shares.error = err.message || String(err);
      if (view === "shares") showError(shares.error);
    }
  }

  async function loadShares(force) {
    if (shares.fetching && !force) return;
    collectSharesForm($("sharesCondPanel"));
    if (!shares.daysLoaded) await loadSharesDays();

    const usePattern = Boolean(shares.patternScheme && isSchemeLike(shares.patternScheme));
    const daySpecs = sharesActiveSpecs();
    if (!usePattern && !daySpecs.length) {
      shares.started = false;
      shares.status = "idle";
      shares.items = [];
      shares.resultCount = 0;
      shares.message = "请先为交易日设置条件";
      if (view === "shares") {
        showLoading(false);
        renderAll();
        showError("请先为至少一个交易日设置涨跌 / 实体 / 影线占比等条件，或导入形态方案");
        setLive("idle");
      }
      return;
    }

    shares.fetching = true;
    shares.started = true;
    shares.error = "";
    if (view === "shares") showError("");
    if (force) {
      shares.items = [];
      shares.resultCount = 0;
      shares.analyzedCount = 0;
      if (view === "shares") {
        renderSharesSummary();
        renderSharesDayRail();
        renderSharesHead();
        renderSharesCards();
      }
      shares.message = shares.code
        ? `正在分析 ${shares.code}…`
        : usePattern
          ? "正在按形态方案筛选…"
          : "正在按日线条件筛选…";
      if (view === "shares") {
        showLoading(true, shares.message);
        setLive("busy");
      }
    }

    const body = usePattern
      ? {
          scheme: shares.patternScheme,
          top: shares.top,
          refresh: force ? "1" : "0",
          workers: 8,
        }
      : {
          days: daySpecs,
          logic: normalizeSharesLogic(shares.logic),
          top: shares.top,
          refresh: force ? "1" : "0",
          workers: 8,
        };
    if (shares.code) body.code = shares.code;

    try {
      const res = await fetch(usePattern ? "/api/screen/shares/pattern" : "/api/screen/shares", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        cache: "no-store",
      });
      const json = await res.json();
      if (!json.ok) {
        throw new Error(json.error || "请求失败");
      }
      applyPayload(shares, json.data || {}, applySharesData);
      if (shares.status === "running") schedulePoll(shares, () => loadShares(false));
      else stopPoll(shares);
    } catch (err) {
      shares.error = err.message || String(err);
      shares.status = "error";
      if (view === "shares") {
        showLoading(false);
        showError(shares.error);
        setLive("idle");
      }
      stopPoll(shares);
    } finally {
      shares.fetching = false;
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
    if (view === "shares") {
      if (!shares.daysLoaded) return loadSharesDays().then(() => {
        if (shares.started || force) return loadShares(force);
      });
      return loadShares(force);
    }
  }

  function openCompany(code) {
    if (!code) return;
    window.location.href = fromHref(code);
  }

  function submitCode(force) {
    const next = readCode();
    if (view !== "shares") return;
    if (next === shares.code && !force) return;
    stopPoll(shares);
    shares.code = next;
    syncUrl();
    loadShares(true);
  }

  function resetList() {
    const list = $("resultList");
    list.innerHTML = `<p class="screen-empty muted">加载中…</p>`;
    list.dataset.date = "";
  }

  function switchView(next) {
    if (next !== "limit" && next !== "industry" && next !== "shares") {
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
    if (view === "shares") {
      if (!shares.daysLoaded) loadSharesDays();
      else if (shares.started) loadShares(false);
      return;
    }
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
      if (view === "shares") current().code = readCode();
      if (view === "shares") collectSharesForm($("sharesCondPanel"));
      load(true);
    });

    $("codeInput").addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter") return;
      ev.preventDefault();
      if (view !== "shares") return;
      submitCode(true);
    });
    $("codeInput").addEventListener("change", () => {
      if (view !== "shares") return;
      submitCode(false);
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

    $("sharesTopSeg")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-top]");
      if (!btn) return;
      const top = Number(btn.dataset.top);
      if (top === shares.top) return;
      shares.top = top;
      renderSeg();
      if (view === "shares" && shares.started) loadShares(false);
    });

    $("sharesClearBtn")?.addEventListener("click", () => {
      if (view !== "shares") return;
      clearSharesPatternMode();
      shares.specsByDate = {};
      persistSharesSpecs();
      stopPoll(shares);
      shares.started = false;
      shares.status = "idle";
      shares.items = [];
      shares.resultCount = 0;
      shares.analyzedCount = 0;
      shares.message = "";
      shares.presetHint = "";
      shares.selectedDate = "";
      shares.presetMenuOpen = false;
      const panel = $("sharesCondPanel");
      if (panel) panel.dataset.date = "";
      renderAll();
      showError("");
      setLive("idle");
    });

    $("sharesCondPanel")?.addEventListener("input", (ev) => {
      if (view !== "shares") return;
      if (!ev.target.matches("input[data-field], select[data-field]")) return;
      const panel = $("sharesCondPanel");
      const prevKeys = panel?.dataset.activeFields || "";
      const prevDays = panel?.dataset.dayCount || "";
      collectSharesForm(panel);
      const keys = sharesActiveFieldKeys(shares.specsByDate[shares.selectedDate] || {}).join(",");
      const dayCount = String(sharesSpecCount());
      renderSharesSummary();
      renderSharesExprBar();
      renderSharesDayRail();
      renderSharesHead();
      if (panel && (keys !== prevKeys || dayCount !== prevDays)) {
        panel.dataset.activeFields = keys;
        panel.dataset.dayCount = dayCount;
        const field = ev.target.dataset.field;
        const bound = ev.target.dataset.bound;
        const start = ev.target.selectionStart;
        const end = ev.target.selectionEnd;
        renderSharesCondPanel(true);
        const again = panel.querySelector(`[data-field="${field}"][data-bound="${bound}"]`);
        if (again) {
          again.focus();
          try {
            if (typeof start === "number") again.setSelectionRange(start, end ?? start);
          } catch {
            /* ignore */
          }
        }
      } else {
        refreshSharesChipsOnly();
      }
    });

    $("sharesCondPanel")?.addEventListener("toggle", (ev) => {
      if (view !== "shares") return;
      const details = ev.target.closest("details.shares-formula-details");
      if (!details) return;
      shares.formulaOpen = details.open;
    }, true);

    $("sharesCondPanel")?.addEventListener("change", (ev) => {
      if (view !== "shares") return;
      if (ev.target.matches("select[data-add-field]")) {
        const key = ev.target.value;
        if (!key) return;
        if (!shares.extraFields) shares.extraFields = [];
        if (!shares.extraFields.includes(key)) shares.extraFields.push(key);
        collectSharesForm($("sharesCondPanel"));
        renderSharesCondPanel(true);
        return;
      }
      if (!ev.target.matches("select[data-field]")) return;
      collectSharesForm($("sharesCondPanel"));
      renderSharesSummary();
      renderSharesExprBar();
      renderSharesDayRail();
      renderSharesHead();
      renderSharesCondPanel(true);
    });

    function handleSharesLogicClick(ev) {
      const logicBtn = ev.target.closest("button[data-logic]");
      if (!logicBtn) return false;
      const next = normalizeSharesLogic(logicBtn.dataset.logic);
      const exitNor = logicBtn.dataset.exitNor === "1";
      if (!exitNor && next === inferDayLogic() && next !== "not") return true;
      applyUniformDayLogic(next);
      persistSharesSpecs();
      renderAll();
      return true;
    }

    function handleSharesDayJoinClick(ev) {
      const dayJoinBtn = ev.target.closest("button[data-day-join]");
      if (!dayJoinBtn || dayJoinBtn.disabled) return false;
      const date = dayJoinBtn.dataset.dayJoin;
      const join = normalizeSharesJoin(dayJoinBtn.dataset.join);
      const spec = date && shares.specsByDate[date];
      if (!spec) return true;
      if (normalizeSharesLogic(shares.logic) === "not") shares.logic = "and";
      spec.join = join;
      syncDayJoins();
      persistSharesSpecs();
      renderSharesExprBar();
      renderSharesSummary();
      renderSharesHead();
      return true;
    }

    $("sharesWorkbench")?.addEventListener("click", (ev) => {
      if (view !== "shares") return;
      if (ev.target.closest("#sharesRunBtn")) {
        shares.code = readCode();
        loadShares(true);
        return;
      }
      if (ev.target.closest("#sharesClearPatternBtn")) {
        clearSharesPatternMode();
        shares.presetHint = "已退出形态方案，可继续编辑筛选式";
        stopPoll(shares);
        shares.started = false;
        shares.status = "idle";
        shares.items = [];
        shares.resultCount = 0;
        const panel = $("sharesCondPanel");
        if (panel) panel.dataset.date = "";
        renderAll();
        showError("");
        setLive("idle");
        return;
      }
      if (ev.target.closest("#sharesPresetMenuBtn")) {
        shares.presetMenuOpen = !shares.presetMenuOpen;
        renderSharesExprBar();
        renderSharesPresetBar();
        return;
      }
      if (ev.target.closest("[data-close-preset]")) {
        shares.presetMenuOpen = false;
        renderSharesExprBar();
        renderSharesPresetBar();
        return;
      }
      if (handleSharesLogicClick(ev)) return;
      if (handleSharesDayJoinClick(ev)) return;
      const removeBtn = ev.target.closest("button[data-remove-date]");
      if (removeBtn) {
        const date = removeBtn.dataset.removeDate;
        if (date) {
          delete shares.specsByDate[date];
          delete shares.fieldLogicDraft[date];
          if (shares.selectedDate === date) shares.selectedDate = "";
          syncDayJoins();
          persistSharesSpecs();
          renderAll();
        }
        return;
      }
      const jump = ev.target.closest("[data-jump-date]");
      if (jump) {
        const date = jump.dataset.jumpDate;
        if (!date) return;
        collectSharesForm($("sharesCondPanel"));
        shares.selectedDate = date;
        renderAll();
      }
    });

    $("sharesCondPanel")?.addEventListener("click", (ev) => {
      if (view !== "shares") return;
      if (ev.target.closest("#sharesClearDayBtn")) {
        if (shares.selectedDate) {
          delete shares.specsByDate[shares.selectedDate];
          delete shares.fieldLogicDraft[shares.selectedDate];
        }
        syncDayJoins();
        persistSharesSpecs();
        shares.selectedDate = "";
        const panel = $("sharesCondPanel");
        if (panel) panel.dataset.date = "";
        renderAll();
        return;
      }
      if (ev.target.closest("[data-close-editor]")) {
        collectSharesForm($("sharesCondPanel"));
        shares.selectedDate = "";
        renderAll();
        return;
      }
      const dayLogicBtn = ev.target.closest("button[data-day-logic]");
      if (dayLogicBtn) {
        const panel = $("sharesCondPanel");
        if (!panel || !shares.selectedDate) return;
        const next = normalizeSharesLogic(dayLogicBtn.dataset.dayLogic);
        // 用点击目标覆盖 DOM 上仍亮着的旧按钮，避免 collect 读到旧且/或
        collectSharesForm(panel, { forceDayLogic: next });
        renderSharesSummary();
        renderSharesExprBar();
        renderSharesDayRail();
        renderSharesHead();
        renderSharesCondPanel(true);
        return;
      }
      const dayNegBtn = ev.target.closest("button[data-day-negate]");
      if (dayNegBtn) {
        const panel = $("sharesCondPanel");
        if (!panel) return;
        dayNegBtn.classList.toggle("is-active");
        dayNegBtn.setAttribute(
          "aria-pressed",
          dayNegBtn.classList.contains("is-active") ? "true" : "false",
        );
        collectSharesForm(panel);
        renderSharesSummary();
        renderSharesExprBar();
        renderSharesDayRail();
        renderSharesHead();
        renderSharesCondPanel(true);
        return;
      }
      const fieldNotBtn = ev.target.closest("button[data-field-not]");
      if (fieldNotBtn) {
        const panel = $("sharesCondPanel");
        if (!panel) return;
        fieldNotBtn.classList.toggle("is-active");
        fieldNotBtn.setAttribute(
          "aria-pressed",
          fieldNotBtn.classList.contains("is-active") ? "true" : "false",
        );
        collectSharesForm(panel);
        renderSharesSummary();
        renderSharesExprBar();
        renderSharesDayRail();
        renderSharesHead();
        renderSharesCondPanel(true);
        return;
      }
      const fieldJoinBtn = ev.target.closest("button[data-field-join]");
      if (fieldJoinBtn) {
        const panel = $("sharesCondPanel");
        if (!panel || !shares.selectedDate) return;
        // 先记下点击目标，再收集表单（此时 DOM 上仍是旧 is-active）
        const key = fieldJoinBtn.dataset.fieldJoin;
        const join = normalizeSharesJoin(fieldJoinBtn.dataset.join);
        if (!key) return;
        collectSharesForm(panel);
        const spec = shares.specsByDate[shares.selectedDate];
        if (!spec) return;
        delete spec.logic;
        spec[`${key}_join`] = join;
        syncFieldJoins(spec);
        persistSharesSpecs();
        renderSharesSummary();
        renderSharesExprBar();
        renderSharesDayRail();
        renderSharesHead();
        renderSharesCondPanel(true);
      }
    });

    $("sharesPresetBar")?.addEventListener("click", (ev) => {
      if (view !== "shares") return;
      if (ev.target.closest("[data-close-preset]")) {
        shares.presetMenuOpen = false;
        renderSharesExprBar();
        renderSharesPresetBar();
        return;
      }
      if (ev.target.closest("#sharesPresetSaveBtn")) {
        const name = $("sharesPresetName")?.value || "";
        saveSharesPreset(name);
        return;
      }
      if (ev.target.closest("#sharesPresetImportBtn")) {
        const ta = $("sharesPresetImportText");
        if (ta) shares.presetImportDraft = ta.value;
        shares.presetImportOpen = !shares.presetImportOpen;
        if (shares.presetImportOpen) shares.presetHint = "";
        renderSharesPresetBar();
        if (shares.presetImportOpen) $("sharesPresetImportText")?.focus();
        return;
      }
      if (ev.target.closest("#sharesPresetImportCancel")) {
        const ta = $("sharesPresetImportText");
        if (ta) shares.presetImportDraft = ta.value;
        shares.presetImportOpen = false;
        renderSharesPresetBar();
        return;
      }
      if (ev.target.closest("#sharesPresetImportConfirm")) {
        const text = $("sharesPresetImportText")?.value || shares.presetImportDraft || "";
        shares.presetImportDraft = text;
        importSharesPresetsFromText(text);
        return;
      }
      if (ev.target.closest("#sharesPresetImportExample")) {
        fillSharesSchemeExample();
        return;
      }
      const del = ev.target.closest("[data-preset-del]");
      if (del) {
        deleteSharesPreset(del.dataset.presetDel);
        return;
      }
      const apply = ev.target.closest("[data-preset-apply]");
      if (apply) {
        applySharesPreset(apply.dataset.presetApply);
      }
    });

    $("sharesPresetBar")?.addEventListener("input", (ev) => {
      if (view !== "shares") return;
      if (ev.target && ev.target.id === "sharesPresetImportText") {
        shares.presetImportDraft = ev.target.value;
      }
    });

    $("sharesPresetBar")?.addEventListener("keydown", (ev) => {
      if (view !== "shares") return;
      if (ev.key === "Escape" && shares.presetImportOpen) {
        ev.preventDefault();
        const ta = $("sharesPresetImportText");
        if (ta) shares.presetImportDraft = ta.value;
        shares.presetImportOpen = false;
        renderSharesPresetBar();
        return;
      }
      if (ev.key !== "Enter") return;
      if (!ev.target.matches("#sharesPresetName")) return;
      ev.preventDefault();
      saveSharesPreset(ev.target.value || "");
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
      if (!date) return;
      if (view === "shares") {
        collectSharesForm($("sharesCondPanel"));
        shares.selectedDate = date;
        renderAll();
        return;
      }
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
    const startCode = String(params.get("code") || "").replace(/\D/g, "").slice(-6);
    if (startCode.length === 6) return "shares";
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
    shares.code = startCode;
    $("codeInput").value = startCode;
  }

  restoreSharesSpecs();
  loadSharesPresets();
  view = initialView();
  applyChrome();
  bindEvents();
  window.OrbitPrefetch?.bindHover($("resultList"), "article.is-stock[data-code]");
  window.OrbitPrefetch?.boot("analysis");
  load(false);
})();
