(() => {
  const MAX_INFLIGHT = 2;
  const HOVER_MS = 350;
  const HOVER_DEEP_MS = 600;
  const BLOCKED = [/\/api\/screen\//i];

  const PAGE_IDLE = {
    world: {
      urls: ["/api/market/tree?lite=1", "/api/market/shares?lite=1", "/api/market/steep?days=15&lite=1", "/api/market/tree", "/api/market/shares"],
      docs: ["/market", "/shares", "/js/market.js", "/js/shares.js"],
    },
    market: {
      urls: ["/api/market/shares?lite=1", "/api/market/steep?days=15&lite=1"],
      docs: ["/shares", "/js/shares.js"],
    },
    shares: {
      urls: ["/api/market/steep?days=15&lite=1"],
      docs: ["/steep", "/js/steep.js"],
    },
    industry: {
      urls: ["/api/market/tree?lite=1"],
      docs: ["/market", "/js/market.js"],
    },
    steep: {
      urls: ["/api/market/tree?lite=1"],
      docs: ["/market", "/js/market.js"],
    },
    analysis: { urls: [], docs: ["/analysis", "/js/analysis.js"] },
    screen: { urls: [], docs: ["/analysis", "/js/analysis.js"] },
    fund: {
      urls: ["/api/funds/tree", "/api/otc-funds/tree"],
      docs: [],
    },
    gmap: {
      urls: ["/api/industries"],
      docs: ["/industry", "/js/industry/app.js"],
    },
    company: { urls: [], docs: [] },
  };

  const NAV_URLS = {
    world: ["/api/global/indices", "/api/global/oil"],
    market: ["/api/market/tree?lite=1", "/api/market/tree"],
    shares: ["/api/market/shares?lite=1", "/api/market/shares"],
    steep: ["/api/market/steep?days=15&lite=1", "/api/market/steep?days=15"],
    industry: ["/api/industries"],
    fund: ["/api/funds/tree", "/api/otc-funds/tree"],
    analysis: [],
    screen: [],
    gmap: ["/api/industries"],
  };

  let booted = false;
  let pageKey = "";
  let context = { stocks: [], industry: "", from: "", code: "" };
  let inflight = 0;
  const queue = [];
  const inflightKeys = new Set();
  let hoverTimer = 0;
  let hoverDeepTimer = 0;
  let hoverCode = "";

  function http() {
    return window.OrbitHttp || null;
  }

  function networkOk() {
    const conn = navigator.connection;
    if (!conn) return true;
    if (conn.saveData) return false;
    const type = String(conn.effectiveType || "");
    return type !== "2g" && type !== "slow-2g";
  }

  function canStart() {
    if (!booted) return false;
    if (document.hidden) return false;
    return networkOk();
  }

  function blocked(url) {
    return BLOCKED.some((re) => re.test(String(url || "")));
  }

  function enqueue(url, priority = 5) {
    if (!url || blocked(url)) return;
    const api = http();
    const key = api ? api.cacheKey(url) : String(url);
    if (inflightKeys.has(key)) return;
    const existing = queue.find((item) => item.key === key);
    if (existing) {
      if (priority < existing.priority) existing.priority = priority;
      queue.sort((a, b) => a.priority - b.priority);
      return;
    }
    queue.push({ url, key, priority });
    queue.sort((a, b) => a.priority - b.priority);
    pump();
  }

  async function startItem(item) {
    const api = http();
    inflightKeys.add(item.key);
    try {
      if (!api || !networkOk()) return;
      const cached = await api.peek(item.url);
      if (cached) return;
      await api.prefetch(item.url);
    } catch {
      /* ignore prefetch errors */
    } finally {
      inflightKeys.delete(item.key);
      inflight -= 1;
      pump();
    }
  }

  function pump() {
    if (!canStart() || !http()) return;
    while (inflight < MAX_INFLIGHT && queue.length) {
      const item = queue.shift();
      if (!item || inflightKeys.has(item.key)) continue;
      inflight += 1;
      void startItem(item);
    }
  }

  function companyUrls(code, deep = false) {
    const value = String(code || "").trim();
    if (!value) return [];
    const enc = encodeURIComponent(value);
    const first = [
      `/api/stocks/profile?code=${enc}`,
      `/api/stocks/line?code=${enc}&period=day&adjust=qfq&limit=180`,
    ];
    if (!deep) return first;
    return first.concat([
      `/api/stocks/ticks?code=${enc}`,
      `/api/stocks/fund-flow?code=${enc}&scope=daily&limit=120`,
    ]);
  }

  function topCodes(stocks, limit = 3) {
    return (stocks || [])
      .map((item) => {
        if (typeof item === "string") return { code: item, score: 0 };
        return {
          code: item.code || item.symbol || "",
          score: Math.abs(Number(item.change_pct ?? item.change_1d ?? 0)) || 0,
        };
      })
      .filter((item) => item.code)
      .sort((a, b) => b.score - a.score)
      .slice(0, limit)
      .map((item) => item.code);
  }

  function prefetchDocs(hrefs) {
    for (const href of hrefs || []) {
      if (!href || document.querySelector(`link[data-orbit-prefetch="${href}"]`)) continue;
      const link = document.createElement("link");
      link.rel = "prefetch";
      link.href = href;
      link.dataset.orbitPrefetch = href;
      document.head.appendChild(link);
    }
  }

  function applyContext() {
    if (pageKey === "company") {
      const from = context.from || "";
      if (from === "market") enqueue("/api/market/tree", 2);
      else if (from === "shares") enqueue("/api/market/shares", 2);
      else if (from === "industry" && context.industry) {
        enqueue(`/api/industries/${encodeURIComponent(context.industry)}/stocks`, 2);
      } else if (from === "steep") {
        enqueue("/api/market/steep?days=15&lite=1", 2);
        enqueue("/api/market/steep?days=15", 3);
      }
      else if (from === "fund" || from === "otc-fund") {
        enqueue("/api/funds/tree", 2);
        enqueue("/api/otc-funds/tree", 2);
      }
      return;
    }
    topCodes(context.stocks, 3).forEach((code, index) => {
      companyUrls(code, false).forEach((url) => enqueue(url, 4 + index));
    });
  }

  function runIdle() {
    const spec = PAGE_IDLE[pageKey];
    if (spec) {
      (spec.urls || []).forEach((url, index) => enqueue(url, 2 + index));
      prefetchDocs(spec.docs);
    }
    applyContext();
  }

  function boot(key, ctx = {}) {
    pageKey = key || pageKey;
    context = { ...context, ...ctx };
    if (booted) {
      applyContext();
      return;
    }
    booted = true;
    runIdle();
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) pump();
    });
  }

  function intent(ctx = {}) {
    context = { ...context, ...ctx };
    if (!booted) return;
    applyContext();
  }

  function hover(code) {
    const value = String(code || "").trim();
    if (!value || !booted) return;
    window.clearTimeout(hoverTimer);
    window.clearTimeout(hoverDeepTimer);
    hoverCode = value;
    hoverTimer = window.setTimeout(() => {
      if (hoverCode !== value || !canStart()) return;
      companyUrls(value, false).forEach((url) => enqueue(url, 1));
    }, HOVER_MS);
    hoverDeepTimer = window.setTimeout(() => {
      if (hoverCode !== value || !canStart()) return;
      companyUrls(value, true).forEach((url) => enqueue(url, 1));
    }, HOVER_DEEP_MS);
  }

  function hoverLeave() {
    window.clearTimeout(hoverTimer);
    window.clearTimeout(hoverDeepTimer);
    hoverCode = "";
  }

  function bindHover(root, selector = "[data-code]") {
    if (!root || root.dataset.orbitHoverBound === "1") return;
    root.dataset.orbitHoverBound = "1";
    root.addEventListener("pointerover", (event) => {
      const el = event.target.closest(selector);
      if (!el || !root.contains(el)) return;
      const from = event.relatedTarget;
      if (from && el.contains(from)) return;
      if (el.dataset.code) hover(el.dataset.code);
    });
    root.addEventListener("pointerout", (event) => {
      const el = event.target.closest(selector);
      if (!el || !root.contains(el)) return;
      const to = event.relatedTarget;
      if (to && el.contains(to)) return;
      hoverLeave();
    });
  }

  function navHover(key) {
    if (!booted) return;
    (NAV_URLS[key] || []).forEach((url) => enqueue(url, 0));
    const spec = PAGE_IDLE[key];
    if (spec) prefetchDocs(spec.docs);
  }

  function prefetchTab(panel) {
    const code = String(context.code || "").trim();
    if (!code || !booted) return;
    const enc = encodeURIComponent(code);
    if (panel === "emotion") {
      enqueue(`/api/stocks/emotion?code=${enc}&source=eastmoney&channel=scores`, 1);
    } else if (panel === "news") {
      enqueue(`/api/stocks/financial-report?code=${enc}&scope=all&limit=24`, 1);
    } else if (panel === "others") {
      enqueue(`/api/list/stock?code=${enc}`, 1);
      enqueue(`/api/stocks/fund-holders?code=${enc}`, 1);
    }
  }

  window.OrbitPrefetch = {
    boot,
    intent,
    hover,
    hoverLeave,
    bindHover,
    navHover,
    prefetchTab,
    enqueue,
  };
})();
