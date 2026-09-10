/** 公司 Marker、弹窗、批量打点。 */

import { jitter } from "./coords.js";
import { extractPhotoUrls, composePoiAddress } from "./placeResolve.js";

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
  let viewerIndex = 0;
  let viewerPhotos = [];
  let viewerScale = 1;
  let viewerX = 0;
  let viewerY = 0;
  const ZOOM_MIN = 1;
  const ZOOM_MAX = 5;

  function nextPopupGen() {
    rt.popupGen = (rt.popupGen || 0) + 1;
    return rt.popupGen;
  }

  function closePopup() {
    nextPopupGen();
    rt.popupCode = "";
    rt.infoWindow?.close?.();
    closePhotoViewer();
  }

  function setMarkerHighlight(marker) {
    if (rt.highlightMarker && rt.highlightMarker !== marker) {
      rt.highlightMarker.setIcon?.(undefined);
      rt.highlightMarker.setzIndex?.(120);
    }
    rt.highlightMarker = marker || null;
    marker?.setzIndex?.(160);
  }

  function poiPhotoUrls(geo, poi) {
    return extractPhotoUrls(
      [geo?.poi_photos, poi?.photos, poi?.photo, poi],
      6
    );
  }

  function completeAddress(geo, poi) {
    const reg = String(geo?.reg_address || "").trim();
    if (reg) return reg;
    return composePoiAddress(poi, geo);
  }

  function bindPopupActions(stock, photos) {
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
    document.querySelectorAll(".map-popup-photo-link").forEach((link, idx) => {
      const img = link.querySelector("img");
      if (img) img.referrerPolicy = "no-referrer";
      img?.addEventListener("error", () => link.remove());
      link.addEventListener("click", (ev) => {
        ev.preventDefault();
        openPhotoViewer(photos, idx);
      });
    });
  }

  function showCompanyPopup(stock, geo, lnglat, poi, opts = {}) {
    const fullName = geo?.full_name || stock.name || "";
    const poiName = geo?.poi_name || poi?.name || "";
    const address = completeAddress(geo, poi);
    const photos = poiPhotoUrls(geo, poi).slice(0, 4);
    const loading = !!opts.loadingPhotos && !photos.length;
    const photoHtml = photos
      .map((src, idx) => {
        const hero = idx === 0 ? " is-hero" : "";
        return `<a class="map-popup-photo-link${hero}" href="${escapeHtml(src)}" data-photo-idx="${idx}"><img class="map-popup-photo" src="${escapeHtml(src)}" alt="${escapeHtml(poiName || stock.name || "高德实景")}" referrerpolicy="no-referrer" /></a>`;
      })
      .join("");
    const html = `<div class="map-popup${photos.length ? " has-photos" : ""}${address ? " has-addr" : ""}">
      <strong>${escapeHtml(stock.name || "-")}</strong>
      <div class="muted">${escapeHtml(stock.code || "")}</div>
      <div>${escapeHtml(fullName || "—")}</div>
      ${poiName ? `<div class="muted">高德：${escapeHtml(poiName)}</div>` : ""}
      ${address ? `<div class="map-popup-addr">${escapeHtml(address)}</div>` : ""}
      ${
        photoHtml
          ? `<div class="map-popup-photos">${photoHtml}</div>`
          : loading
            ? `<div class="muted map-popup-photo-cap">正在加载高德实景…</div>`
            : ""
      }
      <div class="map-popup-actions">
        <button type="button" class="btn ghost map-popup-btn" data-code="${escapeHtml(stock.code || "")}">查看详情</button>
      </div>
    </div>`;
    rt.popupCode = String(stock.code || "").trim();
    rt.infoWindow.setContent(html);
    rt.infoWindow.open(rt.map, lnglat);
    requestAnimationFrame(() => bindPopupActions(stock, photos));
  }

  async function ensurePopupPhotos(stock, geo, lnglat, poi) {
    const code = String(stock.code || "").trim();
    const seq = rt.popupGen || 0;
    if (poiPhotoUrls(geo, poi).length >= 3) return;
    const hit = await places.resolveCompanyPlace(stock, geo, { detailed: true });
    if (seq !== rt.popupGen || rt.popupCode !== code) return;
    if (!hit) {
      if (!poiPhotoUrls(geo, poi).length) {
        showCompanyPopup(stock, geo, lnglat, poi);
      }
      return;
    }
    showCompanyPopup(stock, hit.geo, lnglat, hit.poi);
  }

  function openCompanyPopup(stock, geo, lnglat, poi, opts = {}) {
    const seq = nextPopupGen();
    const photos = poiPhotoUrls(geo, poi);
    const enrich = opts.enrich !== false && photos.length < 3;
    showCompanyPopup(stock, geo, lnglat, poi, { loadingPhotos: enrich });
    if (enrich) {
      ensurePopupPhotos(stock, geo, lnglat, poi).catch(() => {
        if (seq === rt.popupGen) showCompanyPopup(stock, geo, lnglat, poi);
      });
    }
  }

  function renderViewer() {
    const img = document.querySelector("#mapPhotoViewer .map-photo-viewer-img");
    const prev = document.querySelector("#mapPhotoViewer .map-photo-viewer-prev");
    const next = document.querySelector("#mapPhotoViewer .map-photo-viewer-next");
    const cap = document.querySelector("#mapPhotoViewer .map-photo-viewer-cap");
    if (!img) return;
    const src = viewerPhotos[viewerIndex] || "";
    if (img.getAttribute("src") !== src) img.src = src;
    if (prev) prev.hidden = viewerPhotos.length < 2;
    if (next) next.hidden = viewerPhotos.length < 2;
    if (cap) {
      cap.textContent =
        viewerPhotos.length > 1
          ? `高德实景 ${viewerIndex + 1} / ${viewerPhotos.length}`
          : "高德实景";
    }
    applyViewerZoom();
  }

  function applyViewerZoom() {
    const img = document.querySelector("#mapPhotoViewer .map-photo-viewer-img");
    const label = document.querySelector("#mapPhotoViewer .map-photo-viewer-zoom-val");
    if (!img) return;
    img.style.transform = `translate(${viewerX}px, ${viewerY}px) scale(${viewerScale})`;
    img.classList.toggle("is-zoomed", viewerScale > 1.02);
    if (label) label.textContent = `${Math.round(viewerScale * 100)}%`;
  }

  function resetViewerZoom() {
    viewerScale = 1;
    viewerX = 0;
    viewerY = 0;
    applyViewerZoom();
  }

  function zoomViewer(delta) {
    const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, viewerScale + delta));
    viewerScale = Math.round(next * 100) / 100;
    if (viewerScale <= 1) {
      viewerX = 0;
      viewerY = 0;
    }
    applyViewerZoom();
  }

  function closePhotoViewer() {
    const el = document.getElementById("mapPhotoViewer");
    if (el) el.hidden = true;
    resetViewerZoom();
  }

  function stepPhoto(delta) {
    if (viewerPhotos.length < 2) return;
    viewerIndex =
      (viewerIndex + delta + viewerPhotos.length) % viewerPhotos.length;
    resetViewerZoom();
    renderViewer();
  }

  function ensurePhotoViewer() {
    let el = document.getElementById("mapPhotoViewer");
    if (el) return el;
    el = document.createElement("div");
    el.id = "mapPhotoViewer";
    el.className = "map-photo-viewer";
    el.hidden = true;
    el.innerHTML = `
      <button type="button" class="map-photo-viewer-close" aria-label="关闭">×</button>
      <button type="button" class="map-photo-viewer-nav map-photo-viewer-prev" aria-label="上一张">‹</button>
      <figure class="map-photo-viewer-frame">
        <div class="map-photo-viewer-stage">
          <img class="map-photo-viewer-img" alt="高德实景" referrerpolicy="no-referrer" draggable="false" />
        </div>
        <figcaption class="map-photo-viewer-cap">高德实景</figcaption>
        <div class="map-photo-viewer-zoom">
          <button type="button" class="map-photo-viewer-zoom-btn" data-zoom="-0.4" aria-label="缩小">−</button>
          <span class="map-photo-viewer-zoom-val">100%</span>
          <button type="button" class="map-photo-viewer-zoom-btn" data-zoom="0.4" aria-label="放大">+</button>
          <button type="button" class="map-photo-viewer-zoom-btn" data-zoom="reset" aria-label="重置">复位</button>
        </div>
      </figure>
      <button type="button" class="map-photo-viewer-nav map-photo-viewer-next" aria-label="下一张">›</button>
    `;
    const img = el.querySelector(".map-photo-viewer-img");
    const stage = el.querySelector(".map-photo-viewer-stage");
    let dragging = false;
    let moved = false;
    let lastX = 0;
    let lastY = 0;

    el.addEventListener("click", (ev) => {
      if (ev.target === el) closePhotoViewer();
    });
    el.querySelector(".map-photo-viewer-close")?.addEventListener(
      "click",
      closePhotoViewer
    );
    el.querySelector(".map-photo-viewer-prev")?.addEventListener("click", () =>
      stepPhoto(-1)
    );
    el.querySelector(".map-photo-viewer-next")?.addEventListener("click", () =>
      stepPhoto(1)
    );
    el.querySelectorAll(".map-photo-viewer-zoom-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const z = btn.getAttribute("data-zoom");
        if (z === "reset") resetViewerZoom();
        else zoomViewer(Number(z) || 0);
      });
    });
    stage?.addEventListener(
      "wheel",
      (ev) => {
        ev.preventDefault();
        zoomViewer(ev.deltaY < 0 ? 0.25 : -0.25);
      },
      { passive: false }
    );
    img?.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      dragging = viewerScale > 1;
      moved = false;
      lastX = ev.clientX;
      lastY = ev.clientY;
      img.setPointerCapture(ev.pointerId);
    });
    img?.addEventListener("pointermove", (ev) => {
      if (!dragging) return;
      const dx = ev.clientX - lastX;
      const dy = ev.clientY - lastY;
      if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
      viewerX += dx;
      viewerY += dy;
      lastX = ev.clientX;
      lastY = ev.clientY;
      applyViewerZoom();
    });
    img?.addEventListener("pointerup", () => {
      dragging = false;
    });
    img?.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (moved) return;
      if (viewerScale <= 1) zoomViewer(1);
      else resetViewerZoom();
    });
    document.addEventListener("keydown", (ev) => {
      if (el.hidden) return;
      if (ev.key === "Escape") closePhotoViewer();
      if (ev.key === "ArrowLeft") stepPhoto(-1);
      if (ev.key === "ArrowRight") stepPhoto(1);
      if (ev.key === "+" || ev.key === "=") zoomViewer(0.4);
      if (ev.key === "-" || ev.key === "_") zoomViewer(-0.4);
      if (ev.key === "0") resetViewerZoom();
    });
    document.body.appendChild(el);
    return el;
  }

  function openPhotoViewer(photos, index = 0) {
    viewerPhotos = photos.filter(Boolean);
    if (!viewerPhotos.length) return;
    viewerIndex = Math.max(0, Math.min(index, viewerPhotos.length - 1));
    resetViewerZoom();
    const el = ensurePhotoViewer();
    el.hidden = false;
    renderViewer();
  }

  function createCompanyMarker(stock, geo, pos, highlight = false, poi = null) {
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
      const latest = geoStore.get(code) || geo;
      openCompanyPopup(stock, latest, pos, poi || latest);
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
        const { stock, geo, pos, code, poi } = item;
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
          code === getHighlightCode(),
          poi
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
    openCompanyPopup,
    closePopup,
    createCompanyMarker,
    overlayStockMarkers,
  };
}
