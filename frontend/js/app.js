const state = {
  tree: [],
  selectedCode: null,
  stocks: [],
  nameFilter: "",
  codeFilter: "",
  highlightCode: "",
  expandedCode: "",
  page: 1,
  pageSize: 20,
  newsCode: "",
  newsName: "",
  newsLoading: false,
  newsRequestId: 0,
};

const MAIN_COL_COUNT = 9;

const els = {
  tree: document.getElementById("tree"),
  treeMeta: document.getElementById("treeMeta"),
  searchInput: document.getElementById("searchInput"),
  searchResults: document.getElementById("searchResults"),
  companyNameSearch: document.getElementById("companyNameSearch"),
  companyCodeSearch: document.getElementById("companyCodeSearch"),
  companySearchPanel: document.getElementById("companySearchPanel"),
  companySearchResults: document.getElementById("companySearchResults"),
  closeCompanySearch: document.getElementById("closeCompanySearch"),
  indexStatus: document.getElementById("indexStatus"),
  refreshBtn: document.getElementById("refreshBtn"),
  emptyState: document.getElementById("emptyState"),
  detail: document.getElementById("detail"),
  breadcrumb: document.getElementById("breadcrumb"),
  industryTitle: document.getElementById("industryTitle"),
  industryMeta: document.getElementById("industryMeta"),
  stockBody: document.getElementById("stockBody"),
  nameFilter: document.getElementById("nameFilter"),
  codeFilter: document.getElementById("codeFilter"),
  reloadStocksBtn: document.getElementById("reloadStocksBtn"),
  pageSize: document.getElementById("pageSize"),
  prevPage: document.getElementById("prevPage"),
  nextPage: document.getElementById("nextPage"),
  pageInfo: document.getElementById("pageInfo"),
  loading: document.getElementById("loading"),
  errorBox: document.getElementById("errorBox"),
  newsPanel: document.getElementById("newsPanel"),
  newsPanelTitle: document.getElementById("newsPanelTitle"),
  newsPanelMeta: document.getElementById("newsPanelMeta"),
  newsPanelBody: document.getElementById("newsPanelBody"),
  refreshNewsBtn: document.getElementById("refreshNewsBtn"),
  closeNewsPanel: document.getElementById("closeNewsPanel"),
};

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const json = await res.json();
  if (!res.ok || !json.ok) {
    throw new Error(json.error || `请求失败 (${res.status})`);
  }
  return json;
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

function setLoading(on) {
  els.loading.classList.toggle("hidden", !on);
}

function countL3(tree) {
  let n = 0;
  for (const l1 of tree) {
    for (const l2 of l1.children || []) {
      n += (l2.children || []).length;
    }
  }
  return n;
}

function renderTree(tree) {
  els.tree.innerHTML = "";
  for (const l1 of tree) {
    els.tree.appendChild(buildNode(l1, 1));
  }
  els.treeMeta.textContent = `${tree.length} 个一级 · ${countL3(tree)} 个三级`;
}

function buildNode(node, level) {
  const wrap = document.createElement("div");
  wrap.className = "tree-item";

  const row = document.createElement("button");
  row.type = "button";
  row.className = `tree-row level-${level}`;
  row.dataset.code = node.code;

  const hasChildren = Array.isArray(node.children) && node.children.length > 0;
  const chevron = document.createElement("span");
  chevron.className = "chevron";
  chevron.textContent = hasChildren ? "▸" : "·";

  const label = document.createElement("span");
  label.textContent = node.name;

  const count = document.createElement("span");
  count.className = "count";
  count.textContent = node.count ?? "";

  row.append(chevron, label, count);
  wrap.appendChild(row);

  let childBox = null;
  if (hasChildren) {
    childBox = document.createElement("div");
    childBox.className = "children";
    for (const child of node.children) {
      childBox.appendChild(buildNode(child, level + 1));
    }
    wrap.appendChild(childBox);

    row.addEventListener("click", () => {
      const open = childBox.classList.toggle("open");
      chevron.classList.toggle("open", open);
    });
  } else if (level === 3) {
    row.addEventListener("click", () => selectIndustry(node.code, row));
  }

  return wrap;
}

function clearActive() {
  els.tree.querySelectorAll(".tree-row.active").forEach((el) => {
    el.classList.remove("active");
  });
}

function filteredStocks() {
  const nameKw = state.nameFilter.trim().toLowerCase();
  const codeKw = state.codeFilter.trim().toLowerCase();
  return state.stocks.filter((s) => {
    if (nameKw && !String(s.name || "").toLowerCase().includes(nameKw)) {
      return false;
    }
    if (codeKw) {
      const hay = `${s.code || ""}${s.full_code || ""}`.toLowerCase();
      if (!hay.includes(codeKw)) return false;
    }
    return true;
  });
}

function totalPages(total) {
  return Math.max(1, Math.ceil(total / state.pageSize));
}

async function selectIndustry(code, rowEl = null, options = {}) {
  state.selectedCode = code;
  clearActive();
  if (rowEl) {
    rowEl.classList.add("active");
  } else {
    const match = els.tree.querySelector(`.tree-row[data-code="${CSS.escape(code)}"]`);
    if (match) match.classList.add("active");
  }

  els.emptyState.classList.add("hidden");
  els.detail.classList.add("hidden");
  setError("");
  setLoading(true);

  try {
    const json = await api(`/api/industries/${encodeURIComponent(code)}/stocks`);
    const data = json.data;
    state.stocks = data.stocks || [];
    state.highlightCode = options.highlightCode || "";
    const ind = data.industry || {};
    els.breadcrumb.textContent = `${ind.l1_name || "-"} / ${ind.l2_name || "-"}`;
    els.industryTitle.textContent = ind.name || code;
    els.industryMeta.textContent = `行业代码 ${ind.code || code} · 共 ${data.count ?? state.stocks.length} 家上市公司 · 更新于 ${data.updated_at || "-"}`;
    els.nameFilter.value = options.nameFilter || "";
    els.codeFilter.value = options.codeFilter || "";
    state.nameFilter = els.nameFilter.value;
    state.codeFilter = els.codeFilter.value;
    state.page = 1;
    state.expandedCode = state.highlightCode || "";

    if (state.highlightCode) {
      const rows = filteredStocks();
      const hi = rows.findIndex(
        (s) => s.code === state.highlightCode || s.full_code === state.highlightCode
      );
      if (hi >= 0) state.page = Math.floor(hi / state.pageSize) + 1;
    }

    renderStocks();
    els.detail.classList.remove("hidden");

    if (state.highlightCode) {
      const target = els.stockBody.querySelector("tr.highlight");
      if (target) target.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  } catch (err) {
    setError(err.message || String(err));
  } finally {
    setLoading(false);
  }
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

function changeCellHtml(v) {
  const text = displayValue(v);
  const cls = changeClass(text);
  return `<td class="${cls}">${escapeHtml(text)}</td>`;
}

function stockKey(s) {
  return s.code || s.full_code || "";
}

function detailItems(s) {
  return [
    ["完整代码", s.full_code],
    ["纳入时间", s.include_date],
    ["市盈率", s.pe],
    ["PE(TTM)", s.pe_ttm],
    ["市净率", s.pb],
    ["ROE", s.roe],
    ["股息率", s.dividend_yield],
    ["净利增速", s.profit_growth],
    ["营收增速", s.revenue_growth],
  ];
}

function renderDetailRow(s) {
  const tr = document.createElement("tr");
  tr.className = "detail-row";
  const items = detailItems(s)
    .map(
      ([label, value]) => `
      <div class="detail-item">
        <span class="detail-label">${escapeHtml(label)}</span>
        <span class="detail-value">${escapeHtml(displayValue(value))}</span>
      </div>`
    )
    .join("");
  tr.innerHTML = `
    <td colspan="${MAIN_COL_COUNT}">
      <div class="stock-detail">
        ${items}
        <div class="detail-actions-row">
          <button type="button" class="btn ghost news-btn">重要新闻</button>
        </div>
      </div>
    </td>
  `;
  const newsBtn = tr.querySelector(".news-btn");
  newsBtn?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    openNewsPanel(s.code, s.name);
  });
  return tr;
}

function truncateText(text, max = 120) {
  const s = String(text || "").trim();
  if (s.length <= max) return s;
  return `${s.slice(0, max)}…`;
}

function renderNewsItems(items) {
  if (!items.length) {
    els.newsPanelBody.innerHTML = `<p class="muted">暂无筛选出的重要新闻</p>`;
    return;
  }
  els.newsPanelBody.innerHTML = items
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

async function loadCompanyNews({ refresh = false } = {}) {
  if (!state.newsCode || !els.newsPanel || !els.newsPanelBody) return;
  if (state.newsLoading && !refresh) return;

  const requestId = ++state.newsRequestId;
  const code = state.newsCode;
  const name = state.newsName;
  state.newsLoading = true;
  els.newsPanelTitle.textContent = `${name || "公司"}（${code}）重要新闻`;
  els.newsPanelMeta.textContent = refresh ? "正在重新拉取…" : "正在收集新闻…";
    els.newsPanelBody.innerHTML = `<p class="muted">正在收集近 1–2 年公司公告与相关新闻，请稍候…</p>`;
  if (els.refreshNewsBtn) els.refreshNewsBtn.disabled = true;

  try {
    const params = new URLSearchParams({
      code,
      name: name || "",
    });
    if (refresh) params.set("refresh", "1");
    const json = await api(`/api/stocks/news?${params.toString()}`);
    if (requestId !== state.newsRequestId) return;
    const data = json.data || {};
    const modeLabel = data.mode === "llm" ? "LLM 筛选" : "启发式筛选";
    const span =
      data.span_from && data.span_to ? `${data.span_from} ~ ${data.span_to}` : "近1–2年";
    els.newsPanelMeta.textContent = `${modeLabel} · ${span} · 共 ${(data.items || []).length} 条 · 更新于 ${data.updated_at || "-"}`;
    renderNewsItems(data.items || []);
    els.newsPanel.scrollIntoView({ block: "nearest", behavior: "smooth" });
  } catch (err) {
    if (requestId !== state.newsRequestId) return;
    els.newsPanelMeta.textContent = "加载失败";
    els.newsPanelBody.innerHTML = `<p class="news-error">${escapeHtml(err.message || String(err))}</p>`;
  } finally {
    if (requestId === state.newsRequestId) {
      state.newsLoading = false;
      if (els.refreshNewsBtn) els.refreshNewsBtn.disabled = false;
    }
  }
}

function openNewsPanel(code, name) {
  if (!els.newsPanel) return;
  const nextCode = code || "";
  const nextName = name || "";
  const sameCompany = state.newsCode === nextCode && !els.newsPanel.classList.contains("hidden");
  state.newsCode = nextCode;
  state.newsName = nextName;
  els.newsPanel.classList.remove("hidden");
  els.emptyState.classList.add("hidden");
  els.newsPanel.scrollIntoView({ block: "nearest", behavior: "smooth" });
  if (sameCompany && !state.newsLoading) {
    // 已打开同一公司时不再重复请求
    return;
  }
  loadCompanyNews({ refresh: false });
}

function closeNewsPanel() {
  if (!els.newsPanel) return;
  els.newsPanel.classList.add("hidden");
  state.newsRequestId += 1;
  state.newsLoading = false;
  if (els.refreshNewsBtn) els.refreshNewsBtn.disabled = false;
}

function toggleStockDetail(code) {
  state.expandedCode = state.expandedCode === code ? "" : code;
  renderStocks();
}

function renderStocks() {
  const rows = filteredStocks();
  const pages = totalPages(rows.length);
  if (state.page > pages) state.page = pages;
  if (state.page < 1) state.page = 1;

  const start = (state.page - 1) * state.pageSize;
  const pageRows = rows.slice(start, start + state.pageSize);

  els.stockBody.innerHTML = "";
  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="${MAIN_COL_COUNT}" class="muted">没有匹配的公司</td>`;
    els.stockBody.appendChild(tr);
    els.pageInfo.textContent = "0 / 0";
    els.prevPage.disabled = true;
    els.nextPage.disabled = true;
    return;
  }

  pageRows.forEach((s, idx) => {
    const key = stockKey(s);
    const expanded = state.expandedCode && state.expandedCode === key;
    const tr = document.createElement("tr");
    tr.className = "stock-row";
    if (expanded) tr.classList.add("expanded");
    const isHighlight =
      state.highlightCode &&
      (s.code === state.highlightCode || s.full_code === state.highlightCode);
    if (isHighlight) tr.classList.add("highlight");
    tr.dataset.code = key;
    tr.innerHTML = `
      <td class="col-expand"><span class="row-chevron${expanded ? " open" : ""}">▸</span></td>
      <td>${start + idx + 1}</td>
      <td class="code">${escapeHtml(s.code)}</td>
      <td>${escapeHtml(s.name)}</td>
      <td>${escapeHtml(displayValue(s.price))}</td>
      ${changeCellHtml(s.change_1d)}
      ${changeCellHtml(s.change_5d)}
      ${changeCellHtml(s.change_ytd)}
      <td>${escapeHtml(displayValue(s.market_cap))}</td>
    `;
    tr.addEventListener("click", () => toggleStockDetail(key));
    els.stockBody.appendChild(tr);
    if (expanded) {
      els.stockBody.appendChild(renderDetailRow(s));
    }
  });

  els.pageInfo.textContent = `第 ${state.page} / ${pages} 页 · 共 ${rows.length} 家`;
  els.prevPage.disabled = state.page <= 1;
  els.nextPage.disabled = state.page >= pages;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatIndexStatus(index) {
  if (!index) return "";
  if (index.building) {
    const p = index.progress || {};
    return `正在同步公司库 ${p.done || 0}/${p.total || "?"}`;
  }
  if (index.ready) return `已索引 ${index.count || 0} 家公司`;
  return "公司库未就绪，首次搜索将自动同步";
}

async function runCompanySearch() {
  const name = els.companyNameSearch.value.trim();
  const code = els.companyCodeSearch.value.trim();
  if (!name && !code) {
    els.companySearchPanel.classList.add("hidden");
    return;
  }

  try {
    const params = new URLSearchParams();
    if (name) params.set("name", name);
    if (code) params.set("code", code);
    const json = await api(`/api/stocks/search?${params.toString()}`);
    const results = json.data || [];
    els.indexStatus.textContent = formatIndexStatus(json.index);
    els.companySearchPanel.classList.remove("hidden");
    els.companySearchResults.innerHTML = "";

    if (!results.length) {
      const tip = json.index?.building
        ? "暂无结果，公司库同步中，请稍后再试"
        : "未找到匹配公司";
      els.companySearchResults.innerHTML = `<p class="muted" style="padding:8px">${tip}</p>`;
      return;
    }

    for (const item of results) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "company-result";
      btn.innerHTML = `
        <strong>${escapeHtml(item.name)} · ${escapeHtml(item.code)}</strong>
        <span>${escapeHtml(item.l1_name)} / ${escapeHtml(item.l2_name)} / ${escapeHtml(item.l3_name)}</span>
      `;
      btn.addEventListener("click", async () => {
        if (!item.l3_code) return;
        expandToIndustryCode(item.l3_code);
        await selectIndustry(item.l3_code, null, {
          highlightCode: item.code,
          nameFilter: "",
          codeFilter: "",
        });
        els.companySearchPanel.classList.add("hidden");
      });
      els.companySearchResults.appendChild(btn);
    }
  } catch (err) {
    setError(err.message);
  }
}

function expandToIndustryCode(l3Code) {
  const l3Btn = els.tree.querySelector(`.tree-row[data-code="${CSS.escape(l3Code)}"]`);
  if (!l3Btn) return;
  const l2Children = l3Btn.closest(".children");
  if (l2Children) {
    l2Children.classList.add("open");
    const l2Row = l2Children.previousElementSibling;
    if (l2Row) l2Row.querySelector(".chevron")?.classList.add("open");
    const l1Children = l2Children.parentElement?.closest(".children");
    if (l1Children) {
      l1Children.classList.add("open");
      const l1Row = l1Children.previousElementSibling;
      if (l1Row) l1Row.querySelector(".chevron")?.classList.add("open");
    }
  }
}

async function loadTree(refresh = false) {
  setError("");
  els.treeMeta.textContent = "加载中…";
  try {
    const json = await api(`/api/industries${refresh ? "?refresh=1" : ""}`);
    state.tree = json.data;
    renderTree(json.data);
  } catch (err) {
    els.treeMeta.textContent = "加载失败";
    setError(`行业树加载失败：${err.message}`);
  }
}

let searchTimer = null;
els.searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  const q = els.searchInput.value.trim();
  if (!q) {
    els.searchResults.classList.add("hidden");
    els.tree.classList.remove("hidden");
    return;
  }
  searchTimer = setTimeout(async () => {
    try {
      const json = await api(`/api/search?q=${encodeURIComponent(q)}`);
      const results = json.data || [];
      els.tree.classList.add("hidden");
      els.searchResults.classList.remove("hidden");
      els.searchResults.innerHTML = "";
      if (!results.length) {
        els.searchResults.innerHTML = `<p class="muted" style="padding:12px">无匹配行业</p>`;
        return;
      }
      for (const item of results) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "search-result";
        btn.innerHTML = `<strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.l1_name)} / ${escapeHtml(item.l2_name)} · ${escapeHtml(item.code)}</span>`;
        btn.addEventListener("click", () => {
          els.searchInput.value = "";
          els.searchResults.classList.add("hidden");
          els.tree.classList.remove("hidden");
          expandToCode(item);
          selectIndustry(item.code);
        });
        els.searchResults.appendChild(btn);
      }
    } catch (err) {
      setError(err.message);
    }
  }, 220);
});

let companySearchTimer = null;
function scheduleCompanySearch() {
  clearTimeout(companySearchTimer);
  companySearchTimer = setTimeout(runCompanySearch, 250);
}

els.companyNameSearch.addEventListener("input", scheduleCompanySearch);
els.companyCodeSearch.addEventListener("input", scheduleCompanySearch);
els.closeCompanySearch.addEventListener("click", () => {
  els.companySearchPanel.classList.add("hidden");
});

els.closeNewsPanel?.addEventListener("click", () => {
  closeNewsPanel();
});

els.refreshNewsBtn?.addEventListener("click", () => {
  if (state.newsLoading) return;
  loadCompanyNews({ refresh: true });
});

function expandToCode(item) {
  expandToIndustryCode(item.code);
}

els.refreshBtn.addEventListener("click", () => loadTree(true));
els.reloadStocksBtn.addEventListener("click", async () => {
  if (!state.selectedCode) return;
  setLoading(true);
  setError("");
  try {
    const json = await api(
      `/api/industries/${encodeURIComponent(state.selectedCode)}/stocks?refresh=1`
    );
    const data = json.data;
    state.stocks = data.stocks || [];
    els.industryMeta.textContent = `行业代码 ${data.industry?.code || state.selectedCode} · 共 ${data.count ?? state.stocks.length} 家上市公司 · 更新于 ${data.updated_at || "-"}`;
    renderStocks();
  } catch (err) {
    setError(err.message);
  } finally {
    setLoading(false);
  }
});

els.nameFilter.addEventListener("input", () => {
  state.nameFilter = els.nameFilter.value;
  state.page = 1;
  renderStocks();
});

els.codeFilter.addEventListener("input", () => {
  state.codeFilter = els.codeFilter.value;
  state.page = 1;
  renderStocks();
});

els.pageSize.addEventListener("change", () => {
  state.pageSize = Number(els.pageSize.value) || 20;
  state.page = 1;
  renderStocks();
});

els.prevPage.addEventListener("click", () => {
  if (state.page <= 1) return;
  state.page -= 1;
  renderStocks();
});

els.nextPage.addEventListener("click", () => {
  const pages = totalPages(filteredStocks().length);
  if (state.page >= pages) return;
  state.page += 1;
  renderStocks();
});

loadTree();
