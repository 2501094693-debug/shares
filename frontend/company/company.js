const params = new URLSearchParams(window.location.search);
const code = (params.get("code") || "").trim();
const nameHint = (params.get("name") || "").trim();
const industry = (params.get("industry") || "").trim();

const DEFAULT_DAYS = 3;
/** 后端未返回 full_days 时的兜底（约 50 年） */
const FULL_DAYS = 365 * 50 + 5;

const KINDS = [
  { key: "exchange", title: "交易所公告", empty: "暂无交易所公告" },
  { key: "cninfo", title: "巨潮公告", empty: "暂无巨潮公告" },
  { key: "designated_press", title: "七报七网", empty: "暂无指定披露媒体新闻" },
  { key: "official_news", title: "官方新闻", empty: "暂无官方新闻" },
  { key: "other_news", title: "其他新闻", empty: "暂无其他外部新闻" },
  { key: "reports", title: "机构研报", empty: "暂无机构研报" },
];

/** @type {Record<string, { days: number, fullDays: number, items: any[], loading: boolean, exhausted: boolean, updatedAt: string }>} */
const sectionState = Object.fromEntries(
  KINDS.map(({ key }) => [
    key,
    {
      days: DEFAULT_DAYS,
      fullDays: FULL_DAYS,
      items: [],
      loading: false,
      exhausted: false,
      updatedAt: "",
    },
  ])
);

const els = {
  pageTitle: document.getElementById("pageTitle"),
  pageSub: document.getElementById("pageSub"),
  backLink: document.getElementById("backLink"),
  companyBreadcrumb: document.getElementById("companyBreadcrumb"),
  companyName: document.getElementById("companyName"),
  companyCodeChip: document.getElementById("companyCodeChip"),
  quoteStrip: document.getElementById("quoteStrip"),
  metricsGrid: document.getElementById("metricsGrid"),
  metricsPanels: document.getElementById("metricsPanels"),
  chartTabs: document.getElementById("chartTabs"),
  chartAdjust: document.getElementById("chartAdjust"),
  chartMeta: document.getElementById("chartMeta"),
  chartHoverCard: document.getElementById("chartHoverCard"),
  chartWrap: document.getElementById("chartWrap"),
  priceChart: document.getElementById("priceChart"),
  chartEmpty: document.getElementById("chartEmpty"),
  chartAxisScroll: document.getElementById("chartAxisScroll"),
  chartScrollBar: document.getElementById("chartScrollBar"),
  refreshNewsBtn: document.getElementById("refreshNewsBtn"),
  errorBox: document.getElementById("errorBox"),
};

/** @type {{ mode: string, adjust: 'qfq'|'none', loading: boolean, kind: 'intraday'|'kline', items: any[], allItems: any[], viewStart: number, viewSize: number, preClose: number|null, source: string, meta: string }} */
const chartState = {
  mode: "day",
  adjust: "qfq",
  loading: false,
  kind: "kline",
  items: [],
  allItems: [],
  viewStart: 0,
  viewSize: 90,
  preClose: null,
  source: "",
  meta: "",
};

const CHART_MODES = {
  intraday: { label: "分时", kind: "intraday", ndays: 1, viewSize: 0 },
  intraday5: { label: "五日", kind: "intraday", ndays: 5, viewSize: 0 },
  "1m": { label: "1分", kind: "kline", period: "1m", limit: 720, viewSize: 240, adjust: "none" },
  "5m": { label: "5分", kind: "kline", period: "5m", limit: 480, viewSize: 96, adjust: "none" },
  "15m": { label: "15分", kind: "kline", period: "15m", limit: 360, viewSize: 80, adjust: "none" },
  "30m": { label: "30分", kind: "kline", period: "30m", limit: 360, viewSize: 80, adjust: "none" },
  "60m": { label: "60分", kind: "kline", period: "60m", limit: 240, viewSize: 72, adjust: "none" },
  day: { label: "日K", kind: "kline", period: "day", limit: 720, viewSize: 90, adjust: "qfq" },
  week: { label: "周K", kind: "kline", period: "week", limit: 360, viewSize: 80, adjust: "qfq" },
  month: { label: "月K", kind: "kline", period: "month", limit: 240, viewSize: 72, adjust: "qfq" },
};

const MINUTE_KLINE_MODES = new Set(["1m", "5m", "15m", "30m", "60m"]);
const ADJUSTABLE_KLINE_MODES = new Set(["day", "week", "month"]);

function isMinuteKline(mode) {
  return MINUTE_KLINE_MODES.has(mode);
}

function isAdjustableKline(mode) {
  return ADJUSTABLE_KLINE_MODES.has(mode);
}

function klineAdjustFor(mode) {
  if (isAdjustableKline(mode)) return chartState.adjust === "none" ? "none" : "qfq";
  const conf = CHART_MODES[mode];
  return conf?.adjust || "none";
}

function syncChartAdjustUi(mode = chartState.mode) {
  if (!els.chartAdjust) return;
  const show = isAdjustableKline(mode);
  els.chartAdjust.classList.toggle("hidden", !show);
  const current = klineAdjustFor(mode);
  els.chartAdjust.querySelectorAll("[data-adjust]").forEach((el) => {
    const active = el.getAttribute("data-adjust") === current;
    el.classList.toggle("is-active", active);
    el.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

/** K 均线：周期按当前 K 线根数（周K 的 MA5 = 5 周，1分的 MA5 = 5 分钟） */
const KLINE_MA_LINES = [
  { period: 5, key: "ma5", label: "MA5", color: "#f0b429" },
  { period: 10, key: "ma10", label: "MA10", color: "#5b9dff" },
  { period: 20, key: "ma20", label: "MA20", color: "#d48cff" },
];

function computeSmaSeries(closes, period) {
  const n = closes.length;
  const out = new Array(n).fill(null);
  if (period <= 0 || n < period) return out;
  for (let i = period - 1; i < n; i += 1) {
    let sum = 0;
    let ok = true;
    for (let j = i - period + 1; j <= i; j += 1) {
      const v = Number(closes[j]);
      if (!Number.isFinite(v)) {
        ok = false;
        break;
      }
      sum += v;
    }
    // 前 period-1 根及缺数窗口保持 null，绝不写 0
    if (ok) out[i] = sum / period;
  }
  return out;
}

function maPoint(vals, index) {
  if (!Array.isArray(vals) || index == null || index < 0 || index >= vals.length) {
    return null;
  }
  const raw = vals[index];
  if (raw == null || raw === "") return null;
  const v = Number(raw);
  return Number.isFinite(v) ? v : null;
}

function getKlineMaBundle() {
  const all = chartState.allItems || [];
  const closes = all.map((d) => Number(d.close));
  const full = {};
  for (const line of KLINE_MA_LINES) {
    full[line.key] = computeSmaSeries(closes, line.period);
  }
  const { start, size } = chartViewWindow();
  const visible = {};
  for (const line of KLINE_MA_LINES) {
    visible[line.key] = (full[line.key] || []).slice(start, start + size);
  }
  return { full, visible };
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const json = await res.json();
  if (!res.ok || !json.ok) {
    throw new Error(json.error || `请求失败 (${res.status})`);
  }
  return json;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function displayValue(v) {
  if (v == null || String(v).trim() === "") return "-";
  return String(v).trim();
}

function changeClass(v) {
  const text = displayValue(v);
  if (text === "-") return "";
  const num = parseFloat(String(text).replace(/%/g, "").replace(/,/g, ""));
  if (!Number.isFinite(num)) return "";
  if (num > 0) return "change-up";
  if (num < 0) return "change-down";
  return "";
}

function truncateText(text, max = 160) {
  const s = String(text || "").trim();
  if (s.length <= max) return s;
  return `${s.slice(0, max)}…`;
}

function setError(message) {
  if (!message) {
    els.errorBox.classList.add("hidden");
    els.errorBox.textContent = "";
    return;
  }
  els.errorBox.textContent = message;
  els.errorBox.classList.remove("hidden");
}

function sectionEls(kind) {
  return {
    meta: document.querySelector(`[data-meta="${kind}"]`),
    body: document.querySelector(`[data-body="${kind}"]`),
    list: document.querySelector(`[data-list="${kind}"]`),
    hint: document.querySelector(`[data-hint="${kind}"]`),
  };
}

function daysLabel(days) {
  if (days <= DEFAULT_DAYS) return "最新";
  if (days >= 360) {
    const years = days / 365;
    const rounded = years >= 10 ? Math.round(years) : Math.round(years * 10) / 10;
    return `近约 ${rounded} 年`;
  }
  return `近 ${days} 天`;
}

/** 逐步放大窗口；接近上限时一次拉满，便于尽量深回溯 */
function nextDayWindow(current, fullDays) {
  const cur = Math.max(1, Number(current) || DEFAULT_DAYS);
  const cap = Math.max(cur, Number(fullDays) || FULL_DAYS);
  if (cur >= cap) return null;

  let next;
  if (cur < 14) next = 14;
  else if (cur < 30) next = 30;
  else if (cur < 90) next = 90;
  else if (cur < 180) next = 180;
  else if (cur < 365) next = 365;
  else if (cur < 730) next = 730;
  else next = Math.ceil(cur * 1.5);

  if (next >= cap * 0.9) next = cap;
  return Math.min(Math.max(next, cur + 1), cap);
}

function renderQuote(stock) {
  const cells = [
    ["最新", stock.price, ""],
    ["涨幅", stock.change_1d, changeClass(stock.change_1d)],
    ["涨跌", stock.change_amt, changeClass(stock.change_amt)],
    [
      "市值",
      stock.total_market_cap ||
        (stock.market_cap ? `${displayValue(stock.market_cap)}亿` : ""),
      "",
    ],
    ["换手", stock.turnover, ""],
  ];
  els.quoteStrip.innerHTML = cells
    .map(([label, value, cls]) => metricCell([label, value, cls]))
    .join("");
}

/** 指标含义说明（点击展示，尽量白话） */
const METRIC_TIPS = {
  最新: "现在这只股票的最新成交价格。",
  涨幅: "今天比昨天收盘涨了还是跌了，用百分比表示。比如 +2% 就是比昨天贵了 2%。",
  涨跌: "今天比昨天收盘贵了或便宜了多少钱（元）。",
  市值: "按现在股价算，整家公司值多少钱：股价 × 全部股份。",
  换手: "今天卖掉又买走的股份，大概占能流通股份的多少。越高说明今天买卖越热闹。",
  今开: "今天开盘时的第一笔成交价。",
  昨收: "昨天收盘时的价格，用来对比今天涨跌。",
  最高: "今天到现在，成交过的最高价。",
  最低: "今天到现在，成交过的最低价。",
  均价: "把今天所有成交平均一下，大概多少钱一股买到的。",
  总手: "今天一共成交了多少手。1 手 = 100 股。",
  金额: "今天一共成交了多少钱。",
  "换手(实)": "只拿真正容易卖掉的股份来算活跃度，比普通换手更能看出“好卖的那部分”交易有多热。",
  现手: "刚刚那一笔买卖成交了多少手。",
  量比: "今天到现在平均每分钟成交量，和过去几天同时段比。大于 1 说明今天成交比平时更活跃。",
  振幅: "今天最高价和最低价差了多少，相对昨天收盘的比例。越大说明今天价格晃得越厉害。",
  实体涨幅: "从今天开盘价到现在的涨跌，主要看开盘以后实际走出的方向。",
  涨停: "今天按规定允许涨到的最高价。碰到它往往买不进或很难买。",
  跌停: "今天按规定允许跌到的最低价。碰到它往往卖不出或很难卖。",
  外盘: "主动按卖价买进去的成交量。多了，常被看作买的人更积极。",
  内盘: "主动按买价卖出来的成交量。多了，常被看作卖的人更积极。",
  委买: "现在排队等着买的委托量有多少。",
  委卖: "现在排队等着卖的委托量有多少。",
  委差: "想买的量减去想卖的量。正数说明买的人排队更多，负数相反。",
  委比: "买卖排队力量的对比。越接近 +100% 买盘越强，越接近 −100% 卖盘越强。",
  盘后委买: "收盘后那段固定价格交易里，还有多少人挂单想买。",
  盘后量: "收盘后那段时间成交了多少。",
  盘后额: "收盘后那段时间成交了多少钱。",
  近1日: "最近 1 个交易日涨了还是跌了多少。",
  "3日": "最近 3 个交易日累计涨跌多少。",
  "5日": "最近 5 个交易日累计涨跌多少。",
  "10日": "最近 10 个交易日累计涨跌多少。",
  "20日": "最近 20 个交易日累计涨跌多少（大约一个月）。",
  "60日": "最近 60 个交易日累计涨跌多少（大约三个月）。",
  近半年: "最近大约半年累计涨跌多少。",
  近1年: "最近大约一年累计涨跌多少。",
  今年: "从今年开年到现在，累计涨跌多少。",
  "52周最高": "过去一年里出现过的最高价（已按分红送股等做过前复权调整）。",
  "52周最低": "过去一年里出现过的最低价（已按分红送股等做过前复权调整）。",
  历史最高: "上市以来出现过的最高价（前复权后，方便和现在价格对比）。",
  历史最低: "上市以来出现过的最低价（前复权后，方便和现在价格对比）。",
  "市盈率(动)": "用现在市值去除以“预计今年能赚多少钱”。越低通常越便宜，但还要看行业和增长。",
  "市盈率(静)": "用现在市值去除以“去年已经赚到的钱”。看历史盈利贵不贵。",
  "市盈率(TTM)": "用现在市值去除以“最近四个季度一共赚了多少”。看最近一年盈利贵不贵。",
  市净率: "股价相对公司账面净资产贵不贵。数字越小，相对净资产越便宜。",
  "市销率(TTM)": "用现在市值去除以最近一年的销售收入。适合看还没稳定赚钱、但收入很重要的公司。",
  每股收益: "摊到每一股上，公司最近赚了多少钱。",
  每股净资产: "摊到每一股上，公司账面上有多少净资产。",
  净资产收益率: "公司用股东的钱，一年大概能赚回百分之几。越高通常说明赚钱能力越强。",
  "股息(TTM)": "最近一年，平均每股大概分了多少红（税前，仅供参考）。",
  股息率: "按现在股价算，分红收益率大概多少。比如 3%，相当于股价里约有 3% 来自分红。",
  净利增速: "净利润比去年同期增长了多少。正数是赚得更多，负数是赚得更少。",
  营收增速: "销售收入比去年同期增长了多少。",
  总股本: "公司一共发行了多少股。",
  流通股: "现在能在市场上买卖的股份有多少。",
  自由流通股: "去掉大股东等不太容易拿出来卖的股份后，真正好流通的股份大概有多少。",
  总市值: "按现价算，整家公司值多少钱。",
  流通市值: "按现价算，能流通的那部分股份值多少钱。",
  自由流通市值: "按现价算，真正好流通的那部分股份值多少钱。",
  发行股本: "发行或披露口径下的股本数量。",
  注册资本: "工商登记里写的注册资本。",
  纳入时间: "这只股票被放进当前这个申万行业分类的时间。",
  上市时间: "这只股票正式上市交易的日子。",
};

function metricTip(label) {
  return METRIC_TIPS[label] || "";
}

function metricCell([label, value, cls = ""]) {
  const tip = metricTip(label);
  const tipAttr = tip ? ` data-tip="${escapeHtml(tip)}"` : "";
  const tipClass = tip ? " has-tip" : "";
  const tipBtn = tip
    ? ` role="button" tabindex="0" aria-expanded="false" aria-label="${escapeHtml(label)}：查看指标说明"`
    : "";
  return `
    <div class="stat-cell${tipClass}"${tipAttr}${tipBtn}>
      <span class="detail-label">${escapeHtml(label)}</span>
      <span class="detail-value ${cls}">${escapeHtml(displayValue(value))}</span>
    </div>`;
}

function closeMetricTips(except = null) {
  document.querySelectorAll(".stat-cell.has-tip.is-tip-open").forEach((el) => {
    if (except && el === except) return;
    el.classList.remove("is-tip-open");
    el.setAttribute("aria-expanded", "false");
  });
}

function setupMetricTips() {
  const root = document.querySelector(".company-hero-stats");
  if (!root || root.dataset.tipBound === "1") return;
  root.dataset.tipBound = "1";

  root.addEventListener("click", (event) => {
    const cell = event.target.closest(".stat-cell.has-tip");
    if (!cell || !root.contains(cell)) return;
    event.preventDefault();
    const opening = !cell.classList.contains("is-tip-open");
    closeMetricTips(opening ? cell : null);
    cell.classList.toggle("is-tip-open", opening);
    cell.setAttribute("aria-expanded", opening ? "true" : "false");
  });

  root.addEventListener("keydown", (event) => {
    const cell = event.target.closest(".stat-cell.has-tip");
    if (!cell || !root.contains(cell)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    cell.click();
  });

  document.addEventListener("click", (event) => {
    if (event.target.closest(".stat-cell.has-tip")) return;
    closeMetricTips();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMetricTips();
  });
}

function renderMetricSection(title, items, { gridClass = "" } = {}) {
  const cells = items.filter(([, v]) => displayValue(v) !== "-");
  if (!cells.length) return "";
  const gridCls = ["company-metrics", gridClass].filter(Boolean).join(" ");
  return `
    <section class="metrics-section">
      <h4 class="metrics-section-title">${escapeHtml(title)}</h4>
      <div class="${gridCls}">
        ${cells.map(metricCell).join("")}
      </div>
    </section>`;
}

function renderMetrics(stock) {
  const panels = els.metricsPanels || els.metricsGrid;
  if (!panels) return;

  const mcap =
    stock.total_market_cap ||
    (stock.market_cap ? `${displayValue(stock.market_cap)}亿` : "");

  const periodItems = [
    ["近1日", stock.change_1d, changeClass(stock.change_1d)],
    ["3日", stock.change_3d, changeClass(stock.change_3d)],
    ["5日", stock.change_5d, changeClass(stock.change_5d)],
    ["10日", stock.change_10d, changeClass(stock.change_10d)],
    ["20日", stock.change_20d, changeClass(stock.change_20d)],
    ["60日", stock.change_60d, changeClass(stock.change_60d)],
    ["近半年", stock.change_half_year, changeClass(stock.change_half_year)],
    ["近1年", stock.change_1y, changeClass(stock.change_1y)],
    ["今年", stock.change_ytd, changeClass(stock.change_ytd)],
  ].filter(([, v]) => displayValue(v) !== "-");

  const extremeItems = [
    ["52周最高", stock.high_52w],
    ["52周最低", stock.low_52w],
    ["历史最高", stock.high_all],
    ["历史最低", stock.low_all],
  ].filter(([, v]) => displayValue(v) !== "-");

  const renderInlineRows = (title, rows) => {
    const parts = rows
      .map((items) => items.filter(([, v]) => displayValue(v) !== "-"))
      .filter((items) => items.length);
    if (!parts.length) return "";
    return `
    <section class="metrics-section">
      <h4 class="metrics-section-title">${escapeHtml(title)}</h4>
      ${parts
        .map(
          (items) =>
            `<div class="company-metrics metrics-inline-row">${items
              .map(metricCell)
              .join("")}</div>`
        )
        .join("")}
    </section>`;
  };

  const daySection = renderInlineRows("当日行情", [
    [
      ["今开", stock.open],
      ["昨收", stock.prev_close],
      ["最低", stock.low],
      ["最高", stock.high],
      ["均价", stock.avg_price],
      ["涨停", stock.limit_up],
      ["跌停", stock.limit_down],
    ],
    [
      ["总手", stock.volume],
      ["金额", stock.amount],
      ["换手", stock.turnover],
      ["换手(实)", stock.turnover_real],
      ["振幅", stock.amplitude],
      ["量比", stock.volume_ratio],
      ["现手", stock.current_volume],
      ["实体涨幅", stock.solid_change, changeClass(stock.solid_change)],
    ],
    [
      ["外盘", stock.outer_vol],
      ["内盘", stock.inner_vol],
      ["委买", stock.bid_vol],
      ["委卖", stock.ask_vol],
      ["委差", stock.bid_ask_diff, changeClass(stock.bid_ask_diff)],
      ["委比", stock.bid_ask_ratio, changeClass(stock.bid_ask_ratio)],
    ],
    [
      ["盘后委买", stock.after_bid],
      ["盘后量", stock.after_volume],
      ["盘后额", stock.after_amount],
    ],
  ]);

  const periodSection = renderInlineRows("区间涨幅", [
    periodItems,
    extremeItems,
  ]);

  const valuationSection = renderInlineRows("估值与每股", [
    [
      ["市盈率(动)", stock.pe],
      ["市盈率(静)", stock.pe_static],
      ["市盈率(TTM)", stock.pe_ttm],
      ["市净率", stock.pb],
      ["市销率(TTM)", stock.ps_ttm],
    ],
    [
      ["股息(TTM)", stock.dividend_ttm],
      ["股息率", stock.dividend_yield],
      ["净利增速", stock.profit_growth || stock.profit_yoy],
      ["营收增速", stock.revenue_growth || stock.revenue_yoy],
    ],
    [
      ["每股收益", stock.eps],
      ["每股净资产", stock.bvps],
      ["净资产收益率", stock.roe],
    ],
  ]);

  const capitalSection = renderInlineRows("股本与市值", [
    [
      ["总股本", stock.total_shares],
      ["流通股", stock.float_shares],
      ["自由流通股", stock.free_float_shares],
      ["发行股本", stock.issued_shares],
    ],
    [
      ["总市值", mcap],
      ["流通市值", stock.float_market_cap],
      ["自由流通市值", stock.free_float_market_cap],
    ],
    [
      ["注册资本", stock.registered_capital],
      ["上市时间", stock.list_date],
      ["纳入时间", stock.include_date],
    ],
  ]);

  const html = [
    daySection,
    periodSection,
    valuationSection,
    capitalSection,
  ]
    .filter(Boolean)
    .join("");

  panels.innerHTML = html || `<p class="muted">暂无指标数据</p>`;
}

function applyStock(stock, industryMeta = {}) {
  const displayName = stock.name || nameHint || code;
  document.title = `${displayName} · 公司详情`;
  els.pageTitle.textContent = displayName;
  els.companyName.textContent = displayName;

  const codeText = stock.full_code || stock.code || code;
  if (els.companyCodeChip) {
    els.companyCodeChip.textContent = codeText || "";
    els.companyCodeChip.hidden = !codeText;
  }

  const breadcrumbParts = [
    industryMeta.l1_name,
    industryMeta.l2_name,
    industryMeta.name || industryMeta.l3_name,
  ].filter(Boolean);
  els.companyBreadcrumb.textContent = breadcrumbParts.length
    ? breadcrumbParts.join(" / ")
    : "公司详情";

  renderQuote(stock);
  renderMetrics(stock);
}

function renderNewsList(items, emptyText) {
  if (!items.length) {
    return `<p class="muted">${escapeHtml(emptyText)}</p>`;
  }
  return items
    .map((item) => {
      const title = escapeHtml(item.title || "无标题");
      const url = String(item.url || "").trim();
      const titleHtml = url
        ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${title}</a>`
        : `<span>${title}</span>`;
      const extra =
        item.kind === "report" && item.rating
          ? `<span class="news-why">${escapeHtml(item.rating)}</span>`
          : item.why
            ? `<span class="news-why">${escapeHtml(item.why)}</span>`
            : "";
      return `
        <article class="news-item">
          <div class="news-item-meta">
            <time>${escapeHtml(item.published_at || "-")}</time>
            <span>${escapeHtml(item.source || "-")}</span>
            ${extra}
          </div>
          <h3>${titleHtml}</h3>
          <p>${escapeHtml(truncateText(item.summary || ""))}</p>
        </article>
      `;
    })
    .join("");
}

function newestPublished(items) {
  let newest = "";
  for (const item of items || []) {
    const day = String(item.published_at || "").slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) continue;
    if (!newest || day > newest) newest = day;
  }
  return newest;
}

function updateSectionMeta(kind) {
  const ui = sectionEls(kind);
  const st = sectionState[kind];
  const conf = KINDS.find((k) => k.key === kind);
  if (!ui.meta || !st || !conf) return;

  const from = oldestPublished(st.items);
  const to = newestPublished(st.items);
  const span = from && to ? `${from} ~ ${to}` : daysLabel(st.days);

  ui.meta.textContent = `${daysLabel(st.days)} · ${span} · ${st.items.length} 条 · 更新于 ${st.updatedAt || "-"}`;

  if (!ui.hint) return;
  if (st.loading) {
    ui.hint.textContent = `正在加载${daysLabel(st.days)}…`;
  } else if (st.exhausted) {
    ui.hint.textContent = st.items.length
      ? "已加载全部可查区间"
      : conf.empty;
  } else {
    ui.hint.textContent = "下滑加载更早消息";
  }
}

function paintSection(kind) {
  const ui = sectionEls(kind);
  const conf = KINDS.find((k) => k.key === kind);
  const st = sectionState[kind];
  if (!ui.list || !conf || !st) return;
  ui.list.innerHTML = renderNewsList(st.items, conf.empty);
  updateSectionMeta(kind);
}

function needsMoreContent(kind) {
  const ui = sectionEls(kind);
  const st = sectionState[kind];
  if (!ui.body || !st || st.exhausted || st.loading) return false;
  if (!st.items.length) return true;
  return ui.body.scrollHeight <= ui.body.clientHeight + 8;
}

function nearBottom(kind) {
  const ui = sectionEls(kind);
  if (!ui.body) return false;
  return ui.body.scrollTop + ui.body.clientHeight >= ui.body.scrollHeight - 48;
}

function setMetricsLoading(message = "正在加载指标…") {
  if (els.quoteStrip) {
    els.quoteStrip.innerHTML = "";
  }
  const panels = els.metricsPanels || els.metricsGrid;
  if (panels) {
    panels.innerHTML = `<p class="muted metrics-loading">${escapeHtml(message)}</p>`;
  }
}

function applyHeaderOnly(stock = {}, industryMeta = {}) {
  const displayName = stock.name || nameHint || code;
  document.title = `${displayName} · 公司详情`;
  els.pageTitle.textContent = displayName;
  els.companyName.textContent = displayName;

  const codeText = stock.full_code || stock.code || code;
  if (els.companyCodeChip) {
    els.companyCodeChip.textContent = codeText || "";
    els.companyCodeChip.hidden = !codeText;
  }

  const breadcrumbParts = [
    industryMeta.l1_name,
    industryMeta.l2_name,
    industryMeta.name || industryMeta.l3_name,
  ].filter(Boolean);
  els.companyBreadcrumb.textContent = breadcrumbParts.length
    ? breadcrumbParts.join(" / ")
    : "公司详情";
}

function isQuoteReady(stock) {
  // 盘口补全成功后通常至少有今开/昨收或完整涨跌幅字段
  if (!stock || typeof stock !== "object") return false;
  if (stock.quote_ready === true) return true;
  if (stock.quote_ready === false) return false;
  return Boolean(stock.open || stock.prev_close || stock.high || stock.low);
}

async function loadProfile() {
  if (!code) {
    setError("缺少公司代码");
    return null;
  }

  // 标题可用 URL 参数；指标只等接口一次画完，绝不用列表缓存半套数据
  applyHeaderOnly({ code, name: nameHint });
  setMetricsLoading();

  try {
    const qs = new URLSearchParams({ code });
    if (industry) qs.set("industry", industry);
    if (nameHint) qs.set("name", nameHint);
    const json = await api(`/api/stocks/profile?${qs.toString()}`);
    const data = json.data || {};
    const stock = data.stock || {};
    if (!isQuoteReady(stock)) {
      setMetricsLoading("盘口指标暂不可用，请稍后刷新");
      applyHeaderOnly(stock, data.industry || {});
      return stock;
    }
    applyStock(stock, data.industry || {});
    try {
      sessionStorage.removeItem(`stock:${code}`);
    } catch {
      /* ignore */
    }
    return stock;
  } catch (err) {
    setError(err.message || String(err));
    setMetricsLoading("指标加载失败");
    return null;
  }
}

async function fetchNewsKind(kind, days, { refresh = false } = {}) {
  const qs = new URLSearchParams({
    code,
    name: nameHint || els.companyName.textContent || "",
    days: String(days),
    kind,
  });
  if (refresh) qs.set("refresh", "1");
  const json = await api(`/api/stocks/news?${qs.toString()}`);
  return json.data || {};
}

function oldestPublished(items) {
  let oldest = "";
  for (const item of items || []) {
    const day = String(item.published_at || "").slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) continue;
    if (!oldest || day < oldest) oldest = day;
  }
  return oldest;
}

async function loadNewsKind(kind, days, { refresh = false } = {}) {
  const ui = sectionEls(kind);
  const conf = KINDS.find((k) => k.key === kind);
  const st = sectionState[kind];
  if (!ui.body || !conf || !st || st.loading) return;

  st.loading = true;
  st.days = days;
  updateSectionMeta(kind);
  if (!st.items.length) {
    ui.list.innerHTML = `<p class="muted">正在加载${daysLabel(days)}…</p>`;
  }

  try {
    const data = await fetchNewsKind(kind, days, { refresh });
    const groups = data.groups || {};
    const items = groups[kind] || [];
    const fullDays = Number(data.full_days) || FULL_DAYS;

    st.fullDays = fullDays;
    st.days = Number(data.days) || days;
    st.updatedAt = data.updated_at || "";
    st.items = items;
    // 相邻窗口没新增更早条目，只说明中间有空窗（例如 3→14 天无公告），
    // 不能当成数据源见底；否则会在「近 14 天」提前 exhausted，再也拉不到年报等历史。
    st.exhausted =
      st.days >= fullDays - 5 || Boolean(data.source_capped);
    paintSection(kind);
  } catch (err) {
    st.loading = false;
    if (!st.items.length) {
      ui.list.innerHTML = `<p class="news-error">${escapeHtml(err.message || String(err))}</p>`;
    }
    if (ui.hint) ui.hint.textContent = "加载失败，下滑重试";
    ui.meta.textContent = "加载失败";
    throw err;
  } finally {
    st.loading = false;
    updateSectionMeta(kind);
  }

  // 内容不足以滚动时自动继续向更早窗口拉取
  if (needsMoreContent(kind)) {
    await loadOlder(kind);
  }
}

async function loadOlder(kind) {
  const st = sectionState[kind];
  if (!st || st.loading || st.exhausted) return;

  const next = nextDayWindow(st.days, st.fullDays);
  if (next == null) {
    st.exhausted = true;
    updateSectionMeta(kind);
    return;
  }

  const prevCount = st.items.length;
  const prevOldest = oldestPublished(st.items);
  try {
    await loadNewsKind(kind, next, { refresh: false });
  } catch {
    return;
  }

  const st2 = sectionState[kind];
  const newestOldest = oldestPublished(st2.items);
  if (
    !st2.exhausted &&
    !st2.loading &&
    st2.items.length === prevCount &&
    newestOldest &&
    prevOldest &&
    newestOldest >= prevOldest &&
    needsMoreContent(kind)
  ) {
    // 仍无更深数据则继续扩大窗口；若已接近上限会在 nextDayWindow 停住
    await loadOlder(kind);
  }
}

async function loadAllNews({ refresh = false } = {}) {
  if (!code) return;
  els.refreshNewsBtn.disabled = true;
  await Promise.all(
    KINDS.map(async ({ key }) => {
      const st = sectionState[key];
      st.days = DEFAULT_DAYS;
      st.items = [];
      st.exhausted = false;
      st.updatedAt = "";
      try {
        await loadNewsKind(key, DEFAULT_DAYS, { refresh });
      } catch {
        /* 单栏失败不阻断其他栏 */
      }
    })
  );
  els.refreshNewsBtn.disabled = false;
}

function setupScrollLoaders() {
  KINDS.forEach(({ key }) => {
    const ui = sectionEls(key);
    if (!ui.body) return;
    ui.body.addEventListener(
      "scroll",
      () => {
        if (nearBottom(key)) loadOlder(key);
      },
      { passive: true }
    );
  });
}

function setupBackLink() {
  if (industry) {
    els.backLink.href = `/?industry=${encodeURIComponent(industry)}`;
  } else {
    els.backLink.href = "/";
  }
}

/* ---------- 行情图表 ---------- */

function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function fmtNum(n, digits = 2) {
  if (n == null || !Number.isFinite(Number(n))) return "-";
  return Number(n).toFixed(digits);
}

function fmtVol(n) {
  if (n == null || !Number.isFinite(Number(n))) return "-";
  const v = Number(n);
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(1)}万`;
  return String(Math.round(v));
}

function shortTimeLabel(t, mode) {
  const s = String(t || "");
  if (mode === "intraday5") {
    if (s.length >= 10) return s.slice(5, 10); // MM-DD
    return s;
  }
  if (mode === "intraday") {
    if (s.length >= 16) return s.slice(11, 16);
    if (s.length >= 10) return s.slice(5, 10);
    return s;
  }
  // 分钟 K：2026-08-19 15:00 → 08-19 15:00
  if (isMinuteKline(mode)) {
    if (s.length >= 16) return `${s.slice(5, 10)} ${s.slice(11, 16)}`;
    if (s.length >= 10) return s.slice(5, 10);
    return s;
  }
  if (s.length >= 10) return s.slice(0, 10);
  return s;
}

function dayBreakIndices(items) {
  const breaks = [];
  for (let i = 0; i < items.length; i += 1) {
    if (i === 0) {
      breaks.push(i);
      continue;
    }
    const a = String(items[i - 1].time || "").slice(0, 10);
    const b = String(items[i].time || "").slice(0, 10);
    if (a && b && a !== b) breaks.push(i);
  }
  return breaks;
}

function setChartStatus(message, { empty = false } = {}) {
  if (els.chartMeta) els.chartMeta.textContent = message || "";
  if (els.chartEmpty) {
    els.chartEmpty.textContent = empty ? message || "暂无走势数据" : "暂无走势数据";
    els.chartEmpty.classList.toggle("hidden", !empty);
  }
}

function chartViewWindow() {
  const all = chartState.allItems || [];
  const total = all.length;
  let size = Number(chartState.viewSize) || 0;
  if (size <= 0 || size >= total) size = total;
  const maxStart = Math.max(0, total - size);
  const start = Math.min(Math.max(0, Number(chartState.viewStart) || 0), maxStart);
  return {
    all,
    total,
    size,
    maxStart,
    start,
    items: total ? all.slice(start, start + size) : [],
  };
}

function chartMinViewSize(total) {
  if (total <= 1) return Math.max(1, total);
  if (chartState.kind === "intraday") return Math.min(total, 36);
  return Math.min(total, 20);
}

function refreshChartWindowStatus() {
  const conf = CHART_MODES[chartState.mode] || CHART_MODES.day;
  const { total, size } = chartViewWindow();
  if (!total) return;
  const src = chartState.source ? ` · ${chartState.source}` : "";
  const adj = isAdjustableKline(chartState.mode)
    ? chartState.adjust === "none"
      ? " · 不复权"
      : " · 前复权"
    : "";
  const tip =
    size < total
      ? ` · 显示 ${size}/${total}，滚轮缩放 · 拖动/滑动平移`
      : ` · ${total} 点，滚轮可放大`;
  setChartStatus(`${conf.label}${tip}${adj}${src}`);
}

function setChartViewStart(nextStart, { render = true, hoverIndex = null } = {}) {
  const { maxStart } = chartViewWindow();
  const start = Math.min(Math.max(0, Math.round(nextStart)), maxStart);
  if (start === chartState.viewStart && chartState.items.length) {
    syncChartScrollBar();
    if (render) renderChart(hoverIndex);
    return start;
  }
  chartState.viewStart = start;
  const win = chartViewWindow();
  chartState.items = win.items;
  syncChartScrollBar();
  if (render) renderChart(hoverIndex);
  return start;
}

/** 以横轴比例 anchorRatio(0~1) 为锚点缩放可视点数。factor>1 显示更多，factor<1 放大。 */
function zoomChartViewport(anchorRatio, factor, { render = true } = {}) {
  const total = (chartState.allItems || []).length;
  if (total <= 1) return false;
  const win = chartViewWindow();
  const minSize = chartMinViewSize(total);
  const ratio = Math.min(1, Math.max(0, Number(anchorRatio) || 0.5));
  let nextSize = Math.round(win.size * factor);
  nextSize = Math.max(minSize, Math.min(total, nextSize));
  if (nextSize === win.size) return false;

  const anchorIndex = win.start + ratio * win.size;
  let nextStart = Math.round(anchorIndex - ratio * nextSize);
  nextStart = Math.max(0, Math.min(nextStart, total - nextSize));

  chartState.viewSize = nextSize;
  chartState.viewStart = nextStart;
  chartState.items = chartViewWindow().items;
  syncChartScrollBar();
  refreshChartWindowStatus();
  if (render) renderChart();
  return true;
}

function syncChartScrollBar() {
  const bar = els.chartScrollBar;
  const wrap = els.chartAxisScroll;
  if (!bar) return;
  const { maxStart, start, total, size } = chartViewWindow();
  const canScroll = total > size && maxStart > 0;
  if (wrap) wrap.classList.toggle("is-disabled", !canScroll);
  bar.disabled = !canScroll;
  bar.min = "0";
  bar.max = String(Math.max(0, maxStart));
  bar.value = String(start);
  // 滑块宽度随可视比例变化（WebKit）
  const ratio = total > 0 ? Math.min(1, size / total) : 1;
  const thumbPx = Math.max(28, Math.round(48 + ratio * 72));
  bar.style.setProperty("--thumb-w", `${thumbPx}px`);
}

function resetChartViewport(allItems, modeConf) {
  chartState.allItems = Array.isArray(allItems) ? allItems : [];
  const total = chartState.allItems.length;
  let viewSize = Number(modeConf?.viewSize);
  if (!Number.isFinite(viewSize) || viewSize <= 0) {
    viewSize = total; // 分时默认看全天
  }
  chartState.viewSize = viewSize;
  chartState.viewStart = Math.max(0, total - (viewSize > 0 && viewSize < total ? viewSize : total));
  chartState.items = chartViewWindow().items;
  syncChartScrollBar();
}

function chartLayout(w, h) {
  // 顶部/右侧留给坐标与分时涨跌幅
  const pctAxis =
    chartState.kind === "intraday" &&
    chartState.mode === "intraday" &&
    Number.isFinite(chartState.preClose) &&
    chartState.preClose;
  const pad = {
    top: 14,
    right: pctAxis ? 52 : 30,
    bottom: 28,
    left: 60,
  };
  const innerW = Math.max(10, w - pad.left - pad.right);
  const innerH = Math.max(10, h - pad.top - pad.bottom);
  const volH = Math.max(36, Math.floor(innerH * 0.16));
  const gap = 10;
  const priceH = Math.max(100, innerH - volH - gap);
  return {
    pad,
    price: { x: pad.left, y: pad.top, w: innerW, h: priceH },
    volume: {
      x: pad.left,
      y: pad.top + priceH + gap,
      w: innerW,
      h: volH,
    },
  };
}

/** 取 1/2/5×10^n 漂亮步长 */
function niceNum(range, round) {
  const r = Math.abs(Number(range)) || 1;
  const exp = Math.floor(Math.log10(r));
  const frac = r / 10 ** exp;
  let nice;
  if (round) {
    if (frac < 1.5) nice = 1;
    else if (frac < 3) nice = 2;
    else if (frac < 7) nice = 5;
    else nice = 10;
  } else if (frac <= 1) nice = 1;
  else if (frac <= 2) nice = 2;
  else if (frac <= 5) nice = 5;
  else nice = 10;
  return nice * 10 ** exp;
}

function roundToStep(value, step) {
  if (!Number.isFinite(value) || !Number.isFinite(step) || step <= 0) return value;
  const decimals = Math.min(8, Math.max(0, Math.ceil(-Math.log10(step) + 1)));
  const n = Math.round(value / step) * step;
  return Number(n.toFixed(decimals));
}

function fmtAxisPrice(value, step) {
  if (!Number.isFinite(value)) return "-";
  let digits = 2;
  if (Number.isFinite(step) && step > 0) {
    if (step >= 1) digits = Math.abs(step % 1) < 1e-8 ? 0 : 2;
    else if (step >= 0.1) digits = 2;
    else if (step >= 0.01) digits = 2;
    else if (step >= 0.001) digits = 3;
    else digits = 4;
  }
  return value.toFixed(digits);
}

/**
 * 价格纵轴：视窗贴合真实高低（少留白），刻度取落在视窗内的漂亮数。
 * 避免为对齐整数价把范围撑大，否则波动会被压扁。
 * center 有值时（分时昨收）仅做上下对称，仍尽量贴合实际波幅。
 */
function buildPriceScale(
  dataMin,
  dataMax,
  { tickCount = 5, padRatio = 0.02, center = null } = {}
) {
  let lo = Number(dataMin);
  let hi = Number(dataMax);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
    return { min: 0, max: 1, ticks: [0, 0.25, 0.5, 0.75, 1], step: 0.25 };
  }
  if (hi < lo) {
    const t = lo;
    lo = hi;
    hi = t;
  }

  if (Number.isFinite(center)) {
    // 只按实际偏离昨收的幅度对称，最小约 0.15% 防止完全横盘时高度为 0
    const raw = Math.max(hi - center, center - lo);
    const floor = Math.max(Math.abs(center) * 0.0015, 0.01);
    const span = Math.max(raw, floor);
    lo = center - span;
    hi = center + span;
  }

  if (hi <= lo) {
    const d = Math.max(Math.abs(hi) * 0.005, 0.02);
    lo -= d;
    hi += d;
  }

  // 少量边距即可，过大只会让 K 线/分时显得更「平」
  const pad = Math.max((hi - lo) * padRatio, 0.005);
  lo -= pad;
  hi += pad;

  const target = Math.max(4, Math.min(7, tickCount));
  // round=false：倾向更小步长，少把视窗撑开
  let step = niceNum((hi - lo) / Math.max(1, target - 1), false);
  if (step < 0.01) step = 0.01;

  const ticks = [];
  const startI = Math.ceil(lo / step - 1e-9);
  const endI = Math.floor(hi / step + 1e-9);
  for (let i = startI; i <= endI; i += 1) {
    const v = roundToStep(i * step, step);
    if (v >= lo - step * 1e-6 && v <= hi + step * 1e-6) ticks.push(v);
  }

  // 刻度过密则加大步长，但仍不扩张 min/max
  let guard = 0;
  while (ticks.length > 8 && guard < 6) {
    guard += 1;
    step = niceNum(step * 1.8, false);
    if (step < 0.01) step = 0.01;
    ticks.length = 0;
    const a = Math.ceil(lo / step - 1e-9);
    const b = Math.floor(hi / step + 1e-9);
    for (let i = a; i <= b; i += 1) {
      const v = roundToStep(i * step, step);
      if (v >= lo - step * 1e-6 && v <= hi + step * 1e-6) ticks.push(v);
    }
  }

  // 至少两端有可读刻度：不足时补视窗边界（按步长精度格式化）
  if (ticks.length === 0) {
    ticks.push(roundToStep(lo, step), roundToStep(hi, step));
  } else if (ticks.length === 1) {
    if (Math.abs(ticks[0] - lo) > Math.abs(ticks[0] - hi)) ticks.unshift(roundToStep(lo, step));
    else ticks.push(roundToStep(hi, step));
  }

  return {
    min: lo,
    max: hi,
    ticks,
    step,
  };
}

function priceScaleTickCount(priceH) {
  return Math.max(4, Math.min(7, Math.round(Number(priceH) / 42) || 5));
}

function drawGrid(ctx, rect, yTicks, xTicks, colors) {
  ctx.save();
  ctx.strokeStyle = colors.grid;
  ctx.lineWidth = 1;
  for (const y of yTicks) {
    ctx.beginPath();
    ctx.moveTo(rect.x, y);
    ctx.lineTo(rect.x + rect.w, y);
    ctx.stroke();
  }
  for (const x of xTicks) {
    ctx.beginPath();
    ctx.moveTo(x, rect.y);
    ctx.lineTo(x, rect.y + rect.h);
    ctx.stroke();
  }
  ctx.restore();
}

function drawAxesLabels(ctx, layout, priceScale, items, mode, colors, { preClose = null } = {}) {
  const { price, volume } = layout;
  const range = priceScale.max - priceScale.min || 1;
  const ticks = Array.isArray(priceScale.ticks) ? priceScale.ticks : [];
  const yOf = (val) => price.y + ((priceScale.max - val) / range) * price.h;

  ctx.save();
  ctx.font = '11px "JetBrains Mono", Consolas, monospace';
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";

  for (const val of ticks) {
    const y = yOf(val);
    if (y < price.y - 1 || y > price.y + price.h + 1) continue;
    if (Number.isFinite(preClose)) {
      if (val > preClose) ctx.fillStyle = colors.up;
      else if (val < preClose) ctx.fillStyle = colors.down;
      else ctx.fillStyle = colors.muted;
    } else {
      ctx.fillStyle = colors.muted;
    }
    ctx.fillText(fmtAxisPrice(val, priceScale.step), price.x - 8, y);
  }

  // 分时：右侧涨跌幅刻度，与左侧价格对齐
  if (mode === "intraday" && Number.isFinite(preClose) && preClose) {
    ctx.textAlign = "left";
    for (const val of ticks) {
      const y = yOf(val);
      if (y < price.y - 1 || y > price.y + price.h + 1) continue;
      const pct = ((val - preClose) / preClose) * 100;
      if (pct > 0) ctx.fillStyle = colors.up;
      else if (pct < 0) ctx.fillStyle = colors.down;
      else ctx.fillStyle = colors.muted;
      const sign = pct > 0 ? "+" : "";
      ctx.fillText(`${sign}${pct.toFixed(2)}%`, price.x + price.w + 6, y);
    }
  }

  ctx.fillStyle = colors.muted;
  ctx.textBaseline = "top";
  const n = items.length;
  if (n > 0) {
    let idxs;
    if (mode === "intraday5") {
      idxs = dayBreakIndices(items);
    } else if (isMinuteKline(mode)) {
      const breaks = dayBreakIndices(items);
      if (breaks.length >= 2) {
        idxs = breaks.length <= 5 ? breaks.slice() : [
          breaks[0],
          breaks[Math.floor(breaks.length / 2)],
          breaks[breaks.length - 1],
        ];
        if (idxs[idxs.length - 1] !== n - 1) idxs.push(n - 1);
      } else {
        idxs = [0, Math.floor((n - 1) / 2), n - 1];
      }
    } else {
      idxs = [0, Math.floor((n - 1) / 2), n - 1];
    }
    const seen = new Set();
    const plotLeft = price.x;
    const plotRight = price.x + price.w;
    for (const i of idxs) {
      if (seen.has(i)) continue;
      seen.add(i);
      const label = shortTimeLabel(items[i].time, mode);
      let x = plotLeft + ((i + 0.5) / n) * price.w;
      // 首尾标签贴边对齐，避免被 canvas 裁掉
      if (i === 0) {
        ctx.textAlign = "left";
        x = plotLeft;
      } else if (i === n - 1) {
        ctx.textAlign = "right";
        x = plotRight;
      } else {
        ctx.textAlign = "center";
        const approxHalf = Math.min(48, label.length * 3.4);
        x = Math.min(plotRight - approxHalf, Math.max(plotLeft + approxHalf, x));
      }
      ctx.fillText(label, x, volume.y + volume.h + 6);
    }
  }
  ctx.restore();
}

function paintChartFrame(ctx, w, h, colors) {
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "rgba(4, 8, 14, 0.15)";
  ctx.fillRect(0, 0, w, h);
}

function drawIntradayChart(ctx, layout, items, preClose, mode, colors, hoverIndex) {
  const n = items.length;
  if (!n) return;

  const prices = items.map((d) => Number(d.price)).filter(Number.isFinite);
  let minP = Math.min(...prices);
  let maxP = Math.max(...prices);
  if (Number.isFinite(preClose)) {
    minP = Math.min(minP, preClose);
    maxP = Math.max(maxP, preClose);
  }
  const { price, volume } = layout;
  const priceScale = buildPriceScale(minP, maxP, {
    tickCount: priceScaleTickCount(price.h),
    padRatio: 0.015,
    center: mode === "intraday" && Number.isFinite(preClose) ? preClose : null,
  });
  const vols = items.map((d) => Number(d.volume) || 0);
  const maxVol = Math.max(...vols, 1);

  const xAt = (i) => price.x + ((i + 0.5) / n) * price.w;
  const yAt = (p) =>
    price.y + ((priceScale.max - p) / (priceScale.max - priceScale.min || 1)) * price.h;

  const yTicks = (priceScale.ticks || []).map(yAt);
  let xTicks = [0, 0.5, 1].map((t) => price.x + price.w * t);
  if (mode === "intraday5") {
    xTicks = dayBreakIndices(items).map((i) => price.x + (i / Math.max(n, 1)) * price.w);
  }
  drawGrid(ctx, price, yTicks, xTicks, colors);
  drawGrid(
    ctx,
    volume,
    [volume.y, volume.y + volume.h],
    xTicks,
    colors
  );

  // 五日：日期分隔线更明显
  if (mode === "intraday5") {
    ctx.save();
    ctx.strokeStyle = "rgba(42, 212, 184, 0.22)";
    ctx.lineWidth = 1;
    for (const i of dayBreakIndices(items)) {
      if (i <= 0) continue;
      const x = price.x + (i / n) * price.w;
      ctx.beginPath();
      ctx.moveTo(x, price.y);
      ctx.lineTo(x, volume.y + volume.h);
      ctx.stroke();
    }
    ctx.restore();
  }

  if (Number.isFinite(preClose)) {
    const y = yAt(preClose);
    ctx.save();
    ctx.strokeStyle = colors.ref;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(price.x, y);
    ctx.lineTo(price.x + price.w, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
  }

  // volume bars
  const barW = Math.max(1, (price.w / n) * 0.7);
  for (let i = 0; i < n; i += 1) {
    const v = vols[i];
    const h = (v / maxVol) * volume.h;
    const x = xAt(i) - barW / 2;
    const prev = i > 0 ? Number(items[i - 1].price) : preClose;
    const cur = Number(items[i].price);
    const up = Number.isFinite(prev) ? cur >= prev : true;
    ctx.fillStyle = up ? colors.upSoft : colors.downSoft;
    ctx.fillRect(x, volume.y + volume.h - h, barW, h);
  }

  // avg line
  ctx.beginPath();
  let startedAvg = false;
  for (let i = 0; i < n; i += 1) {
    const avg = Number(items[i].avg_price);
    if (!Number.isFinite(avg)) continue;
    const x = xAt(i);
    const y = yAt(avg);
    if (!startedAvg) {
      ctx.moveTo(x, y);
      startedAvg = true;
    } else ctx.lineTo(x, y);
  }
  if (startedAvg) {
    ctx.strokeStyle = colors.avg;
    ctx.lineWidth = 1.2;
    ctx.stroke();
  }

  // price line + fill
  ctx.beginPath();
  let startedPrice = false;
  for (let i = 0; i < n; i += 1) {
    const p = Number(items[i].price);
    if (!Number.isFinite(p)) continue;
    const x = xAt(i);
    const y = yAt(p);
    if (!startedPrice) {
      ctx.moveTo(x, y);
      startedPrice = true;
    } else ctx.lineTo(x, y);
  }
  if (startedPrice) {
    ctx.strokeStyle = colors.accent;
    ctx.lineWidth = 1.6;
    ctx.stroke();

    ctx.beginPath();
    startedPrice = false;
    for (let i = 0; i < n; i += 1) {
      const p = Number(items[i].price);
      if (!Number.isFinite(p)) continue;
      const x = xAt(i);
      const y = yAt(p);
      if (!startedPrice) {
        ctx.moveTo(x, y);
        startedPrice = true;
      } else ctx.lineTo(x, y);
    }
    ctx.lineTo(xAt(n - 1), price.y + price.h);
    ctx.lineTo(xAt(0), price.y + price.h);
    ctx.closePath();
    const gradient = ctx.createLinearGradient(0, price.y, 0, price.y + price.h);
    gradient.addColorStop(0, "rgba(42, 212, 184, 0.18)");
    gradient.addColorStop(1, "rgba(42, 212, 184, 0)");
    ctx.fillStyle = gradient;
    ctx.fill();
  }

  if (hoverIndex != null && hoverIndex >= 0 && hoverIndex < n) {
    const x = xAt(hoverIndex);
    const p = Number(items[hoverIndex].price);
    ctx.save();
    ctx.strokeStyle = colors.cross;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x, price.y);
    ctx.lineTo(x, volume.y + volume.h);
    ctx.stroke();
    if (Number.isFinite(p)) {
      const y = yAt(p);
      ctx.beginPath();
      ctx.moveTo(price.x, y);
      ctx.lineTo(price.x + price.w, y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = colors.accent;
      ctx.beginPath();
      ctx.arc(x, y, 3.2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  drawAxesLabels(ctx, layout, priceScale, items, mode, colors, { preClose });
}

function drawMaLines(ctx, maVisible, yAt, xAt, n) {
  for (const line of KLINE_MA_LINES) {
    const vals = maVisible[line.key] || [];
    ctx.save();
    ctx.strokeStyle = line.color;
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < n; i += 1) {
      const v = maPoint(vals, i);
      if (v == null) {
        started = false;
        continue;
      }
      const x = xAt(i);
      const y = yAt(v);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
    ctx.restore();
  }
}

function drawKlineChart(ctx, layout, items, mode, colors, hoverIndex) {
  const n = items.length;
  if (!n) return;

  const { visible: maVisible } = getKlineMaBundle();
  const highs = items.map((d) => Number(d.high)).filter(Number.isFinite);
  const lows = items.map((d) => Number(d.low)).filter(Number.isFinite);
  const maNums = [];
  for (const line of KLINE_MA_LINES) {
    const vals = maVisible[line.key] || [];
    for (let i = 0; i < vals.length; i += 1) {
      const v = maPoint(vals, i);
      if (v != null) maNums.push(v);
    }
  }
  const lo = Math.min(...lows, ...(maNums.length ? maNums : lows));
  const hi = Math.max(...highs, ...(maNums.length ? maNums : highs));
  const { price, volume } = layout;
  const priceScale = buildPriceScale(lo, hi, {
    tickCount: priceScaleTickCount(price.h),
    padRatio: 0.02,
  });
  const vols = items.map((d) => Number(d.volume) || 0);
  const maxVol = Math.max(...vols, 1);
  const slot = price.w / n;
  const bodyW = Math.max(2, Math.min(14, slot * 0.62));

  const xAt = (i) => price.x + (i + 0.5) * slot;
  const yAt = (p) =>
    price.y + ((priceScale.max - p) / (priceScale.max - priceScale.min || 1)) * price.h;

  const yTicks = (priceScale.ticks || []).map(yAt);
  let xTicks = [0, 0.5, 1].map((t) => price.x + price.w * t);
  if (isMinuteKline(mode)) {
    const breaks = dayBreakIndices(items);
    if (breaks.length >= 2) {
      xTicks = breaks.map((i) => price.x + (i / Math.max(n, 1)) * price.w);
    }
  }
  drawGrid(ctx, price, yTicks, xTicks, colors);
  drawGrid(ctx, volume, [volume.y, volume.y + volume.h], xTicks, colors);

  for (let i = 0; i < n; i += 1) {
    const d = items[i];
    const o = Number(d.open);
    const c = Number(d.close);
    const h = Number(d.high);
    const l = Number(d.low);
    if (![o, c, h, l].every(Number.isFinite)) continue;
    const up = c >= o;
    const color = up ? colors.up : colors.down;
    const soft = up ? colors.upSoft : colors.downSoft;
    const x = xAt(i);

    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, yAt(h));
    ctx.lineTo(x, yAt(l));
    ctx.stroke();

    const y1 = yAt(Math.max(o, c));
    const y2 = yAt(Math.min(o, c));
    const bh = Math.max(1, y2 - y1);
    if (up) {
      ctx.strokeRect(x - bodyW / 2, y1, bodyW, bh);
    } else {
      ctx.fillRect(x - bodyW / 2, y1, bodyW, bh);
    }

    const vh = (vols[i] / maxVol) * volume.h;
    ctx.fillStyle = soft;
    ctx.fillRect(x - bodyW / 2, volume.y + volume.h - vh, bodyW, vh);
  }

  drawMaLines(ctx, maVisible, yAt, xAt, n);

  if (hoverIndex != null && hoverIndex >= 0 && hoverIndex < n) {
    const x = xAt(hoverIndex);
    ctx.save();
    ctx.strokeStyle = colors.cross;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x, price.y);
    ctx.lineTo(x, volume.y + volume.h);
    ctx.stroke();
    ctx.restore();
  }

  drawAxesLabels(ctx, layout, priceScale, items, mode, colors);
}

function renderChart(hoverIndex = null) {
  const canvas = els.priceChart;
  const wrap = els.chartWrap;
  if (!canvas || !wrap) return;

  const dpr = window.devicePixelRatio || 1;
  const cssW = Math.max(320, wrap.clientWidth || 640);
  const cssH = Math.max(240, wrap.clientHeight || 320);
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const colors = {
    accent: cssVar("--accent", "#2ad4b8"),
    muted: cssVar("--muted", "#8494a8"),
    up: cssVar("--up", "#ff5d6c"),
    down: cssVar("--down", "#3dd68c"),
    upSoft: "rgba(255, 93, 108, 0.45)",
    downSoft: "rgba(61, 214, 140, 0.45)",
    avg: cssVar("--accent-hot", "#f0b429"),
    grid: "rgba(42, 212, 184, 0.08)",
    ref: "rgba(132, 148, 168, 0.55)",
    cross: "rgba(232, 238, 247, 0.35)",
  };

  paintChartFrame(ctx, cssW, cssH, colors);
  const items = chartState.items || [];
  if (!items.length) return;

  const layout = chartLayout(cssW, cssH);
  if (chartState.kind === "intraday") {
    drawIntradayChart(
      ctx,
      layout,
      items,
      chartState.preClose,
      chartState.mode,
      colors,
      hoverIndex
    );
  } else {
    drawKlineChart(ctx, layout, items, chartState.mode, colors, hoverIndex);
  }
}

function hideHoverCard() {
  if (!els.chartHoverCard) return;
  els.chartHoverCard.classList.add("hidden");
  els.chartHoverCard.setAttribute("aria-hidden", "true");
  els.chartHoverCard.innerHTML = "";
}

function showHoverCard() {
  if (!els.chartHoverCard) return;
  els.chartHoverCard.classList.remove("hidden");
  els.chartHoverCard.setAttribute("aria-hidden", "false");
}

function updateHoverLabel(index, evt = null) {
  if (!els.chartHoverCard) return;
  const items = chartState.items || [];
  if (index == null || index < 0 || index >= items.length) {
    hideHoverCard();
    return;
  }
  const d = items[index];

  const row = (label, valueHtml, valueCls = "") =>
    `<span class="chart-hover-item"><span class="k">${escapeHtml(label)}</span><span class="v ${valueCls}">${valueHtml}</span></span>`;

  const pctText = (pct) => {
    if (pct == null || !Number.isFinite(Number(pct))) return null;
    const n = Number(pct);
    const cls = n > 0 ? "change-up" : n < 0 ? "change-down" : "";
    const sign = n > 0 ? "+" : "";
    return { text: `${sign}${n.toFixed(2)}%`, cls: `chart-hover-pct ${cls}` };
  };

  let rows = [];
  if (chartState.kind === "intraday") {
    let pct = null;
    const price = Number(d.price);
    if (Number.isFinite(chartState.preClose) && Number.isFinite(price) && chartState.preClose) {
      pct = ((price - chartState.preClose) / chartState.preClose) * 100;
    }
    const priceCls =
      pct > 0 ? "change-up" : pct < 0 ? "change-down" : "";
    const p = pctText(pct);
    rows = [
      row("现价", escapeHtml(fmtNum(d.price)), priceCls),
      row("均价", escapeHtml(fmtNum(d.avg_price))),
      p ? row("涨跌幅", escapeHtml(p.text), p.cls) : "",
      row("成交量", escapeHtml(fmtVol(d.volume))),
    ].filter(Boolean);
  } else {
    let pct = Number(d.pct_chg);
    if (!Number.isFinite(pct) && index > 0) {
      const prevClose = Number(items[index - 1].close);
      const close = Number(d.close);
      if (Number.isFinite(prevClose) && prevClose && Number.isFinite(close)) {
        pct = ((close - prevClose) / prevClose) * 100;
      }
    }
    const closeCls =
      Number.isFinite(pct) && pct > 0
        ? "change-up"
        : Number.isFinite(pct) && pct < 0
          ? "change-down"
          : "";
    const p = pctText(pct);
    const absIndex = (Number(chartState.viewStart) || 0) + index;
    const { full: maFull } = getKlineMaBundle();
    const maRows = KLINE_MA_LINES.map((line) => {
      const v = maPoint(maFull[line.key] || [], absIndex);
      if (v == null) return "";
      return row(
        line.label,
        `<span style="color:${line.color}">${escapeHtml(fmtNum(v))}</span>`
      );
    }).filter(Boolean);
    rows = [
      row("开盘", escapeHtml(fmtNum(d.open))),
      row("最低", escapeHtml(fmtNum(d.low))),
      row("最高", escapeHtml(fmtNum(d.high))),
      row("收盘", escapeHtml(fmtNum(d.close)), closeCls),
      p ? row("涨跌幅", escapeHtml(p.text), p.cls) : "",
      ...maRows,
      row("成交量", escapeHtml(fmtVol(d.volume))),
    ].filter(Boolean);
  }

  els.chartHoverCard.innerHTML = `
    <p class="chart-hover-card-time">${escapeHtml(d.time || "")}</p>
    <div class="chart-hover-card-rows">${rows.join("")}</div>
  `;
  showHoverCard();
}

function pointerIndex(evt) {
  const canvas = els.priceChart;
  const wrap = els.chartWrap;
  const items = chartState.items || [];
  if (!canvas || !wrap || !items.length) return null;
  const rect = canvas.getBoundingClientRect();
  const x = evt.clientX - rect.left;
  const layout = chartLayout(rect.width, rect.height);
  if (x < layout.price.x || x > layout.price.x + layout.price.w) return null;
  const t = (x - layout.price.x) / layout.price.w;
  const idx = Math.min(items.length - 1, Math.max(0, Math.floor(t * items.length)));
  return idx;
}

function panChartByPixels(dx, canvasWidth) {
  const { size, maxStart } = chartViewWindow();
  if (maxStart <= 0 || size <= 0) return false;
  const layout = chartLayout(canvasWidth, 300);
  const barW = layout.price.w / size;
  if (barW <= 0) return false;
  // 右拖看更早，左拖看更新
  const deltaBars = Math.round(-dx / barW);
  if (!deltaBars) return false;
  setChartViewStart(chartState.viewStart + deltaBars, { render: true });
  return true;
}

async function loadChart(mode = chartState.mode) {
  if (!code || !els.priceChart) return;
  const conf = CHART_MODES[mode] || CHART_MODES.day;
  chartState.mode = mode;
  chartState.kind = conf.kind;
  chartState.loading = true;
  syncChartAdjustUi(mode);
  setChartStatus(`正在加载${conf.label}…`);
  hideHoverCard();

  try {
    let data;
    if (conf.kind === "intraday") {
      const qs = new URLSearchParams({
        code,
        ndays: String(conf.ndays || 1),
      });
      const json = await api(`/api/stocks/intraday?${qs.toString()}`);
      data = json.data || {};
      resetChartViewport(data.items || [], conf);
      chartState.preClose = Number(data.pre_close);
      if (!Number.isFinite(chartState.preClose)) chartState.preClose = null;
      chartState.source = data.source || "";
    } else {
      const qs = new URLSearchParams({
        code,
        period: conf.period,
        adjust: klineAdjustFor(mode),
        limit: String(conf.limit || 180),
      });
      const json = await api(`/api/stocks/kline?${qs.toString()}`);
      data = json.data || {};
      resetChartViewport(data.items || [], conf);
      chartState.preClose = null;
      chartState.source = data.source || "";
    }

    const count = chartState.allItems.length;
    if (!count) {
      setChartStatus("暂无走势数据", { empty: true });
      renderChart();
      return;
    }
    refreshChartWindowStatus();
    renderChart();
  } catch (err) {
    resetChartViewport([], conf);
    setChartStatus(err.message || "走势加载失败", { empty: true });
    renderChart();
  } finally {
    chartState.loading = false;
  }
}

function setupChart() {
  if (!els.chartTabs || !els.priceChart) return;

  els.chartTabs.addEventListener("click", (evt) => {
    const btn = evt.target.closest(".chart-tab");
    if (!btn) return;
    const mode = btn.getAttribute("data-mode");
    if (!mode || mode === chartState.mode) return;
    els.chartTabs.querySelectorAll(".chart-tab").forEach((el) => {
      const active = el === btn;
      el.classList.toggle("is-active", active);
      el.setAttribute("aria-selected", active ? "true" : "false");
    });
    loadChart(mode);
  });

  els.chartAdjust?.addEventListener("click", (evt) => {
    const btn = evt.target.closest("[data-adjust]");
    if (!btn || !isAdjustableKline(chartState.mode)) return;
    const adjust = btn.getAttribute("data-adjust");
    if (!adjust || adjust === chartState.adjust) return;
    chartState.adjust = adjust === "none" ? "none" : "qfq";
    syncChartAdjustUi();
    loadChart(chartState.mode);
  });

  syncChartAdjustUi();

  if (els.chartScrollBar) {
    els.chartScrollBar.addEventListener("input", () => {
      hideHoverCard();
      setChartViewStart(Number(els.chartScrollBar.value) || 0, { render: true });
    });
  }

  let hoverIdx = null;
  let pan = null;

  const onMove = (evt) => {
    if (pan) {
      const dx = evt.clientX - pan.lastX;
      if (Math.abs(evt.clientX - pan.originX) > 4) pan.moved = true;
      if (pan.moved && Math.abs(dx) >= 1) {
        hideHoverCard();
        hoverIdx = null;
        panChartByPixels(dx, pan.width);
        pan.lastX = evt.clientX;
      }
      return;
    }
    const idx = pointerIndex(evt);
    if (idx === hoverIdx) {
      return;
    }
    hoverIdx = idx;
    updateHoverLabel(idx, evt);
    renderChart(idx);
  };

  const onLeave = () => {
    if (pan) return;
    hoverIdx = null;
    hideHoverCard();
    renderChart();
  };

  const onDown = (evt) => {
    if (evt.button != null && evt.button !== 0) return;
    const rect = els.priceChart.getBoundingClientRect();
    pan = {
      originX: evt.clientX,
      lastX: evt.clientX,
      width: rect.width,
      moved: false,
    };
    els.chartWrap?.classList.add("is-panning");
    try {
      els.priceChart.setPointerCapture(evt.pointerId);
    } catch {
      /* ignore */
    }
  };

  const onUp = (evt) => {
    if (!pan) return;
    const wasPan = pan.moved;
    pan = null;
    els.chartWrap?.classList.remove("is-panning");
    try {
      els.priceChart.releasePointerCapture(evt.pointerId);
    } catch {
      /* ignore */
    }
    if (!wasPan) {
      const idx = pointerIndex(evt);
      hoverIdx = idx;
      updateHoverLabel(idx, evt);
      renderChart(idx);
    } else {
      hideHoverCard();
      hoverIdx = null;
      renderChart();
    }
  };

  els.priceChart.addEventListener("pointerdown", onDown);
  els.priceChart.addEventListener("pointermove", onMove);
  els.priceChart.addEventListener("pointerup", onUp);
  els.priceChart.addEventListener("pointercancel", onUp);
  els.priceChart.addEventListener("pointerleave", onLeave);

  els.priceChart.addEventListener(
    "wheel",
    (evt) => {
      const total = (chartState.allItems || []).length;
      if (!total) return;
      evt.preventDefault();
      hideHoverCard();
      hoverIdx = null;

      const rect = els.priceChart.getBoundingClientRect();
      const layout = chartLayout(rect.width, rect.height);
      const x = evt.clientX - rect.left;
      let anchorRatio = 0.5;
      if (x >= layout.price.x && x <= layout.price.x + layout.price.w) {
        anchorRatio = (x - layout.price.x) / layout.price.w;
      }

      // 横向滚轮/触控板：平移；纵向：以指针为锚点缩放
      if (Math.abs(evt.deltaX) > Math.abs(evt.deltaY) * 1.15) {
        const { maxStart } = chartViewWindow();
        if (maxStart <= 0) return;
        const step = Math.max(1, Math.round(Math.abs(evt.deltaX) / 40));
        setChartViewStart(chartState.viewStart + (evt.deltaX > 0 ? step : -step), {
          render: true,
        });
        return;
      }

      const steps = Math.max(1, Math.min(5, Math.round(Math.abs(evt.deltaY) / 72) || 1));
      const base = evt.deltaY > 0 ? 1.14 : 1 / 1.14; // 向下：看更多；向上：放大
      const factor = base ** steps;
      zoomChartViewport(anchorRatio, factor, { render: true });
    },
    { passive: false }
  );

  if (typeof ResizeObserver !== "undefined" && els.chartWrap) {
    let timer = 0;
    const ro = new ResizeObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        syncChartScrollBar();
        renderChart(hoverIdx);
      }, 60);
    });
    ro.observe(els.chartWrap);
  } else {
    window.addEventListener("resize", () => {
      syncChartScrollBar();
      renderChart(hoverIdx);
    });
  }
}

els.refreshNewsBtn.addEventListener("click", () =>
  loadAllNews({ refresh: true })
);

setupBackLink();
setupScrollLoaders();
setupMetricTips();
setupChart();
(async () => {
  await loadProfile();
  await Promise.all([
    loadChart("day"),
    loadAllNews({ refresh: false }),
  ]);
})();
