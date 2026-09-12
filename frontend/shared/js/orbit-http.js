(() => {
  const CACHE_NAME = "orbit-prefetch-v1";
  const STRIP = new Set(["refresh", "live"]);
  const TTL_RULES = [
    { prefix: "/api/market/tree", ttl: 90_000 },
    { prefix: "/api/market/history", ttl: 6 * 3600_000 },
    { prefix: "/api/market/shares", ttl: 90_000 },
    { prefix: "/api/market/steep", ttl: 90_000 },
    { prefix: "/api/stocks/profile", ttl: 60_000 },
    { prefix: "/api/stocks/line", ttl: 120_000 },
    { prefix: "/api/stocks/ticks", ttl: 8_000 },
    { prefix: "/api/stocks/fund-flow", ttl: 60_000 },
    { prefix: "/api/stocks/financial-report", ttl: 600_000 },
    { prefix: "/api/stocks/fund-holders", ttl: 600_000 },
    { prefix: "/api/stocks/emotion", ttl: 60_000 },
    { prefix: "/api/list/stock", ttl: 600_000 },
    { prefix: "/api/industries/", ttl: 6 * 3600_000 },
    { prefix: "/api/industries", ttl: 30 * 60_000 },
    { prefix: "/api/funds/tree", ttl: 30 * 60_000 },
    { prefix: "/api/otc-funds/tree", ttl: 30 * 60_000 },
  ];
  const DEFAULT_TTL = 60_000;

  function toUrl(input) {
    try {
      return new URL(String(input), window.location.origin);
    } catch {
      return null;
    }
  }

  function cacheKey(input) {
    const url = toUrl(input);
    if (!url) return String(input || "");
    for (const key of [...url.searchParams.keys()]) {
      if (STRIP.has(key)) url.searchParams.delete(key);
    }
    const params = [...url.searchParams.entries()].sort((a, b) => {
      if (a[0] === b[0]) return String(a[1]).localeCompare(String(b[1]));
      return a[0].localeCompare(b[0]);
    });
    url.search = "";
    for (const [key, value] of params) url.searchParams.append(key, value);
    return `${url.pathname}${url.search}`;
  }

  function hasBypass(input) {
    const url = toUrl(input);
    if (!url) return false;
    const refresh = url.searchParams.get("refresh");
    const live = url.searchParams.get("live");
    return (refresh && refresh !== "0") || (live && live !== "0");
  }

  function ttlFor(input) {
    const key = cacheKey(input);
    for (const rule of TTL_RULES) {
      if (key.startsWith(rule.prefix)) return rule.ttl;
    }
    return DEFAULT_TTL;
  }

  async function openCache() {
    if (!("caches" in window)) return null;
    try {
      return await caches.open(CACHE_NAME);
    } catch {
      return null;
    }
  }

  async function peek(input, options = {}) {
    const cache = await openCache();
    if (!cache) return null;
    try {
      const resp = await cache.match(cacheKey(input));
      if (!resp) return null;
      const packed = await resp.json();
      const age = Date.now() - Number(packed.cachedAt || 0);
      const ttl = Number(packed.ttlMs || 0);
      if (!packed.body || !Number.isFinite(age) || age < 0) return null;
      if (!options.allowStale && age > ttl) return null;
      return packed.body;
    } catch {
      return null;
    }
  }

  async function put(input, body, ttlMs) {
    const cache = await openCache();
    if (!cache || body == null) return;
    try {
      await cache.put(
        cacheKey(input),
        new Response(
          JSON.stringify({
            cachedAt: Date.now(),
            ttlMs: ttlMs || ttlFor(input),
            body,
          }),
          { headers: { "Content-Type": "application/json" } },
        ),
      );
    } catch {
      /* quota / private mode */
    }
  }

  async function fetchJson(input, options = {}) {
    const { signal, timeoutMs } = options;
    let ctrl = null;
    let timer = 0;
    let fetchSignal = signal;
    if (timeoutMs) {
      ctrl = new AbortController();
      if (signal) {
        if (signal.aborted) ctrl.abort();
        else signal.addEventListener("abort", () => ctrl.abort(), { once: true });
      }
      timer = window.setTimeout(() => ctrl.abort(), timeoutMs);
      fetchSignal = ctrl.signal;
    }
    try {
      const res = await fetch(input, { signal: fetchSignal, cache: "no-store" });
      const json = await res.json();
      if (!res.ok || json.ok === false) {
        throw new Error(json.error || `请求失败 (${res.status})`);
      }
      return json;
    } finally {
      if (timer) window.clearTimeout(timer);
    }
  }

  async function get(input, options = {}) {
    const bypass = options.bypassCache || hasBypass(input);
    if (!bypass) {
      const cached = await peek(input);
      if (cached) return cached;
    }
    const json = await fetchJson(input, options);
    if (!hasBypass(input) || options.writeCache) {
      await put(input, json, options.ttlMs || ttlFor(input));
    }
    return json;
  }

  async function prefetch(input, options = {}) {
    try {
      const cached = await peek(input);
      if (cached) return cached;
      const json = await fetchJson(input, options);
      await put(input, json, options.ttlMs || ttlFor(input));
      return json;
    } catch {
      return null;
    }
  }

  window.OrbitHttp = { cacheKey, ttlFor, peek, put, get, prefetch };
})();
