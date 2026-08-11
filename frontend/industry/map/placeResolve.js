/** 用公司全称做高德 PlaceSearch，得到 GCJ-02 坐标。 */

export function createPlaceResolver({ amap, geoStore }) {
  function companySearchKeyword(stock, geo) {
    return (
      String(geo?.full_name || "").trim() ||
      String(stock?.name || "").trim() ||
      String(stock?.code || "").trim()
    );
  }

  function placeSearch(keyword, cityHint) {
    const kw = String(keyword || "").trim();
    if (!kw) return Promise.resolve(null);
    const key = `${cityHint || ""}|${kw}`;
    const { rt, loadPlugin, ensureReady } = amap;
    if (rt.geocodeCache[key]) return Promise.resolve(rt.geocodeCache[key]);
    if (rt.geocodeInflight[key]) return rt.geocodeInflight[key];

    rt.geocodeInflight[key] = (async () => {
      try {
        await ensureReady();
        await loadPlugin("AMap.PlaceSearch");
        const poi = await new Promise((resolve) => {
          const ps = new AMap.PlaceSearch({
            pageSize: 5,
            pageIndex: 1,
            city: cityHint || "全国",
            citylimit: false,
            extensions: "base",
          });
          ps.search(kw, (status, result) => {
            if (status === "complete" && result?.poiList?.pois?.length) {
              resolve(result.poiList.pois[0]);
              return;
            }
            resolve(null);
          });
        });
        if (poi) rt.geocodeCache[key] = poi;
        return poi;
      } catch {
        return null;
      } finally {
        delete rt.geocodeInflight[key];
      }
    })();

    return rt.geocodeInflight[key];
  }

  /**
   * @returns {Promise<{ pos:[number,number], geo:object, poi:object }|null>}
   */
  async function resolveCompanyPlace(stock, geo = {}) {
    const code = String(stock?.code || geo?.code || "").trim();
    const merged = {
      ...(geo || {}),
      ...(code && geoStore.get(code) ? geoStore.get(code) : {}),
      code,
    };

    if (
      String(merged.geocode_source || "") === "amap_place" &&
      merged.lat != null &&
      merged.lng != null
    ) {
      const pos = [Number(merged.lng), Number(merged.lat)];
      if (Number.isFinite(pos[0]) && Number.isFinite(pos[1])) {
        return {
          pos,
          geo: merged,
          poi: { name: merged.poi_name, address: merged.poi_address },
        };
      }
    }

    const keyword = companySearchKeyword(stock, merged);
    const cityHint = merged.reg_city || merged.reg_province || "";
    let poi = await placeSearch(keyword, cityHint);
    if (!poi && stock?.name && keyword !== stock.name) {
      poi = await placeSearch(`${stock.name}股份有限公司`, cityHint);
    }
    if (!poi && stock?.name) {
      poi = await placeSearch(stock.name, cityHint);
    }
    if (!poi?.location) return null;

    const lng = Number(poi.location.lng ?? poi.location[0]);
    const lat = Number(poi.location.lat ?? poi.location[1]);
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null;

    const next = {
      ...merged,
      lat,
      lng,
      coord_system: "gcj02",
      geocode_source: "amap_place",
      poi_name: poi.name || "",
      poi_address:
        poi.address ||
        [poi.pname, poi.cityname, poi.adname].filter(Boolean).join("") ||
        "",
    };
    if (code) geoStore.set(code, next);
    return { pos: [lng, lat], geo: next, poi };
  }

  return { placeSearch, resolveCompanyPlace, companySearchKeyword };
}
