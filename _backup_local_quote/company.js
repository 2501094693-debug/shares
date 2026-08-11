const params = new URLSearchParams(window.location.search);
const code = (params.get("code") || "").trim();
const nameHint = (params.get("name") || "").trim();
const industry = (params.get("industry") || "").trim();
const fromList = (params.get("from") || "").trim(); // search | industry
const returnCname = (params.get("cname") || "").trim();
const returnCcode = (params.get("ccode") || "").trim();

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

function readCachedStock(stockCode) {
  try {
    const raw = sessionStorage.getItem(`stock:${stockCode}`);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
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
    ["市值", stock.total_market_cap || (stock.market_cap ? `${displayValue(stock.market_cap)}亿` : ""), ""],
    ["换手", stock.turnover, ""],
  ];
  els.quoteStrip.innerHTML = cells
    .map(
      ([label, value, cls]) => `
      <div class="stat-cell">
        <span class="detail-label">${escapeHtml(label)}</span>
        <span class="detail-value ${cls}">${escapeHtml(displayValue(value))}</span>
      </div>`
    )
    .join("");
}

function metricCell([label, value, cls = ""]) {
  return `
    <div class="stat-cell">
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
      ["股息率", stock.dividend_yield],
      ["净利增速", stock.profit_growth || stock.profit_yoy],
      ["营收增速", stock.revenue_growth || stock.revenue_yoy],
    ]),
    renderMetricSection("股本与市值", [
      ["总股本", stock.total_shares],
      ["流通股", stock.float_shares],
      ["总市值", stock.total_market_cap || (stock.market_cap ? `${displayValue(stock.market_cap)}亿` : "")],
      ["流通市值", stock.float_market_cap],
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

async function loadProfile() {
  if (!code) {
    setError("缺少公司代码");
    return null;
  }

  const cached = readCachedStock(code);
  if (cached) {
    applyStock(cached, {
      l1_name: cached.l1_name,
      l2_name: cached.l2_name,
      name: cached.l3_name,
    });
  }

  try {
    const qs = new URLSearchParams({ code });
    if (industry) qs.set("industry", industry);
    if (nameHint) qs.set("name", nameHint);
    const json = await api(`/api/stocks/profile?${qs.toString()}`);
    const data = json.data || {};
    const stock = data.stock || {};
    applyStock(stock, data.industry || {});
    try {
      sessionStorage.setItem(`stock:${code}`, JSON.stringify(stock));
    } catch {
      /* ignore quota */
    }
    return stock;
  } catch (err) {
    if (!cached) setError(err.message || String(err));
    return cached;
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
  // 列表页用 sessionStorage 快照恢复地图；URL 参数作兜底
  if (fromList === "search" || returnCname || returnCcode) {
    const qs = new URLSearchParams();
    qs.set("from", "search");
    if (returnCname) qs.set("cname", returnCname);
    if (returnCcode) qs.set("ccode", returnCcode);
    els.backLink.href = `/?${qs.toString()}`;
    return;
  }
  if (fromList === "industry" && industry) {
    els.backLink.href = `/?industry=${encodeURIComponent(industry)}`;
    return;
  }
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
