const params = new URLSearchParams(window.location.search);
const code = (params.get("code") || "").trim();
const nameHint = (params.get("name") || "").trim();
const industry = (params.get("industry") || "").trim();

const els = {
  pageTitle: document.getElementById("pageTitle"),
  pageSub: document.getElementById("pageSub"),
  backLink: document.getElementById("backLink"),
  companyBreadcrumb: document.getElementById("companyBreadcrumb"),
  companyName: document.getElementById("companyName"),
  companyMeta: document.getElementById("companyMeta"),
  quoteStrip: document.getElementById("quoteStrip"),
  metricsGrid: document.getElementById("metricsGrid"),
  newsMeta: document.getElementById("newsMeta"),
  newsBody: document.getElementById("newsBody"),
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

function renderNewsItems(items) {
  if (!items.length) {
    els.newsBody.innerHTML = `<p class="muted">暂无筛选出的重要新闻</p>`;
    return;
  }
  els.newsBody.innerHTML = items
    .map((item) => {
      const title = escapeHtml(item.title || "无标题");
      const url = String(item.url || "").trim();
      const titleHtml = url
        ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${title}</a>`
        : `<span>${title}</span>`;
      const kindLabel = item.kind === "notice" ? "公告" : "新闻";
      return `
        <article class="news-item">
          <div class="news-item-meta">
            <time>${escapeHtml(item.published_at || "-")}</time>
            <span class="news-kind">${kindLabel}</span>
            <span>${escapeHtml(item.source || "-")}</span>
            ${item.why ? `<span class="news-why">${escapeHtml(item.why)}</span>` : ""}
          </div>
          <h3>${titleHtml}</h3>
          <p>${escapeHtml(truncateText(item.summary || ""))}</p>
        </article>
      `;
    })
    .join("");
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

async function loadNews({ refresh = false } = {}) {
  if (!code) return;
  els.newsMeta.textContent = refresh ? "正在重新拉取…" : "正在收集近 1–2 年公告与新闻…";
  els.newsBody.innerHTML = `<p class="muted">请稍候…</p>`;
  els.refreshNewsBtn.disabled = true;
  try {
    const qs = new URLSearchParams({
      code,
      name: nameHint || els.companyName.textContent || "",
    });
    if (refresh) qs.set("refresh", "1");
    const json = await api(`/api/stocks/news?${qs.toString()}`);
    const data = json.data || {};
    const modeLabel = data.mode === "llm" ? "LLM 筛选" : "启发式筛选";
    const span =
      data.span_from && data.span_to ? `${data.span_from} ~ ${data.span_to}` : "近1–2年";
    els.newsMeta.textContent = `${modeLabel} · ${span} · 共 ${(data.items || []).length} 条 · 更新于 ${data.updated_at || "-"}`;
    renderNewsItems(data.items || []);
  } catch (err) {
    els.newsMeta.textContent = "加载失败";
    els.newsBody.innerHTML = `<p class="news-error">${escapeHtml(err.message || String(err))}</p>`;
  } finally {
    els.refreshNewsBtn.disabled = false;
  }
}

function setupBackLink() {
  if (industry) {
    els.backLink.href = `/?industry=${encodeURIComponent(industry)}`;
  } else {
    els.backLink.href = "/";
  }
}

els.refreshNewsBtn.addEventListener("click", () => loadNews({ refresh: true }));

setupBackLink();
(async () => {
  await loadProfile();
  await loadNews({ refresh: false });
})();
