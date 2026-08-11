import { createCompanyMap } from "./map/index.js";

const state = {
  tree: [],
  selectedCode: null,
  stocks: [],
  highlightCode: "",
  page: 1,
  pageSize: 20,
  searchMode: false,
  viewMode: "map",
};

/** @type {ReturnType<typeof createCompanyMap>} */
let companyMap;

const LIST_RESTORE_KEY = "sw:listRestore";

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
  content: document.getElementById("hudList") || document.querySelector(".hud-right"),
  breadcrumb: document.getElementById("breadcrumb"),
  industryTitle: document.getElementById("industryTitle"),
  industryMeta: document.getElementById("industryMeta"),
  stockBody: document.getElementById("stockList"),
  reloadStocksBtn: document.getElementById("reloadStocksBtn"),
  pageSize: document.getElementById("pageSize"),
  prevPage: document.getElementById("prevPage"),
  nextPage: document.getElementById("nextPage"),
  pageInfo: document.getElementById("pageInfo"),
  loading: document.getElementById("loading"),
  errorBox: document.getElementById("errorBox"),
  listView: document.getElementById("listView"),
  mapBaseMode: document.getElementById("mapBaseMode"),
  mapStatus: document.getElementById("mapStatus"),
  mapUnknown: document.getElementById("mapUnknown"),
  regMap: document.getElementById("regMap"),
  hud: document.querySelector(".hud"),
};

const MAP_BASE_MODE_KEY = "sw:mapBaseMode";

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
  els.content?.classList.toggle("is-loading", on);
  if (on) {
    els.errorBox.classList.add("hidden");
  }
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
  els.treeMeta.textContent = `SECTORS · ${tree.length} 一级 · ${countL3(tree)} 三级`;
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
  return state.stocks;
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

function changeChipHtml(v, label) {
  const text = displayValue(v);
  const cls = changeClass(text);
  return `<span class="metric-chip ${cls}"><em>${escapeHtml(label)}</em>${escapeHtml(text)}</span>`;
}

function setStockListMessage(message) {
  if (!els.stockBody) return;
  els.stockBody.innerHTML = `<div class="stock-list-empty muted">${escapeHtml(message)}</div>`;
}

function stockKey(s) {
  return s.code || s.full_code || "";
}

const HUD_STORAGE_KEY = "sw-map-hud-collapsed";
const HUD_LABELS = { search: "搜索", tree: "行业树", list: "公司列表" };
let hudCollapsed = { search: false, tree: false, list: false };

function readHudCollapsed() {
  try {
    const raw = JSON.parse(localStorage.getItem(HUD_STORAGE_KEY) || "{}");
    return {
      search: !!raw.search,
      tree: !!raw.tree,
      list: !!raw.list,
    };
  } catch {
    return { search: false, tree: false, list: false };
  }
}

function persistHudCollapsed() {
  try {
    localStorage.setItem(HUD_STORAGE_KEY, JSON.stringify(hudCollapsed));
  } catch {
    /* ignore */
  }
}

function applyHudCollapsed() {
  const hud = els.hud;
  if (!hud) return;
  hud.classList.toggle("is-search-collapsed", hudCollapsed.search);
  hud.classList.toggle("is-tree-collapsed", hudCollapsed.tree);
  hud.classList.toggle("is-list-collapsed", hudCollapsed.list);

  document.querySelectorAll("[data-collapse]").forEach((btn) => {
    const key = btn.getAttribute("data-collapse");
    if (!key || !(key in hudCollapsed)) return;
    const collapsed = hudCollapsed[key];
    btn.setAttribute("aria-expanded", String(!collapsed));
    btn.textContent = "收起";
    btn.title = `收起${HUD_LABELS[key] || ""}`;
  });

  if (hudCollapsed.search) {
    els.companySearchPanel?.classList.add("hidden");
  }

  // 收起后面板完全隐藏；展开按钮文案保持明确
  const expandLabels = {
    search: "展开搜索",
    tree: "展开行业",
    list: "展开列表",
  };
  document.querySelectorAll("[data-expand]").forEach((btn) => {
    const key = btn.getAttribute("data-expand");
    if (!key || !(key in hudCollapsed)) return;
    btn.hidden = !hudCollapsed[key];
    btn.setAttribute("aria-hidden", String(!hudCollapsed[key]));
    if (expandLabels[key]) btn.textContent = expandLabels[key];
  });

  // HUD 折叠会改变地图可视区域
  if (companyMap) {
    companyMap.ensureReady().catch(() => {});
  }
}

function setHudPanelCollapsed(key, collapsed) {
  if (!(key in hudCollapsed)) return;
  hudCollapsed[key] = !!collapsed;
  persistHudCollapsed();
  applyHudCollapsed();
}

function expandHudPanel(key) {
  setHudPanelCollapsed(key, false);
}

function initHudPanels() {
  hudCollapsed = readHudCollapsed();
  applyHudCollapsed();

  document.querySelectorAll("[data-collapse]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.getAttribute("data-collapse");
      if (!key) return;
      setHudPanelCollapsed(key, true);
    });
  });

  document.querySelectorAll("[data-expand]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.getAttribute("data-expand");
      if (!key) return;
      expandHudPanel(key);
    });
  });
}


function mapHudPadding() {
  const w = window.innerWidth || 1200;
  if (w <= 860) return [96, 16, 260, 16];
  const top = hudCollapsed.search ? 48 : 118;
  const left = hudCollapsed.tree ? 48 : w <= 1100 ? 290 : 330;
  const right = hudCollapsed.list ? 48 : w <= 1100 ? 360 : 410;
  return [top, right, 20, left];
}

function initCompanyMap() {
  companyMap = createCompanyMap({
    container: els.regMap,
    getStocks: () => state.stocks,
    getSearchMode: () => state.searchMode,
    getHighlightCode: () => state.highlightCode,
    setHighlightCode: (code) => {
      state.highlightCode = code || "";
    },
    getHudPadding: mapHudPadding,
    api,
    escapeHtml,
    onOpenCompany: openCompanyPage,
    onListRender: () => renderStocks(),
    onError: (msg) => setError(msg),
    statusEl: els.mapStatus,
    unknownEl: els.mapUnknown,
  });

  let savedMode = "normal";
  try {
    savedMode = localStorage.getItem(MAP_BASE_MODE_KEY) || "normal";
  } catch {
    /* ignore */
  }
  if (savedMode && companyMap.BASE_MODES?.[savedMode]) {
    companyMap.setBaseMode(savedMode);
    if (els.mapBaseMode) els.mapBaseMode.value = savedMode;
  }
}

function saveListRestoreState(extra = {}) {
  try {
    const payload = {
      v: 1,
      mode: state.searchMode ? "search" : "industry",
      cname: els.companyNameSearch?.value?.trim() || "",
      ccode: els.companyCodeSearch?.value?.trim() || "",
      industry: state.selectedCode || "",
      stocks: state.stocks || [],
      listMapKind:
        companyMap?.view.listMapKind ||
        (state.searchMode ? "search" : "industry"),
      mapLevel: companyMap?.view.mapLevel || "province",
      mapProvince: companyMap?.view.mapProvince || null,
      highlightCode: extra.highlightCode || state.highlightCode || "",
      page: state.page || 1,
      savedAt: Date.now(),
    };
    sessionStorage.setItem(LIST_RESTORE_KEY, JSON.stringify(payload));
  } catch {
    /* quota / private mode */
  }
}

function peekListRestoreState() {
  try {
    const data = JSON.parse(sessionStorage.getItem(LIST_RESTORE_KEY) || "null");
    if (!data || data.v !== 1) return null;
    if (Date.now() - (data.savedAt || 0) > 2 * 60 * 60 * 1000) {
      sessionStorage.removeItem(LIST_RESTORE_KEY);
      return null;
    }
    return data;
  } catch {
    return null;
  }
}

function consumeListRestoreState() {
  const data = peekListRestoreState();
  if (data) sessionStorage.removeItem(LIST_RESTORE_KEY);
  return data;
}

async function restoreListState(data) {
  if (!data) return false;
  if (data.mode === "search" && Array.isArray(data.stocks)) {
    if (els.companyNameSearch) els.companyNameSearch.value = data.cname || "";
    if (els.companyCodeSearch) els.companyCodeSearch.value = data.ccode || "";
    // showSearchResults 会清 highlight；先展示结果再标回
    await showSearchResults(data.stocks, {});
    if (data.highlightCode) {
      state.highlightCode = data.highlightCode;
      state.page = data.page || 1;
      renderStocks();
    }
    // 若离开前是同省城市级列表地图，尽量还原到同一尺度
    if (
      data.listMapKind === "search" &&
      data.mapLevel === "city" &&
      data.mapProvince &&
      state.stocks.length
    ) {
      companyMap.applySnapshot({
        listMapKind: "search",
        mapLevel: "city",
        mapProvince: data.mapProvince,
        mapStreetFocus: "",
      });
      try {
        await companyMap.renderMap();
      } catch {
        await companyMap.syncToSearchResults(state.stocks);
      }
    }
    return true;
  }
  if (data.mode === "industry" && data.industry) {
    if (els.companyNameSearch) els.companyNameSearch.value = "";
    if (els.companyCodeSearch) els.companyCodeSearch.value = "";
    expandToIndustryCode(data.industry);
    await selectIndustry(data.industry, null, {
      highlightCode: data.highlightCode || "",
    });
    return true;
  }
  return false;
}

function openCompanyPage(stock) {
  const code = stock.code || "";
  if (!code) return;
  const industry = state.selectedCode || stock.l3_code || "";
  // 离开前快照列表+地图，供详情页「返回列表」精确恢复
  saveListRestoreState({ highlightCode: code });
  try {
    sessionStorage.setItem(
      `stock:${code}`,
      JSON.stringify({
        ...stock,
        l3_code: industry,
      })
    );
  } catch {
    /* ignore */
  }
  const qs = new URLSearchParams({
    code,
    name: stock.name || "",
  });
  if (state.searchMode) {
    qs.set("from", "search");
    const cname = els.companyNameSearch?.value?.trim() || "";
    const ccode = els.companyCodeSearch?.value?.trim() || "";
    if (cname) qs.set("cname", cname);
    if (ccode) qs.set("ccode", ccode);
  } else {
    qs.set("from", "industry");
    if (industry) qs.set("industry", industry);
  }
  window.location.href = `/company.html?${qs.toString()}`;
}

async function selectIndustry(code, rowEl = null, options = {}) {
  state.searchMode = false;
  companyMap.applySnapshot({ listMapKind: "industry", mapStreetFocus: "" });
  state.selectedCode = code;
  expandHudPanel("list");
  expandHudPanel("tree");
  clearActive();
  if (rowEl) {
    rowEl.classList.add("active");
  } else {
    const match = els.tree.querySelector(`.tree-row[data-code="${CSS.escape(code)}"]`);
    if (match) match.classList.add("active");
  }

  els.emptyState.classList.add("hidden");
  els.detail.classList.remove("hidden");
  setError("");
  state.stocks = [];
  state.page = 1;
  companyMap.resetDrilldown();
  els.breadcrumb.textContent = "加载中…";
  els.industryTitle.textContent = code;
  els.industryMeta.textContent = "正在拉取成分股列表…";
  setStockListMessage("正在加载成分股…");
  els.pageInfo.textContent = "";
  els.prevPage.disabled = true;
  els.nextPage.disabled = true;
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
    state.page = 1;

    if (state.highlightCode) {
      const rows = filteredStocks();
      const hi = rows.findIndex(
        (s) => s.code === state.highlightCode || s.full_code === state.highlightCode
      );
      if (hi >= 0) state.page = Math.floor(hi / state.pageSize) + 1;
    }

    renderStocks();
    companyMap.refreshFromStocks();

    if (state.highlightCode) {
      const target = els.stockBody.querySelector(".stock-card.is-focused, .stock-card.highlight");
      if (target) target.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    const url = new URL(window.location.href);
    url.searchParams.set("industry", code);
    url.searchParams.delete("cname");
    url.searchParams.delete("ccode");
    window.history.replaceState({}, "", url);
  } catch (err) {
    state.stocks = [];
    companyMap.resetDrilldown();
    setStockListMessage("加载失败");
    setError(err.message || String(err));
    companyMap.refreshFromStocks();
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
    setStockListMessage("没有匹配的公司");
    els.pageInfo.textContent = "0 / 0";
    els.prevPage.disabled = true;
    els.nextPage.disabled = true;
    return;
  }

  pageRows.forEach((s, idx) => {
    const card = document.createElement("article");
    card.className = "stock-card";
    card.setAttribute("role", "listitem");
    const isHighlight =
      state.highlightCode &&
      (s.code === state.highlightCode || s.full_code === state.highlightCode);
    const isStreetFocus =
      companyMap?.view.mapStreetFocus &&
      companyMap.view.mapStreetFocus === stockKey(s);
    if (isHighlight) card.classList.add("highlight", "is-focused");
    if (isStreetFocus) card.classList.add("is-street-focus");
    card.dataset.code = stockKey(s);
    card.title = isStreetFocus
      ? "再次点击返回列表地图视野"
      : "点击在地图上定位注册地";
    card.innerHTML = `
      <div class="stock-card-top">
        <div class="stock-card-identity">
          <span class="stock-card-idx">${start + idx + 1}</span>
          <div class="stock-card-names">
            <strong class="stock-card-name">${escapeHtml(s.name || "-")}</strong>
            <code class="stock-card-code">${escapeHtml(s.code || "-")}</code>
          </div>
        </div>
        <div class="stock-card-quote">
          <span class="stock-card-price">${escapeHtml(displayValue(s.price))}</span>
          <span class="stock-card-mcap"><em>市值</em>${escapeHtml(displayValue(s.market_cap))}</span>
        </div>
      </div>
      <div class="stock-card-metrics">
        ${changeChipHtml(s.change_1d, "近1日")}
        ${changeChipHtml(s.change_5d, "近5日")}
        ${changeChipHtml(s.change_ytd, "今年")}
      </div>
      <div class="stock-card-foot">
        <span class="stock-card-hint">${
          isStreetFocus ? "再点返回列表地图" : "定位注册地"
        }</span>
        <button type="button" class="btn ghost btn-detail">详情</button>
      </div>
    `;
    card.addEventListener("click", () => companyMap.onCompanyCardClick(s));
    card.querySelector(".btn-detail")?.addEventListener("click", (ev) => {
      ev.stopPropagation();
      openCompanyPage(s);
    });
    els.stockBody.appendChild(card);
  });

  els.pageInfo.textContent = `${state.page} / ${pages} · 共 ${rows.length} 家`;
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
  if (index.complete) return `已索引 ${index.count || 0} 家公司`;
  if (index.l3_total) {
    return `索引不完整 ${index.l3_covered || 0}/${index.l3_total} 行业 · ${index.count || 0} 家`;
  }
  if (index.ready) return `已索引 ${index.count || 0} 家公司`;
  return "公司库未就绪，首次搜索将自动同步";
}

async function showSearchResults(results, meta = {}) {
  state.searchMode = true;
  state.selectedCode = null;
  state.stocks = results;
  state.highlightCode = "";
  state.page = 1;
  companyMap.resetDrilldown();
  companyMap.applySnapshot({ listMapKind: "search", mapStreetFocus: "" });
  clearActive();
  expandHudPanel("list");
  expandHudPanel("search");

  els.companySearchPanel.classList.add("hidden");
  els.emptyState.classList.add("hidden");
  els.detail.classList.remove("hidden");

  const parts = [];
  if (els.companyNameSearch.value.trim()) {
    parts.push(`名称「${els.companyNameSearch.value.trim()}」`);
  }
  if (els.companyCodeSearch.value.trim()) {
    parts.push(`代码「${els.companyCodeSearch.value.trim()}」`);
  }
  els.breadcrumb.textContent = "公司搜索";
  els.industryTitle.textContent = parts.length ? parts.join(" · ") : "公司搜索结果";
  const status = formatIndexStatus(meta.index);
  els.industryMeta.textContent = [
    `共 ${results.length} 家匹配公司`,
    status,
  ]
    .filter(Boolean)
    .join(" · ");

  // 记住搜索条件，便于详情页「返回列表」恢复搜索地图
  const url = new URL(window.location.href);
  url.searchParams.delete("industry");
  const cname = els.companyNameSearch.value.trim();
  const ccode = els.companyCodeSearch.value.trim();
  if (cname) url.searchParams.set("cname", cname);
  else url.searchParams.delete("cname");
  if (ccode) url.searchParams.set("ccode", ccode);
  else url.searchParams.delete("ccode");
  window.history.replaceState({}, "", url);

  renderStocks();
  if (!results.length) {
    await companyMap.refreshFromStocks();
    return;
  }
  // 搜索结果统一先落到「列表地图」；点公司再进街道级，再点可退回
  await companyMap.syncToSearchResults(results);
}

async function clearCompanySearchView() {
  state.searchMode = false;
  companyMap.applySnapshot({ listMapKind: "", mapStreetFocus: "" });
  els.companySearchPanel.classList.add("hidden");
  if (els.indexStatus) els.indexStatus.textContent = "";

  const url = new URL(window.location.href);
  url.searchParams.delete("cname");
  url.searchParams.delete("ccode");
  window.history.replaceState({}, "", url);

  const bootIndustry = url.searchParams.get("industry");
  if (bootIndustry) {
    expandToIndustryCode(bootIndustry);
    await selectIndustry(bootIndustry);
    return;
  }

  state.selectedCode = null;
  state.stocks = [];
  companyMap.resetDrilldown();
  els.detail.classList.add("hidden");
  els.emptyState.classList.remove("hidden");
  els.stockBody.innerHTML = "";
  els.breadcrumb.textContent = "";
  els.industryTitle.textContent = "";
  els.industryMeta.textContent = "";
  els.pageInfo.textContent = "";
  companyMap.refreshFromStocks();
}

async function runCompanySearch() {
  const name = els.companyNameSearch.value.trim();
  const code = els.companyCodeSearch.value.trim();
  if (!name && !code) {
    if (state.searchMode) await clearCompanySearchView();
    else els.companySearchPanel.classList.add("hidden");
    return;
  }

  try {
    const params = new URLSearchParams();
    if (name) params.set("name", name);
    if (code) params.set("code", code);
    const json = await api(`/api/stocks/search?${params.toString()}`);
    const results = json.data || [];
    if (els.indexStatus) els.indexStatus.textContent = formatIndexStatus(json.index);
    setError("");

    if (!results.length) {
      const tip = json.index?.building
        ? "暂无结果，公司库同步中，请稍后再试"
        : json.index && json.index.complete === false
          ? "未找到匹配公司（索引不完整，已触发后台补全）"
          : "未找到匹配公司";
      await showSearchResults([], { index: json.index });
      setStockListMessage(tip);
      els.pageInfo.textContent = "0 / 0";
      els.prevPage.disabled = true;
      els.nextPage.disabled = true;
      return;
    }

    await showSearchResults(results, { index: json.index });
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
  expandHudPanel("tree");
  expandHudPanel("search");
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
  expandHudPanel("search");
  companySearchTimer = setTimeout(runCompanySearch, 250);
}

els.companyNameSearch.addEventListener("input", scheduleCompanySearch);
els.companyCodeSearch.addEventListener("input", scheduleCompanySearch);
els.closeCompanySearch?.addEventListener("click", () => {
  els.companyNameSearch.value = "";
  els.companyCodeSearch.value = "";
  clearCompanySearchView();
});

els.refreshBtn.addEventListener("click", () => loadTree(true));
els.reloadStocksBtn.addEventListener("click", async () => {
  if (!state.selectedCode) return;
  setError("");
  setStockListMessage("正在刷新…");
  setLoading(true);
  try {
    const json = await api(
      `/api/industries/${encodeURIComponent(state.selectedCode)}/stocks?refresh=1`
    );
    const data = json.data;
    state.stocks = data.stocks || [];
    companyMap.resetDrilldown();
    els.industryMeta.textContent = `行业代码 ${data.industry?.code || state.selectedCode} · 共 ${data.count ?? state.stocks.length} 家上市公司 · 更新于 ${data.updated_at || "-"}`;
    renderStocks();
    companyMap.refreshFromStocks();
  } catch (err) {
    setError(err.message);
  } finally {
    setLoading(false);
  }
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

els.mapBaseMode?.addEventListener("change", () => {
  const mode = els.mapBaseMode.value || "normal";
  companyMap.setBaseMode(mode);
  try {
    localStorage.setItem(MAP_BASE_MODE_KEY, mode);
  } catch {
    /* ignore */
  }
});

(async () => {
  initCompanyMap();
  initHudPanels();
  const pendingRestore = peekListRestoreState();
  const bootParams = new URLSearchParams(window.location.search);
  const bootCname = (bootParams.get("cname") || "").trim();
  const bootCcode = (bootParams.get("ccode") || "").trim();
  const bootFrom = (bootParams.get("from") || "").trim();
  const wantSearchRestore =
    !!pendingRestore ||
    bootFrom === "search" ||
    !!(bootCname || bootCcode);

  // 行业树/列表不依赖地图就绪；地图失败时仍可浏览数据
  const mapBoot = companyMap
    .ensureReady()
    .then(() => {
      if (!wantSearchRestore) companyMap.showOverview();
      else companyMap.setStatus("正在恢复列表地图…");
    })
    .catch((err) => {
      setError(err.message || String(err));
    });

  await loadTree();

  const restored = await restoreListState(consumeListRestoreState());
  if (restored) {
    await mapBoot;
    return;
  }

  if (bootCname || bootCcode || bootFrom === "search") {
    if (els.companyNameSearch) els.companyNameSearch.value = bootCname;
    if (els.companyCodeSearch) els.companyCodeSearch.value = bootCcode;
    if (bootCname || bootCcode) {
      await runCompanySearch();
      await mapBoot;
      return;
    }
  }
  const bootIndustry = bootParams.get("industry");
  if (bootIndustry) {
    expandToIndustryCode(bootIndustry);
    await selectIndustry(bootIndustry);
  } else if (wantSearchRestore) {
    await mapBoot;
    companyMap.showOverview();
  } else {
    await mapBoot;
  }
})();
