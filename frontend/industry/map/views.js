/** 省级总览着色 + 省内城市下钻图层。 */

import { toAmapLngLat } from "./coords.js";
import { jitter } from "./coords.js";

function provinceFillColor(count, maxCount) {
  if (!count) return "rgba(148, 168, 186, 0.08)";
  const t = maxCount <= 1 ? 1 : Math.min(1, count / maxCount);
  const alpha = 0.10 + t * 0.28;
  // 浅薄荷色，避免过深的青绿
  return `rgba(160, 230, 210, ${alpha.toFixed(3)})`;
}

function geoRingsToPaths(coordinates) {
  if (!Array.isArray(coordinates) || !coordinates.length) return [];
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

export function createMapViews({
  amap,
  geoStore,
  markers,
  places,
  escapeHtml,
  getStocks,
  getHighlightCode,
  getView,
  onStatus,
  onUnknown,
  onChrome,
  onProvinceClick,
}) {
  const {
    rt,
    clearLayers,
    addOverlay,
    forceResize,
    fitChina,
    fitOverlays,
    ensureDetailedBasemap,
    searchDistrict,
  } = amap;

  function aggregateProvinces(stocks) {
    const counts = {};
    let unknown = 0;
    for (const s of stocks) {
      const c = String(s.code || "").trim();
      const geo = geoStore.get(c);
      const prov = geo?.reg_province || "";
      if (!prov) {
        unknown += 1;
        continue;
      }
      counts[prov] = (counts[prov] || 0) + 1;
    }
    return { counts, unknown };
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
      strokeColor: "#3a9e90",
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

    for (const city of cities) {
      const name = String(city.name || "").trim();
      const lnglat = resolveCenter(city.center);
      if (name && lnglat) {
        const label = addAreaLabel(name, lnglat);
        if (label) drawn.push(label);
      }
    }

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

  function renderProvinceOverview() {
    const stocks = getStocks();
    const { counts, unknown } = aggregateProvinces(stocks);
    const maxCount = Math.max(0, ...Object.values(counts), 0);
    onUnknown?.(unknown);
    onStatus?.(
      `省级总览 · 已定位 ${stocks.length - unknown}/${stocks.length} 家`
    );

    clearLayers();
    forceResize();
    try {
      rt.map.setFeatures(["bg", "road", "building", "point"]);
    } catch {
      /* ignore */
    }

    const features = (rt.chinaGeo?.features || []).filter(
      (f) => f?.properties?.name
    );

    for (const feature of features) {
      const name = feature.properties.name;
      const count = counts[name] || 0;
      const strokeColor = "#5a6d82";
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
          polygon.setOptions({ strokeColor: "#2ad4b8", strokeWeight: 2 });
          rt.infoWindow.setContent(
            `<div class="map-tip"><strong>${escapeHtml(name)}</strong> · ${count} 家</div>`
          );
          rt.infoWindow.open(rt.map, ev.lnglat);
        });
        polygon.on("mousemove", (ev) => {
          rt.infoWindow.open(rt.map, ev.lnglat);
        });
        polygon.on("mouseout", () => {
          polygon.setOptions({ strokeColor, strokeWeight });
          rt.infoWindow.close();
        });
        polygon.on("click", () => {
          if (!count) return;
          onProvinceClick?.(name);
        });
        addOverlay(polygon);
      }
    }

    const centroids = rt.provinceCentroids || {};
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
    forceResize();
    onChrome?.();
  }

  async function renderCityDrilldown() {
    const { mapProvince: province } = getView();
    const stocks = [];
    for (const s of getStocks()) {
      const c = String(s.code || "").trim();
      const geo = geoStore.get(c);
      if (!geo || geo.reg_province !== province) continue;
      stocks.push({ stock: s, geo });
    }

    onUnknown?.(0);
    onStatus?.(`${province} · 加载市区划与公司标注…`);

    clearLayers();
    forceResize();
    ensureDetailedBasemap();

    const fitTargets = [];

    try {
      const provDist = await searchDistrict(province, {
        level: "province",
        subdistrict: 0,
        extensions: "all",
      });
      fitTargets.push(
        ...drawBoundaries(provDist.boundaries, {
          strokeColor: "#2ad4b8",
          strokeWeight: 2.5,
          fillColor: "#ffffff",
          fillOpacity: 0,
          zIndex: 40,
          bubble: true,
        })
      );
    } catch {
      const feature = (rt.chinaGeo?.features || []).find(
        (f) => (f?.properties?.name || "") === province
      );
      if (feature) {
        const polygons = polygonsFromFeature(feature, {
          fillColor: "#ffffff",
          fillOpacity: 0,
          strokeColor: "#2ad4b8",
          strokeWeight: 2.5,
          zIndex: 40,
        });
        for (const polygon of polygons) {
          addOverlay(polygon);
          fitTargets.push(polygon);
        }
      }
    }

    const cityLayers = await drawProvinceCities(province);
    fitTargets.push(...cityLayers);

    for (const { stock, geo } of stocks) {
      const hit = await places.resolveCompanyPlace(stock, geo);
      if (!hit) continue;
      const { pos, geo: g2 } = hit;
      const [dj, di] = jitter(String(stock.code || ""));
      const lng = pos[0] + di;
      const lat = pos[1] + dj;
      const code = String(stock.code || "").trim();
      const marker = markers.createCompanyMarker(
        stock,
        g2,
        [lng, lat],
        code === getHighlightCode()
      );
      addOverlay(marker);
      if (code) {
        rt.markersByCode[code] = marker;
        if (code === getHighlightCode()) rt.highlightMarker = marker;
      }
      fitTargets.push(marker);
    }

    const markerCount = Object.keys(rt.markersByCode).length;
    onStatus?.(`${province} · 高德标注 ${markerCount}/${stocks.length} 家`);

    const companyMarkers = Object.values(rt.markersByCode || {});
    if (companyMarkers.length) {
      fitOverlays(companyMarkers, 12);
    } else if (fitTargets.length) {
      fitOverlays(fitTargets, 9);
    }
    ensureDetailedBasemap();
    onChrome?.();
    forceResize();
  }

  return {
    aggregateProvinces,
    drawBoundaries,
    drawProvinceCities,
    renderProvinceOverview,
    renderCityDrilldown,
  };
}
