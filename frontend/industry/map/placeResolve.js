/** 用公司全称做高德 PlaceSearch，得到 GCJ-02 坐标；定位时再补 POI 实景图。 */

const PHOTO_LIMIT = 6;

export function extractPhotoUrls(source, limit = PHOTO_LIMIT) {
  const urls = [];
  const seen = new Set();

  const push = (raw) => {
    if (urls.length >= limit) return;
    let u = "";
    if (typeof raw === "string") u = raw;
    else if (raw && typeof raw === "object") {
      u = raw.url || raw.picUrl || raw.imgUrl || raw.src || raw.href || "";
    }
    u = String(u || "").trim();
    if (u.startsWith("//")) u = `https:${u}`;
    u = u.replace(/^http:\/\//i, "https://");
    if (!/^https:\/\//i.test(u) || seen.has(u)) return;
    if (!/autonavi|amap\.com|amapcdn|\.(jpg|jpeg|png|webp)(\?|$)/i.test(u)) {
      return;
    }
    seen.add(u);
    urls.push(u);
  };

  const walkPhotos = (node) => {
    if (!node || urls.length >= limit) return;
    const list = Array.isArray(node) ? node : [node];
    for (const item of list) {
      push(item);
      if (urls.length >= limit) return;
    }
  };

  const roots = Array.isArray(source) ? source : [source];
  for (const src of roots) {
    if (!src) continue;
    if (typeof src === "string") {
      push(src);
      continue;
    }
    if (Array.isArray(src)) {
      walkPhotos(src);
      continue;
    }
    walkPhotos(src.photos);
    walkPhotos(src.photo);
    walkPhotos(src.pics);
    walkPhotos(src.pic);
    walkPhotos(src.deep?.photos);
    walkPhotos(src.dining?.photos);
    walkPhotos(src.hotel?.photos);
    walkPhotos(src.scenic?.photos);
    if (src.url || src.picUrl) push(src);
  }
  return urls.slice(0, limit);
}

export function composePoiAddress(poi, geo = {}) {
  const street = String(poi?.address || geo?.poi_address || "").trim();
  const parts = [
    poi?.pname || geo?.reg_province,
    poi?.cityname || geo?.reg_city,
    poi?.adname,
  ]
    .map((s) => String(s || "").trim())
    .filter(Boolean);
  const uniq = [];
  for (const part of parts) {
    if (uniq.some((u) => u === part || u.includes(part) || part.includes(u))) {
      continue;
    }
    uniq.push(part);
  }
  let prefix = "";
  for (const part of uniq) {
    if (street.startsWith(part) || street.includes(part) || prefix.includes(part)) {
      continue;
    }
    prefix += part;
  }
  if (!prefix) return street;
  if (!street) return prefix;
  if (street.startsWith(prefix)) return street;
  return `${prefix}${street}`;
}

export function createPlaceResolver({ amap, geoStore, api }) {
  function companySearchKeyword(stock, geo) {
    return (
      String(geo?.full_name || "").trim() ||
      String(stock?.name || "").trim() ||
      String(stock?.code || "").trim()
    );
  }

  function firstPoi(status, result) {
    if (status !== "complete") return null;
    const pois = result?.poiList?.pois || result?.pois || [];
    return pois.length ? pois[0] : null;
  }

  function withPlugin(run) {
    const { rt, loadPlugin, ensureReady } = amap;
    return (async () => {
      await ensureReady();
      await loadPlugin("AMap.PlaceSearch");
      return run(rt);
    })();
  }

  function cached(key, factory) {
    const { rt } = amap;
    if (rt.geocodeCache[key]) return Promise.resolve(rt.geocodeCache[key]);
    if (rt.geocodeInflight[key]) return rt.geocodeInflight[key];
    rt.geocodeInflight[key] = (async () => {
      try {
        const value = await factory();
        if (value != null) rt.geocodeCache[key] = value;
        return value;
      } catch {
        return null;
      } finally {
        delete rt.geocodeInflight[key];
      }
    })();
    return rt.geocodeInflight[key];
  }

  function placeSearch(keyword, cityHint, detailed = false) {
    const kw = String(keyword || "").trim();
    if (!kw) return Promise.resolve(null);
    const key = `${cityHint || ""}|${kw}|${detailed ? "all" : "base"}`;
    return cached(key, () =>
      withPlugin(
        () =>
          new Promise((resolve) => {
            const ps = new AMap.PlaceSearch({
              pageSize: 5,
              pageIndex: 1,
              city: cityHint || "全国",
              citylimit: false,
              extensions: detailed ? "all" : "base",
            });
            ps.search(kw, (status, result) => resolve(firstPoi(status, result)));
          })
      )
    );
  }

  function getPoiDetails(poiId, cityHint) {
    const id = String(poiId || "").trim();
    if (!id) return Promise.resolve(null);
    return cached(`detail|${id}`, () =>
      withPlugin(
        () =>
          new Promise((resolve) => {
            const ps = new AMap.PlaceSearch({
              pageSize: 1,
              city: cityHint || "全国",
              extensions: "all",
            });
            ps.getDetails(id, (status, result) =>
              resolve(firstPoi(status, result))
            );
          })
      )
    );
  }

  function nearbyPois(lng, lat, cityHint) {
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
      return Promise.resolve([]);
    }
    const key = `near|${cityHint || ""}|${lng.toFixed(5)}|${lat.toFixed(5)}`;
    return cached(key, () =>
      withPlugin(
        () =>
          new Promise((resolve) => {
            const ps = new AMap.PlaceSearch({
              pageSize: 10,
              pageIndex: 1,
              city: cityHint || "全国",
              citylimit: false,
              extensions: "all",
              type: "商务住宅|公司企业|风景名胜|科教文化服务|政府机构及社会团体",
            });
            const center = new AMap.LngLat(lng, lat);
            ps.searchNearBy("公司", center, 280, (status, result) =>
              resolve(
                status === "complete"
                  ? result?.poiList?.pois || result?.pois || []
                  : []
              )
            );
          })
      )
    ).then((value) => (Array.isArray(value) ? value : []));
  }

  async function fetchServerPhotos({ poiId, lng, lat, keyword, city }) {
    if (!api || !amap.rt.webServiceReady) return [];
    const key = `srv|${poiId || ""}|${lng ?? ""}|${lat ?? ""}|${keyword || ""}`;
    const packed = await cached(key, async () => {
      const q = new URLSearchParams();
      if (poiId) q.set("poi_id", poiId);
      if (Number.isFinite(lng) && Number.isFinite(lat)) {
        q.set("lng", String(lng));
        q.set("lat", String(lat));
      }
      if (keyword) q.set("keyword", keyword);
      if (city) q.set("city", city);
      if (![...q.keys()].length) return [];
      try {
        const json = await api(`/api/map/place-photos?${q.toString()}`);
        return extractPhotoUrls(json.data?.photos || json.data, PHOTO_LIMIT);
      } catch {
        return [];
      }
    });
    return Array.isArray(packed) ? packed : [];
  }

  async function collectPhotos(poi, lng, lat, cityHint, keyword) {
    let photos = extractPhotoUrls(poi, PHOTO_LIMIT);
    if (photos.length < PHOTO_LIMIT && poi?.id) {
        const detail = await getPoiDetails(poi.id, cityHint);
      if (detail) {
        poi = { ...poi, ...detail };
        photos = extractPhotoUrls([detail, poi], PHOTO_LIMIT);
      }
    }
    if (photos.length < 3) {
      const near = await nearbyPois(lng, lat, cityHint);
      photos = extractPhotoUrls([poi, ...near, ...photos], PHOTO_LIMIT);
    }
    if (photos.length < 3) {
      const extra = await fetchServerPhotos({
        poiId: poi?.id || "",
        lng,
        lat,
        keyword,
        city: cityHint,
      });
      photos = extractPhotoUrls([...photos, ...extra], PHOTO_LIMIT);
    }
    return { poi, photos };
  }

  /**
   * @returns {Promise<{ pos:[number,number], geo:object, poi:object }|null>}
   */
  async function resolveCompanyPlace(stock, geo = {}, opts = {}) {
    const detailed = !!opts.detailed;
    const code = String(stock?.code || geo?.code || "").trim();
    const merged = {
      ...(geo || {}),
      ...(code && geoStore.get(code) ? geoStore.get(code) : {}),
      code,
    };

    const keyword = companySearchKeyword(stock, merged);
    const cityHint = merged.reg_city || merged.reg_province || "";

    if (
      detailed &&
      String(merged.geocode_source || "") === "amap_place" &&
      merged.poi_id &&
      merged.lng != null &&
      merged.lat != null
    ) {
      const pos = [Number(merged.lng), Number(merged.lat)];
      if (Number.isFinite(pos[0]) && Number.isFinite(pos[1])) {
        const seed = {
          id: merged.poi_id,
          name: merged.poi_name,
          address: merged.poi_address,
          photos: merged.poi_photos,
          location: { lng: pos[0], lat: pos[1] },
        };
        const packed = await collectPhotos(
          seed,
          pos[0],
          pos[1],
          cityHint,
          keyword
        );
        const next = { ...merged, poi_photos: packed.photos };
        if (code) geoStore.set(code, next);
        return { pos, geo: next, poi: packed.poi };
      }
    }

    let poi = await placeSearch(keyword, cityHint, detailed);
    if (!poi && stock?.name && keyword !== stock.name) {
      poi = await placeSearch(`${stock.name}股份有限公司`, cityHint, detailed);
    }
    if (!poi && stock?.name) {
      poi = await placeSearch(stock.name, cityHint, detailed);
    }

    if (poi?.location) {
      const lng = Number(poi.location.lng ?? poi.location[0]);
      const lat = Number(poi.location.lat ?? poi.location[1]);
      if (Number.isFinite(lng) && Number.isFinite(lat)) {
        let photos = extractPhotoUrls(poi, PHOTO_LIMIT);
        if (detailed) {
          const packed = await collectPhotos(poi, lng, lat, cityHint, keyword);
          poi = packed.poi;
          photos = packed.photos;
        }
        const next = {
          ...merged,
          lat,
          lng,
          coord_system: "gcj02",
          geocode_source: "amap_place",
          poi_id: poi.id || merged.poi_id || "",
          poi_name: poi.name || "",
          poi_address: composePoiAddress(poi, merged) || merged.poi_address || "",
          poi_photos: photos.length ? photos : merged.poi_photos || [],
        };
        if (code) geoStore.set(code, next);
        return { pos: [lng, lat], geo: next, poi };
      }
    }

    if (
      String(merged.geocode_source || "") === "amap_place" &&
      merged.lat != null &&
      merged.lng != null
    ) {
      const pos = [Number(merged.lng), Number(merged.lat)];
      if (Number.isFinite(pos[0]) && Number.isFinite(pos[1])) {
        let photos = extractPhotoUrls(merged.poi_photos, PHOTO_LIMIT);
        let cachedPoi = {
          id: merged.poi_id,
          name: merged.poi_name,
          address: merged.poi_address,
          photos: merged.poi_photos,
        };
        if (detailed && photos.length < 3) {
          const packed = await collectPhotos(
            cachedPoi,
            pos[0],
            pos[1],
            cityHint,
            keyword
          );
          cachedPoi = packed.poi;
          photos = packed.photos;
          const next = { ...merged, poi_photos: photos };
          if (code) geoStore.set(code, next);
          return { pos, geo: next, poi: cachedPoi };
        }
        return { pos, geo: merged, poi: cachedPoi };
      }
    }
    return null;
  }

  return { placeSearch, resolveCompanyPlace, companySearchKeyword };
}
