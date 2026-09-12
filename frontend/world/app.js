const POLL_MS = 60_000;

const REGION_COORDS = {
  us: { lat: 40.7128, lng: -74.006, city: "纽约" },
  eu: { lat: 50.1109, lng: 8.6821, city: "法兰克福" },
  uk: { lat: 51.5074, lng: -0.1278, city: "伦敦" },
  de: { lat: 52.52, lng: 13.405, city: "柏林" },
  fr: { lat: 48.8566, lng: 2.3522, city: "巴黎" },
  jp: { lat: 35.6762, lng: 139.6503, city: "东京" },
  kr: { lat: 37.5665, lng: 126.978, city: "首尔" },
  cn: { lat: 31.2304, lng: 121.4737, city: "上海" },
  hk: { lat: 22.3193, lng: 114.1694, city: "香港" },
  in: { lat: 19.076, lng: 72.8777, city: "孟买" },
};

const OIL_COORDS = {
  brent: { lat: 57.15, lng: -2.09, city: "北海" },
  wti: { lat: 29.76, lng: -95.37, city: "休斯顿" },
  dubai: { lat: 25.2048, lng: 55.2708, city: "迪拜" },
};

const CAT_COLORS = {
  indices: "#2ad4b8",
  rates: "#f0b429",
  bonds: "#a78bfa",
  oil: "#ff8c42",
};

const $ = (id) => document.getElementById(id);

const state = {
  viewMode: "roadmap",
  overview: null,
  layers: { indices: true, rates: true, bonds: true, oil: true },
  markerDefs: [],
  markers2d: [],
  selectedId: null,
  pollTimer: 0,
};

const mapRuntime = {
  provider: "amap",
  map: null,
  ready: false,
  loading: null,
  satelliteLayer: null,
  roadNetLayer: null,
};

function esc(text) {
  const el = document.createElement("span");
  el.textContent = text ?? "";
  return el.innerHTML;
}

function fmtNum(value, digits = 2) {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}

function fmtPct(value) {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function tone(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "flat";
  return n > 0 ? "up" : "down";
}

function setStatus(text, kind = "") {
  const el = $("worldStatus");
  if (!el) return;
  el.textContent = text;
  el.dataset.state = kind;
}

function isChinaMarket(marker) {
  return marker?.id === "region:cn" || marker?.data?.region === "cn";
}

function emptyDetailText() {
  return "点击地图标注查看详情，或拖动平移缩放地图。";
}

function resetMapStage() {
  const stage = $("mapStage");
  if (!stage) return null;
  stage.replaceChildren();
  stage.classList.remove("amap-container");
  stage.removeAttribute("data-provider");
  return stage;
}

/** 高德国内点用 GCJ-02；海外点保持 WGS-84。 */
function wgs84ToGcj02(lng, lat) {
  const PI = Math.PI;
  const A = 6378245.0;
  const EE = 0.00669342162296594323;
  if (lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271) {
    return [lng, lat];
  }
  const transformLat = (x, y) => {
    let ret =
      -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
    ret += ((20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0) / 3.0;
    ret += ((20.0 * Math.sin(y * PI) + 40.0 * Math.sin((y / 3.0) * PI)) * 2.0) / 3.0;
    ret += ((160.0 * Math.sin((y / 12.0) * PI) + 320 * Math.sin((y * PI) / 30.0)) * 2.0) / 3.0;
    return ret;
  };
  const transformLng = (x, y) => {
    let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
    ret += ((20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0) / 3.0;
    ret += ((20.0 * Math.sin(x * PI) + 40.0 * Math.sin((x / 3.0) * PI)) * 2.0) / 3.0;
    ret += ((150.0 * Math.sin((x / 12.0) * PI) + 300.0 * Math.sin((x / 30.0) * PI)) * 2.0) / 3.0;
    return ret;
  };
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

function toAmapPos(lat, lng) {
  return wgs84ToGcj02(Number(lng), Number(lat));
}

async function fetchMapConfig(url) {
  const resp = await fetch(url);
  const json = await resp.json();
  if (!json.ok) throw new Error(json.error || "地图配置加载失败");
  return json.data || {};
}

function loadAmap(key, securityJsCode) {
  if (window.AMap) return Promise.resolve(window.AMap);
  return new Promise((resolve, reject) => {
    if (securityJsCode) {
      window._AMapSecurityConfig = { securityJsCode };
    }
    const timeout = window.setTimeout(() => {
      reject(new Error("高德地图加载超时"));
    }, 15000);
    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`;
    script.async = true;
    script.onload = () => {
      window.clearTimeout(timeout);
      if (!window.AMap) {
        reject(new Error("高德地图 SDK 未就绪"));
        return;
      }
      resolve(window.AMap);
    };
    script.onerror = () => {
      window.clearTimeout(timeout);
      reject(new Error("高德地图脚本加载失败"));
    };
    document.head.appendChild(script);
  });
}

async function createAmapMap(stage) {
  const cfg = await fetchMapConfig("/api/map/config");
  const key = cfg.key || "";
  if (!key) {
    throw new Error("未配置高德地图 Key：请在项目根目录 .env 设置 AMAP_JS_KEY");
  }
  await loadAmap(key, cfg.securityJsCode || "");
  mapRuntime.map = new AMap.Map(stage, {
    zoom: 3,
    center: [12, 20],
    viewMode: "2D",
    mapStyle: "amap://styles/dark",
    zooms: [2, 18],
    resizeEnable: true,
    scrollWheel: true,
    doubleClickZoom: true,
    dragEnable: true,
    keyboardEnable: true,
    features: ["bg", "road", "building", "point"],
    showLabel: true,
    showIndoorMap: false,
  });
  mapRuntime.provider = "amap";
  stage.dataset.provider = "amap";
}

async function ensureMap() {
  if (mapRuntime.ready) return;
  if (mapRuntime.loading) return mapRuntime.loading;

  mapRuntime.loading = (async () => {
    const stage = $("mapStage");
    if (!stage) throw new Error("地图容器不存在");
    setStatus("加载高德地图…", "busy");
    await createAmapMap(stage);
    mapRuntime.ready = true;
    applyViewMode(state.viewMode);
  })();

  try {
    await mapRuntime.loading;
  } finally {
    mapRuntime.loading = null;
  }
}

function resizeMap() {
  if (!mapRuntime.ready || !mapRuntime.map) return;
  try {
    mapRuntime.map.resize();
  } catch {
    /* ignore */
  }
}

function fitMapMarkers() {
  if (!mapRuntime.map || !state.markerDefs.length) return;
  const overlays = state.markers2d.map((rec) => rec.overlay).filter(Boolean);
  const padding = [48, 48, 48, 48];
  if (overlays.length) {
    mapRuntime.map.setFitView(overlays, false, padding, 5);
    return;
  }
  const lngs = [];
  const lats = [];
  for (const marker of state.markerDefs) {
    const [lng, lat] = toAmapPos(marker.lat, marker.lng);
    lngs.push(lng);
    lats.push(lat);
  }
  mapRuntime.map.setBounds(
    new AMap.Bounds([Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]),
    false,
    padding,
  );
}

function clearMarkers2d() {
  for (const rec of state.markers2d) {
    try {
      rec.overlay?.setMap(null);
      mapRuntime.map?.remove(rec.overlay);
    } catch {
      /* ignore */
    }
  }
  state.markers2d = [];
}

function buildSummaryLines(marker) {
  const lines = [];
  const { data } = marker;

  if (state.layers.indices && data.indices?.length) {
    const top = data.indices[0];
    lines.push(
      `<span class="world-tag" data-cat="indices">指</span> ${esc(top.name)} ${fmtNum(top.price)} <em data-tone="${tone(top.change_pct)}">${fmtPct(top.change_pct)}</em>`,
    );
  }
  if (state.layers.rates && data.rate) {
    lines.push(
      `<span class="world-tag" data-cat="rates">率</span> ${esc(data.rate.label)} ${fmtNum(data.rate.value)}%`,
    );
  }
  if (state.layers.bonds && data.bonds?.length) {
    const b10 = data.bonds.find((b) => b.id === "10y") || data.bonds[0];
    const val = b10?.latest?.close;
    lines.push(
      `<span class="world-tag" data-cat="bonds">债</span> ${esc(b10.name)} ${fmtNum(val)}%`,
    );
  }
  if (state.layers.oil && data.oil) {
    const o = data.oil;
    lines.push(
      `<span class="world-tag" data-cat="oil">油</span> ${esc(o.name)} ${fmtNum(o.price)} <em data-tone="${tone(o.change_pct)}">${fmtPct(o.change_pct)}</em>`,
    );
  }
  return lines;
}

function markerLabelHtml(marker) {
  const enter = isChinaMarket(marker)
    ? `<div class="world-marker-enter">点击进入中国市场</div>`
    : "";
  return `
    <div class="world-marker-title">${esc(marker.title)}</div>
    <div class="world-marker-city muted">${esc(marker.city || "")}</div>
    <div class="world-marker-lines">${buildSummaryLines(marker).join("")}</div>
    ${enter}
  `;
}

function createMarker2d(marker) {
  if (!mapRuntime.map) return;

  const labelEl = document.createElement("div");
  labelEl.className = "world-marker-label world-map-marker-label";
  labelEl.dataset.markerId = marker.id;
  labelEl.innerHTML = markerLabelHtml(marker);
  labelEl.addEventListener("click", (e) => {
    e.stopPropagation();
    if (isChinaMarket(marker)) {
      window.location.href = "/cn";
      return;
    }
    selectMarker(marker.id);
  });

  const overlay = new AMap.Marker({
    position: toAmapPos(marker.lat, marker.lng),
    content: labelEl,
    offset: new AMap.Pixel(0, -8),
    anchor: "bottom-center",
    zIndex: 120,
  });
  mapRuntime.map.add(overlay);
  state.markers2d.push({ id: marker.id, overlay, labelEl, marker });
}

function groupIndicesByRegion(indices) {
  const map = new Map();
  for (const row of indices?.items || []) {
    if (!map.has(row.region)) map.set(row.region, []);
    map.get(row.region).push(row);
  }
  return map;
}

function groupRatesByRegion(rates) {
  const map = new Map();
  for (const row of rates?.items || []) map.set(row.region, row);
  return map;
}

function groupBondsByRegion(bonds) {
  const map = new Map();
  for (const row of bonds?.items || []) map.set(row.region, row.series || []);
  return map;
}

function buildMarkerDefs() {
  const overview = state.overview;
  if (!overview) {
    state.markerDefs = [];
    return;
  }

  const idxMap = groupIndicesByRegion(overview.indices);
  const rateMap = groupRatesByRegion(overview.rates);
  const bondMap = groupBondsByRegion(overview.bonds);
  const defs = [];

  const regions = new Set([
    ...idxMap.keys(),
    ...rateMap.keys(),
    ...bondMap.keys(),
  ]);

  for (const region of regions) {
    const coord = REGION_COORDS[region];
    if (!coord) continue;

    const indices = idxMap.get(region) || [];
    const rateRow = rateMap.get(region);
    const bonds = bondMap.get(region) || [];

    const hasVisible =
      (state.layers.indices && indices.length) ||
      (state.layers.rates && rateRow) ||
      (state.layers.bonds && bonds.length);

    if (!hasVisible) continue;

    const regionName = indices[0]?.region_name || rateRow?.name || region;
    defs.push({
      id: `region:${region}`,
      category: "indices",
      lat: coord.lat,
      lng: coord.lng,
      city: coord.city,
      title: regionName,
      color: CAT_COLORS.indices,
      data: {
        region,
        regionName,
        indices: state.layers.indices ? indices : [],
        rate: state.layers.rates && rateRow
          ? { label: rateRow.label, value: rateRow.latest?.value, history: rateRow.history }
          : null,
        bonds: state.layers.bonds ? bonds : [],
      },
    });
  }

  if (state.layers.oil) {
    for (const item of overview.oil?.items || []) {
      const coord = OIL_COORDS[item.id];
      if (!coord) continue;
      defs.push({
        id: `oil:${item.id}`,
        category: "oil",
        lat: coord.lat,
        lng: coord.lng,
        city: coord.city,
        title: item.name,
        color: CAT_COLORS.oil,
        data: {
          oil: item,
          regionName: item.name,
        },
      });
    }
  }

  state.markerDefs = defs;
}

function syncMarkers2d() {
  if (!mapRuntime.ready) return;
  clearMarkers2d();
  for (const marker of state.markerDefs) createMarker2d(marker);
}

function rebuildMarkers() {
  buildMarkerDefs();
  syncMarkers2d();
  if (state.selectedId && state.markerDefs.some((m) => m.id === state.selectedId)) {
    selectMarker(state.selectedId, false);
  } else {
    state.selectedId = null;
    renderDetail(null);
  }
}

function renderDetail(markerRec) {
  const panel = $("detailPanel");
  if (!panel) return;
  const marker = markerRec?.marker || markerRec;
  if (!marker) {
    panel.innerHTML = `<p class="muted world-detail-empty">${emptyDetailText()}</p>`;
    return;
  }

  const { data } = marker;
  const blocks = [];

  if (data.indices?.length) {
    blocks.push(`
      <section class="world-detail-block">
        <h3><span class="world-layer-dot" data-cat="indices"></span>股市指数</h3>
        <ul class="world-detail-list">
          ${data.indices.map((row) => `
            <li>
              <span>${esc(row.name)}</span>
              <strong class="num">${fmtNum(row.price)}</strong>
              <em class="num" data-tone="${tone(row.change_pct)}">${fmtPct(row.change_pct)}</em>
            </li>
          `).join("")}
        </ul>
      </section>
    `);
  }

  if (data.rate) {
    blocks.push(`
      <section class="world-detail-block">
        <h3><span class="world-layer-dot" data-cat="rates"></span>央行利率</h3>
        <p class="world-detail-hero">
          <span>${esc(data.rate.label)}</span>
          <strong>${fmtNum(data.rate.value)}%</strong>
        </p>
      </section>
    `);
  }

  if (data.bonds?.length) {
    blocks.push(`
      <section class="world-detail-block">
        <h3><span class="world-layer-dot" data-cat="bonds"></span>国债收益率</h3>
        <ul class="world-detail-list">
          ${data.bonds.map((row) => `
            <li>
              <span>${esc(row.name)}</span>
              <strong class="num">${fmtNum(row.latest?.close)}%</strong>
            </li>
          `).join("")}
        </ul>
      </section>
    `);
  }

  if (data.oil) {
    const o = data.oil;
    blocks.push(`
      <section class="world-detail-block">
        <h3><span class="world-layer-dot" data-cat="oil"></span>原油期货</h3>
        <p class="world-detail-hero">
          <span>${esc(o.name)}</span>
          <strong>${fmtNum(o.price)}</strong>
          <em class="num" data-tone="${tone(o.change_pct)}">${fmtPct(o.change_pct)}</em>
        </p>
        <p class="muted world-detail-meta">开 ${fmtNum(o.open)} · 高 ${fmtNum(o.high)} · 低 ${fmtNum(o.low)}</p>
      </section>
    `);
  }

  const chinaCta =
    marker.id === "region:cn" || marker.data?.region === "cn"
      ? `
        <p class="muted world-detail-enter-hint">行业行情 · 个股行情 · 涨跌停</p>
        <a class="btn world-detail-enter" href="/cn">进入中国市场</a>
      `
      : "";

  panel.innerHTML = `
    <header class="world-detail-head">
      <h2>${esc(marker.title)}</h2>
      <span class="muted">${esc(marker.city || "")}</span>
      ${chinaCta}
    </header>
    ${blocks.join("")}
  `;
}

function findMarkerRec(id) {
  const rec = state.markers2d.find((m) => m.id === id);
  if (rec) return rec;
  const def = state.markerDefs.find((m) => m.id === id);
  return def ? { id, marker: def } : null;
}

function selectMarker(id, focus = true) {
  state.selectedId = id;

  document.querySelectorAll(".world-map-marker-label").forEach((el) => {
    el.classList.toggle("is-active", el.dataset.markerId === id);
  });

  const rec = findMarkerRec(id);
  renderDetail(rec);

  if (!focus || !rec?.marker || !mapRuntime.map) return;
  const { lat, lng } = rec.marker;
  mapRuntime.map.panTo(toAmapPos(lat, lng));
  if (mapRuntime.map.getZoom() < 4) mapRuntime.map.setZoom(4);
}

function applyAmapViewMode(mode) {
  if (!mapRuntime.map || !window.AMap) return;
  if (!mapRuntime.satelliteLayer) {
    mapRuntime.satelliteLayer = new AMap.TileLayer.Satellite({
      zooms: [2, 20],
      detectRetina: true,
      zIndex: 2,
    });
  }
  if (!mapRuntime.roadNetLayer) {
    mapRuntime.roadNetLayer = new AMap.TileLayer.RoadNet({
      zooms: [2, 20],
      detectRetina: true,
      zIndex: 3,
    });
  }
  const removeLayer = (layer) => {
    try {
      mapRuntime.map.remove(layer);
    } catch {
      /* ignore */
    }
  };
  removeLayer(mapRuntime.satelliteLayer);
  removeLayer(mapRuntime.roadNetLayer);
  if (mode === "satellite") {
    mapRuntime.map.add([mapRuntime.satelliteLayer, mapRuntime.roadNetLayer]);
    return;
  }
  try {
    mapRuntime.map.setMapStyle("amap://styles/dark");
    mapRuntime.map.setFeatures(["bg", "road", "building", "point"]);
  } catch {
    /* ignore */
  }
}

function applyViewMode(mode) {
  const next = mode === "satellite" ? "satellite" : "roadmap";
  state.viewMode = next;
  if (!mapRuntime.map) return;
  applyAmapViewMode(next);
}

function setViewMode(mode) {
  const next = mode === "satellite" ? "satellite" : "roadmap";
  state.viewMode = next;
  document.querySelectorAll(".world-view-btn").forEach((btn) => {
    const active = btn.dataset.view === next;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-pressed", active ? "true" : "false");
  });
  applyViewMode(next);
}

async function fetchJson(url, timeoutMs = 90_000, extra = {}) {
  if (window.OrbitHttp) {
    const json = await OrbitHttp.get(url, { timeoutMs, ...extra });
    return json.data;
  }
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const resp = await fetch(url, { signal: ctrl.signal });
    const json = await resp.json();
    if (!json.ok) throw new Error(json.error || "加载失败");
    return json.data;
  } finally {
    window.clearTimeout(timer);
  }
}

function apiUrl(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value != null && value !== "") url.searchParams.set(key, String(value));
  }
  return `${url.pathname}${url.search}`;
}

async function loadOverview(force = false, { poll = false } = {}) {
  setStatus("同步中…", "busy");
  const refresh = force ? { refresh: "1" } : {};
  const httpOpts = poll ? { bypassCache: true, writeCache: true } : {};
  try {
    const [indices, oil] = await Promise.all([
      fetchJson(apiUrl("/api/global/indices", refresh), 30_000, httpOpts),
      fetchJson(apiUrl("/api/global/oil", refresh), 30_000, httpOpts),
    ]);
    state.overview = { indices, oil, rates: { items: [] }, bonds: { items: [] } };
    rebuildMarkers();
    setStatus("指数/原油已更新，利率国债加载中…", "busy");

    const [rates, bonds] = await Promise.all([
      fetchJson(apiUrl("/api/global/rates", { ...refresh, limit: 24 }), 60_000, httpOpts),
      fetchJson(apiUrl("/api/global/bonds", { ...refresh, limit: 60 }), 60_000, httpOpts),
    ]);
    state.overview = {
      indices,
      oil,
      rates,
      bonds,
      updated_at: new Date().toISOString().slice(0, 19),
    };
    rebuildMarkers();
    setStatus(`更新 ${state.overview.updated_at}`, "live");
  } catch (err) {
    const msg = err.name === "AbortError" ? "请求超时，请稍后重试" : (err.message || "加载失败");
    setStatus(msg, "error");
    if (state.overview) rebuildMarkers();
  }
}

function bindUi() {
  $("refreshBtn")?.addEventListener("click", () => loadOverview(true));

  document.querySelectorAll(".world-view-btn").forEach((btn) => {
    btn.addEventListener("click", () => setViewMode(btn.dataset.view));
  });

  document.querySelectorAll(".world-layer-chip input").forEach((input) => {
    input.addEventListener("change", () => {
      const layer = input.closest(".world-layer-chip")?.dataset.layer;
      if (!layer) return;
      state.layers[layer] = input.checked;
      rebuildMarkers();
    });
  });

  window.addEventListener("resize", () => resizeMap());
  state.pollTimer = window.setInterval(() => loadOverview(false, { poll: true }), POLL_MS);
}

async function boot() {
  bindUi();
  window.OrbitPrefetch?.boot("world");
  await ensureMap();
  resizeMap();
  await loadOverview(false);
  fitMapMarkers();
}

boot().catch((err) => {
  setStatus(err.message || "页面初始化失败", "error");
  console.error(err);
});
