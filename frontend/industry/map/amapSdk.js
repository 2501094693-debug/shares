/** 高德 SDK 加载、地图实例、行政区查询。 */

const BASE_MODES = {
  normal: "标准",
  satellite: "卫星",
  hybrid: "卫星路网",
};

export function createAmapRuntime({ container, api, getHudPadding }) {
  const rt = {
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
    /** @type {'normal'|'satellite'|'hybrid'} */
    baseMode: "normal",
  };

  function loadAmapScript(key, securityJsCode) {
    if (window.AMap) return Promise.resolve(window.AMap);
    if (rt.loadingSdk) return rt.loadingSdk;
    rt.loadingSdk = new Promise((resolve, reject) => {
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
      rt.loadingSdk = null;
    });
    return rt.loadingSdk;
  }

  function loadPlugin(name) {
    return new Promise((resolve, reject) => {
      if (!window.AMap?.plugin) {
        reject(new Error("高德插件加载器不可用"));
        return;
      }
      AMap.plugin(name, () => resolve());
    });
  }

  function forceResize() {
    if (!rt.map) return;
    try {
      rt.map.resize();
    } catch {
      /* ignore */
    }
    requestAnimationFrame(() => {
      try {
        rt.map?.resize();
      } catch {
        /* ignore */
      }
    });
    setTimeout(() => {
      try {
        rt.map?.resize();
      } catch {
        /* ignore */
      }
    }, 120);
  }

  function fitChina() {
    if (!rt.map) return;
    forceResize();
    rt.map.setBounds(
      new AMap.Bounds([73.0, 17.5], [135.5, 54.0]),
      false,
      getHudPadding()
    );
  }

  function fitOverlays(targets, maxZoom = 12) {
    if (!rt.map || !targets?.length) {
      fitChina();
      return;
    }
    forceResize();
    rt.map.setFitView(targets, false, getHudPadding(), maxZoom);
  }

  function focusTargets(targets, zoom = 16) {
    if (!rt.map || !targets?.length) return;
    forceResize();
    const pad = getHudPadding();
    try {
      rt.map.setFitView(targets, false, pad, zoom);
    } catch {
      const first = targets[0];
      const pos =
        typeof first?.getPosition === "function" ? first.getPosition() : first;
      if (pos) rt.map.setZoomAndCenter(zoom, pos);
    }
  }

  function clearLayers() {
    if (rt.map && rt.overlays.length) {
      rt.map.remove(rt.overlays);
    }
    rt.overlays = [];
    rt.markersByCode = {};
    rt.highlightMarker = null;
    rt.infoWindow?.close?.();
  }

  function addOverlay(item) {
    if (!item) return;
    rt.overlays.push(item);
    rt.map.add(item);
  }

  /** 缓存卫星/路网层；标准底图始终保留，切模式只叠层，避免 setLayers 弄丢地名。 */
  let satelliteLayer = null;
  let roadNetLayer = null;

  function ensureBaseLayers() {
    if (!window.AMap) return;
    if (!satelliteLayer) {
      satelliteLayer = new AMap.TileLayer.Satellite({
        zooms: [3, 20],
        detectRetina: true,
        zIndex: 2,
      });
    }
    if (!roadNetLayer) {
      roadNetLayer = new AMap.TileLayer.RoadNet({
        zooms: [3, 20],
        detectRetina: true,
        zIndex: 3,
      });
    }
  }

  function removeOverlayLayer(layer) {
    if (!rt.map || !layer) return;
    try {
      rt.map.remove(layer);
    } catch {
      /* ignore */
    }
  }

  function restoreNormalLabels() {
    if (!rt.map) return;
    try {
      rt.map.setMapStyle("amap://styles/normal");
      // point = 兴趣点/地名
      rt.map.setFeatures(["bg", "road", "building", "point"]);
      rt.map.setStatus?.({ showLabel: true });
    } catch {
      /* ignore */
    }
  }

  /** 应用底图模式：标准 / 卫星 / 卫星+路网。 */
  function applyBaseMode(mode = rt.baseMode) {
    if (!rt.map || !window.AMap) return;
    const next = BASE_MODES[mode] ? mode : "normal";
    rt.baseMode = next;
    ensureBaseLayers();

    try {
      // 先清掉叠加层，再按模式 add；切勿 setLayers 替换内置矢量底图
      removeOverlayLayer(satelliteLayer);
      removeOverlayLayer(roadNetLayer);

      if (next === "satellite") {
        rt.map.add(satelliteLayer);
        return;
      }
      if (next === "hybrid") {
        rt.map.add([satelliteLayer, roadNetLayer]);
        return;
      }

      restoreNormalLabels();
    } catch {
      /* ignore */
    }
  }

  function setBaseMode(mode) {
    const next = BASE_MODES[mode] ? mode : "normal";
    rt.baseMode = next;
    if (rt.map) applyBaseMode(next);
    return next;
  }

  function getBaseMode() {
    return rt.baseMode;
  }

  function ensureDetailedBasemap() {
    if (!rt.map) return;
    try {
      applyBaseMode(rt.baseMode);
    } catch {
      /* ignore */
    }
    const kept = [];
    for (const item of rt.overlays) {
      const isPoly =
        item &&
        (item instanceof AMap.Polygon ||
          String(item?.CLASS_NAME || item?.className || "").includes("Polygon"));
      if (isPoly) {
        const fo = Number(item.getOptions?.()?.fillOpacity ?? 1);
        if (fo > 0.05) {
          try {
            rt.map.remove(item);
          } catch {
            /* ignore */
          }
          continue;
        }
      }
      kept.push(item);
    }
    rt.overlays = kept;
  }

  async function ensureReady() {
    if (rt.ready && rt.map) {
      forceResize();
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
    rt.amapKey = key;
    await loadAmapScript(key, securityJsCode);

    if (!rt.map) {
      rt.map = new AMap.Map(container, {
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
      try {
        rt.map.setStatus({
          scrollWheel: true,
          doubleClickZoom: true,
          dragEnable: true,
        });
      } catch {
        /* ignore */
      }
      rt.infoWindow = new AMap.InfoWindow({
        isCustom: false,
        offset: new AMap.Pixel(0, -8),
      });
      if (!rt._resizeBound) {
        rt._resizeBound = true;
        window.addEventListener("resize", () => forceResize());
        container.addEventListener(
          "wheel",
          (e) => {
            e.preventDefault();
          },
          { passive: false }
        );
      }
      if (rt.baseMode !== "normal") applyBaseMode(rt.baseMode);
    }

    if (!rt.chinaGeo) {
      const [chinaRes, centroidsRes] = await Promise.all([
        fetch("/geo/china-provinces.json"),
        fetch("/geo/province-centroids.json"),
      ]);
      if (!chinaRes.ok) throw new Error("省级地图数据加载失败");
      rt.chinaGeo = await chinaRes.json();
      rt.provinceCentroids = centroidsRes.ok ? await centroidsRes.json() : {};
    }
    rt.ready = true;
    forceResize();
  }

  function searchDistrict(keyword, opts) {
    const cacheKey = `${opts.level || ""}|${opts.subdistrict ?? ""}|${opts.extensions || ""}|${keyword}`;
    if (rt.districtCache[cacheKey]) {
      return Promise.resolve(rt.districtCache[cacheKey]);
    }
    return loadPlugin("AMap.DistrictSearch").then(
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
              rt.districtCache[cacheKey] = row;
              resolve(row);
              return;
            }
            reject(new Error(`行政区查询失败：${keyword}`));
          });
        })
    );
  }

  return {
    rt,
    loadPlugin,
    ensureReady,
    forceResize,
    fitChina,
    fitOverlays,
    focusTargets,
    clearLayers,
    addOverlay,
    ensureDetailedBasemap,
    setBaseMode,
    getBaseMode,
    applyBaseMode,
    searchDistrict,
    BASE_MODES,
  };
}
