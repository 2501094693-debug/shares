(() => {
  const PRIMARY = [
    { key: "market", href: "/market", title: "行业行情 · 涨跌与资金", ico: "▣", label: "行业行情" },
    { key: "shares", href: "/shares", title: "个股行情 · 涨幅排序", ico: "▤", label: "个股行情" },
    { key: "steep", href: "/steep", title: "涨跌停 · 多日名单", ico: "↕", label: "涨跌停" },
    { key: "fund", href: "/fund", title: "基金 · ETF / LOF / 开放式", ico: "◉", label: "基金" },
    { key: "analysis", href: "/analysis", title: "研判 · 涨跌停分析 / 个股分析", ico: "▥", label: "研判" },
    { key: "gmap", href: "/gmap", title: "谷歌地图 · 全球检索", ico: "⌖", label: "谷歌" },
    { key: "industry", href: "/industry", title: "行业树 · 地图与分类", ico: "◈", label: "行业树" },
  ];

  function currentKey() {
    const path = location.pathname.replace(/\.html$/, "") || "/";
    if (path === "/" || path === "") return "world";
    if (path.startsWith("/world")) return "world";
    if (path.startsWith("/cn")) return "market";
    if (path.startsWith("/market")) return "market";
    if (path.startsWith("/shares")) return "shares";
    if (path.startsWith("/analysis") || path.startsWith("/screen")) return "analysis";
    if (path.startsWith("/steep")) return "steep";
    if (path.startsWith("/industry")) return "industry";
    if (path.startsWith("/otc-fund") || path.startsWith("/fund")) return "fund";
    if (path.startsWith("/gmap")) return "gmap";
    if (path.startsWith("/company")) return "company";
    return "";
  }

  function linkHtml(item, active) {
    const current = active ? ' aria-current="page"' : "";
    return `<a class="app-rail-link${active ? " is-active" : ""}" href="${item.href}" data-nav="${item.key}" title="${item.title}"${current}>
      <span class="app-rail-ico" aria-hidden="true">${item.ico}</span>
      <span>${item.label}</span>
    </a>`;
  }

  function render() {
    const rail = document.getElementById("appRail") || document.querySelector(".app-rail");
    if (!rail) return;

    const key = currentKey();
    const world = key === "world";

    const brand = `<a class="app-rail-brand" href="/" title="回全球行情">
      <span class="app-rail-mark">OR</span>
      <span class="app-rail-word">ORBIT</span>
    </a>`;

    const links = world
      ? linkHtml(
          { key: "world", href: "/", title: "全球市场 · 股指利率国债原油", ico: "◎", label: "全球" },
          true,
        )
      : [
          linkHtml({ key: "world", href: "/", title: "回全球行情", ico: "◎", label: "回全球" }, false),
          ...PRIMARY.map((item) => linkHtml(item, item.key === key)),
        ].join("");

    rail.setAttribute("aria-label", "主导航");
    rail.innerHTML = `${brand}<div class="app-rail-links">${links}</div>`;
    bindNavPrefetch(rail);
  }

  function bindNavPrefetch(rail) {
    if (!rail || rail.dataset.orbitNavBound === "1") return;
    rail.dataset.orbitNavBound = "1";
    let timer = 0;
    rail.addEventListener("pointerover", (event) => {
      const link = event.target.closest("[data-nav]");
      if (!link || !rail.contains(link)) return;
      const from = event.relatedTarget;
      if (from && link.contains(from)) return;
      const key = link.dataset.nav || "";
      if (!key || key === currentKey()) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        window.OrbitPrefetch?.navHover(key);
      }, 150);
    });
    rail.addEventListener("pointerout", (event) => {
      const link = event.target.closest("[data-nav]");
      if (!link || !rail.contains(link)) return;
      const to = event.relatedTarget;
      if (to && link.contains(to)) return;
      window.clearTimeout(timer);
    });
  }

  render();
})();
