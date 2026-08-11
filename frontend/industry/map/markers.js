/** 公司 Marker、弹窗、批量打点。 */

import { jitter } from "./coords.js";

export function createMarkerLayer({
  amap,
  places,
  geoStore,
  escapeHtml,
  getHighlightCode,
  onOpenCompany,
}) {
  const { rt, addOverlay, ensureReady, ensureDetailedBasemap, fitOverlays } =
    amap;

  function setMarkerHighlight(marker) {
    if (rt.highlightMarker && rt.highlightMarker !== marker) {
      rt.highlightMarker.setIcon?.(undefined);
      rt.highlightMarker.setzIndex?.(120);
    }
    rt.highlightMarker = marker || null;
    marker?.setzIndex?.(160);
  }

  function showCompanyPopup(stock, geo, lnglat) {
    const fullName = geo?.full_name || stock.name || "";
    const poiName = geo?.poi_name || "";
    const poiAddr = geo?.poi_address || geo?.reg_address || "";
    const html = `<div class="map-popup">
      <strong>${escapeHtml(stock.name || "-")}</strong>
      <div class="muted">${escapeHtml(stock.code || "")}</div>
      <div>${escapeHtml(fullName || "—")}</div>
      ${poiName ? `<div class="muted">高德：${escapeHtml(poiName)}</div>` : ""}
      ${poiAddr ? `<div class="muted">${escapeHtml(poiAddr)}</div>` : ""}
      <button type="button" class="btn ghost map-popup-btn" data-code="${escapeHtml(stock.code || "")}">查看详情</button>
    </div>`;
    rt.infoWindow.setContent(html);
    rt.infoWindow.open(rt.map, lnglat);
    requestAnimationFrame(() => {
      const btn = document.querySelector(
        `.map-popup-btn[data-code="${CSS.escape(stock.code || "")}"]`
      );
      btn?.addEventListener(
        "click",
        (ev) => {
          ev.preventDefault();
          onOpenCompany?.(stock);
        },
        { once: true }
      );
    });
  }

  function createCompanyMarker(stock, geo, pos, highlight = false) {
    const code = String(stock.code || "").trim();
    const title = geo?.full_name || stock.name || code;
    const marker = new AMap.Marker({
      position: pos,
      title,
      bubble: true,
      zIndex: highlight || code === getHighlightCode() ? 160 : 120,
      animation: highlight ? "AMAP_ANIMATION_DROP" : "AMAP_ANIMATION_NONE",
    });
    marker.on("click", () => {
      setMarkerHighlight(marker);
      showCompanyPopup(stock, geo, pos);
    });
    return marker;
  }

  /**
   * 批量 PlaceSearch + 钉点。
   * @param {object[]} stocks
   * @param {{ fit?: boolean, maxZoom?: number, searchMode?: boolean }} opts
   */
  async function overlayStockMarkers(stocks, opts = {}) {
    const { fit = false, maxZoom, searchMode = false } = opts;
    await ensureReady();
    const token = geoStore.currentToken();
    await geoStore.enrichStocks(stocks, token);
    if (token !== geoStore.currentToken()) return 0;

    if (fit || searchMode) ensureDetailedBasemap();

    const fitTargets = [];
    let pinned = 0;
    const concurrency = 2;
    const list = [...stocks];

    for (let i = 0; i < list.length; i += concurrency) {
      if (token !== geoStore.currentToken()) return 0;
      const chunk = list.slice(i, i + concurrency);
      const settled = await Promise.all(
        chunk.map(async (stock) => {
          const code = String(stock.code || "").trim();
          if (!code) return null;
          const geo = geoStore.get(code) || {};
          const hit = await places.resolveCompanyPlace(stock, geo);
          if (!hit) return null;
          return { stock, ...hit, code };
        })
      );

      for (const item of settled) {
        if (!item) continue;
        const { stock, geo, pos, code } = item;
        const [dj, di] = jitter(code);
        const lnglat = [pos[0] + di, pos[1] + dj];

        let marker = rt.markersByCode[code];
        if (marker) {
          rt.map.remove(marker);
          rt.overlays = rt.overlays.filter((x) => x !== marker);
        }
        marker = createCompanyMarker(
          stock,
          geo,
          lnglat,
          code === getHighlightCode()
        );
        addOverlay(marker);
        rt.markersByCode[code] = marker;
        if (code === getHighlightCode()) rt.highlightMarker = marker;
        fitTargets.push(marker);
        pinned += 1;
      }
    }

    if (fit && fitTargets.length) {
      const zoom =
        maxZoom ?? (fitTargets.length === 1 ? 15 : searchMode ? 12 : 8);
      fitOverlays(fitTargets, zoom);
    }
    return pinned;
  }

  return {
    setMarkerHighlight,
    showCompanyPopup,
    createCompanyMarker,
    overlayStockMarkers,
  };
}
