/**
 * 公司地点地图控制器。
 *
 * 流程：
 *   列表/搜索 → enrich（后端全称+省市区）
 *            → PlaceSearch（前端坐标）
 *            → Marker / 省市区图层
 *
 * 对外只依赖 ctx 回调，方便 app.js 接入与单测替换。
 */

import { createAmapRuntime } from "./amapSdk.js";
import { createGeoStore } from "./geoStore.js";
import { createPlaceResolver } from "./placeResolve.js";
import { createMarkerLayer } from "./markers.js";
import { createMapViews } from "./views.js";

/**
 * @param {object} ctx
 * @param {HTMLElement} ctx.container
 * @param {() => object[]} ctx.getStocks
 * @param {() => boolean} ctx.getSearchMode
 * @param {() => string} ctx.getHighlightCode
 * @param {(code: string) => void} ctx.setHighlightCode
 * @param {() => number[]} ctx.getHudPadding  [上,右,下,左]
 * @param {(path: string, opts?: object) => Promise<any>} ctx.api
 * @param {(s: any) => string} ctx.escapeHtml
 * @param {(stock: object) => void} ctx.onOpenCompany
 * @param {() => void} [ctx.onListRender]
 * @param {(msg: string) => void} [ctx.onError]
 * @param {HTMLElement|null} [ctx.statusEl]
 * @param {HTMLElement|null} [ctx.unknownEl]
 * @param {HTMLElement|null} [ctx.backBtn]
 */
export function createCompanyMap(ctx) {
  const view = {
    mapLevel: "province",
    mapProvince: null,
    mapStreetFocus: "",
    listMapKind: "",
  };

  const setStatus = (text) => {
    if (ctx.statusEl) ctx.statusEl.textContent = text || "";
  };
  const setUnknown = (n) => {
    if (!ctx.unknownEl) return;
    ctx.unknownEl.textContent = n > 0 ? `未知注册地 ${n} 家` : "";
  };
  const syncChrome = () => {};

  const amap = createAmapRuntime({
    container: ctx.container,
    api: ctx.api,
    getHudPadding: ctx.getHudPadding,
  });

  const geoStore = createGeoStore({
    api: ctx.api,
    onProgress: setStatus,
  });

  const places = createPlaceResolver({ amap, geoStore });

  const markers = createMarkerLayer({
    amap,
    places,
    geoStore,
    escapeHtml: ctx.escapeHtml,
    getHighlightCode: ctx.getHighlightCode,
    onOpenCompany: ctx.onOpenCompany,
  });

  const views = createMapViews({
    amap,
    geoStore,
    markers,
    places,
    escapeHtml: ctx.escapeHtml,
    getStocks: ctx.getStocks,
    getHighlightCode: ctx.getHighlightCode,
    getView: () => view,
    onStatus: setStatus,
    onUnknown: setUnknown,
    onChrome: syncChrome,
    onProvinceClick: (name) => {
      view.mapLevel = "city";
      view.mapProvince = name;
      renderMap().catch((err) => ctx.onError?.(err.message || String(err)));
    },
  });

  function resetDrilldown() {
    view.mapLevel = "province";
    view.mapProvince = null;
    view.mapStreetFocus = "";
  }

  function getSnapshot() {
    return {
      mapLevel: view.mapLevel,
      mapProvince: view.mapProvince,
      mapStreetFocus: view.mapStreetFocus,
      listMapKind: view.listMapKind,
    };
  }

  function applySnapshot(snap = {}) {
    if (snap.mapLevel != null) view.mapLevel = snap.mapLevel;
    if (snap.mapProvince !== undefined) view.mapProvince = snap.mapProvince;
    if (snap.mapStreetFocus != null) view.mapStreetFocus = snap.mapStreetFocus;
    if (snap.listMapKind != null) view.listMapKind = snap.listMapKind;
  }

  async function renderMap() {
    try {
      await amap.ensureReady();
      if (view.mapLevel === "city" && view.mapProvince) {
        await views.renderCityDrilldown();
      } else {
        view.mapLevel = "province";
        view.mapProvince = null;
        views.renderProvinceOverview();
      }
      syncChrome();
    } catch (err) {
      setStatus("");
      ctx.onError?.(err.message || String(err));
    }
  }

  /** 行业列表 / 通用刷新。 */
  async function refreshFromStocks() {
    const stocks = ctx.getStocks();
    const token = geoStore.bumpToken();
    if (!stocks.length) {
      setStatus("选择行业或搜索公司以查看注册地分布");
      setUnknown(0);
      try {
        await amap.ensureReady();
        view.mapLevel = "province";
        view.mapProvince = null;
        amap.clearLayers();
        if (amap.rt.chinaGeo) {
          views.renderProvinceOverview();
        } else {
          amap.fitChina();
        }
        syncChrome();
      } catch (err) {
        ctx.onError?.(err.message || String(err));
      }
      return;
    }
    try {
      setStatus("正在补齐注册地…");
      await geoStore.enrichStocks(stocks, token);
      if (token !== geoStore.currentToken()) return;
      await renderMap();
      if (token === geoStore.currentToken() && view.mapLevel === "province") {
        const pinned = await markers.overlayStockMarkers(stocks, {
          fit: ctx.getSearchMode() || stocks.length <= 80,
          searchMode: ctx.getSearchMode(),
        });
        setStatus(
          pinned
            ? `高德搜索标注 ${pinned} 家公司`
            : "高德未搜到可标注的公司地点"
        );
      }
    } catch (err) {
      if (token !== geoStore.currentToken()) return;
      setStatus("");
      ctx.onError?.(err.message || String(err));
    }
  }

  /** 搜索结果列表地图：同省下钻，跨省直接打点适配。 */
  async function syncToSearchResults(stocks) {
    const token = geoStore.bumpToken();
    view.mapStreetFocus = "";
    view.listMapKind = "search";
    amap.rt.infoWindow?.close?.();
    try {
      await amap.ensureReady();
      setStatus("正在补齐注册地…");
      await geoStore.enrichStocks(stocks, token);
      if (token !== geoStore.currentToken()) return;

      const provinces = new Map();
      for (const s of stocks) {
        const c = String(s.code || "").trim();
        const prov = String(geoStore.get(c)?.reg_province || "").trim();
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
      const sameProvince =
        !!dominant &&
        (stocks.length === 1 ||
          dominantCount >= Math.max(2, Math.ceil(stocks.length * 0.6)));

      if (sameProvince) {
        view.mapLevel = "city";
        view.mapProvince = dominant;
        await renderMap();
        if (token !== geoStore.currentToken()) return;
        ctx.onListRender?.();
        return;
      }

      view.mapLevel = "province";
      view.mapProvince = null;
      amap.clearLayers();
      amap.forceResize();
      amap.ensureDetailedBasemap();
      setStatus("高德地点搜索中…");
      const pinned = await markers.overlayStockMarkers(stocks, {
        fit: true,
        maxZoom: 12,
        searchMode: true,
      });
      if (token !== geoStore.currentToken()) return;
      setStatus(
        pinned
          ? `高德搜索标注 ${pinned} 家公司`
          : "高德未搜到可标注的公司地点"
      );
      amap.ensureDetailedBasemap();
      syncChrome();
      ctx.onListRender?.();
    } catch (err) {
      if (token !== geoStore.currentToken()) return;
      setStatus("");
      ctx.onError?.(err.message || String(err));
    }
  }

  async function focusCompany(stock) {
    const code = String(stock.code || "").trim();
    if (!code) return;
    if (!view.mapStreetFocus) {
      view.listMapKind =
        view.listMapKind || (ctx.getSearchMode() ? "search" : "industry");
    }
    ctx.setHighlightCode(code);
    view.mapStreetFocus = code;
    ctx.onListRender?.();
    setStatus(`高德搜索 ${stock.name || code}…`);

    try {
      await amap.ensureReady();
      const token = geoStore.bumpToken();
      await geoStore.enrichStocks([stock], token);
      if (token !== geoStore.currentToken()) return;

      const geo = geoStore.get(code) || {};
      const hit = await places.resolveCompanyPlace(stock, geo);
      if (!hit) {
        view.mapStreetFocus = "";
        setStatus(
          `${stock.name || code}：高德未搜到「${geo.full_name || stock.name || code}」`
        );
        ctx.onListRender?.();
        return;
      }
      if (token !== geoStore.currentToken()) return;

      const { pos, geo: g2, poi } = hit;
      view.mapLevel = "city";
      view.mapProvince = g2.reg_province || view.mapProvince || null;

      amap.clearLayers();
      amap.forceResize();
      amap.ensureDetailedBasemap();

      const areaName = g2.reg_city || g2.reg_province || "";
      if (areaName) {
        try {
          const dist = await amap.searchDistrict(areaName, {
            level: g2.reg_city ? "city" : "province",
            subdistrict: g2.reg_city ? 0 : 1,
            extensions: "all",
          });
          if (token !== geoStore.currentToken()) return;
          views.drawBoundaries(dist.boundaries || [], {
            strokeColor: "#2ad4b8",
            strokeWeight: 2,
            fillColor: "#ffffff",
            fillOpacity: 0,
            zIndex: 40,
            bubble: true,
          });
          if (!g2.reg_city && g2.reg_province) {
            await views.drawProvinceCities(g2.reg_province);
            if (token !== geoStore.currentToken()) return;
          }
        } catch {
          /* 区划失败仍显示公司点 */
        }
      }
      if (token !== geoStore.currentToken()) return;

      const marker = markers.createCompanyMarker(stock, g2, pos, true);
      amap.addOverlay(marker);
      amap.rt.markersByCode[code] = marker;
      markers.setMarkerHighlight(marker);

      amap.focusTargets([marker], 16);
      requestAnimationFrame(() => {
        if (token !== geoStore.currentToken()) return;
        amap.focusTargets([marker], 16);
        markers.showCompanyPopup(stock, g2, pos);
      });
      setTimeout(() => {
        if (token !== geoStore.currentToken()) return;
        amap.focusTargets([marker], 16);
      }, 160);
      syncChrome();

      const areaLabel = [g2.reg_province, g2.reg_city, poi?.name]
        .filter(Boolean)
        .join(" · ");
      setStatus(
        `${stock.name || code} · ${areaLabel || "高德标注"}（再点返回列表地图）`
      );
    } catch (err) {
      view.mapStreetFocus = "";
      setStatus("");
      ctx.onError?.(err.message || String(err));
    }
  }

  /** 按当前公司列表重新在地图上标注（退出街道聚焦后的列表地图）。 */
  async function annotateListCompanies() {
    const stocks = ctx.getStocks();
    const token = geoStore.bumpToken();
    view.mapStreetFocus = "";
    amap.rt.infoWindow?.close?.();
    markers.setMarkerHighlight(null);

    if (!stocks.length) {
      setStatus("选择行业或搜索公司以查看注册地分布");
      setUnknown(0);
      try {
        await amap.ensureReady();
        view.mapLevel = "province";
        view.mapProvince = null;
        amap.clearLayers();
        if (amap.rt.chinaGeo) views.renderProvinceOverview();
        else amap.fitChina();
        syncChrome();
      } catch (err) {
        ctx.onError?.(err.message || String(err));
      }
      return;
    }

    try {
      await amap.ensureReady();
      setStatus("正在标注列表公司…");
      await geoStore.enrichStocks(stocks, token);
      if (token !== geoStore.currentToken()) return;

      view.mapLevel = "province";
      view.mapProvince = null;
      view.listMapKind =
        view.listMapKind || (ctx.getSearchMode() ? "search" : "industry");

      amap.clearLayers();
      amap.forceResize();
      amap.ensureDetailedBasemap();

      const searchLike =
        view.listMapKind === "search" || ctx.getSearchMode();
      const pinned = await markers.overlayStockMarkers(stocks, {
        fit: true,
        maxZoom: searchLike ? 12 : stocks.length <= 80 ? 10 : 8,
        searchMode: searchLike,
      });
      if (token !== geoStore.currentToken()) return;

      setStatus(
        pinned
          ? `列表地图 · 已标注 ${pinned}/${stocks.length} 家`
          : "高德未搜到可标注的公司地点"
      );
      amap.ensureDetailedBasemap();
      syncChrome();
    } catch (err) {
      if (token !== geoStore.currentToken()) return;
      setStatus("");
      ctx.onError?.(err.message || String(err));
    }
  }

  async function exitStreetFocus(stock) {
    const code = String(stock?.code || view.mapStreetFocus || "").trim();
    view.mapStreetFocus = "";
    amap.rt.infoWindow?.close?.();
    markers.setMarkerHighlight(null);
    if (code) ctx.setHighlightCode(code);
    ctx.onListRender?.();

    try {
      if (amap.rt.map) {
        const z = amap.rt.map.getZoom?.() || 16;
        if (z > 11) amap.rt.map.setZoom(10);
      }
    } catch {
      /* ignore */
    }

    await annotateListCompanies();
  }

  async function onCompanyCardClick(stock) {
    const code = String(stock.code || "").trim();
    if (!code) return;
    if (view.mapStreetFocus && view.mapStreetFocus === code) {
      await exitStreetFocus(stock);
      return;
    }
    await focusCompany(stock);
  }

  return {
    view,
    geoStore,
    getSnapshot,
    applySnapshot,
    resetDrilldown,
    ensureReady: () => amap.ensureReady(),
    showOverview: () => {
      views.renderProvinceOverview();
      setStatus("选择行业或搜索公司以查看注册地分布");
    },
    renderMap,
    refreshFromStocks,
    syncToSearchResults,
    annotateListCompanies,
    focusCompany,
    exitStreetFocus,
    onCompanyCardClick,
    setStatus,
    setBaseMode: (mode) => amap.setBaseMode(mode),
    getBaseMode: () => amap.getBaseMode(),
    BASE_MODES: amap.BASE_MODES,
  };
}
