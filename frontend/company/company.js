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
  refreshNewsBtn: document.getElementById("refreshNewsBtn"),
  errorBox: document.getElementById("errorBox"),
};

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

/** 指标含义说明（悬停展示） */
const METRIC_TIPS = {
  最新: "当前最新成交价。",
  涨幅: "相对昨收的涨跌幅百分比。",
  涨跌: "相对昨收的涨跌金额。",
  市值: "总市值 = 最新价 × 总股本。",
  换手: "换手率 = 成交量 / 流通股本，反映当日流通股交易活跃度。",
  今开: "今日开盘价，集合竞价后的第一笔成交价。",
  昨收: "上一交易日收盘价。",
  最高: "今日盘中最高成交价。",
  最低: "今日盘中最低成交价。",
  均价: "成交额 / 成交量，反映当日平均交易成本。",
  总手: "今日累计成交量，单位为手（1 手 = 100 股）。",
  金额: "今日累计成交金额。",
  "换手(实)": "按自由流通股本计算的换手率，更能反映实际可交易股份的活跃度。",
  现手: "最近一笔成交的数量（手）。",
  量比: "当日开盘至现在的平均每分钟成交量，与过去 5 个交易日同期平均每分钟成交量之比。",
  振幅: "（最高价 − 最低价）/ 昨收 × 100%，反映当日价格波动幅度。",
  实体涨幅: "（最新价 − 今开）/ 昨收，衡量开盘后实体涨跌幅度。",
  涨停: "当日涨停价格。",
  跌停: "当日跌停价格。",
  外盘: "主动买入成交量合计，偏多力量参考。",
  内盘: "主动卖出成交量合计，偏空力量参考。",
  委买: "当前买盘委托量合计。",
  委卖: "当前卖盘委托量合计。",
  委差: "委买量 − 委卖量，正值买盘更强，负值卖盘更强。",
  委比: "（委买 − 委卖）/（委买 + 委卖），衡量买卖盘力量对比。",
  盘后委买: "盘后固定价格交易阶段的买盘委托量。",
  盘后量: "盘后固定价格交易成交量。",
  盘后额: "盘后固定价格交易成交额。",
  主力净流入: "主力资金（超大单+大单）净流入金额，正值为流入，负值为流出。",
  "5日净流入": "近 5 个交易日主力资金净流入合计。",
  近1日: "最近 1 个交易日涨跌幅。",
  "3日": "近 3 个交易日累计涨跌幅。",
  "5日": "近 5 个交易日累计涨跌幅。",
  "10日": "近 10 个交易日累计涨跌幅。",
  "20日": "近 20 个交易日累计涨跌幅。",
  "60日": "近 60 个交易日累计涨跌幅。",
  近半年: "近约半年（约 120 个交易日）累计涨跌幅。",
  近1年: "近约一年（约 250 个交易日）累计涨跌幅。",
  今年: "今年以来（相对年初首个交易日）累计涨跌幅。",
  "52周最高": "近 52 周（约一年）内的最高价，前复权口径。",
  "52周最低": "近 52 周（约一年）内的最低价，前复权口径。",
  历史最高: "上市以来最高价，前复权口径。",
  历史最低: "上市以来最低价，前复权口径。",
  "市盈率(动)": "动态市盈率 = 总市值 / 预估全年净利润，反映按最新盈利预测的估值。",
  "市盈率(静)": "静态市盈率 = 总市值 / 上一年度净利润。",
  "市盈率(TTM)": "滚动市盈率 = 总市值 / 近四个季度净利润合计。",
  市净率: "市净率 = 总市值 / 净资产，衡量股价相对账面净资产的溢价。",
  "市销率(TTM)": "市销率 = 总市值 / 近四个季度营业收入合计。",
  每股收益: "归属于普通股股东的净利润 / 总股本。",
  每股净资产: "净资产 / 总股本，即账面每股权益。",
  净资产收益率: "净利润 / 净资产，衡量股东权益的回报水平（ROE）。",
  "股息(TTM)": "近 12 个月每股派息合计（税前口径，供参考）。",
  股息率: "股息率 ≈ 每股股息(TTM) / 最新价，衡量分红收益率。",
  净利增速: "净利润同比增长率。",
  营收增速: "营业收入同比增长率。",
  总股本: "公司已发行的股份总数。",
  流通股: "可在二级市场交易的股份数量。",
  自由流通股: "扣除持股 ≥5% 等受限股份后，实际更易流通的股份数量。",
  总市值: "最新价 × 总股本。",
  流通市值: "最新价 × 流通股本。",
  自由流通市值: "最新价 × 自由流通股本。",
  发行股本: "发行时或披露口径下的股本数量。",
  注册资本: "公司工商登记的注册资本。",
  纳入时间: "该公司被纳入当前申万行业分类的时间。",
  上市时间: "股票在交易所正式挂牌上市的日期。",
};

function metricTip(label) {
  return METRIC_TIPS[label] || "";
}

function metricCell([label, value, cls = ""]) {
  const tip = metricTip(label);
  const tipAttr = tip
    ? ` data-tip="${escapeHtml(tip)}" title="${escapeHtml(tip)}"`
    : "";
  const tipClass = tip ? " has-tip" : "";
  return `
    <div class="stat-cell${tipClass}"${tipAttr}>
      <span class="detail-label">${escapeHtml(label)}</span>
      <span class="detail-value ${cls}">${escapeHtml(displayValue(value))}</span>
    </div>`;
}

function renderMetricSection(title, items) {
  const cells = items.filter(([, v]) => displayValue(v) !== "-");
  if (!cells.length) return "";
  return `
    <section class="metrics-section">
      <h4 class="metrics-section-title">${escapeHtml(title)}</h4>
      <div class="company-metrics">
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

  const html = [
    renderMetricSection("当日行情", [
      ["今开", stock.open],
      ["昨收", stock.prev_close],
      ["最高", stock.high],
      ["最低", stock.low],
      ["均价", stock.avg_price],
      ["总手", stock.volume],
      ["金额", stock.amount],
      ["换手", stock.turnover],
      ["换手(实)", stock.turnover_real],
      ["现手", stock.current_volume],
      ["量比", stock.volume_ratio],
      ["振幅", stock.amplitude],
      ["实体涨幅", stock.solid_change, changeClass(stock.solid_change)],
      ["涨停", stock.limit_up],
      ["跌停", stock.limit_down],
      ["外盘", stock.outer_vol],
      ["内盘", stock.inner_vol],
      ["委买", stock.bid_vol],
      ["委卖", stock.ask_vol],
      ["委差", stock.bid_ask_diff, changeClass(stock.bid_ask_diff)],
      ["委比", stock.bid_ask_ratio, changeClass(stock.bid_ask_ratio)],
      ["盘后委买", stock.after_bid],
      ["盘后量", stock.after_volume],
      ["盘后额", stock.after_amount],
    ]),
    renderMetricSection("资金流向", [
      ["主力净流入", stock.main_net_inflow, changeClass(stock.main_net_inflow)],
      ["5日净流入", stock.main_net_inflow_5d, changeClass(stock.main_net_inflow_5d)],
    ]),
    renderMetricSection("区间涨幅", [
      ["近1日", stock.change_1d, changeClass(stock.change_1d)],
      ["3日", stock.change_3d, changeClass(stock.change_3d)],
      ["5日", stock.change_5d, changeClass(stock.change_5d)],
      ["10日", stock.change_10d, changeClass(stock.change_10d)],
      ["20日", stock.change_20d, changeClass(stock.change_20d)],
      ["60日", stock.change_60d, changeClass(stock.change_60d)],
      ["近半年", stock.change_half_year, changeClass(stock.change_half_year)],
      ["近1年", stock.change_1y, changeClass(stock.change_1y)],
      ["今年", stock.change_ytd, changeClass(stock.change_ytd)],
      ["52周最高", stock.high_52w],
      ["52周最低", stock.low_52w],
      ["历史最高", stock.high_all],
      ["历史最低", stock.low_all],
    ]),
    renderMetricSection("估值与每股", [
      ["市盈率(动)", stock.pe],
      ["市盈率(静)", stock.pe_static],
      ["市盈率(TTM)", stock.pe_ttm],
      ["市净率", stock.pb],
      ["市销率(TTM)", stock.ps_ttm],
      ["每股收益", stock.eps],
      ["每股净资产", stock.bvps],
      ["净资产收益率", stock.roe],
      ["股息(TTM)", stock.dividend_ttm],
      ["股息率", stock.dividend_yield],
      ["净利增速", stock.profit_growth || stock.profit_yoy],
      ["营收增速", stock.revenue_growth || stock.revenue_yoy],
    ]),
    renderMetricSection("股本与市值", [
      ["总股本", stock.total_shares],
      ["流通股", stock.float_shares],
      ["自由流通股", stock.free_float_shares],
      ["总市值", mcap],
      ["流通市值", stock.float_market_cap],
      ["自由流通市值", stock.free_float_market_cap],
      ["发行股本", stock.issued_shares],
      ["注册资本", stock.registered_capital],
      ["纳入时间", stock.include_date],
      ["上市时间", stock.list_date],
    ]),
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

  const prevCount = st.items.length;
  const prevOldest = oldestPublished(st.items);

  try {
    const data = await fetchNewsKind(kind, days, { refresh });
    const groups = data.groups || {};
    const items = groups[kind] || [];
    const fullDays = Number(data.full_days) || FULL_DAYS;

    st.fullDays = fullDays;
    st.days = Number(data.days) || days;
    st.updatedAt = data.updated_at || "";
    st.items = items;
    const newestOldest = oldestPublished(items);
    const noDeeper =
      prevCount > 0 &&
      items.length <= prevCount &&
      newestOldest &&
      prevOldest &&
      newestOldest >= prevOldest;
    st.exhausted =
      st.days >= fullDays - 5 ||
      Boolean(data.source_capped) ||
      noDeeper;
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

els.refreshNewsBtn.addEventListener("click", () =>
  loadAllNews({ refresh: true })
);

setupBackLink();
setupScrollLoaders();
(async () => {
  await loadProfile();
  await loadAllNews({ refresh: false });
})();
