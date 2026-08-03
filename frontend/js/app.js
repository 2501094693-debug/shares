const state = {
  tree: [],
  selectedCode: null,
  stocks: [],
  nameFilter: "",
  codeFilter: "",
  highlightCode: "",
  page: 1,
  pageSize: 20,
};

const MAIN_COL_COUNT = 8;

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

function openCompanyPage(stock) {
  const code = stock.code || "";
  if (!code) return;
  try {
    sessionStorage.setItem(
      `stock:${code}`,
      JSON.stringify({
        ...stock,
        l3_code: state.selectedCode || stock.l3_code || "",
      })
    );
  } catch {
    /* ignore */
  }
  const qs = new URLSearchParams({
    code,
    name: stock.name || "",
  });
  if (state.selectedCode) qs.set("industry", state.selectedCode);
  window.location.href = `/company.html?${qs.toString()}`;
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

    const url = new URL(window.location.href);
    url.searchParams.set("industry", code);
    window.history.replaceState({}, "", url);
  } catch (err) {
    setError(err.message || String(err));
  } finally {
    setLoading(false);
  }
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
    const tr = document.createElement("tr");
    tr.className = "stock-row";
    const isHighlight =
      state.highlightCode &&
      (s.code === state.highlightCode || s.full_code === state.highlightCode);
    if (isHighlight) tr.classList.add("highlight");
    tr.dataset.code = stockKey(s);
    tr.title = "点击查看详情与新闻";
    tr.innerHTML = `
      <td>${start + idx + 1}</td>
      <td class="code">${escapeHtml(s.code)}</td>
      <td>${escapeHtml(s.name)}</td>
      <td>${escapeHtml(displayValue(s.price))}</td>
      ${changeCellHtml(s.change_1d)}
      ${changeCellHtml(s.change_5d)}
      ${changeCellHtml(s.change_ytd)}
      <td>${escapeHtml(displayValue(s.market_cap))}</td>
    `;
    tr.addEventListener("click", () => openCompanyPage(s));
    els.stockBody.appendChild(tr);
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
      btn.addEventListener("click", () => {
        const qs = new URLSearchParams({
          code: item.code || "",
          name: item.name || "",
        });
        if (item.l3_code) qs.set("industry", item.l3_code);
        try {
          sessionStorage.setItem(`stock:${item.code}`, JSON.stringify(item));
        } catch {
          /* ignore */
        }
        window.location.href = `/company.html?${qs.toString()}`;
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
          expandToIndustryCode(item.code);
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

(async () => {
  await loadTree();
  const bootIndustry = new URLSearchParams(window.location.search).get("industry");
  if (bootIndustry) {
    expandToIndustryCode(bootIndustry);
    await selectIndustry(bootIndustry);
  }
})();
