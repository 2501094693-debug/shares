const $ = (id) => document.getElementById(id);

const MAP_TYPES = {
  roadmap: "roadmap",
  satellite: "satellite",
  hybrid: "hybrid",
  terrain: "terrain",
};

const DARK_STYLES = [
  { elementType: "geometry", stylers: [{ color: "#0b121e" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#0b121e" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#8494a8" }] },
  {
    featureType: "administrative.country",
    elementType: "geometry.stroke",
    stylers: [{ color: "#2ad4b8" }, { weight: 0.5 }],
  },
  {
    featureType: "administrative.locality",
    elementType: "labels.text.fill",
    stylers: [{ color: "#e8eef7" }],
  },
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  {
    featureType: "poi.park",
    elementType: "geometry",
    stylers: [{ color: "#0d1a16" }],
  },
  {
    featureType: "road",
    elementType: "geometry",
    stylers: [{ color: "#1a2433" }],
  },
  {
    featureType: "road",
    elementType: "geometry.stroke",
    stylers: [{ color: "#0b121e" }],
  },
  {
    featureType: "road.highway",
    elementType: "geometry",
    stylers: [{ color: "#243044" }],
  },
  {
    featureType: "road.highway",
    elementType: "labels.text.fill",
    stylers: [{ color: "#f0b429" }],
  },
  { featureType: "transit", stylers: [{ visibility: "off" }] },
  {
    featureType: "water",
    elementType: "geometry",
    stylers: [{ color: "#070b12" }],
  },
  {
    featureType: "water",
    elementType: "labels.text.fill",
    stylers: [{ color: "#2ad4b8" }],
  },
];

const state = {
  map: null,
  marker: null,
  info: null,
  geocoder: null,
  mapType: "roadmap",
  sv: null,
  pano: null,
  place: null,
  streetOpen: false,
  streetHint: "",
  aerialOpen: false,
  aerialMode: "",
  map3d: null,
  Map3DElement: null,
  aerialHeading: 0,
  aerialTilt: 55,
  aerialRange: 900,
  prevMapType: "roadmap",
};

function esc(text) {
  const el = document.createElement("span");
  el.textContent = text ?? "";
  return el.innerHTML;
}

function setStatus(text, tone = "") {
  const el = $("gmapStatus");
  if (!el) return;
  el.textContent = text;
  el.dataset.state = tone;
}

function fmtCoord(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(6);
}

function parseLatLng(query) {
  const m = String(query || "")
    .trim()
    .match(/^(-?\d+(?:\.\d+)?)\s*[,，\s]\s*(-?\d+(?:\.\d+)?)$/);
  if (!m) return null;
  const lat = Number(m[1]);
  const lng = Number(m[2]);
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
  return { lat, lng };
}

function usesDarkStyle(type) {
  return type === "roadmap" || type === "terrain";
}

function loadGoogleMaps(key) {
  if (window.google?.maps) return Promise.resolve(window.google.maps);

  return new Promise((resolve, reject) => {
    const callbackName = "__orbitGmapReady";
    const timeout = window.setTimeout(() => {
      reject(new Error("Google Maps 加载超时，请检查网络是否可访问 Google"));
    }, 20000);

    window[callbackName] = () => {
      window.clearTimeout(timeout);
      delete window[callbackName];
      if (!window.google?.maps) {
        reject(new Error("Google Maps SDK 未就绪"));
        return;
      }
      resolve(window.google.maps);
    };

    window.gm_authFailure = () => {
      window.clearTimeout(timeout);
      reject(new Error("Google Maps API Key 无效，或未启用 Maps JavaScript API"));
    };

    const script = document.createElement("script");
    script.src =
      `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}` +
      `&libraries=places&language=zh-CN&v=weekly&callback=${callbackName}`;
    script.async = true;
    script.defer = true;
    script.onerror = () => {
      window.clearTimeout(timeout);
      reject(new Error("Google Maps 脚本加载失败（国内网络可能无法访问）"));
    };
    document.head.appendChild(script);
  });
}

function currentTarget() {
  if (state.place) return { lat: state.place.lat, lng: state.place.lng };
  const c = state.map?.getCenter?.();
  if (c) return { lat: c.lat(), lng: c.lng() };
  return { lat: 37.8199, lng: -122.4783 };
}

function rangeFromZoom(zoom) {
  const z = Number.isFinite(zoom) ? zoom : 16;
  return Math.round(380 * 2 ** Math.max(0, 18 - Math.min(z, 18)));
}

async function ensureMaps3d() {
  if (state.Map3DElement) return state.Map3DElement;
  if (!google.maps.importLibrary) return null;
  try {
    const lib = await google.maps.importLibrary("maps3d");
    state.Map3DElement = lib?.Map3DElement || null;
    return state.Map3DElement;
  } catch (err) {
    console.warn("三维俯瞰库不可用", err);
    return null;
  }
}

function setAerialChrome(open, mode = "") {
  state.aerialOpen = !!open;
  state.aerialMode = open ? mode : "";
  const stage = document.querySelector(".app-stage");
  stage?.classList.toggle("is-aerial-open", mode === "3d");
  stage?.classList.toggle("is-aerial-2d", mode === "2d");
  $("gmapAerialBtn")?.classList.toggle("is-active", state.aerialOpen);
  if (mode === "3d") {
    window.setTimeout(() => {
      try {
        google.maps.event.trigger(state.map, "resize");
      } catch {
        /* ignore */
      }
    }, 60);
  }
}

function applyAerialCamera() {
  if (state.aerialMode === "3d" && state.map3d) {
    state.map3d.heading = state.aerialHeading;
    state.map3d.tilt = state.aerialTilt;
    state.map3d.range = state.aerialRange;
    return;
  }
  if (state.aerialMode === "2d" && state.map) {
    try {
      state.map.setHeading(state.aerialHeading);
      state.map.setTilt(Math.min(45, state.aerialTilt));
    } catch {
      /* ignore */
    }
  }
}

function setAerialTarget(target) {
  const zoom = state.map?.getZoom?.() ?? 16;
  state.aerialRange = rangeFromZoom(Math.max(zoom, 16));
  if (state.aerialMode === "3d" && state.map3d) {
    state.map3d.center = { lat: target.lat, lng: target.lng, altitude: 0 };
    applyAerialCamera();
    const meta = $("gmapAerialMeta");
    if (meta) meta.textContent = "三维实景俯瞰 · 拖动旋转 / 滚轮拉近";
    return;
  }
  if (state.aerialMode === "2d" && state.map) {
    state.map.panTo(target);
    if (state.map.getZoom() < 18) state.map.setZoom(18);
    applyAerialCamera();
    const meta = $("gmapAerialMeta");
    if (meta) {
      meta.textContent =
        state.map.getTilt() >= 30
          ? "卫星 45° 俯瞰 · 可旋转"
          : "此地没有 45° 航拍，已切到卫星正射";
    }
  }
}

async function openAerial(place) {
  closeStreetView();
  const target = place || currentTarget();
  state.aerialHeading = 0;
  state.aerialTilt = 55;
  setStatus("打开俯瞰…", "busy");

  const Map3DElement = await ensureMaps3d();
  if (Map3DElement) {
    const host = $("aerialStage");
    if (!state.map3d) {
      state.map3d = new Map3DElement({
        center: { lat: target.lat, lng: target.lng, altitude: 0 },
        range: rangeFromZoom(Math.max(state.map?.getZoom?.() ?? 16, 16)),
        tilt: state.aerialTilt,
        heading: state.aerialHeading,
        mode: "HYBRID",
      });
      host?.replaceChildren(state.map3d);
    }
    setAerialChrome(true, "3d");
    setAerialTarget(target);
    if (place) showPlace(place);
    setStatus("俯瞰已打开", "live");
    return;
  }

  state.prevMapType = state.mapType || "roadmap";
  setAerialChrome(true, "2d");
  if (state.map) {
    state.map.setOptions({
      mapTypeId: "satellite",
      styles: [],
      rotateControl: true,
      tilt: 45,
      heading: 0,
    });
    state.aerialTilt = 45;
  }
  setAerialTarget(target);
  if (place) showPlace(place);
  setStatus("俯瞰已打开", "live");
}

function closeAerial() {
  const mode = state.aerialMode;
  setAerialChrome(false);
  if (mode === "3d") {
    try {
      state.map3d?.remove?.();
    } catch {
      /* ignore */
    }
    state.map3d = null;
    const host = $("aerialStage");
    if (host) host.innerHTML = "";
  }
  if (mode === "2d" && state.map) {
    try {
      state.map.setTilt(0);
      state.map.setHeading(0);
      state.map.setOptions({ rotateControl: false });
    } catch {
      /* ignore */
    }
    setMapType(state.prevMapType || "roadmap");
  }
  const meta = $("gmapAerialMeta");
  if (meta) meta.textContent = "卫星 45° / 三维实景";
}

function nudgeAerial(action) {
  if (!state.aerialOpen) return;
  if (action === "left") state.aerialHeading = (state.aerialHeading + 315) % 360;
  if (action === "right") state.aerialHeading = (state.aerialHeading + 45) % 360;
  if (action === "steep") {
    state.aerialTilt = Math.min(state.aerialMode === "3d" ? 80 : 45, state.aerialTilt + 10);
  }
  if (action === "flat") state.aerialTilt = Math.max(0, state.aerialTilt - 10);
  applyAerialCamera();
}

function headingBetween(from, to) {
  const φ1 = (from.lat * Math.PI) / 180;
  const φ2 = (to.lat * Math.PI) / 180;
  const Δλ = ((to.lng - from.lng) * Math.PI) / 180;
  const y = Math.sin(Δλ) * Math.cos(φ2);
  const x =
    Math.cos(φ1) * Math.sin(φ2) -
    Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
  return (Math.atan2(y, x) * 180) / Math.PI;
}

function setStreetOpen(open) {
  state.streetOpen = !!open;
  document.querySelector(".app-stage")?.classList.toggle("is-street-open", state.streetOpen);
  $("gmapStreetBtn")?.classList.toggle("is-active", state.streetOpen);
  if (state.streetOpen) {
    window.setTimeout(() => {
      try {
        google.maps.event.trigger(state.map, "resize");
        google.maps.event.trigger(state.pano, "resize");
      } catch {
        /* ignore */
      }
    }, 60);
  }
}

async function findPanorama(latLng) {
  if (!state.sv) return null;
  const attempts = [
    { location: latLng, radius: 80, source: google.maps.StreetViewSource.OUTDOOR },
    { location: latLng, radius: 250, source: google.maps.StreetViewSource.OUTDOOR },
    { location: latLng, radius: 400 },
  ];
  for (const req of attempts) {
    try {
      const { data } = await state.sv.getPanorama(req);
      if (data?.location) return data;
    } catch {
      /* try next radius */
    }
  }
  return null;
}

function applyPanorama(data, lookAt) {
  const loc = data.location;
  const pos = loc.latLng;
  const to = pos
    ? { lat: pos.lat(), lng: pos.lng() }
    : lookAt;
  let heading = 0;
  if (lookAt && to) heading = headingBetween(to, lookAt);
  state.pano.setPano(loc.pano);
  state.pano.setPov({ heading, pitch: 0 });
  state.pano.setVisible(true);
  const date = data.imageDate ? ` · ${data.imageDate}` : "";
  const meta = $("gmapStreetMeta");
  if (meta) meta.textContent = `${loc.description || "街景"}${date}`;
}

async function openStreetView(place = state.place) {
  if (!state.pano || !place) {
    setStatus("请先选中一个地点", "error");
    return;
  }
  closeAerial();
  setStatus("查找街景…", "busy");
  const data = await findPanorama({ lat: place.lat, lng: place.lng });
  if (!data) {
    state.streetHint = "附近没有街景（中国大陆覆盖很少，可试香港、东京、纽约）";
    showPlace(place);
    setStatus("该位置暂无街景", "error");
    return;
  }
  applyPanorama(data, { lat: place.lat, lng: place.lng });
  setStreetOpen(true);
  state.streetHint = "已打开街景，可拖动或点击箭头前进";
  showPlace(place);
  setStatus("街景已打开", "live");
}

function closeStreetView() {
  try {
    state.pano?.setVisible(false);
  } catch {
    /* ignore */
  }
  setStreetOpen(false);
  const meta = $("gmapStreetMeta");
  if (meta) meta.textContent = "拖动地图上的小人，或选中地点后打开";
}

function showPlace(place) {
  const panel = $("gmapDetail");
  if (!panel || !place) return;
  state.place = place;
  const lat = place.lat;
  const lng = place.lng;
  const hint = state.streetHint
    ? `<p class="muted gmap-street-hint">${esc(state.streetHint)}</p>`
    : `<p class="muted gmap-street-hint">「街景」看地面全景，「俯瞰」看 45° 航拍 / 三维实景。可试旧金山金门大桥、东京站、香港中环。</p>`;
  panel.innerHTML = `
    <div class="gmap-detail-head">
      <h2>${esc(place.name || "选中位置")}</h2>
      <p class="muted">${esc(place.address || "未解析到地址")}</p>
    </div>
    <dl class="gmap-detail-meta">
      <div><dt>纬度</dt><dd>${esc(fmtCoord(lat))}</dd></div>
      <div><dt>经度</dt><dd>${esc(fmtCoord(lng))}</dd></div>
    </dl>
    <div class="gmap-detail-actions">
      <button id="gmapStreetOpen" class="btn ghost" type="button">${
        state.streetOpen ? "刷新街景" : "打开街景"
      }</button>
      <button id="gmapAerialOpen" class="btn ghost" type="button">${
        state.aerialOpen ? "刷新俯瞰" : "打开俯瞰"
      }</button>
    </div>
    ${hint}
  `;
}

function focusPlace(place, zoom = 14) {
  if (!state.map || !place) return;
  const pos = { lat: place.lat, lng: place.lng };
  if (!state.marker) {
    state.marker = new google.maps.Marker({
      map: state.map,
      position: pos,
    });
  } else {
    state.marker.setPosition(pos);
    state.marker.setMap(state.map);
  }
  state.map.panTo(pos);
  if (state.map.getZoom() < zoom) state.map.setZoom(zoom);
  state.streetHint = "";
  showPlace(place);
  if (state.streetOpen) openStreetView(place);
  if (state.aerialOpen) setAerialTarget(pos);
}

async function reverseGeocode(latLng) {
  if (!state.geocoder) return { lat: latLng.lat(), lng: latLng.lng() };
  try {
    const { results } = await state.geocoder.geocode({ location: latLng });
    const top = results?.[0];
    return {
      name: top?.address_components?.[0]?.long_name || "选中位置",
      address: top?.formatted_address || "",
      lat: latLng.lat(),
      lng: latLng.lng(),
    };
  } catch {
    return { lat: latLng.lat(), lng: latLng.lng(), name: "选中位置" };
  }
}

async function searchQuery(query) {
  const text = String(query || "").trim();
  if (!text || !state.map) return;
  const parsed = parseLatLng(text);
  if (parsed) {
    focusPlace({ ...parsed, name: "坐标", address: `${parsed.lat}, ${parsed.lng}` }, 12);
    setStatus("已定位坐标", "live");
    return;
  }
  if (!state.geocoder) return;
  setStatus("搜索中…", "busy");
  try {
    const { results } = await state.geocoder.geocode({ address: text });
    const top = results?.[0];
    const loc = top?.geometry?.location;
    if (!loc) throw new Error("未找到地点");
    focusPlace({
      name: top.address_components?.[0]?.long_name || text,
      address: top.formatted_address || text,
      lat: loc.lat(),
      lng: loc.lng(),
    });
    setStatus("已定位", "live");
  } catch (err) {
    setStatus(err.message || "搜索失败", "error");
  }
}

function setMapType(type) {
  const next = MAP_TYPES[type] ? type : "roadmap";
  state.mapType = next;
  document.querySelectorAll(".gmap-type-btn").forEach((btn) => {
    const on = btn.dataset.type === next;
    btn.classList.toggle("is-active", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
  if (!state.map) return;
  state.map.setMapTypeId(next);
  state.map.setOptions({
    styles: usesDarkStyle(next) ? DARK_STYLES : [],
  });
}

function bindHud() {
  document.querySelectorAll(".gmap-type-btn").forEach((btn) => {
    btn.addEventListener("click", () => setMapType(btn.dataset.type));
  });

  $("gmapSearchForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    searchQuery($("gmapSearch")?.value);
  });

  $("gmapLocateBtn")?.addEventListener("click", () => {
    if (!navigator.geolocation) {
      setStatus("浏览器不支持定位", "error");
      return;
    }
    setStatus("定位中…", "busy");
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const latLng = new google.maps.LatLng(
          pos.coords.latitude,
          pos.coords.longitude
        );
        const place = await reverseGeocode(latLng);
        place.name = place.name || "当前位置";
        focusPlace(place, 16);
        setStatus("已定位", "live");
      },
      () => setStatus("定位失败或被拒绝", "error"),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  });

  $("gmapStreetBtn")?.addEventListener("click", () => {
    if (state.streetOpen) closeStreetView();
    else openStreetView();
  });
  $("gmapStreetClose")?.addEventListener("click", () => closeStreetView());
  $("gmapAerialBtn")?.addEventListener("click", () => {
    if (state.aerialOpen) closeAerial();
    else openAerial();
  });
  $("gmapAerialClose")?.addEventListener("click", () => closeAerial());
  document.querySelectorAll("[data-aerial]").forEach((btn) => {
    btn.addEventListener("click", () => nudgeAerial(btn.dataset.aerial));
  });
  $("gmapDetail")?.addEventListener("click", (event) => {
    if (event.target?.id === "gmapStreetOpen") openStreetView();
    if (event.target?.id === "gmapAerialOpen") openAerial(state.place);
  });
}

async function initMap() {
  setStatus("读取配置…", "busy");
  const resp = await fetch("/api/gmap/config");
  const json = await resp.json();
  if (!json.ok) throw new Error(json.error || "地图配置加载失败");
  const key = json.data?.key || "";
  if (!key) {
    throw new Error("未配置 Google Maps Key：请在项目根目录 .env 设置 GOOGLE_MAPS_API_KEY");
  }

  setStatus("加载 SDK…", "busy");
  await loadGoogleMaps(key);

  const stage = $("gmapStage");
  state.map = new google.maps.Map(stage, {
    center: { lat: 20, lng: 12 },
    zoom: 3,
    minZoom: 2,
    maxZoom: 21,
    mapTypeId: "roadmap",
    backgroundColor: "#070b12",
    disableDefaultUI: true,
    zoomControl: true,
    scaleControl: true,
    streetViewControl: true,
    gestureHandling: "greedy",
    clickableIcons: true,
    styles: DARK_STYLES,
  });
  state.geocoder = new google.maps.Geocoder();
  state.sv = new google.maps.StreetViewService();
  state.pano = new google.maps.StreetViewPanorama($("streetStage"), {
    visible: false,
    disableDefaultUI: false,
    addressControl: false,
    panControl: true,
    zoomControl: true,
    fullscreenControl: false,
    motionTracking: false,
    enableCloseButton: false,
  });
  state.map.setStreetView(state.pano);
  state.pano.addListener("visible_changed", () => {
    const vis = !!state.pano.getVisible();
    if (vis !== state.streetOpen) setStreetOpen(vis);
  });

  state.map.addListener("click", async (event) => {
    if (!event.latLng) return;
    const place = await reverseGeocode(event.latLng);
    focusPlace(place, Math.max(state.map.getZoom(), 12));
  });

  const input = $("gmapSearch");
  try {
    if (input && google.maps.places?.Autocomplete) {
      const autocomplete = new google.maps.places.Autocomplete(input, {
        fields: ["geometry", "name", "formatted_address"],
      });
      autocomplete.bindTo("bounds", state.map);
      autocomplete.addListener("place_changed", () => {
        const place = autocomplete.getPlace();
        const loc = place?.geometry?.location;
        if (!loc) {
          searchQuery(input.value);
          return;
        }
        focusPlace({
          name: place.name || "选中位置",
          address: place.formatted_address || "",
          lat: loc.lat(),
          lng: loc.lng(),
        });
        setStatus("已定位", "live");
      });
    }
  } catch (err) {
    console.warn("Places Autocomplete 不可用", err);
  }

  setStatus("就绪", "live");
  window.OrbitPrefetch?.boot("gmap");
}

bindHud();
initMap().catch((err) => {
  console.error(err);
  setStatus(err.message || "地图初始化失败", "error");
  window.OrbitPrefetch?.boot("gmap");
  const panel = $("gmapDetail");
  if (panel) {
    panel.innerHTML = `<p class="muted gmap-detail-empty">${esc(
      err.message || "地图初始化失败"
    )}</p>`;
  }
});
