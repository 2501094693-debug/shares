const state = {
  tree: [],
  selectedCode: null,
  stocks: [],
  highlightCode: "",
  /** 当前街道级聚焦的公司代码；再次点击同一公司则退回列表地图 */
  mapStreetFocus: "",
  /** 进入街道级之前的列表地图类型：search | industry */
  listMapKind: "",
  page: 1,
  pageSize: 20,
  searchMode: false,
  viewMode: "map",
  mapLevel: "province",
  mapProvince: null,
  geoByCode: {},
  geoToken: 0,
};

const GEO_BATCH = 50;

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
  mapBackBtn: document.getElementById("mapBackBtn"),
  mapStatus: document.getElementById("mapStatus"),
  mapUnknown: document.getElementById("mapUnknown"),
  regMap: document.getElementById("regMap"),
  hud: document.querySelector(".hud"),
};

const mapState = {
  map: null,
  overlays: [],
  infoWindow: null,
  chinaGeo: null,
  provinceCentroids: null,
  amapKey: "",
  ready: false,
  loadingSdk: null,
  districtCache: {},
  markersByCode: {},
  highlightMarker: null,
  geocodeCache: {},
  geocodeInflight: {},
  _resizeBound: false,
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

  forceMapResize();
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

function openCompanyPage(stock) {
  const code = stock.code || "";
  if (!code) return;
  const industry = state.selectedCode || stock.l3_code || "";
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
  if (industry) qs.set("industry", industry);
  window.location.href = `/company.html?${qs.toString()}`;
}

function showCompanyPopup(stock, geo, lnglat) {
  const industry =
    stock.l3_name || stock.industry || stock.l3_code || state.selectedCode || "";
  const fullName = geo?.full_name || stock.name || "";
  const poiName = geo?.poi_name || "";
  const poiAddr = geo?.poi_address || geo?.reg_address || "";
  const html = `<div class="map-popup">
    <strong>${escapeHtml(stock.name || "-")}</strong>
    <div class="muted">${escapeHtml(stock.code || "")}</div>
    <div>${escapeHtml(fullName || "—")}</div>
    ${poiName ? `<div class="muted">高德：${escapeHtml(poiName)}</div>` : ""}
    ${poiAddr ? `<div class="muted">${escapeHtml(poiAddr)}</div>` : ""}
    <div>${escapeHtml(industry || "—")}</div>
    <button type="button" class="btn ghost map-popup-btn" data-code="${escapeHtml(stock.code || "")}">查看详情</button>
  </div>`;
  mapState.infoWindow.setContent(html);
  mapState.infoWindow.open(mapState.map, lnglat);
  requestAnimationFrame(() => {
    const btn = document.querySelector(
      `.map-popup-btn[data-code="${CSS.escape(stock.code || "")}"]`
    );
    btn?.addEventListener(
      "click",
      (ev) => {
        ev.preventDefault();
        openCompanyPage(stock);
      },
      { once: true }
    );
  });
}

function setMarkerHighlight(marker) {
  if (mapState.highlightMarker && mapState.highlightMarker !== marker) {
    mapState.highlightMarker.setIcon?.(undefined);
    mapState.highlightMarker.setzIndex?.(120);
  }
  mapState.highlightMarker = marker || null;
  marker?.setzIndex?.(160);
}

async function onCompanyCardClick(stock) {
  const code = String(stock.code || "").trim();
  if (!code) return;
  // 已在该公司街道级视图 → 退回搜索/行业列表对应的地图视野
  if (state.mapStreetFocus && state.mapStreetFocus === code) {
    await exitCompanyStreetFocus(stock);
    return;
  }
  await focusCompanyOnMap(stock);
}

async function exitCompanyStreetFocus(stock) {
  const code = String(stock?.code || state.mapStreetFocus || "").trim();
  state.mapStreetFocus = "";
  mapState.infoWindow?.close?.();
  setMarkerHighlight(null);
  state.highlightCode = code || state.highlightCode;
  renderStocks();
  setError("");

  // 立刻离开街道级缩放，避免异步恢复期间仍停在原地点
  try {
    if (mapState.map) {
      const z = mapState.map.getZoom?.() || 16;
      if (z > 11) mapState.map.setZoom(10);
    }
  } catch {
    /* ignore */
  }

  try {
    const kind =
      state.listMapKind ||
      (state.searchMode ? "search" : "industry");
    if (kind === "search" && state.stocks.length) {
      await syncMapToSearchResults(state.stocks);
      return;
    }
    await refreshMapFromStocks();
  } catch (err) {
    setError(err.message || String(err));
  }
}

async function focusCompanyOnMap(stock) {
  const code = String(stock.code || "").trim();
  if (!code) return;
  // 记录进入街道级前的列表地图类型，供再次点击恢复
  if (!state.mapStreetFocus) {
    state.listMapKind =
      state.listMapKind ||
      (state.searchMode ? "search" : "industry");
  }
  state.highlightCode = code;
  state.mapStreetFocus = code;
  renderStocks();
  setError("");
  setMapStatus(`高德搜索 ${stock.name || code}…`);

  try {
    await ensureMapAssets();
    const token = ++state.geoToken;
    await enrichMissingGeo([stock], token);
    if (token !== state.geoToken) return;

    const geo = state.geoByCode[code] || {};
    const hit = await resolveCompanyPlace(stock, geo);
    if (!hit) {
      state.mapStreetFocus = "";
      setMapStatus(
        `${stock.name || code}：高德未搜到「${geo.full_name || stock.name || code}」`
      );
      renderStocks();
      return;
    }
    if (token !== state.geoToken) return;

    const { pos, geo: g2, poi } = hit;
    state.mapLevel = "city";
    state.mapProvince = g2.reg_province || state.mapProvince || null;

    // 清掉省级着色面，否则会盖住道路/地名，看起来「只有色块没有内容」
    clearMapLayers();
    forceMapResize();
    ensureDetailedBasemap();

    // 画所在市（或省）描边，帮助识别行政区，但不填充
    const areaName = g2.reg_city || g2.reg_province || "";
    if (areaName) {
      try {
        const dist = await searchDistrict(areaName, {
          level: g2.reg_city ? "city" : "province",
          subdistrict: g2.reg_city ? 0 : 1,
          extensions: "all",
        });
        if (token !== state.geoToken) return;
        drawBoundaries(dist.boundaries || [], {
          strokeColor: "#0f6e56",
          strokeWeight: 2,
          fillColor: "#ffffff",
          fillOpacity: 0,
          zIndex: 40,
          bubble: true,
        });
        if (!g2.reg_city && g2.reg_province) {
          await drawProvinceCities(g2.reg_province);
          if (token !== state.geoToken) return;
        }
      } catch {
        /* 区划失败仍继续显示公司点与底图 */
      }
    }
    if (token !== state.geoToken) return;

    const marker = createCompanyMarker(stock, g2, pos, true);
    addOverlay(marker);
    mapState.markersByCode[code] = marker;
    setMarkerHighlight(marker);

    // 按 HUD 边距居中，避免左右面板把点挤出可视中央
    focusMapOnTargets([marker], 16);
    // resize / 弹窗后 dual-pass，保证连续点击两家公司时第二次仍居中
    requestAnimationFrame(() => {
      if (token !== state.geoToken) return;
      focusMapOnTargets([marker], 16);
      showCompanyPopup(stock, g2, pos);
    });
    setTimeout(() => {
      if (token !== state.geoToken) return;
      focusMapOnTargets([marker], 16);
    }, 160);
    syncMapChrome();

    const areaLabel = [g2.reg_province, g2.reg_city, poi?.name]
      .filter(Boolean)
      .join(" · ");
    setMapStatus(`${stock.name || code} · ${areaLabel || "高德标注"}（再点返回列表地图）`);
  } catch (err) {
    state.mapStreetFocus = "";
    setMapStatus("");
    setError(err.message || String(err));
  }
}

async function selectIndustry(code, rowEl = null, options = {}) {
  state.searchMode = false;
  state.listMapKind = "industry";
  state.mapStreetFocus = "";
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
  resetMapDrilldown();
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
    refreshMapFromStocks();

    if (state.highlightCode) {
      const target = els.stockBody.querySelector(".stock-card.is-focused, .stock-card.highlight");
      if (target) target.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    const url = new URL(window.location.href);
    url.searchParams.set("industry", code);
    window.history.replaceState({}, "", url);
  } catch (err) {
    state.stocks = [];
    resetMapDrilldown();
    setStockListMessage("加载失败");
    setError(err.message || String(err));
    refreshMapFromStocks();
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
    syncMapChrome();
    return;
  }

  pageRows.forEach((s, idx) => {
    const card = document.createElement("article");
    card.className = "stock-card";
    card.setAttribute("role", "listitem");
    const isHighlight =
      state.highlightCode &&
      (s.code === state.highlightCode || s.full_code === state.highlightCode);
    const isStreetFocus = state.mapStreetFocus && state.mapStreetFocus === stockKey(s);
    if (isHighlight) card.classList.add("highlight", "is-focused");
    if (isStreetFocus) card.classList.add("is-street-focus");
    card.dataset.code = stockKey(s);
    card.title = isStreetFocus
      ? "再次点击返回列表地图视野"
      : "点击在地图上定位注册地";
    const change1d = displayValue(s.change_1d);
    const change1dCls = changeClass(change1d);
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
          <span class="stock-card-chg ${change1dCls}">${escapeHtml(change1d)}</span>
        </div>
      </div>
      <div class="stock-card-metrics">
        ${changeChipHtml(s.change_5d, "近5日")}
        ${changeChipHtml(s.change_ytd, "今年")}
        <span class="metric-chip"><em>市值</em>${escapeHtml(displayValue(s.market_cap))}</span>
      </div>
      <div class="stock-card-foot">
        <span class="stock-card-hint">${
          isStreetFocus ? "再点返回列表地图" : "定位注册地"
        }</span>
        <button type="button" class="btn ghost btn-detail">详情</button>
      </div>
    `;
    card.addEventListener("click", () => onCompanyCardClick(s));
    card.querySelector(".btn-detail")?.addEventListener("click", (ev) => {
      ev.stopPropagation();
      openCompanyPage(s);
    });
    els.stockBody.appendChild(card);
  });

  els.pageInfo.textContent = `${state.page} / ${pages} · 共 ${rows.length} 家`;
  els.prevPage.disabled = state.page <= 1;
  els.nextPage.disabled = state.page >= pages;
  syncMapChrome();
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
  state.listMapKind = "search";
  state.mapStreetFocus = "";
  state.selectedCode = null;
  state.stocks = results;
  state.highlightCode = "";
  state.page = 1;
  resetMapDrilldown();
  // resetMapDrilldown 会清 mapStreetFocus；保持列表地图类型
  state.listMapKind = "search";
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

  renderStocks();
  if (!results.length) {
    await refreshMapFromStocks();
    return;
  }
  // 搜索结果统一先落到「列表地图」；点公司再进街道级，再点可退回
  await syncMapToSearchResults(results);
}

/** 搜索列表地图：同省则下钻该省，否则按标注点适配到省市尺度。 */
async function syncMapToSearchResults(stocks) {
  const token = ++state.geoToken;
  state.mapStreetFocus = "";
  mapState.infoWindow?.close?.();
  try {
    await ensureMapAssets();
    setMapStatus("正在补齐注册地…");
    await enrichMissingGeo(stocks, token);
    if (token !== state.geoToken) return;

    const provinces = new Map();
    for (const s of stocks) {
      const c = String(s.code || "").trim();
      const prov = String(state.geoByCode[c]?.reg_province || "").trim();
      if (!prov) continue;
      provinces.set(prov, (provinces.get(prov) || 0) + 1);
    }

    let dominant = "";
    let dominantCount = 0;
    for (const [prov, n] of provinces) {
      if (n > dominantCount) {
        dominant = prov;
        dominantCount = n;
      }
    }
    // 1 家也按所在省展示；多家则多数同省才下钻
    const sameProvince =
      !!dominant &&
      (stocks.length === 1 ||
        dominantCount >= Math.max(2, Math.ceil(stocks.length * 0.6)));

    state.listMapKind = "search";

    if (sameProvince) {
      state.mapLevel = "city";
      state.mapProvince = dominant;
      await renderMap();
      if (token !== state.geoToken) return;
      renderStocks();
      return;
    }

    // 跨省：不画全国着色，直接打点并缩放到点集（省市尺度）
    state.mapLevel = "province";
    state.mapProvince = null;
    clearMapLayers();
    forceMapResize();
    ensureDetailedBasemap();
    await overlayStockMarkers(stocks, { fit: true, maxZoom: 12 });
    if (token !== state.geoToken) return;
    ensureDetailedBasemap();
    syncMapChrome();
    renderStocks();
  } catch (err) {
    if (token !== state.geoToken) return;
    setMapStatus("");
    setError(err.message || String(err));
  }
}

async function clearCompanySearchView() {
  state.searchMode = false;
  state.listMapKind = "";
  state.mapStreetFocus = "";
  els.companySearchPanel.classList.add("hidden");
  if (els.indexStatus) els.indexStatus.textContent = "";

  const bootIndustry = new URLSearchParams(window.location.search).get("industry");
  if (bootIndustry) {
    expandToIndustryCode(bootIndustry);
    await selectIndustry(bootIndustry);
    return;
  }

  state.selectedCode = null;
  state.stocks = [];
  resetMapDrilldown();
  els.detail.classList.add("hidden");
  els.emptyState.classList.remove("hidden");
  els.stockBody.innerHTML = "";
  els.breadcrumb.textContent = "";
  els.industryTitle.textContent = "";
  els.industryMeta.textContent = "";
  els.pageInfo.textContent = "";
  refreshMapFromStocks();
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
  setStockListMessage("正在重新拉取…");
  setLoading(true);
  try {
    const json = await api(
      `/api/industries/${encodeURIComponent(state.selectedCode)}/stocks?refresh=1`
    );
    const data = json.data;
    state.stocks = data.stocks || [];
    resetMapDrilldown();
    els.industryMeta.textContent = `行业代码 ${data.industry?.code || state.selectedCode} · 共 ${data.count ?? state.stocks.length} 家上市公司 · 更新于 ${data.updated_at || "-"}`;
    renderStocks();
    refreshMapFromStocks();
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

els.mapBackBtn?.addEventListener("click", () => {
  state.mapStreetFocus = "";
  resetMapDrilldown();
  renderMap();
});

function resetMapDrilldown() {
  state.mapLevel = "province";
  state.mapProvince = null;
  state.mapStreetFocus = "";
}

function syncMapChrome() {
  els.mapBackBtn?.classList.toggle(
    "hidden",
    !(state.mapLevel === "city" && state.mapProvince)
  );
}

function setMapStatus(text) {
  if (els.mapStatus) els.mapStatus.textContent = text || "";
}

function setMapUnknown(n) {
  if (!els.mapUnknown) return;
  els.mapUnknown.textContent = n > 0 ? `未知注册地 ${n} 家` : "";
}

function loadAmapScript(key, securityJsCode) {
  if (window.AMap) return Promise.resolve(window.AMap);
  if (mapState.loadingSdk) return mapState.loadingSdk;
  mapState.loadingSdk = new Promise((resolve, reject) => {
    if (securityJsCode) {
      window._AMapSecurityConfig = { securityJsCode };
    }
    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`;
    script.async = true;
    script.onload = () => {
      if (!window.AMap) {
        reject(new Error("高德地图 SDK 未就绪"));
        return;
      }
      resolve(window.AMap);
    };
    script.onerror = () => reject(new Error("高德地图脚本加载失败"));
    document.head.appendChild(script);
  }).finally(() => {
    mapState.loadingSdk = null;
  });
  return mapState.loadingSdk;
}

async function ensureMapAssets() {
  if (mapState.ready && mapState.map) {
    forceMapResize();
    return;
  }

  const cfg = await api("/api/map/config");
  const key = cfg.data?.key || "";
  const securityJsCode = cfg.data?.securityJsCode || "";
  if (!key) {
    throw new Error(
      "未配置高德地图 Key：请在项目根目录 .env 设置 AMAP_JS_KEY（见 .env.example）"
    );
  }
  mapState.amapKey = key;
  await loadAmapScript(key, securityJsCode);

  if (!mapState.map) {
    mapState.map = new AMap.Map(els.regMap, {
      zoom: 4,
      center: [104.5, 35.2],
      viewMode: "2D",
      mapStyle: "amap://styles/normal",
      zooms: [3, 18],
      resizeEnable: true,
      scrollWheel: true,
      doubleClickZoom: true,
      dragEnable: true,
      keyboardEnable: true,
      features: ["bg", "road", "building", "point"],
      showLabel: true,
      showIndoorMap: false,
    });
    // 确保滚轮缩放开启（部分环境默认异常时再设一次）
    try {
      mapState.map.setStatus({
        scrollWheel: true,
        doubleClickZoom: true,
        dragEnable: true,
      });
    } catch {
      /* ignore */
    }
    mapState.infoWindow = new AMap.InfoWindow({
      isCustom: false,
      offset: new AMap.Pixel(0, -8),
    });
    if (!mapState._resizeBound) {
      mapState._resizeBound = true;
      window.addEventListener("resize", () => {
        forceMapResize();
      });
      // 仅取消浏览器默认（整页缩放/滚动），高德仍会收到同一 wheel 事件
      els.regMap.addEventListener(
        "wheel",
        (e) => {
          e.preventDefault();
        },
        { passive: false }
      );
    }
  }

  if (!mapState.chinaGeo) {
    const [chinaRes, centroidsRes] = await Promise.all([
      fetch("/geo/china-provinces.json"),
      fetch("/geo/province-centroids.json"),
    ]);
    if (!chinaRes.ok) throw new Error("省级地图数据加载失败");
    mapState.chinaGeo = await chinaRes.json();
    mapState.provinceCentroids = centroidsRes.ok
      ? await centroidsRes.json()
      : {};
  }
  mapState.ready = true;
  forceMapResize();
}

async function enrichMissingGeo(stocks, token) {
  // 无公司全称则重拉（PlaceSearch 依赖全称）
  for (const c of Object.keys(state.geoByCode)) {
    const g = state.geoByCode[c];
    if (!String(g?.full_name || "").trim()) {
      delete state.geoByCode[c];
    }
  }
  const codes = [];
  const seen = new Set();
  for (const s of stocks) {
    const c = String(s.code || "").trim();
    if (!c || seen.has(c) || state.geoByCode[c]) continue;
    seen.add(c);
    codes.push(c);
  }
  if (!codes.length) return;

  for (let i = 0; i < codes.length; i += GEO_BATCH) {
    if (token !== state.geoToken) return;
    const batch = codes.slice(i, i + GEO_BATCH);
    const done = Math.min(i + batch.length, codes.length);
    setMapStatus(`补齐注册地 ${done}/${codes.length}…`);
    const json = await api("/api/stocks/geo-enrich", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codes: batch }),
    });
    const items = json.data?.items || {};
    Object.assign(state.geoByCode, items);
  }
}

function aggregateProvinces(stocks) {
  const counts = {};
  let unknown = 0;
  for (const s of stocks) {
    const c = String(s.code || "").trim();
    const geo = state.geoByCode[c];
    const prov = geo?.reg_province || "";
    if (!prov) {
      unknown += 1;
      continue;
    }
    counts[prov] = (counts[prov] || 0) + 1;
  }
  return { counts, unknown };
}

function provinceFillColor(count, maxCount) {
  if (!count) return "rgba(216, 208, 194, 0.35)";
  const t = maxCount <= 1 ? 1 : Math.min(1, count / maxCount);
  const alpha = 0.25 + t * 0.55;
  return `rgba(15, 110, 86, ${alpha.toFixed(3)})`;
}

function clearMapLayers() {
  if (mapState.map && mapState.overlays.length) {
    mapState.map.remove(mapState.overlays);
  }
  mapState.overlays = [];
  mapState.markersByCode = {};
  mapState.highlightMarker = null;
  mapState.infoWindow?.close?.();
}

function addOverlay(item) {
  if (!item) return;
  mapState.overlays.push(item);
  mapState.map.add(item);
}

/** 为左右悬浮面板预留视野边距，避免全国图被挡住。 [上,右,下,左] */
function mapHudPadding() {
  const w = window.innerWidth || 1200;
  if (w <= 860) return [96, 16, 260, 16];

  const top = hudCollapsed.search ? 64 : 108;
  const left = hudCollapsed.tree ? 48 : w <= 1100 ? 290 : 330;
  const right = hudCollapsed.list ? 48 : w <= 1100 ? 360 : 410;
  return [top, right, 20, left];
}

function forceMapResize() {
  if (!mapState.map) return;
  try {
    mapState.map.resize();
  } catch {
    /* ignore */
  }
  requestAnimationFrame(() => {
    try {
      mapState.map?.resize();
    } catch {
      /* ignore */
    }
  });
  setTimeout(() => {
    try {
      mapState.map?.resize();
    } catch {
      /* ignore */
    }
  }, 120);
}

/** 把目标放到「未被 HUD 挡住」的可视区域中心。 */
function focusMapOnTargets(targets, zoom = 16) {
  if (!mapState.map || !targets?.length) return;
  forceMapResize();
  const pad = mapHudPadding();
  try {
    mapState.map.setFitView(targets, false, pad, zoom);
  } catch {
    const first = targets[0];
    const pos =
      typeof first?.getPosition === "function" ? first.getPosition() : first;
    if (pos) mapState.map.setZoomAndCenter(zoom, pos);
  }
}

/** 露出道路/地名等底图细节；清掉不透明行政区填充面。 */
function ensureDetailedBasemap() {
  if (!mapState.map) return;
  try {
    mapState.map.setMapStyle("amap://styles/normal");
    mapState.map.setFeatures(["bg", "road", "building", "point"]);
    mapState.map.setStatus?.({ showLabel: true });
  } catch {
    /* ignore */
  }
  const kept = [];
  for (const item of mapState.overlays) {
    const isPoly =
      item &&
      (item instanceof AMap.Polygon ||
        String(item?.CLASS_NAME || item?.className || "").includes("Polygon"));
    if (isPoly) {
      const fo = Number(item.getOptions?.()?.fillOpacity ?? 1);
      if (fo > 0.05) {
        try {
          mapState.map.remove(item);
        } catch {
          /* ignore */
        }
        continue;
      }
    }
    kept.push(item);
  }
  mapState.overlays = kept;
}

function fitChina() {
  if (!mapState.map) return;
  forceMapResize();
  mapState.map.setBounds(
    new AMap.Bounds([73.0, 17.5], [135.5, 54.0]),
    false,
    mapHudPadding()
  );
}

function fitOverlays(targets, maxZoom = 12) {
  if (!mapState.map || !targets?.length) {
    fitChina();
    return;
  }
  forceMapResize();
  mapState.map.setFitView(targets, false, mapHudPadding(), maxZoom);
}

/** GeoJSON coordinates → AMap path（[lng, lat]）。 */
function geoRingsToPaths(coordinates) {
  if (!Array.isArray(coordinates) || !coordinates.length) return [];
  // Polygon: [ring...]；已是 ring 时直接用
  const first = coordinates[0];
  if (typeof first?.[0] === "number") {
    return [coordinates.map((c) => [c[0], c[1]])];
  }
  return coordinates.map((ring) => ring.map((c) => [c[0], c[1]]));
}

function polygonsFromFeature(feature, options) {
  const geom = feature?.geometry;
  if (!geom) return [];
  const list = [];
  // bubble:true 必须：面盖住底图时，否则拖拽/滚轮事件进不了地图
  if (geom.type === "Polygon") {
    list.push(
      new AMap.Polygon({
        bubble: true,
        path: geoRingsToPaths(geom.coordinates),
        ...options,
      })
    );
  } else if (geom.type === "MultiPolygon") {
    for (const poly of geom.coordinates || []) {
      list.push(
        new AMap.Polygon({
          bubble: true,
          path: geoRingsToPaths(poly),
          ...options,
        })
      );
    }
  }
  return list;
}

function renderProvinceOverview() {
  const { counts, unknown } = aggregateProvinces(state.stocks);
  const maxCount = Math.max(0, ...Object.values(counts), 0);
  setMapUnknown(unknown);
  setMapStatus(
    `省级总览 · 已定位 ${state.stocks.length - unknown}/${state.stocks.length} 家`
  );
  els.mapBackBtn?.classList.add("hidden");

  clearMapLayers();
  forceMapResize();
  try {
    mapState.map.setFeatures(["bg", "road", "building", "point"]);
  } catch {
    /* ignore */
  }

  const features = (mapState.chinaGeo?.features || []).filter(
    (f) => f?.properties?.name
  );

  for (const feature of features) {
    const name = feature.properties.name;
    const count = counts[name] || 0;
    const strokeColor = "#5f6b7a";
    const strokeWeight = 1;
    const fillColor = provinceFillColor(count, maxCount);
    const polygons = polygonsFromFeature(feature, {
      fillColor,
      fillOpacity: 1,
      strokeColor,
      strokeWeight,
      cursor: count ? "pointer" : "default",
      extData: { name, count },
    });
    for (const polygon of polygons) {
      polygon.on("mouseover", (ev) => {
        polygon.setOptions({ strokeColor: "#0f6e56", strokeWeight: 2 });
        mapState.infoWindow.setContent(
          `<div class="map-tip">${escapeHtml(name)}：${count} 家</div>`
        );
        mapState.infoWindow.open(mapState.map, ev.lnglat);
      });
      polygon.on("mousemove", (ev) => {
        mapState.infoWindow.open(mapState.map, ev.lnglat);
      });
      polygon.on("mouseout", () => {
        polygon.setOptions({ strokeColor, strokeWeight });
        mapState.infoWindow.close();
      });
      polygon.on("click", () => {
        if (!count) return;
        state.mapLevel = "city";
        state.mapProvince = name;
        renderMap();
      });
      addOverlay(polygon);
    }
  }

  const centroids = mapState.provinceCentroids || {};
  for (const [name, count] of Object.entries(counts)) {
    if (!count) continue;
    const pt = centroids[name];
    if (!Array.isArray(pt) || pt.length < 2) continue;
    const amapPos = toAmapLngLat(pt[0], pt[1], "wgs84");
    if (!amapPos) continue;
    const marker = new AMap.Marker({
      position: amapPos,
      content: `<div class="province-count-label"><span>${count}</span></div>`,
      offset: new AMap.Pixel(-14, -14),
      bubble: true,
      zIndex: 120,
    });
    addOverlay(marker);
  }

  fitChina();
  forceMapResize();
  syncMapChrome();
}

function jitter(seed) {
  const n = Number(String(seed).replace(/\D/g, "").slice(-4) || "0");
  const a = ((n % 17) - 8) * 0.00025;
  const b = ((Math.floor(n / 17) % 17) - 8) * 0.00025;
  return [a, b];
}

/** 静态省中心点（WGS-84 近似）→ GCJ-02，仅用于省级数量气泡。 */
function wgs84ToGcj02(lng, lat) {
  const PI = Math.PI;
  const A = 6378245.0;
  const EE = 0.00669342162296594323;
  const outOfChina =
    lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271;
  if (outOfChina) return [lng, lat];

  function transformLat(x, y) {
    let ret =
      -100.0 +
      2.0 * x +
      3.0 * y +
      0.2 * y * y +
      0.1 * x * y +
      0.2 * Math.sqrt(Math.abs(x));
    ret +=
      ((20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0) /
      3.0;
    ret +=
      ((20.0 * Math.sin(y * PI) + 40.0 * Math.sin((y / 3.0) * PI)) * 2.0) / 3.0;
    ret +=
      ((160.0 * Math.sin((y / 12.0) * PI) + 320 * Math.sin((y * PI) / 30.0)) *
        2.0) /
      3.0;
    return ret;
  }
  function transformLng(x, y) {
    let ret =
      300.0 +
      x +
      2.0 * y +
      0.1 * x * x +
      0.1 * x * y +
      0.1 * Math.sqrt(Math.abs(x));
    ret +=
      ((20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0) /
      3.0;
    ret +=
      ((20.0 * Math.sin(x * PI) + 40.0 * Math.sin((x / 3.0) * PI)) * 2.0) / 3.0;
    ret +=
      ((150.0 * Math.sin((x / 12.0) * PI) + 300.0 * Math.sin((x / 30.0) * PI)) *
        2.0) /
      3.0;
    return ret;
  }

  let dLat = transformLat(lng - 105.0, lat - 35.0);
  let dLng = transformLng(lng - 105.0, lat - 35.0);
  const radLat = (lat / 180.0) * PI;
  let magic = Math.sin(radLat);
  magic = 1 - EE * magic * magic;
  const sqrtMagic = Math.sqrt(magic);
  dLat = (dLat * 180.0) / (((A * (1 - EE)) / (magic * sqrtMagic)) * PI);
  dLng = (dLng * 180.0) / ((A / sqrtMagic) * Math.cos(radLat) * PI);
  return [lng + dLng, lat + dLat];
}

function toAmapLngLat(lat, lng, coordSystem) {
  const la = Number(lat);
  const ln = Number(lng);
  if (!Number.isFinite(la) || !Number.isFinite(ln)) return null;
  if (String(coordSystem || "").toLowerCase() === "gcj02") {
    return [ln, la];
  }
  return wgs84ToGcj02(ln, la);
}

/**
 * 高德 PlaceSearch：用公司全称搜索 POI。
 * @returns {Promise<object|null>} 首个 POI
 */
function amapPlaceSearch(keyword, cityHint) {
  const kw = String(keyword || "").trim();
  if (!kw) return Promise.resolve(null);
  const key = `${cityHint || ""}|${kw}`;
  if (mapState.geocodeCache[key]) {
    return Promise.resolve(mapState.geocodeCache[key]);
  }
  if (mapState.geocodeInflight[key]) {
    return mapState.geocodeInflight[key];
  }

  mapState.geocodeInflight[key] = (async () => {
    try {
      await ensureMapAssets();
      await loadAmapPlugin("AMap.PlaceSearch");
      const poi = await new Promise((resolve) => {
        const placeSearch = new AMap.PlaceSearch({
          pageSize: 5,
          pageIndex: 1,
          city: cityHint || "全国",
          citylimit: false,
          extensions: "base",
        });
        placeSearch.search(kw, (status, result) => {
          if (status === "complete" && result?.poiList?.pois?.length) {
            resolve(result.poiList.pois[0]);
            return;
          }
          resolve(null);
        });
      });
      if (poi) mapState.geocodeCache[key] = poi;
      return poi;
    } catch {
      return null;
    } finally {
      delete mapState.geocodeInflight[key];
    }
  })();

  return mapState.geocodeInflight[key];
}

function companySearchKeyword(stock, geo) {
  return (
    String(geo?.full_name || "").trim() ||
    String(stock?.name || "").trim() ||
    String(stock?.code || "").trim()
  );
}

/**
 * 用公司全称做高德地点搜索，返回 { pos:[lng,lat], poi, geo }。
 */
async function resolveCompanyPlace(stock, geo = {}) {
  const code = String(stock?.code || geo?.code || "").trim();
  const merged = {
    ...(geo || {}),
    ...(code && state.geoByCode[code] ? state.geoByCode[code] : {}),
    code,
  };

  // 已有 PlaceSearch 结果可直接用
  if (
    String(merged.geocode_source || "") === "amap_place" &&
    merged.lat != null &&
    merged.lng != null
  ) {
    const pos = [Number(merged.lng), Number(merged.lat)];
    if (Number.isFinite(pos[0]) && Number.isFinite(pos[1])) {
      return {
        pos,
        geo: merged,
        poi: { name: merged.poi_name, address: merged.poi_address },
      };
    }
  }

  const keyword = companySearchKeyword(stock, merged);
  const cityHint = merged.reg_city || merged.reg_province || "";
  let poi = await amapPlaceSearch(keyword, cityHint);

  // 全称搜不到时，尝试「简称 + 股份有限公司」
  if (!poi && stock?.name && keyword !== stock.name) {
    poi = await amapPlaceSearch(`${stock.name}股份有限公司`, cityHint);
  }
  if (!poi && stock?.name) {
    poi = await amapPlaceSearch(stock.name, cityHint);
  }
  if (!poi?.location) return null;

  const lng = Number(poi.location.lng ?? poi.location[0]);
  const lat = Number(poi.location.lat ?? poi.location[1]);
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null;

  const next = {
    ...merged,
    lat,
    lng,
    coord_system: "gcj02",
    geocode_source: "amap_place",
    poi_name: poi.name || "",
    poi_address:
      poi.address ||
      [poi.pname, poi.cityname, poi.adname].filter(Boolean).join("") ||
      "",
  };
  if (code) state.geoByCode[code] = next;
  return { pos: [lng, lat], geo: next, poi };
}

function createCompanyMarker(stock, geo, pos, highlight = false) {
  const code = String(stock.code || "").trim();
  const title = geo?.full_name || stock.name || code;
  const marker = new AMap.Marker({
    position: pos,
    title,
    bubble: true,
    zIndex: highlight || code === state.highlightCode ? 160 : 120,
    animation: highlight ? "AMAP_ANIMATION_DROP" : "AMAP_ANIMATION_NONE",
  });
  marker.on("click", () => {
    setMarkerHighlight(marker);
    showCompanyPopup(stock, geo, pos);
  });
  return marker;
}

function loadAmapPlugin(name) {
  return new Promise((resolve, reject) => {
    if (!window.AMap?.plugin) {
      reject(new Error("高德插件加载器不可用"));
      return;
    }
    AMap.plugin(name, () => resolve());
  });
}

function searchDistrict(keyword, opts) {
  const cacheKey = `${opts.level || ""}|${opts.subdistrict ?? ""}|${opts.extensions || ""}|${keyword}`;
  if (mapState.districtCache[cacheKey]) {
    return Promise.resolve(mapState.districtCache[cacheKey]);
  }
  return loadAmapPlugin("AMap.DistrictSearch").then(
    () =>
      new Promise((resolve, reject) => {
        const ds = new AMap.DistrictSearch({
          level: opts.level || "province",
          subdistrict: opts.subdistrict ?? 0,
          extensions: opts.extensions || "all",
        });
        ds.search(keyword, (status, result) => {
          const row = result?.districtList?.[0];
          if (status === "complete" && row) {
            mapState.districtCache[cacheKey] = row;
            resolve(row);
            return;
          }
          reject(new Error(`行政区查询失败：${keyword}`));
        });
      })
  );
}

function cityNameKeys(name) {
  const raw = String(name || "").trim();
  if (!raw) return [];
  const keys = new Set([raw]);
  keys.add(raw.replace(/(市|地区|盟|自治州)$/, ""));
  keys.add(raw.endsWith("市") ? raw : `${raw}市`);
  return [...keys];
}

function matchCityCount(cityName, cityCounts) {
  for (const key of cityNameKeys(cityName)) {
    if (cityCounts[key]) return cityCounts[key];
  }
  for (const [k, n] of Object.entries(cityCounts)) {
    if (cityName.includes(k) || k.includes(String(cityName).replace(/市$/, ""))) {
      return n;
    }
  }
  return 0;
}

function aggregateCityCounts(stocksInProvince) {
  const out = {};
  for (const { geo } of stocksInProvince) {
    const city = String(geo.reg_city || "").trim();
    if (!city) continue;
    const canon =
      city.endsWith("市") ||
      city.endsWith("州") ||
      city.endsWith("盟") ||
      city.endsWith("地区")
        ? city
        : `${city}市`;
    out[canon] = (out[canon] || 0) + 1;
    out[city] = out[canon];
    out[city.replace(/(市|地区|盟|自治州)$/, "")] = out[canon];
  }
  return out;
}

function drawBoundaries(boundaries, options) {
  const polys = [];
  if (!boundaries?.length) return polys;
  for (const bound of boundaries) {
    const polygon = new AMap.Polygon({
      bubble: true,
      path: bound,
      ...options,
    });
    addOverlay(polygon);
    polys.push(polygon);
  }
  return polys;
}

function addAreaLabel(name, lnglat, className = "city-area-label") {
  if (!name || !lnglat) return null;
  const marker = new AMap.Marker({
    position: lnglat,
    content: `<div class="${className}">${escapeHtml(name)}</div>`,
    offset: new AMap.Pixel(0, 0),
    anchor: "center",
    bubble: true,
    zIndex: 80,
  });
  addOverlay(marker);
  return marker;
}

/** 绘制省内各市描边 + 市名（不填充，避免盖住底图）。 */
async function drawProvinceCities(province) {
  const drawn = [];
  let cities = [];
  try {
    const dist = await searchDistrict(province, {
      level: "province",
      subdistrict: 1,
      extensions: "all",
    });
    cities = dist?.districtList || [];
  } catch {
    return drawn;
  }

  const strokeOpts = {
    strokeColor: "#3d7a6a",
    strokeWeight: 1.25,
    strokeOpacity: 0.9,
    fillColor: "#ffffff",
    fillOpacity: 0,
    zIndex: 45,
    bubble: true,
    cursor: "default",
  };

  const resolveCenter = (center) => {
    if (typeof center === "string" && center.includes(",")) {
      const [lng, lat] = center.split(",").map(Number);
      if (Number.isFinite(lng) && Number.isFinite(lat)) return [lng, lat];
    }
    if (!center) return null;
    if (typeof center.getLng === "function") {
      return [center.getLng(), center.getLat()];
    }
    if (Array.isArray(center) && center.length >= 2) return [center[0], center[1]];
    if (center.lng != null && center.lat != null) return [center.lng, center.lat];
    return null;
  };

  // 先标市名
  for (const city of cities) {
    const name = String(city.name || "").trim();
    const lnglat = resolveCenter(city.center);
    if (name && lnglat) {
      const label = addAreaLabel(name, lnglat);
      if (label) drawn.push(label);
    }
  }

  // 子级常无 boundaries，需按市再查；控制并发
  const concurrency = 4;
  for (let i = 0; i < cities.length; i += concurrency) {
    const chunk = cities.slice(i, i + concurrency);
    const parts = await Promise.all(
      chunk.map(async (city) => {
        const name = String(city.name || "").trim();
        let bounds = city.boundaries || [];
        if (!bounds.length && name) {
          try {
            const detail = await searchDistrict(name, {
              level: "city",
              subdistrict: 0,
              extensions: "all",
            });
            bounds = detail?.boundaries || [];
          } catch {
            bounds = [];
          }
        }
        if (!bounds.length) return [];
        return drawBoundaries(bounds, {
          ...strokeOpts,
          extData: { city: name },
        });
      })
    );
    for (const polys of parts) drawn.push(...polys);
  }
  return drawn;
}

async function renderCityDrilldown() {
  const province = state.mapProvince;
  const stocks = [];
  for (const s of state.stocks) {
    const c = String(s.code || "").trim();
    const geo = state.geoByCode[c];
    if (!geo || geo.reg_province !== province) continue;
    stocks.push({ stock: s, geo });
  }

  setMapUnknown(0);
  setMapStatus(`${province} · 加载市区划与公司标注…`);
  els.mapBackBtn?.classList.remove("hidden");

  clearMapLayers();
  forceMapResize();
  ensureDetailedBasemap();

  const fitTargets = [];

  // 省界描边
  try {
    const provDist = await searchDistrict(province, {
      level: "province",
      subdistrict: 0,
      extensions: "all",
    });
    fitTargets.push(
      ...drawBoundaries(provDist.boundaries, {
        strokeColor: "#0f6e56",
        strokeWeight: 2.5,
        fillColor: "#ffffff",
        fillOpacity: 0,
        zIndex: 40,
        bubble: true,
      })
    );
  } catch {
    const feature = (mapState.chinaGeo?.features || []).find(
      (f) => (f?.properties?.name || "") === province
    );
    if (feature) {
      const polygons = polygonsFromFeature(feature, {
        fillColor: "#ffffff",
        fillOpacity: 0,
        strokeColor: "#0f6e56",
        strokeWeight: 2.5,
        zIndex: 40,
      });
      for (const polygon of polygons) {
        addOverlay(polygon);
        fitTargets.push(polygon);
      }
    }
  }

  // 市界 + 市名，让「省市内容」可见
  const cityLayers = await drawProvinceCities(province);
  fitTargets.push(...cityLayers);

  // 公司点：PlaceSearch + Marker
  for (const { stock, geo } of stocks) {
    const hit = await resolveCompanyPlace(stock, geo);
    if (!hit) continue;
    const { pos, geo: g2 } = hit;
    const [dj, di] = jitter(String(stock.code || ""));
    const lng = pos[0] + di;
    const lat = pos[1] + dj;
    const code = String(stock.code || "").trim();
    const marker = createCompanyMarker(
      stock,
      g2,
      [lng, lat],
      code === state.highlightCode
    );
    addOverlay(marker);
    if (code) {
      mapState.markersByCode[code] = marker;
      if (code === state.highlightCode) mapState.highlightMarker = marker;
    }
    fitTargets.push(marker);
  }

  const markerCount = Object.keys(mapState.markersByCode).length;
  setMapStatus(`${province} · 高德标注 ${markerCount}/${stocks.length} 家`);

  const companyMarkers = Object.values(mapState.markersByCode || {});
  if (companyMarkers.length) {
    fitOverlays(companyMarkers, 12);
  } else if (fitTargets.length) {
    fitOverlays(fitTargets, 9);
  }
  ensureDetailedBasemap();
  syncMapChrome();
  forceMapResize();
}

async function renderMap() {
  try {
    await ensureMapAssets();
    if (state.mapLevel === "city" && state.mapProvince) {
      await renderCityDrilldown();
    } else {
      state.mapLevel = "province";
      state.mapProvince = null;
      renderProvinceOverview();
    }
    syncMapChrome();
  } catch (err) {
    setMapStatus("");
    setError(err.message || String(err));
  }
}

async function refreshMapFromStocks() {
  const token = ++state.geoToken;
  if (!state.stocks.length) {
    setMapStatus("选择行业或搜索公司以查看注册地分布");
    setMapUnknown(0);
    try {
      await ensureMapAssets();
      state.mapLevel = "province";
      state.mapProvince = null;
      clearMapLayers();
      // 空数据时仍画全国省界底衬
      if (mapState.chinaGeo) {
        renderProvinceOverview();
      } else {
        fitChina();
      }
      syncMapChrome();
    } catch (err) {
      setError(err.message || String(err));
    }
    return;
  }
  try {
    setMapStatus("正在补齐注册地…");
    await enrichMissingGeo(state.stocks, token);
    if (token !== state.geoToken) return;
    await renderMap();
    // 省级总览时补打公司点，避免「只有省着色看不到公司」
    if (token === state.geoToken && state.mapLevel === "province") {
      await overlayStockMarkers(state.stocks, {
        fit: state.searchMode || state.stocks.length <= 80,
      });
    }
  } catch (err) {
    if (token !== state.geoToken) return;
    setMapStatus("");
    setError(err.message || String(err));
  }
}

/** 在当前地图上叠加公司点：高德 PlaceSearch(公司全称) + Marker。 */
async function overlayStockMarkers(stocks, { fit = false, maxZoom } = {}) {
  await ensureMapAssets();
  const token = state.geoToken;
  await enrichMissingGeo(stocks, token);
  if (token !== state.geoToken) return;

  if (fit || state.searchMode) {
    ensureDetailedBasemap();
  }

  setMapStatus("高德地点搜索中…");
  const fitTargets = [];
  let pinned = 0;
  const concurrency = 2;
  const list = [...stocks];

  for (let i = 0; i < list.length; i += concurrency) {
    if (token !== state.geoToken) return;
    const chunk = list.slice(i, i + concurrency);
    const settled = await Promise.all(
      chunk.map(async (stock) => {
        const code = String(stock.code || "").trim();
        if (!code) return null;
        const geo = state.geoByCode[code] || {};
        const hit = await resolveCompanyPlace(stock, geo);
        if (!hit) return null;
        return { stock, ...hit, code };
      })
    );

    for (const item of settled) {
      if (!item) continue;
      const { stock, geo, pos, code } = item;
      const [dj, di] = jitter(code);
      const lnglat = [pos[0] + di, pos[1] + dj];

      let marker = mapState.markersByCode[code];
      if (marker) {
        mapState.map.remove(marker);
        mapState.overlays = mapState.overlays.filter((x) => x !== marker);
      }
      marker = createCompanyMarker(
        stock,
        geo,
        lnglat,
        code === state.highlightCode
      );
      addOverlay(marker);
      mapState.markersByCode[code] = marker;
      if (code === state.highlightCode) mapState.highlightMarker = marker;
      fitTargets.push(marker);
      pinned += 1;
    }
  }

  if (fit && fitTargets.length) {
    const zoom =
      maxZoom ?? (fitTargets.length === 1 ? 15 : state.searchMode ? 12 : 8);
    fitOverlays(fitTargets, zoom);
  }
  if (pinned) {
    setMapStatus(`高德搜索标注 ${pinned} 家公司`);
  } else {
    setMapStatus("高德未搜到可标注的公司地点");
  }
}

(async () => {
  initHudPanels();
  try {
    await ensureMapAssets();
    renderProvinceOverview();
    setMapStatus("选择行业或搜索公司以查看注册地分布");
  } catch (err) {
    setError(err.message || String(err));
  }
  await loadTree();
  const bootIndustry = new URLSearchParams(window.location.search).get("industry");
  if (bootIndustry) {
    expandToIndustryCode(bootIndustry);
    await selectIndustry(bootIndustry);
  }
})();
