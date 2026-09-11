import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { toAmapLngLat } from "/js/industry/map/coords.js";

const POLL_MS = 60_000;
const GLOBE_RADIUS = 1.6;

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
  viewMode: "globe",
  overview: null,
  layers: { indices: true, rates: true, bonds: true, oil: true },
  markerDefs: [],
  markers3d: [],
  markers2d: [],
  selectedId: null,
  pollTimer: 0,
};

let scene;
let camera;
let renderer;
let labelRenderer;
let controls;
let globe;
let markerGroup;
let raycaster;
let pointer;
let resizeObserver;
let globeActive = true;

const MAP_HUD_PADDING = [48, 380, 48, 48];

const map2d = {
  map: null,
  overlays: [],
  ready: false,
  loading: null,
  loadingSdk: null,
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

function latLngToVec3(lat, lng, radius) {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lng + 180) * (Math.PI / 180);
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

function setStatus(text, kind = "") {
  const el = $("worldStatus");
  el.textContent = text;
  el.dataset.state = kind;
}

function emptyDetailText() {
  return state.viewMode === "map"
    ? "点击地图标注查看详情，或拖动平移缩放地图。"
    : "点击地球上的标注查看详情，或拖动旋转地球。";
}

function initGlobe() {
  const stage = $("globeStage");
  const w = stage.clientWidth;
  const h = stage.clientHeight;

  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(42, w / h, 0.1, 100);
  camera.position.set(0, 0.4, 4.8);

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(w, h);
  renderer.setClearColor(0x000000, 0);
  stage.appendChild(renderer.domElement);

  labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(w, h);
  labelRenderer.domElement.className = "world-label-layer";
  stage.appendChild(labelRenderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.minDistance = 2.4;
  controls.maxDistance = 8;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.35;

  const ambient = new THREE.AmbientLight(0xffffff, 0.55);
  scene.add(ambient);
  const sun = new THREE.DirectionalLight(0xffffff, 1.1);
  sun.position.set(5, 2, 4);
  scene.add(sun);

  const loader = new THREE.TextureLoader();
  const earthTex = loader.load(
    "https://unpkg.com/three-globe@2.31.1/example/img/earth-blue-marble.jpg",
  );
  const bumpTex = loader.load(
    "https://unpkg.com/three-globe@2.31.1/example/img/earth-topology.png",
  );

  const geometry = new THREE.SphereGeometry(GLOBE_RADIUS, 64, 64);
  const material = new THREE.MeshPhongMaterial({
    map: earthTex,
    bumpMap: bumpTex,
    bumpScale: 0.025,
    specular: new THREE.Color(0x333333),
    shininess: 8,
  });
  globe = new THREE.Mesh(geometry, material);
  scene.add(globe);

  const atmosGeo = new THREE.SphereGeometry(GLOBE_RADIUS * 1.015, 64, 64);
  const atmosMat = new THREE.MeshBasicMaterial({
    color: 0x2ad4b8,
    transparent: true,
    opacity: 0.08,
    side: THREE.BackSide,
  });
  scene.add(new THREE.Mesh(atmosGeo, atmosMat));

  const starsGeo = new THREE.BufferGeometry();
  const starCount = 1200;
  const positions = new Float32Array(starCount * 3);
  for (let i = 0; i < starCount; i += 1) {
    const r = 18 + Math.random() * 12;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = r * Math.cos(phi);
  }
  starsGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const stars = new THREE.Points(
    starsGeo,
    new THREE.PointsMaterial({ color: 0x8899aa, size: 0.04, transparent: true, opacity: 0.7 }),
  );
  scene.add(stars);

  markerGroup = new THREE.Group();
  scene.add(markerGroup);

  raycaster = new THREE.Raycaster();
  pointer = new THREE.Vector2();

  renderer.domElement.addEventListener("pointerdown", onGlobePointerDown);
  resizeObserver = new ResizeObserver(resizeGlobe);
  resizeObserver.observe(stage);

  animateGlobe();
}

function loadAmapScript(key, securityJsCode) {
  if (window.AMap) return Promise.resolve(window.AMap);
  if (map2d.loadingSdk) return map2d.loadingSdk;
  map2d.loadingSdk = new Promise((resolve, reject) => {
    if (securityJsCode) {
      window._AMapSecurityConfig = { securityJsCode };
    }
    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`;
    script.async = true;
    script.onload = () => {
      if (!window.AMap) reject(new Error("高德地图 SDK 未就绪"));
      else resolve(window.AMap);
    };
    script.onerror = () => reject(new Error("高德地图脚本加载失败"));
    document.head.appendChild(script);
  }).finally(() => {
    map2d.loadingSdk = null;
  });
  return map2d.loadingSdk;
}

function fitMapMarkers(maxZoom = 8) {
  if (!map2d.map || !map2d.overlays.length) return;
  try {
    map2d.map.setFitView(map2d.overlays, false, MAP_HUD_PADDING, maxZoom);
  } catch {
    /* ignore */
  }
}

async function ensureMap2d() {
  if (map2d.ready) return;
  if (map2d.loading) return map2d.loading;

  map2d.loading = (async () => {
    const resp = await fetch("/api/map/config");
    const json = await resp.json();
    if (!json.ok) throw new Error(json.error || "地图配置加载失败");
    const key = json.data?.key || "";
    const securityJsCode = json.data?.securityJsCode || "";
    if (!key) {
      throw new Error("未配置高德地图 Key：请在项目根目录 .env 设置 AMAP_JS_KEY");
    }

    await loadAmapScript(key, securityJsCode);

    const stage = $("mapStage");
    map2d.map = new AMap.Map(stage, {
      zoom: 2,
      center: [20, 25],
      viewMode: "2D",
      mapStyle: "amap://styles/normal",
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
    map2d.overlays = [];
    map2d.ready = true;
    requestAnimationFrame(() => {
      try {
        map2d.map?.resize();
      } catch {
        /* ignore */
      }
    });
  })();

  try {
    await map2d.loading;
  } finally {
    map2d.loading = null;
  }
}

function resizeGlobe() {
  if (state.viewMode !== "globe") return;
  const stage = $("globeStage");
  const w = stage.clientWidth;
  const h = stage.clientHeight;
  if (!w || !h) return;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
  labelRenderer.setSize(w, h);
}

function resizeMap() {
  if (!map2d.ready || state.viewMode !== "map") return;
  try {
    map2d.map.resize();
  } catch {
    /* ignore */
  }
  requestAnimationFrame(() => {
    try {
      map2d.map?.resize();
    } catch {
      /* ignore */
    }
  });
}

function onGlobePointerDown(event) {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(markerGroup.children, true);
  if (!hits.length) return;
  let obj = hits[0].object;
  while (obj && !obj.userData?.markerId) obj = obj.parent;
  if (obj?.userData?.markerId) selectMarker(obj.userData.markerId);
}

function animateGlobe() {
  requestAnimationFrame(animateGlobe);
  if (!globeActive || state.viewMode !== "globe") return;
  controls.update();
  renderer.render(scene, camera);
  labelRenderer.render(scene, camera);
}

function clearMarkers3d() {
  while (markerGroup.children.length) {
    const child = markerGroup.children[0];
    markerGroup.remove(child);
    child.traverse((node) => {
      if (node.element?.parentNode) node.element.parentNode.removeChild(node.element);
    });
  }
  state.markers3d = [];
}

function clearMarkers2d() {
  if (map2d.map && map2d.overlays.length) {
    try {
      map2d.map.remove(map2d.overlays);
    } catch {
      /* ignore */
    }
  }
  map2d.overlays = [];
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
  return `
    <div class="world-marker-title">${esc(marker.title)}</div>
    <div class="world-marker-city muted">${esc(marker.city || "")}</div>
    <div class="world-marker-lines">${buildSummaryLines(marker).join("")}</div>
  `;
}

function createMarker3d(marker) {
  const pos = latLngToVec3(marker.lat, marker.lng, GLOBE_RADIUS * 1.002);
  const normal = pos.clone().normalize();

  const pinGeo = new THREE.SphereGeometry(0.028, 12, 12);
  const pinMat = new THREE.MeshBasicMaterial({
    color: new THREE.Color(marker.color || CAT_COLORS[marker.category] || "#2ad4b8"),
  });
  const pin = new THREE.Mesh(pinGeo, pinMat);
  pin.position.copy(pos);
  pin.userData.markerId = marker.id;

  const ringGeo = new THREE.RingGeometry(0.04, 0.055, 24);
  const ringMat = new THREE.MeshBasicMaterial({
    color: pinMat.color,
    transparent: true,
    opacity: 0.55,
    side: THREE.DoubleSide,
  });
  const ring = new THREE.Mesh(ringGeo, ringMat);
  ring.position.copy(pos.clone().add(normal.clone().multiplyScalar(0.01)));
  ring.lookAt(pos.clone().add(normal));
  ring.userData.markerId = marker.id;

  const labelEl = document.createElement("div");
  labelEl.className = "world-marker-label";
  labelEl.dataset.markerId = marker.id;
  labelEl.innerHTML = markerLabelHtml(marker);
  labelEl.addEventListener("pointerdown", (e) => {
    e.stopPropagation();
    selectMarker(marker.id);
  });

  const label = new CSS2DObject(labelEl);
  label.position.copy(pos.clone().add(normal.clone().multiplyScalar(0.12)));
  label.userData.markerId = marker.id;

  const group = new THREE.Group();
  group.add(pin, ring, label);
  group.userData.markerId = marker.id;
  group.userData.marker = marker;
  markerGroup.add(group);
  state.markers3d.push({ id: marker.id, group, labelEl, marker });
}

function createMarker2d(marker) {
  if (!map2d.map || !window.AMap) return;
  const pos = toAmapLngLat(marker.lat, marker.lng);
  if (!pos) return;

  const labelEl = document.createElement("div");
  labelEl.className = "world-marker-label world-map-marker-label";
  labelEl.dataset.markerId = marker.id;
  labelEl.innerHTML = markerLabelHtml(marker);
  labelEl.addEventListener("click", (e) => {
    e.stopPropagation();
    selectMarker(marker.id);
  });

  const amapMarker = new AMap.Marker({
    position: pos,
    content: labelEl,
    offset: new AMap.Pixel(-95, -68),
    zIndex: 120,
  });
  amapMarker.on("click", () => selectMarker(marker.id));
  map2d.map.add(amapMarker);
  map2d.overlays.push(amapMarker);
  state.markers2d.push({ id: marker.id, amapMarker, labelEl, marker });
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

function syncMarkers3d() {
  clearMarkers3d();
  for (const marker of state.markerDefs) createMarker3d(marker);
}

function syncMarkers2d() {
  if (!map2d.ready) return;
  clearMarkers2d();
  for (const marker of state.markerDefs) createMarker2d(marker);
}

function rebuildMarkers() {
  buildMarkerDefs();
  syncMarkers3d();
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

  panel.innerHTML = `
    <header class="world-detail-head">
      <h2>${esc(marker.title)}</h2>
      <span class="muted">${esc(marker.city || "")}</span>
    </header>
    ${blocks.join("")}
  `;
}

function findMarkerRec(id) {
  const def = state.markerDefs.find((m) => m.id === id);
  if (!def) return null;
  const rec3d = state.markers3d.find((m) => m.id === id);
  if (rec3d) return rec3d;
  const rec2d = state.markers2d.find((m) => m.id === id);
  if (rec2d) return { id, marker: rec2d.marker };
  return { id, marker: def };
}

function selectMarker(id, focus = true) {
  state.selectedId = id;

  state.markers3d.forEach((rec) => {
    const active = rec.id === id;
    rec.labelEl.classList.toggle("is-active", active);
    const pin = rec.group.children.find((c) => c.geometry?.type === "SphereGeometry");
    if (pin) pin.scale.setScalar(active ? 1.5 : 1);
  });

  document.querySelectorAll(".world-map-marker-label").forEach((el) => {
    el.classList.toggle("is-active", el.dataset.markerId === id);
  });

  const rec = findMarkerRec(id);
  renderDetail(rec);

  if (!focus || !rec) return;

  if (state.viewMode === "globe" && rec.group) {
    controls.autoRotate = false;
    const target = rec.group.position.clone().normalize().multiplyScalar(3.2);
    camera.position.lerp(target, 0.35);
    controls.target.set(0, 0, 0);
  }

  if (state.viewMode === "map" && rec.marker && map2d.map) {
    const pos = toAmapLngLat(rec.marker.lat, rec.marker.lng);
    if (pos) {
      map2d.map.setZoomAndCenter(Math.max(map2d.map.getZoom(), 4), pos);
    }
  }
}

async function setViewMode(mode) {
  if (mode === state.viewMode) return;

  if (mode === "map") {
    try {
      await ensureMap2d();
    } catch (err) {
      setStatus(err.message || "二维地图加载失败", "error");
      return;
    }
  }

  state.viewMode = mode;

  const globeStage = $("globeStage");
  const mapStage = $("mapStage");
  const isGlobe = mode === "globe";

  globeStage.hidden = !isGlobe;
  mapStage.hidden = isGlobe;
  globeActive = isGlobe;
  document.body.classList.toggle("world-view-map", !isGlobe);

  document.querySelectorAll(".world-view-btn").forEach((btn) => {
    const active = btn.dataset.view === mode;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-pressed", active ? "true" : "false");
  });

  if (!isGlobe) {
    syncMarkers2d();
    requestAnimationFrame(() => {
      resizeMap();
      if (map2d.ready && state.markerDefs.length) fitMapMarkers();
    });
  } else {
    resizeGlobe();
  }

  if (!state.selectedId) {
    renderDetail(null);
  } else {
    selectMarker(state.selectedId, false);
  }
}

async function fetchJson(url, timeoutMs = 90_000) {
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

async function loadOverview(force = false) {
  setStatus("同步中…", "busy");
  const refresh = force ? { refresh: "1" } : {};
  try {
    const [indices, oil] = await Promise.all([
      fetchJson(apiUrl("/api/global/indices", refresh), 30_000),
      fetchJson(apiUrl("/api/global/oil", refresh), 30_000),
    ]);
    state.overview = { indices, oil, rates: { items: [] }, bonds: { items: [] } };
    rebuildMarkers();
    setStatus("指数/原油已更新，利率国债加载中…", "busy");

    const [rates, bonds] = await Promise.all([
      fetchJson(apiUrl("/api/global/rates", { ...refresh, limit: 24 }), 60_000),
      fetchJson(apiUrl("/api/global/bonds", { ...refresh, limit: 60 }), 60_000),
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
  $("refreshBtn").addEventListener("click", () => loadOverview(true));

  document.querySelectorAll(".world-view-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      setViewMode(btn.dataset.view).catch((err) => {
        setStatus(err.message || "切换视图失败", "error");
      });
    });
  });

  document.querySelectorAll(".world-layer-chip input").forEach((input) => {
    input.addEventListener("change", () => {
      const layer = input.closest(".world-layer-chip")?.dataset.layer;
      if (!layer) return;
      state.layers[layer] = input.checked;
      rebuildMarkers();
    });
  });

  window.addEventListener("resize", () => {
    resizeGlobe();
    resizeMap();
  });

  state.pollTimer = window.setInterval(() => loadOverview(false), POLL_MS);
}

try {
  initGlobe();
  bindUi();
  loadOverview(false);
} catch (err) {
  setStatus(err.message || "页面初始化失败", "error");
  console.error(err);
}
