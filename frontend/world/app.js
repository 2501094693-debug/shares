const POLL_MS = 60_000;
const HISTORY_LIMIT = 240;

const REGION_COORDS = {
  us: { lat: 40.7128, lng: -74.006, city: "纽约" },
  eu: { lat: 48.2, lng: 10.8, city: "法兰克福" },
  uk: { lat: 54.2, lng: -8.4, city: "伦敦" },
  de: { lat: 55.4, lng: 18.6, city: "柏林" },
  fr: { lat: 43.2, lng: -0.6, city: "巴黎" },
  jp: { lat: 37.4, lng: 142.6, city: "东京" },
  kr: { lat: 34.2, lng: 130.8, city: "首尔" },
  cn: { lat: 34.8, lng: 116.2, city: "上海" },
  hk: { lat: 15.2, lng: 111.2, city: "香港" },
  in: { lat: 16.8, lng: 74.2, city: "孟买" },
};

const OIL_COORDS = {
  brent: { lat: 64.8, lng: 0.4, city: "北海" },
  wti: { lat: 24.8, lng: -94.8, city: "休斯顿" },
  dubai: { lat: 27.4, lng: 50.4, city: "迪拜" },
  oman: { lat: 16.8, lng: 65.6, city: "马斯喀特" },
  shanghai: { lat: 28.2, lng: 126.4, city: "上海" },
  urals: { lat: 56.8, lng: 60.4, city: "乌拉尔" },
};

/** 初始像素偏移（再经 layoutMarkerLabels 螺旋占位避让）。 */
const MARKER_OFFSET = {
  "region:us": [-60, -50],
  "region:eu": [30, 10],
  "region:uk": [-170, -40],
  "region:de": [180, -120],
  "region:fr": [-90, 150],
  "region:jp": [100, -110],
  "region:kr": [170, 10],
  "region:cn": [-150, -40],
  "region:hk": [30, 210],
  "region:in": [-50, 70],
  "oil:brent": [10, -150],
  "oil:wti": [120, 140],
  "oil:dubai": [-160, -50],
  "oil:oman": [-10, 190],
  "oil:shanghai": [180, 120],
  "oil:urals": [-100, -110],
};

const $ = (id) => document.getElementById(id);

const state = {
  viewMode: "roadmap",
  overview: null,
  history: {},
  historySource: {},
  oilHistory: {},
  oilHistorySource: {},
  layers: { indices: true, oil: true },
  markerDefs: [],
  markers2d: [],
  selectedId: null,
  chartCode: null,
  oilCode: null,
  pollTimer: 0,
};

const mapRuntime = {
  provider: "amap",
  map: null,
  ready: false,
  loading: null,
  satelliteLayer: null,
  roadNetLayer: null,
  layoutTimer: 0,
  mapEventsBound: false,
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

function setOilStatus(text, kind = "") {
  const el = $("worldOilStatus");
  if (!el) return;
  el.textContent = text;
  el.dataset.state = kind;
}

function indexItems() {
  return state.overview?.indices?.items || [];
}

function oilItems() {
  return state.overview?.oil?.items || [];
}

function findIndex(code) {
  return indexItems().find((row) => row.code === code) || null;
}

function findOil(id) {
  return oilItems().find((row) => row.id === id) || null;
}

function historyPoints(code) {
  return state.history?.[code] || [];
}

function oilHistoryPoints(id) {
  return state.oilHistory?.[id] || [];
}

function klineMetaText(points, sourceLabel) {
  const src = (sourceLabel || "").trim();
  if (!points?.length) {
    return src ? `日K · 暂无数据 · ${src}` : "日K · 暂无数据";
  }
  return src ? `日K · ${points.length} 根 · ${src}` : `日K · ${points.length} 根`;
}

/** oilprice 等源常无当日开高低，用日 K 末根补卡片底部。 */
function oilOhlc(row) {
  const last = oilHistoryPoints(row?.id)?.at?.(-1) || null;
  return {
    open: row?.open ?? last?.open ?? null,
    high: row?.high ?? last?.high ?? null,
    low: row?.low ?? last?.low ?? null,
  };
}

/** 地图小火花线：现价与末收偏差过大时丢弃（防错源） */
function historyForSpark(code, price) {
  const points = historyPoints(code);
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
  bindMapLayoutEvents();
}

function bindMapLayoutEvents() {
  if (!mapRuntime.map || mapRuntime.mapEventsBound) return;
  mapRuntime.mapEventsBound = true;
  const schedule = () => scheduleMarkerLayoutBurst();
  mapRuntime.map.on("moveend", schedule);
  mapRuntime.map.on("zoomend", schedule);
  mapRuntime.map.on("resize", schedule);
}

function scheduleMarkerLayout(delay = 40) {
  if (mapRuntime.layoutTimer) window.clearTimeout(mapRuntime.layoutTimer);
  mapRuntime.layoutTimer = window.setTimeout(() => {
    mapRuntime.layoutTimer = 0;
    layoutMarkerLabels();
  }, delay);
}

/** fit / 同步后多拍一次，避免 setFitView 动画未结束或卡片高度未稳定。 */
function scheduleMarkerLayoutBurst() {
  scheduleMarkerLayout(40);
  window.setTimeout(() => layoutMarkerLabels(), 120);
  window.setTimeout(() => layoutMarkerLabels(), 280);
}

/** 与 AMap bottom-center + offset 对齐；TIP 计入卡片下方小三角。 */
const LABEL_TIP = 8;

function markerAnchorPt(rec) {
  if (!rec?.marker || !mapRuntime.map) return null;
  const [lng, lat] = toAmapPos(rec.marker.lat, rec.marker.lng);
  return mapRuntime.map.lngLatToContainer([lng, lat]) || null;
}

function markerLabelSize(rec) {
  const el = rec?.labelEl;
  const w = Math.max(el?.offsetWidth || 158, 120);
  const h = Math.max(el?.offsetHeight || 64, 48) + LABEL_TIP;
  return { w, h };
}

function markerScreenRect(rec, ox, oy, size) {
  const pt = markerAnchorPt(rec);
  if (!pt) return null;
  const { w, h } = size || markerLabelSize(rec);
  const left = pt.x + ox - w / 2;
  const top = pt.y + oy - (h - LABEL_TIP);
  return {
    left,
    top,
    right: left + w,
    bottom: top + h,
    w,
    h,
    cx: left + w / 2,
    cy: top + h / 2,
  };
}

function rectsOverlap(a, b, gap = 10) {
  return !(
    a.right + gap <= b.left ||
    b.right + gap <= a.left ||
    a.bottom + gap <= b.top ||
    b.bottom + gap <= a.top
  );
}

function rectOutOfBounds(rect, stageW, stageH, pad) {
  let cost = 0;
  if (rect.left < pad) cost += pad - rect.left;
  if (rect.right > stageW - pad) cost += rect.right - (stageW - pad);
  if (rect.top < pad) cost += pad - rect.top;
  if (rect.bottom > stageH - pad) cost += rect.bottom - (stageH - pad);
  return cost;
}

/** 优先用预设偏移，再沿螺旋向外找空位（确定性、不飞出太远）。 */
function offsetCandidates(preferredOx, preferredOy, maxR = 360) {
  const out = [[preferredOx, preferredOy]];
  const seen = new Set([`${preferredOx},${preferredOy}`]);
  const add = (ox, oy) => {
    const key = `${Math.round(ox)},${Math.round(oy)}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push([ox, oy]);
  };
  // 八向短距优先
  const dirs = [
    [0, -1],
    [1, -1],
    [1, 0],
    [1, 1],
    [0, 1],
    [-1, 1],
    [-1, 0],
    [-1, -1],
  ];
  for (let r = 18; r <= maxR; r += 16) {
    for (const [dx, dy] of dirs) add(preferredOx + dx * r, preferredOy + dy * r);
    const steps = Math.max(8, Math.round((Math.PI * 2 * r) / 28));
    for (let i = 0; i < steps; i += 1) {
      const rad = (i / steps) * Math.PI * 2;
      add(preferredOx + Math.cos(rad) * r, preferredOy + Math.sin(rad) * r);
    }
  }
  return out;
}

function layoutMarkerLabels() {
  if (!mapRuntime.map || !state.markers2d.length) return;
  const stage = $("mapStage");
  const stageW = stage?.clientWidth || 0;
  const stageH = stage?.clientHeight || 0;
  if (!stageW || !stageH) return;

  const GAP = 20;
  const PAD = 6;

  const items = state.markers2d
    .map((rec) => {
      const size = markerLabelSize(rec);
      const base = MARKER_OFFSET[rec.id] || [0, -8];
      return {
        rec,
        ox: base[0],
        oy: base[1],
        preferredOx: base[0],
        preferredOy: base[1],
        size,
        area: size.w * size.h,
      };
    })
    .filter((item) => item.rec.labelEl && item.rec.overlay)
    .sort((a, b) => b.area - a.area);

  const placed = [];

  for (const item of items) {
    const candidates = offsetCandidates(item.preferredOx, item.preferredOy);
    let best = null;
    let bestScore = Infinity;

    for (const [ox, oy] of candidates) {
      const rect = markerScreenRect(item.rec, ox, oy, item.size);
      if (!rect) continue;
      if (placed.some((p) => rectsOverlap(rect, p.rect, GAP))) continue;

      const dist = Math.hypot(ox - item.preferredOx, oy - item.preferredOy);
      const oob = rectOutOfBounds(rect, stageW, stageH, PAD);
      // 出界可接受，但优先贴边内；绝不接受与已放置重叠的候选
      const score = dist + oob * 3;
      if (score < bestScore) {
        bestScore = score;
        best = { ox, oy, rect };
        if (dist < 1 && oob === 0) break;
      }
    }

    if (!best) {
      // 极端拥挤：选与已放置重叠面积最小的位置
      let minHit = Infinity;
      for (const [ox, oy] of candidates) {
        const rect = markerScreenRect(item.rec, ox, oy, item.size);
        if (!rect) continue;
        let hit = 0;
        for (const p of placed) {
          if (!rectsOverlap(rect, p.rect, 0)) continue;
          hit +=
            (Math.min(rect.right, p.rect.right) - Math.max(rect.left, p.rect.left)) *
            (Math.min(rect.bottom, p.rect.bottom) - Math.max(rect.top, p.rect.top));
        }
        const dist = Math.hypot(ox - item.preferredOx, oy - item.preferredOy);
        const score = hit * 1000 + dist;
        if (score < minHit) {
          minHit = score;
          best = { ox, oy, rect };
        }
      }
    }

    if (!best) continue;
    item.ox = best.ox;
    item.oy = best.oy;
    placed.push({ rect: best.rect });
  }

  for (const item of items) {
    try {
      item.rec.overlay.setOffset(new AMap.Pixel(Math.round(item.ox), Math.round(item.oy)));
    } catch {
      /* ignore */
    }
  }
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
  scheduleMarkerLayout();
}

function fitMapMarkers() {
  if (!mapRuntime.map || !state.markerDefs.length) return;
  const overlays = state.markers2d.map((rec) => rec.overlay).filter(Boolean);
  const padding = [72, 88, 88, 72];
  const afterFit = () => {
    scheduleMarkerLayoutBurst();
  };
  if (overlays.length) {
    mapRuntime.map.setFitView(overlays, false, padding, 4);
    afterFit();
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
  afterFit();
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

function markerIndexRowsHtml(indices) {
  return (indices || [])
    .map(
      (row) => `
      <div class="world-card-item">
        <div class="world-card-name">${esc(row.name || row.code || "—")}</div>
        <div class="world-card-row">
          <strong class="world-card-px">${fmtNum(row.price)}</strong>
          <em data-tone="${tone(row.change_pct)}">${fmtPct(row.change_pct)}</em>
        </div>
      </div>`,
    )
    .join("");
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
  const indices = marker.data.indices || [];
  const multi = indices.length > 1;
  return `
    <div class="world-card${multi ? " world-card--stack" : ""}">
      <div class="world-card-kicker">
        <span>${esc(marker.title)}</span>
        <span class="muted">${esc(marker.city || "")}</span>
      </div>
      ${
        multi
          ? `<div class="world-card-list">${markerIndexRowsHtml(indices)}</div>`
          : `
      <div class="world-card-name">${esc(indices[0]?.name || "主要指数")}</div>
      <div class="world-card-row">
        <strong class="world-card-px">${fmtNum(indices[0]?.price)}</strong>
        <em data-tone="${tone(indices[0]?.change_pct)}">${fmtPct(indices[0]?.change_pct)}</em>
      </div>`
      }
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
  // 等卡片量完高度后再避让，避免中国四指数等高卡片被低估
  window.requestAnimationFrame(() => {
    layoutMarkerLabels();
    scheduleMarkerLayoutBurst();
  });
}

function klineBlock(code) {
  return `<article class="chart-card chart-card--kline" data-kline-code="${esc(code)}">
    <header class="chart-card__head">
      <div class="chart-card__head-main">
        <div class="chart-card__title">
          <span class="chart-card__mark" aria-hidden="true"></span>
          <h3>走势</h3>
        </div>
        <div class="chart-kline-hover chart-hover-card hidden" aria-hidden="true"></div>
      </div>
      <p class="chart-card__meta muted">日K</p>
      <div class="chart-card__controls">
        <div class="chart-select-group">
          <label class="chart-select-wrap" aria-label="周期">
            <select class="chart-select" disabled>
              <option selected>日K</option>
            </select>
          </label>
        </div>
      </div>
    </header>
    <div class="chart-card__stage">
      <div class="chart-canvas-wrap">
        <canvas width="720" height="360" aria-label="指数日K走势图"></canvas>
        <p class="muted chart-empty hidden">暂无走势数据</p>
      </div>
    </div>
    <footer class="chart-card__foot">
      <div class="chart-axis-scroll is-disabled">
        <input class="chart-scroll-bar" type="range" min="0" max="0" value="0" step="1" aria-label="时间轴滑动" disabled />
      </div>
    </footer>
  </article>`;
}

function indexCardHtml(row) {
  const code = row.code || "";
  const active = code === state.chartCode;
  const chgTone = tone(row.change_pct);
  return `<article class="screen-card world-index-card${active ? " is-active" : ""}" data-code="${esc(code)}" data-region="${esc(row.region || "")}" role="option" aria-selected="${active ? "true" : "false"}" tabindex="0">
    <button type="button" class="screen-card-head" data-index-code="${esc(code)}" title="定位到地图">
      <div class="screen-card-name">
        <strong>${esc(row.name || code)}</strong>
        <span>${esc(code)}</span>
        <em>${esc(row.region_name || row.region || "")}</em>
      </div>
      <div class="screen-card-score">
        <b data-tone="${chgTone}">${fmtPct(row.change_pct)}</b>
        <span>${fmtNum(row.price)}</span>
      </div>
    </button>
    ${klineBlock(code)}
    <footer class="screen-card-meta">
      <span>开 <b>${fmtNum(row.open)}</b></span>
      <span>高 <b>${fmtNum(row.high)}</b></span>
      <span>低 <b>${fmtNum(row.low)}</b></span>
    </footer>
  </article>`;
}

function mountIndexKline(card) {
  const klineEl = card.querySelector(".chart-card--kline");
  const code = klineEl?.dataset.klineCode;
  if (!klineEl || !code || !window.OrbitKline) return;
  const points = historyPoints(code);
  window.OrbitKline.mount(klineEl, {
    items: points,
    meta: klineMetaText(points, state.historySource?.[code]),
  });
}

function patchIndexCard(el, row, { remountKline = true } = {}) {
  const name = el.querySelector(".screen-card-name strong");
  if (name) name.textContent = row.name || row.code || "—";
  const codeEl = el.querySelector(".screen-card-name span");
  if (codeEl) codeEl.textContent = row.code || "";
  const region = el.querySelector(".screen-card-name em");
  if (region) region.textContent = row.region_name || row.region || "";
  const score = el.querySelector(".screen-card-score b");
  if (score) {
    score.textContent = fmtPct(row.change_pct);
    score.dataset.tone = tone(row.change_pct);
  }
  const price = el.querySelector(".screen-card-score span");
  if (price) price.textContent = fmtNum(row.price);
  const metas = el.querySelectorAll(".screen-card-meta span b");
  if (metas[0]) metas[0].textContent = fmtNum(row.open);
  if (metas[1]) metas[1].textContent = fmtNum(row.high);
  if (metas[2]) metas[2].textContent = fmtNum(row.low);
  const active = row.code === state.chartCode;
  el.classList.toggle("is-active", active);
  el.setAttribute("aria-selected", active ? "true" : "false");
  if (remountKline) mountIndexKline(el);
}

function bindIndexCard(el) {
  const activate = () => {
    const code = el.dataset.code;
    if (code) selectIndex(code, { focusMap: true });
  };
  el.querySelector(".screen-card-head")?.addEventListener("click", activate);
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      activate();
    }
  });
}

function listCodesSignature(items) {
  return items.map((row) => row.code).join("|");
}

function syncIndexCardActive() {
  const list = $("worldIndexList");
  if (!list) return;
  list.querySelectorAll(".world-index-card").forEach((el) => {
    const active = el.dataset.code === state.chartCode;
    el.classList.toggle("is-active", active);
    el.setAttribute("aria-selected", active ? "true" : "false");
  });
  list.querySelector(".world-index-card.is-active")?.scrollIntoView({ block: "nearest" });
}

function renderIndexList({ force = false } = {}) {
  const list = $("worldIndexList");
  if (!list) return;
  const items = indexItems();
  if (!items.length) {
    list.innerHTML = `<p class="world-index-empty muted">暂无指数数据</p>`;
    list.dataset.codes = "";
    return;
  }

  const signature = listCodesSignature(items);
  const existing = [...list.querySelectorAll(".world-index-card")];
  const canPatch =
    !force &&
    list.dataset.codes === signature &&
    existing.length === items.length &&
    existing.every((el, i) => el.dataset.code === items[i].code);

  if (canPatch) {
    existing.forEach((el, i) => patchIndexCard(el, items[i]));
  } else {
    let lastRegion = "";
    list.innerHTML = items
      .map((row) => {
        const regionHead =
          row.region !== lastRegion
            ? `<div class="world-index-region" role="presentation">${esc(row.region_name || row.region)}</div>`
            : "";
        lastRegion = row.region;
        return `${regionHead}${indexCardHtml(row)}`;
      })
      .join("");
    list.dataset.codes = signature;
    list.querySelectorAll(".world-index-card").forEach((el) => {
      bindIndexCard(el);
      mountIndexKline(el);
    });
  }

  syncIndexCardActive();
}

function oilCity(id) {
  return OIL_COORDS[id]?.city || "";
}

function oilCardHtml(row) {
  const id = row.id || "";
  const active = id === state.oilCode;
  const chgTone = tone(row.change_pct);
  const city = oilCity(id);
  const ohlc = oilOhlc(row);
  return `<article class="screen-card world-index-card world-oil-card${active ? " is-active" : ""}" data-oil-id="${esc(id)}" role="option" aria-selected="${active ? "true" : "false"}" tabindex="0">
    <button type="button" class="screen-card-head" data-oil-id="${esc(id)}" title="定位到地图">
      <div class="screen-card-name">
        <strong>${esc(row.name || id)}</strong>
        <span>${esc(id.toUpperCase())}</span>
        <em>${esc(city)}</em>
      </div>
      <div class="screen-card-score">
        <b data-tone="${chgTone}">${fmtPct(row.change_pct)}</b>
        <span>${fmtNum(row.price)}</span>
      </div>
    </button>
    ${klineBlock(`oil:${id}`)}
    <footer class="screen-card-meta">
      <span>开 <b>${fmtNum(ohlc.open)}</b></span>
      <span>高 <b>${fmtNum(ohlc.high)}</b></span>
      <span>低 <b>${fmtNum(ohlc.low)}</b></span>
    </footer>
  </article>`;
}

function mountOilKline(card) {
  const klineEl = card.querySelector(".chart-card--kline");
  const raw = klineEl?.dataset.klineCode || "";
  const id = raw.startsWith("oil:") ? raw.slice(4) : card.dataset.oilId;
  if (!klineEl || !id || !window.OrbitKline) return;
  const points = oilHistoryPoints(id);
  window.OrbitKline.mount(klineEl, {
    items: points,
    meta: klineMetaText(points, state.oilHistorySource?.[id]),
  });
}

function patchOilCard(el, row) {
  const name = el.querySelector(".screen-card-name strong");
  if (name) name.textContent = row.name || row.id || "—";
  const codeEl = el.querySelector(".screen-card-name span");
  if (codeEl) codeEl.textContent = (row.id || "").toUpperCase();
  const region = el.querySelector(".screen-card-name em");
  if (region) region.textContent = oilCity(row.id);
  const score = el.querySelector(".screen-card-score b");
  if (score) {
    score.textContent = fmtPct(row.change_pct);
    score.dataset.tone = tone(row.change_pct);
  }
  const price = el.querySelector(".screen-card-score span");
  if (price) price.textContent = fmtNum(row.price);
  const ohlc = oilOhlc(row);
  const metas = el.querySelectorAll(".screen-card-meta span b");
  if (metas[0]) metas[0].textContent = fmtNum(ohlc.open);
  if (metas[1]) metas[1].textContent = fmtNum(ohlc.high);
  if (metas[2]) metas[2].textContent = fmtNum(ohlc.low);
  const active = row.id === state.oilCode;
  el.classList.toggle("is-active", active);
  el.setAttribute("aria-selected", active ? "true" : "false");
  mountOilKline(el);
}

function bindOilCard(el) {
  const activate = () => {
    const id = el.dataset.oilId;
    if (id) selectOil(id, { focusMap: true });
  };
  el.querySelector(".screen-card-head")?.addEventListener("click", activate);
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      activate();
    }
  });
}

function listOilSignature(items) {
  return items.map((row) => row.id).join("|");
}

function syncOilCardActive() {
  const list = $("worldOilList");
  if (!list) return;
  list.querySelectorAll(".world-oil-card").forEach((el) => {
    const active = el.dataset.oilId === state.oilCode;
    el.classList.toggle("is-active", active);
    el.setAttribute("aria-selected", active ? "true" : "false");
  });
  list.querySelector(".world-oil-card.is-active")?.scrollIntoView({ block: "nearest" });
}

function renderOilList({ force = false } = {}) {
  const list = $("worldOilList");
  if (!list) return;
  const items = oilItems();
  if (!items.length) {
    list.innerHTML = `<p class="world-index-empty muted">暂无原油数据</p>`;
    list.dataset.codes = "";
    return;
  }

  const signature = listOilSignature(items);
  const existing = [...list.querySelectorAll(".world-oil-card")];
  const canPatch =
    !force &&
    list.dataset.codes === signature &&
    existing.length === items.length &&
    existing.every((el, i) => el.dataset.oilId === items[i].id);

  if (canPatch) {
    existing.forEach((el, i) => patchOilCard(el, items[i]));
  } else {
    list.innerHTML = items.map((row) => oilCardHtml(row)).join("");
    list.dataset.codes = signature;
    list.querySelectorAll(".world-oil-card").forEach((el) => {
      bindOilCard(el);
      mountOilKline(el);
    });
  }

  syncOilCardActive();
}

function selectOil(id, { focusMap = false } = {}) {
  const row = findOil(id);
  if (!row) return;
  state.oilCode = row.id;
  state.selectedId = `oil:${row.id}`;
  const list = $("worldOilList");
  if (list?.querySelector(".world-oil-card")) {
    syncOilCardActive();
  } else {
    renderOilList();
  }
  highlightMarkers();
  closeChartPop();

  if (!focusMap || !mapRuntime.map) return;
  const marker = state.markerDefs.find((m) => m.id === state.selectedId);
  if (!marker) return;
  mapRuntime.map.panTo(toAmapPos(marker.lat, marker.lng));
  if (mapRuntime.map.getZoom() < 3) mapRuntime.map.setZoom(3);
}

function ensureOilSelection() {
  if (state.oilCode && findOil(state.oilCode)) {
    renderOilList();
    return;
  }
  const first = oilItems()[0];
  if (first) {
    state.oilCode = first.id;
    renderOilList();
  } else {
    state.oilCode = null;
    renderOilList();
  }
}

function highlightMarkers() {
  document.querySelectorAll(".world-map-marker-label").forEach((el) => {
    el.classList.toggle("is-active", Boolean(state.selectedId) && el.dataset.markerId === state.selectedId);
  });
  state.markers2d.forEach((rec) => {
    try {
      rec.overlay?.setzIndex(rec.id === state.selectedId ? 220 : 120);
    } catch {
      /* ignore */
    }
  });
}

function selectIndex(code, { focusMap = false } = {}) {
  const row = findIndex(code);
  if (!row) return;
  state.chartCode = row.code;
  state.selectedId = `region:${row.region}`;
  const list = $("worldIndexList");
  if (list?.querySelector(".world-index-card")) {
    syncIndexCardActive();
  } else {
    renderIndexList();
  }
  highlightMarkers();
  closeChartPop();

  if (!focusMap || !mapRuntime.map) return;
  const marker = state.markerDefs.find((m) => m.id === state.selectedId);
  if (!marker) return;
  mapRuntime.map.panTo(toAmapPos(marker.lat, marker.lng));
  if (mapRuntime.map.getZoom() < 3) mapRuntime.map.setZoom(3);
}

function ensureIndexSelection() {
  if (state.chartCode && findIndex(state.chartCode)) {
    state.selectedId = `region:${findIndex(state.chartCode).region}`;
    renderIndexList();
    highlightMarkers();
    return;
  }
  const first = indexItems()[0];
  if (first) {
    state.chartCode = first.code;
    state.selectedId = `region:${first.region}`;
    renderIndexList();
    highlightMarkers();
  } else {
    state.chartCode = null;
    state.selectedId = null;
    renderIndexList();
  }
}

function rebuildMarkers() {
  buildMarkerDefs();
  syncMarkers2d();
  ensureIndexSelection();
  ensureOilSelection();
  highlightMarkers();
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

function isChinaMarket(marker) {
  return marker?.id === "region:cn" || marker?.data?.region === "cn";
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
    const ohlc = oilOhlc(o);
    const points = oilHistoryPoints(o.id);
    const src = state.oilHistorySource?.[o.id] || "";
    pop.hidden = false;
    pop.innerHTML = `
      <header class="world-pop-head">
        <div>
          <p class="world-pop-kicker">原油 · ${esc(marker.city || "")}${src ? ` · ${esc(src)}` : ""}</p>
          <h2>${esc(o.name || marker.title)}</h2>
        </div>
        <button type="button" class="world-pop-close" data-close aria-label="关闭">×</button>
      </header>
      <div class="world-pop-hero">
        <strong>${fmtNum(o.price)}</strong>
        <em data-tone="${tone(o.change_pct)}">${fmtPct(o.change_pct)}</em>
      </div>
      <div class="world-pop-chart">${sparkSvg(points, 320, 110, { fill: true })}</div>
      <p class="muted world-pop-meta">开 ${fmtNum(ohlc.open)} · 高 ${fmtNum(ohlc.high)} · 低 ${fmtNum(ohlc.low)}</p>
    `;
    pop.querySelector("[data-close]")?.addEventListener("click", () => selectMarker(null, false));
    return;
  }

  const indices = marker.data.indices || [];
  const active = indices.find((row) => row.code === state.chartCode) || indices[0];
  if (active) state.chartCode = active.code;
  const points = historyForSpark(active?.code, active?.price);
  const first = points[0]?.date || points[0]?.time || "";
  const last = points[points.length - 1]?.date || points[points.length - 1]?.time || "";
  const src = state.historySource?.[active?.code] || "";
  const china = isChinaMarket(marker)
    ? `<a class="btn world-pop-enter" href="/cn">进入中国市场</a>`
    : "";

  pop.hidden = false;
  pop.innerHTML = `
    <header class="world-pop-head">
      <div>
        <p class="world-pop-kicker">${esc(marker.title)} · ${esc(marker.city || "")} · 日线${src ? ` · ${esc(src)}` : ""}</p>
        <h2>${esc(active?.name || marker.title)}</h2>
      </div>
      <button type="button" class="world-pop-close" data-close aria-label="关闭">×</button>
    </header>
    <div class="world-pop-hero">
      <strong>${fmtNum(active?.price)}</strong>
      <em data-tone="${tone(active?.change_pct)}">${fmtPct(active?.change_pct)}</em>
    </div>
    <div class="world-pop-chart">${sparkSvg(points, 320, 110, { fill: true })}</div>
    <p class="muted world-pop-meta">${esc(first)}${first && last ? " → " : ""}${esc(last)}${points.length ? ` · ${points.length} 根` : "暂无走势"}</p>
    ${indices.length > 1 ? `
      <div class="world-pop-switch" role="tablist">
        ${indices.map((row) => `
          <button type="button" class="world-pop-tab${row.code === active?.code ? " is-active" : ""}" data-code="${esc(row.code)}">
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
      syncIndexCardActive();
      renderChartPop(marker);
    });
  });
}

function selectMarker(id, focus = true) {
  if (!id) {
    state.selectedId = state.chartCode ? `region:${findIndex(state.chartCode)?.region || ""}` : null;
    if (!state.chartCode) state.selectedId = null;
    highlightMarkers();
    closeChartPop();
    return;
  }

  const rec = findMarkerRec(id);
  const marker = rec?.marker;
  if (!marker) return;

  if (marker.category === "oil") {
    state.selectedId = id;
    state.oilCode = marker.data.oil?.id || id.replace(/^oil:/, "");
    syncOilCardActive();
    highlightMarkers();
    renderChartPop(marker);
    if (focus && mapRuntime.map) {
      mapRuntime.map.panTo(toAmapPos(marker.lat, marker.lng));
      if (mapRuntime.map.getZoom() < 3) mapRuntime.map.setZoom(3);
    }
    return;
  }

  const indices = marker.data.indices || [];
  const active =
    indices.find((row) => row.code === state.chartCode) || indices[0];
  if (!active) return;

  state.chartCode = active.code;
  state.selectedId = `region:${marker.data.region || active.region || ""}`;
  syncIndexCardActive();
  highlightMarkers();
  renderChartPop(marker);

  if (focus && mapRuntime.map) {
    mapRuntime.map.panTo(toAmapPos(marker.lat, marker.lng));
    if (mapRuntime.map.getZoom() < 3) mapRuntime.map.setZoom(3);
  }
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
  setOilStatus("同步中…", "busy");
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

    const [history, oilHistory] = await Promise.all([
      fetchOptional(
        apiUrl("/api/global/indices/history", { ...refresh, limit: HISTORY_LIMIT }),
        60_000,
        httpOpts,
      ),
      fetchOptional(
        apiUrl("/api/global/oil/history", { ...refresh, limit: HISTORY_LIMIT }),
        60_000,
        httpOpts,
      ),
    ]);
    state.history = history?.by_code || {};
    state.historySource = history?.source_label_by_code || {};
    state.oilHistory = oilHistory?.by_id || {};
    state.oilHistorySource = oilHistory?.source_label_by_id || {};
    rebuildMarkers();
    setStatus("live", "live");
    setOilStatus("live", "live");
  } catch (err) {
    const msg = err.name === "AbortError" ? "请求超时，请稍后重试" : (err.message || "加载失败");
    setStatus(msg, "error");
    setOilStatus(msg, "error");
    if (state.overview) rebuildMarkers();
  }
}

const SIDE_FOLD_KEY = "orbit-world-side-collapsed";

function readSideFold() {
  try {
    const raw = JSON.parse(localStorage.getItem(SIDE_FOLD_KEY) || "{}");
    return {
      indices: Boolean(raw.indices),
      oil: Boolean(raw.oil),
    };
  } catch {
    return { indices: false, oil: false };
  }
}

function writeSideFold(next) {
  try {
    localStorage.setItem(SIDE_FOLD_KEY, JSON.stringify(next));
  } catch {
    /* ignore */
  }
}

function sideToggleGlyph(side, collapsed) {
  if (side === "oil") return collapsed ? "◂" : "▸";
  return collapsed ? "▸" : "◂";
}

function applySideFold(side, collapsed, { persist = true } = {}) {
  const panel = document.querySelector(`.world-side[data-side="${side}"]`);
  if (!panel) return;
  panel.classList.toggle("is-collapsed", collapsed);
  const toggle = panel.querySelector(`.world-side-toggle[data-side="${side}"]`);
  const rail = panel.querySelector(`.world-side-rail[data-side="${side}"]`);
  if (toggle) {
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    toggle.title = collapsed ? "展开" : "收起";
    toggle.textContent = sideToggleGlyph(side, collapsed);
  }
  if (rail) rail.hidden = !collapsed;
  if (persist) {
    const cur = readSideFold();
    cur[side] = collapsed;
    writeSideFold(cur);
  }
  window.requestAnimationFrame(() => resizeMap());
}

function toggleSideFold(side) {
  const panel = document.querySelector(`.world-side[data-side="${side}"]`);
  if (!panel) return;
  applySideFold(side, !panel.classList.contains("is-collapsed"));
}

function bindSideFold() {
  const saved = readSideFold();
  applySideFold("indices", saved.indices, { persist: false });
  applySideFold("oil", saved.oil, { persist: false });
  document.querySelectorAll(".world-side-toggle[data-side]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleSideFold(btn.dataset.side);
    });
  });
  document.querySelectorAll(".world-side-rail[data-side]").forEach((btn) => {
    btn.addEventListener("click", () => applySideFold(btn.dataset.side, false));
  });
}

function bindUi() {
  bindSideFold();
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
