/** 后端注册地 enrich 缓存（全称 / 省市区）。 */

const GEO_BATCH = 50;

export function createGeoStore({ api, onProgress }) {
  /** @type {Record<string, object>} */
  const byCode = {};
  let token = 0;

  function bumpToken() {
    token += 1;
    return token;
  }

  function currentToken() {
    return token;
  }

  function get(code) {
    return byCode[String(code || "").trim()] || null;
  }

  function set(code, row) {
    const c = String(code || "").trim();
    if (!c) return;
    byCode[c] = row;
  }

  function merge(items) {
    Object.assign(byCode, items || {});
  }

  /** 无全称的旧条目作废，强制重拉。 */
  function invalidateIncomplete() {
    for (const c of Object.keys(byCode)) {
      if (!String(byCode[c]?.full_name || "").trim()) {
        delete byCode[c];
      }
    }
  }

  async function enrichStocks(stocks, expectToken) {
    invalidateIncomplete();
    const codes = [];
    const seen = new Set();
    for (const s of stocks || []) {
      const c = String(s.code || "").trim();
      if (!c || seen.has(c) || byCode[c]) continue;
      seen.add(c);
      codes.push(c);
    }
    if (!codes.length) return;

    for (let i = 0; i < codes.length; i += GEO_BATCH) {
      if (expectToken !== token) return;
      const batch = codes.slice(i, i + GEO_BATCH);
      const done = Math.min(i + batch.length, codes.length);
      onProgress?.(`补齐注册地 ${done}/${codes.length}…`);
      const json = await api("/api/stocks/geo-enrich", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ codes: batch }),
      });
      merge(json.data?.items || {});
    }
  }

  return {
    byCode,
    bumpToken,
    currentToken,
    get,
    set,
    merge,
    enrichStocks,
  };
}
