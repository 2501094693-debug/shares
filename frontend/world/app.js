const POLL_MS = 60_000;

const REGION_COORDS = {
  us: { lat: 40.7128, lng: -74.006, city: "纽约" },
  eu: { lat: 47.8, lng: 9.2, city: "法兰克福" },
  uk: { lat: 53.8, lng: -7.2, city: "伦敦" },
  de: { lat: 54.6, lng: 16.8, city: "柏林" },
  fr: { lat: 44.6, lng: 1.2, city: "巴黎" },
  jp: { lat: 36.2, lng: 140.2, city: "东京" },
  kr: { lat: 36.1, lng: 129.4, city: "首尔" },
  cn: { lat: 32.4, lng: 118.8, city: "上海" },
  hk: { lat: 20.6, lng: 114.8, city: "香港" },
  in: { lat: 18.4, lng: 74.2, city: "孟买" },
};

const OIL_COORDS = {
  brent: { lat: 62.4, lng: 1.8, city: "北海" },
  wti: { lat: 27.2, lng: -92.4, city: "休斯顿" },
  dubai: { lat: 24.2, lng: 56.8, city: "迪拜" },
};

/** 像素偏移，避免西欧 / 东亚卡片叠在一起。 */
const MARKER_OFFSET = {
  "region:us": [-8, -10],
  "region:eu": [88, 6],
  "region:uk": [-108, -16],
  "region:de": [124, -56],
  "region:fr": [-36, 86],
  "region:jp": [18, -12],
  "region:kr": [64, 48],
  "region:cn": [-16, -8],
  "region:hk": [56, 64],
  "region:in": [12, 18],
  "oil:brent": [12, -28],
  "oil:wti": [78, 52],
  "oil:dubai": [10, -8],
};

const $ = (id) => document.getElementById(id);

const state = {
  viewMode: "roadmap",
  overview: null,
  history: {},
  layers: { indices: true, oil: true },
  markerDefs: [],
  markers2d: [],
  selectedId: null,
  chartCode: null,
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

function historyFor(code, price) {
  const points = state.history?.[code] || [];
  if (!points.length) return [];
  const last = Number(points[points.length - 1]?.close);
  const px = Number(price);
  if (Number.isFinite(px) && px !== 0 && Number.isFinite(last) && Math.abs(last / px - 1) > 0.18) {
    return [];
  }
  return points;
}

function sparkSvg(points, w = 136, h = 34, { fill = false } = {}) {
  const closes = (points || [])
    .map((p) => Number(p.close))
    .filter((n) => Number.isFinite(n));
  if (closes.length < 2) {
    return `<svg class="world-spark" viewBox="0 0 ${w} ${h}" aria-hidden="true"></svg>`;
  }
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;
  const step = (w - 2) / (closes.length - 1);
  const coords = closes.map((c, i) => {
    const x = 1 + i * step;
    const y = h - 1 - ((c - min) / span) * (h - 2);
    return [x, y];
  });
  const line = coords
    .map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");
  const up = closes[closes.length - 1] >= closes[0];
  const color = up ? "var(--up)" : "var(--down)";
  const area = fill
    ? `${line} L${coords[coords.length - 1][0].toFixed(1)},${h} L${coords[0][0].toFixed(1)},${h} Z`
    : "";
  return `
    <svg class="world-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true" style="color:${color}">
      ${fill ? `<path class="world-spark-fill" d="${area}" fill="currentColor"></path>` : ""}
      <path d="${line}" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"></path>
    </svg>
  `;
}

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
    ret += ((150.0 * Math.sin((x / 12.0) * PI) + 300.0 * Math.sin((x * PI) / 30.0)) * 2.0) / 3.0;
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
  mapRuntime.map.on("click", () => selectMarker(null, false));
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
  const padding = [72, 88, 88, 72];
  if (overlays.length) {
    mapRuntime.map.setFitView(overlays, false, padding, 4);
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

function markerLabelHtml(marker) {
  if (marker.category === "oil") {
    const o = marker.data.oil || {};
    return `
      <div class="world-card world-card-oil">
        <div class="world-card-kicker">原油 · ${esc(marker.city || "")}</div>
        <div class="world-card-name">${esc(o.name || marker.title)}</div>
        <div class="world-card-row">
          <strong class="world-card-px">${fmtNum(o.price)}</strong>
          <em data-tone="${tone(o.change_pct)}">${fmtPct(o.change_pct)}</em>
        </div>
      </div>
    `;
  }
  const top = marker.data.indices?.[0] || {};
  const extra = Math.max(0, (marker.data.indices?.length || 0) - 1);
  return `
    <div class="world-card">
      <div class="world-card-kicker">
        <span>${esc(marker.title)}</span>
        <span class="muted">${esc(marker.city || "")}</span>
      </div>
      <div class="world-card-name">${esc(top.name || "主要指数")}${extra ? `<span class="muted"> +${extra}</span>` : ""}</div>
      <div class="world-card-row">
        <strong class="world-card-px">${fmtNum(top.price)}</strong>
        <em data-tone="${tone(top.change_pct)}">${fmtPct(top.change_pct)}</em>
      </div>
      ${sparkSvg(historyFor(top.code, top.price))}
    </div>
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
    selectMarker(marker.id);
  });

  const [ox, oy] = MARKER_OFFSET[marker.id] || [0, -8];
  const overlay = new AMap.Marker({
    position: toAmapPos(marker.lat, marker.lng),
    content: labelEl,
    offset: new AMap.Pixel(ox, oy),
    anchor: "bottom-center",
    zIndex: marker.id === state.selectedId ? 220 : 120,
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

function buildMarkerDefs() {
  const overview = state.overview;
  if (!overview) {
    state.markerDefs = [];
    return;
  }

  const idxMap = groupIndicesByRegion(overview.indices);
  const defs = [];

  for (const [region, indices] of idxMap) {
    const coord = REGION_COORDS[region];
    if (!coord || !indices.length) continue;
    defs.push({
      id: `region:${region}`,
      category: "indices",
      lat: coord.lat,
      lng: coord.lng,
      city: coord.city,
      title: indices[0]?.region_name || region,
      data: { region, indices },
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
        data: { oil: item },
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
    selectMarker(null, false);
  }
}

function findMarkerRec(id) {
  const rec = state.markers2d.find((m) => m.id === id);
  if (rec) return rec;
  const def = state.markerDefs.find((m) => m.id === id);
  return def ? { id, marker: def } : null;
}

function closeChartPop() {
  const pop = $("worldChartPop");
  if (!pop) return;
  pop.hidden = true;
  pop.replaceChildren();
}

function renderChartPop(marker) {
  const pop = $("worldChartPop");
  if (!pop) return;
  if (!marker) {
    closeChartPop();
    return;
  }

  if (marker.category === "oil") {
    const o = marker.data.oil || {};
    pop.hidden = false;
    pop.innerHTML = `
      <header class="world-pop-head">
        <div>
          <p class="world-pop-kicker">原油期货 · ${esc(marker.city || "")}</p>
          <h2>${esc(o.name || marker.title)}</h2>
        </div>
        <button type="button" class="world-pop-close" data-close>×</button>
      </header>
      <div class="world-pop-hero">
        <strong>${fmtNum(o.price)}</strong>
        <em data-tone="${tone(o.change_pct)}">${fmtPct(o.change_pct)}</em>
      </div>
      <p class="muted world-pop-meta">开 ${fmtNum(o.open)} · 高 ${fmtNum(o.high)} · 低 ${fmtNum(o.low)}</p>
    `;
    pop.querySelector("[data-close]")?.addEventListener("click", () => selectMarker(null, false));
    return;
  }

  const indices = marker.data.indices || [];
  const active = indices.find((row) => row.code === state.chartCode) || indices[0];
  if (active) state.chartCode = active.code;
  const points = historyFor(active?.code, active?.price);
  const first = points[0]?.date || "";
  const last = points[points.length - 1]?.date || "";
  const china = isChinaMarket(marker)
    ? `<a class="btn world-pop-enter" href="/cn">进入中国市场</a>`
    : "";

  pop.hidden = false;
  pop.innerHTML = `
    <header class="world-pop-head">
      <div>
        <p class="world-pop-kicker">${esc(marker.title)} · ${esc(marker.city || "")} · 日线</p>
        <h2>${esc(active?.name || marker.title)}</h2>
      </div>
      <button type="button" class="world-pop-close" data-close>×</button>
    </header>
    <div class="world-pop-hero">
      <strong>${fmtNum(active?.price)}</strong>
      <em data-tone="${tone(active?.change_pct)}">${fmtPct(active?.change_pct)}</em>
    </div>
    <div class="world-pop-chart">${sparkSvg(points, 320, 110, { fill: true })}</div>
    <p class="muted world-pop-meta">${esc(first)}${first && last ? " — " : ""}${esc(last)}${points.length ? ` · ${points.length} 根` : "暂无走势"}</p>
    ${indices.length > 1 ? `
      <div class="world-pop-switch" role="tablist">
        ${indices.map((row) => `
          <button type="button" class="world-pop-tab${row.code === active.code ? " is-active" : ""}" data-code="${esc(row.code)}">
            ${esc(row.name)}
          </button>
        `).join("")}
      </div>
    ` : ""}
    ${china}
  `;
  pop.querySelector("[data-close]")?.addEventListener("click", () => selectMarker(null, false));
  pop.querySelectorAll("[data-code]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      state.chartCode = btn.dataset.code;
      renderChartPop(marker);
    });
  });
}

function selectMarker(id, focus = true) {
  state.selectedId = id || null;
  if (!id) state.chartCode = null;

  document.querySelectorAll(".world-map-marker-label").forEach((el) => {
    el.classList.toggle("is-active", Boolean(id) && el.dataset.markerId === id);
  });
  state.markers2d.forEach((rec) => {
    try {
      rec.overlay?.setzIndex(rec.id === id ? 220 : 120);
    } catch {
      /* ignore */
    }
  });

  const rec = id ? findMarkerRec(id) : null;
  renderChartPop(rec?.marker || null);

  if (!focus || !rec?.marker || !mapRuntime.map) return;
  const { lat, lng } = rec.marker;
  mapRuntime.map.panTo(toAmapPos(lat, lng));
  if (mapRuntime.map.getZoom() < 3) mapRuntime.map.setZoom(3);
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

async function fetchOptional(url, timeoutMs, extra = {}) {
  try {
    return await fetchJson(url, timeoutMs, extra);
  } catch (err) {
    console.warn("全球行情接口失败", url, err);
    return null;
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
      fetchOptional(apiUrl("/api/global/indices", refresh), 30_000, httpOpts),
      fetchOptional(apiUrl("/api/global/oil", refresh), 30_000, httpOpts),
    ]);
    state.overview = {
      indices: indices || { items: [] },
      oil: oil || { items: [] },
    };
    rebuildMarkers();

    const history = await fetchOptional(
      apiUrl("/api/global/indices/history", { ...refresh, limit: 90 }),
      45_000,
      httpOpts,
    );
    state.history = history?.by_code || {};
    rebuildMarkers();
    setStatus("live", "live");
  } catch (err) {
    const msg = err.name === "AbortError" ? "请求超时，请稍后重试" : (err.message || "加载失败");
    setStatus(msg, "error");
    if (state.overview) rebuildMarkers();
  }
}

function bindUi() {
  document.querySelectorAll(".world-view-btn").forEach((btn) => {
    btn.addEventListener("click", () => setViewMode(btn.dataset.view));
  });
  $("worldChartPop")?.addEventListener("click", (e) => e.stopPropagation());
  window.addEventListener("resize", () => resizeMap());
  state.pollTimer = window.setInterval(() => loadOverview(false, { poll: true }), POLL_MS);
}

async function boot() {
  bindUi();
  window.OrbitPrefetch?.boot("world");
  const mapTask = ensureMap()
    .then(() => {
      resizeMap();
      if (state.overview) rebuildMarkers();
    })
    .catch((err) => {
      console.error(err);
      setStatus(err.message || "地图加载失败", "error");
    });
  await Promise.all([mapTask, loadOverview(false)]);
  rebuildMarkers();
  fitMapMarkers();
}

boot().catch((err) => {
  setStatus(err.message || "页面初始化失败", "error");
  console.error(err);
});
