const params = new URLSearchParams(window.location.search);
const code = (params.get("code") || "").trim();
const nameHint = (params.get("name") || "").trim();
const industry = (params.get("industry") || "").trim();

const DEFAULT_DAYS = 3;
const FULL_DAYS = 730;

const KINDS = [
  { key: "notices", title: "公司公告", empty: "近窗口内暂无公司公告" },
  { key: "news", title: "外部新闻", empty: "近窗口内暂无相关外部新闻" },
  { key: "reports", title: "机构研报", empty: "近窗口内暂无机构研报" },
];

/** @type {Record<string, number>} */
const sectionDays = {
  notices: DEFAULT_DAYS,
  news: DEFAULT_DAYS,
  reports: DEFAULT_DAYS,
};

const els = {
  pageTitle: document.getElementById("pageTitle"),
  pageSub: document.getElementById("pageSub"),
  backLink: document.getElementById("backLink"),
  companyBreadcrumb: document.getElementById("companyBreadcrumb"),
  companyName: document.getElementById("companyName"),
  companyMeta: document.getElementById("companyMeta"),
  quoteStrip: document.getElementById("quoteStrip"),
  metricsGrid: document.getElementById("metricsGrid"),
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
    olderBtn: document.querySelector(`.load-older-btn[data-kind="${kind}"]`),
  };
}

function renderQuote(stock) {
  const cells = [
    ["价格", stock.price, ""],
    ["近1日", stock.change_1d, changeClass(stock.change_1d)],
    ["近5日", stock.change_5d, changeClass(stock.change_5d)],
    ["今年以来", stock.change_ytd, changeClass(stock.change_ytd)],
    ["市值(亿)", stock.market_cap, ""],
  ];
  els.quoteStrip.innerHTML = cells
    .map(
      ([label, value, cls]) => `
      <div class="quote-item">
        <span class="detail-label">${escapeHtml(label)}</span>
        <span class="detail-value ${cls}">${escapeHtml(displayValue(value))}</span>
      </div>`
    )
    .join("");
}

function renderMetrics(stock) {
  const items = [
    ["完整代码", stock.full_code],
    ["纳入时间", stock.include_date],
    ["市盈率", stock.pe],
    ["PE(TTM)", stock.pe_ttm],
    ["市净率", stock.pb],
    ["ROE", stock.roe],
    ["股息率", stock.dividend_yield],
    ["净利增速", stock.profit_growth],
    ["营收增速", stock.revenue_growth],
  ];
  els.metricsGrid.innerHTML = items
    .map(
      ([label, value]) => `
      <div class="detail-item">
        <span class="detail-label">${escapeHtml(label)}</span>
        <span class="detail-value">${escapeHtml(displayValue(value))}</span>
      </div>`
    )
    .join("");
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

function daysLabel(days) {
  if (days <= DEFAULT_DAYS) return `近 ${days} 天`;
  if (days >= 360) return `近约 ${Math.round(days / 365)} 年`;
  return `近 ${days} 天`;
}

function applyStock(stock, industryMeta = {}) {
  const displayName = stock.name || nameHint || code;
  document.title = `${displayName} · 公司详情`;
  els.pageTitle.textContent = displayName;
  els.companyName.textContent = displayName;
  const breadcrumbParts = [
    industryMeta.l1_name,
    industryMeta.l2_name,
    industryMeta.name || industryMeta.l3_name,
  ].filter(Boolean);
  els.companyBreadcrumb.textContent = breadcrumbParts.length
    ? breadcrumbParts.join(" / ")
    : "公司详情";
  els.companyMeta.textContent = [
    `代码 ${stock.code || code}`,
    stock.full_code ? `完整代码 ${stock.full_code}` : "",
    industry ? `行业 ${industry}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  renderQuote(stock);
  renderMetrics(stock);
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

async function loadNewsKind(kind, days, { refresh = false } = {}) {
  const ui = sectionEls(kind);
  const conf = KINDS.find((k) => k.key === kind);
  if (!ui.body || !conf) return;

  const older = days > DEFAULT_DAYS;
  ui.meta.textContent = older
    ? `正在加载${daysLabel(days)}…`
    : "正在加载近 3 天…";
  ui.body.innerHTML = `<p class="muted">请稍候…</p>`;
  if (ui.olderBtn) ui.olderBtn.disabled = true;

  try {
    const qs = new URLSearchParams({
      code,
      name: nameHint || els.companyName.textContent || "",
      days: String(days),
      kind,
    });
    if (refresh) qs.set("refresh", "1");
    const json = await api(`/api/stocks/news?${qs.toString()}`);
    const data = json.data || {};
    const groups = data.groups || {};
    const items = groups[kind] || [];
    const span =
      data.span_from && data.span_to
        ? `${data.span_from} ~ ${data.span_to}`
        : daysLabel(days);
    const fullDays = Number(data.full_days) || FULL_DAYS;

    sectionDays[kind] = Number(data.days) || days;
    ui.meta.textContent = `${daysLabel(sectionDays[kind])} · ${span} · ${items.length} 条 · 更新于 ${data.updated_at || "-"}`;
    ui.body.innerHTML = renderNewsList(items, conf.empty);

    if (ui.olderBtn) {
      const atFull = sectionDays[kind] >= fullDays - 5;
      ui.olderBtn.hidden = atFull;
      ui.olderBtn.disabled = false;
      ui.olderBtn.dataset.fullDays = String(fullDays);
      ui.olderBtn.textContent = atFull
        ? "已是全部可查区间"
        : `加载更早（${daysLabel(fullDays)}）`;
    }
  } catch (err) {
    ui.meta.textContent = "加载失败";
    ui.body.innerHTML = `<p class="news-error">${escapeHtml(err.message || String(err))}</p>`;
    if (ui.olderBtn) ui.olderBtn.disabled = false;
  }
}

async function loadAllNews({ refresh = false, days = DEFAULT_DAYS } = {}) {
  if (!code) return;
  els.refreshNewsBtn.disabled = true;
  await Promise.all(
    KINDS.map(({ key }) => {
      sectionDays[key] = days;
      return loadNewsKind(key, days, { refresh });
    })
  );
  els.refreshNewsBtn.disabled = false;
}

function setupBackLink() {
  if (industry) {
    els.backLink.href = `/?industry=${encodeURIComponent(industry)}`;
  } else {
    els.backLink.href = "/";
  }
}

els.refreshNewsBtn.addEventListener("click", () =>
  loadAllNews({ refresh: true, days: DEFAULT_DAYS })
);

document.querySelectorAll(".load-older-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const kind = btn.getAttribute("data-kind");
    if (!kind) return;
    const fullDays = Number(btn.dataset.fullDays) || FULL_DAYS;
    loadNewsKind(kind, fullDays, { refresh: false });
  });
});

setupBackLink();
(async () => {
  await loadProfile();
  await loadAllNews({ refresh: false, days: DEFAULT_DAYS });
})();
