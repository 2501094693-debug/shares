(() => {
  const VENUE_LISTED = "listed";
  const VENUE_OTC = "otc";

  const GROUP_LABELS = {
    etf: "ETF（场内）",
    lof: "LOF（场内）",
    open: "开放式（场外）",
  };

  const OTC_TYPE_MAP = [
    ["货币", "hb"],
    ["FOF", "fof"],
    ["QDII", "qdii"],
    ["指数", "zs"],
    ["债券", "zq"],
    ["混合", "hh"],
    ["股票", "gp"],
  ];

  const LISTED_SORTS = [
    { key: "change_pct", label: "涨跌" },
    { key: "amount", label: "成交额" },
    { key: "premium", label: "折价率" },
    { key: "main_net", label: "主力" },
  ];
  const OTC_SORTS = [
    { key: "day_pct", label: "日涨跌" },
    { key: "month_pct", label: "近1月" },
    { key: "year_pct", label: "近1年" },
  ];
  const SEARCH_SORTS = [
    { key: "day_change", label: "日涨跌" },
    { key: "month_pct", label: "近1月" },
    { key: "year_pct", label: "近1年" },
  ];

  const LISTED_COLUMNS = [
    { key: "name", label: "名称" },
    { key: "price", label: "最新", num: true },
    { key: "change_pct", label: "涨跌", num: true, tone: true },
    { key: "amount", label: "成交额", num: true },
    { key: "premium", label: "折价率", num: true, tone: true },
    { key: "main_net", label: "主力", num: true, tone: true },
    { key: "turnover", label: "换手", num: true },
  ];
  const OTC_COLUMNS = [
    { key: "name", label: "名称" },
    { key: "unit_nav", label: "净值", num: true },
    { key: "day_pct", label: "日涨跌", num: true, tone: true },
    { key: "month_pct", label: "近1月", num: true, tone: true },
    { key: "year_pct", label: "近1年", num: true, tone: true },
    { key: "type_name", label: "类型" },
  ];
  const SEARCH_COLUMNS = [
    { key: "name", label: "名称" },
    { key: "price_or_nav", label: "最新/净值", num: true },
    { key: "day_change", label: "日涨跌", num: true, tone: true },
    { key: "month_pct", label: "近1月", num: true, tone: true },
    { key: "year_pct", label: "近1年", num: true, tone: true },
    { key: "type_name", label: "类型" },
  ];

  const state = {
    tree: [],
    categories: [],
    selectedCode: "",
    selectedName: "",
    venue: VENUE_LISTED,
    items: [],
    searchMode: false,
    market: "",
    sort: "change_pct",
    filter: "",
    page: 1,
    pageSize: 50,
    total: 0,
    fetching: false,
    listedIndex: null,
    otcIndex: null,
    holdingsCode: "",
    holdingsLoading: false,
    holdingsVenue: "",
  };

  const $ = (id) => document.getElementById(id);

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setLive(kind) {
    const el = $("liveDot");
    if (!el) return;
    el.dataset.state = kind;
    el.textContent = kind === "live" ? "LIVE" : kind === "busy" ? "SYNC" : "IDLE";
  }

  function showError(message) {
    const box = $("errorBox");
    if (!message) {
      box.classList.add("hidden");
      box.textContent = "";
      return;
    }
    box.textContent = message;
    box.classList.remove("hidden");
  }

  function setLoading(on) {
    $("loading").classList.toggle("hidden", !on);
    if (on) showError("");
  }

  async function api(path, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    if (window.OrbitHttp && method === "GET") return OrbitHttp.get(path, options);
    const res = await fetch(path, options);
    const json = await res.json();
    if (!res.ok || !json.ok) {
      throw new Error(json.error || `请求失败 (${res.status})`);
    }
    return json;
  }

  function parsePct(value) {
    if (value == null || value === "") return null;
    const n = parseFloat(String(value).replace("%", ""));
    return Number.isFinite(n) ? n : null;
  }

  function parseYi(value) {
    if (value == null || value === "") return null;
    const text = String(value).trim();
    const sign = text.startsWith("-") ? -1 : 1;
    const abs = text.replace(/^-/, "");
    if (abs.endsWith("亿")) {
      const n = parseFloat(abs);
      return Number.isFinite(n) ? sign * n * 1e8 : null;
    }
    if (abs.endsWith("万")) {
      const n = parseFloat(abs);
      return Number.isFinite(n) ? sign * n * 1e4 : null;
    }
    const n = parseFloat(abs);
    return Number.isFinite(n) ? sign * n : null;
  }

  function tone(value) {
    const n = parsePct(value);
    if (n == null || n === 0) return "flat";
    return n > 0 ? "up" : "down";
  }

  function rowVenue(row) {
    return row?.venue || state.venue;
  }

  function dayChange(row) {
    return row.change_pct || row.day_pct || "";
  }

  function priceOrNav(row) {
    return row.price || row.unit_nav || "—";
  }

  function sortValue(row, field) {
    if (field === "day_change") return parsePct(dayChange(row));
    if (field === "change_pct" || field === "premium" || field === "turnover") {
      return parsePct(row[field]);
    }
    if (field === "day_pct" || field === "month_pct" || field === "year_pct") {
      return parsePct(row[field]);
    }
    if (field === "amount" || field === "main_net") {
      return parseYi(row[field]);
    }
    if (field === "price") {
      const n = parseFloat(row.price);
      return Number.isFinite(n) ? n : null;
    }
    if (field === "unit_nav" || field === "price_or_nav") {
      const n = parseFloat(priceOrNav(row));
      return Number.isFinite(n) ? n : null;
    }
    return null;
  }

  function categoryLabel(code) {
    const hit = state.categories.find((item) => item.code === code);
    return hit?.name || code || "";
  }

  function categoryMeta(code) {
    return state.categories.find((item) => item.code === code) || null;
  }

  function findLeaf(code) {
    if (!code) return null;
    for (const group of state.tree) {
      if (group.code === code) return group.children?.[0] || null;
      for (const child of group.children || []) {
        if (child.code === code) return child;
      }
    }
    return null;
  }

  function venueOfCode(code) {
    return categoryMeta(code)?.venue || findLeaf(code)?.venue || state.venue;
  }

  function readQueryCat() {
    return new URLSearchParams(location.search).get("cat") || "";
  }

  function syncQuery(code) {
    const url = new URL(location.href);
    if (code) url.searchParams.set("cat", code);
    else url.searchParams.delete("cat");
    const next = `${url.pathname}${url.search}${url.hash}`;
    if (`${location.pathname}${location.search}${location.hash}` !== next) {
      history.replaceState(null, "", next);
    }
  }

  function companyHref(row) {
    const qs = new URLSearchParams({
      code: row.code || "",
      name: row.name || "",
      from: "fund",
    });
    const cat = row.category_code || state.selectedCode;
    if (cat) qs.set("cat", cat);
    return `/company.html?${qs}`;
  }

  function stockHref(row, fundVenue) {
    const venue = fundVenue || rowVenue(row);
    const qs = new URLSearchParams({
      code: row.code || "",
      name: row.name || "",
      from: venue === VENUE_OTC ? "otc-fund" : "fund",
    });
    if (state.selectedCode) qs.set("cat", state.selectedCode);
    else if (venue === VENUE_OTC) qs.set("cat", "gp");
    return `/company.html?${qs}`;
  }

  function inferCategory(row) {
    if (row.category_code) return row.category_code;
    if (rowVenue(row) !== VENUE_OTC) return "";
    const type = String(row.type_name || "");
    for (const [keyword, code] of OTC_TYPE_MAP) {
      if (type.includes(keyword)) return code;
    }
    return "";
  }

  function currentColumns() {
    if (state.searchMode) return SEARCH_COLUMNS;
    return state.venue === VENUE_OTC ? OTC_COLUMNS : LISTED_COLUMNS;
  }

  function currentSorts() {
    if (state.searchMode) return SEARCH_SORTS;
    return state.venue === VENUE_OTC ? OTC_SORTS : LISTED_SORTS;
  }

  function isOtcCategoryMode() {
    return !state.searchMode && state.venue === VENUE_OTC;
  }

  function applyVenueChrome() {
    $("marketSeg")?.classList.toggle("hidden", state.searchMode || state.venue !== VENUE_LISTED);
    const sorts = currentSorts();
    if (!sorts.some((item) => item.key === state.sort)) {
      state.sort = sorts[0].key;
    }
    $("sortSeg").innerHTML = sorts
      .map(
        (item) =>
          `<button type="button" data-sort="${esc(item.key)}" class="${
            item.key === state.sort ? "is-active" : ""
          }">${esc(item.label)}</button>`
      )
      .join("");
    $("tableHead").innerHTML = `<tr>${currentColumns()
      .map((col) => `<th${col.num ? ' class="num"' : ""}>${esc(col.label)}</th>`)
      .join("")}</tr>`;
  }

  function setHoldingsError(message) {
    const box = $("holdingsError");
    if (!box) return;
    if (!message) {
      box.classList.add("hidden");
      box.textContent = "";
      return;
    }
    box.textContent = message;
    box.classList.remove("hidden");
  }

  function setHoldingsLoading(on) {
    $("holdingsLoading")?.classList.toggle("hidden", !on);
    if (on) setHoldingsError("");
  }

  function closeHoldings() {
    state.holdingsCode = "";
    state.holdingsVenue = "";
    $("holdingsPane")?.classList.add("hidden");
    $("fundLayout")?.classList.remove("has-holdings");
    $("tableBody")?.querySelectorAll("tr.fund-row.is-active").forEach((el) => {
      el.classList.remove("is-active");
    });
    setHoldingsError("");
    setHoldingsLoading(false);
  }

  function renderHoldings(data, fundVenue) {
    const holdings = data?.holdings || [];
    const industries = data?.industries || [];
    const title = data?.name || data?.code || "持仓详情";
    const metaParts = [data?.code || ""];
    if (data?.market) metaParts.push(data.market);
    if (data?.report_date) metaParts.push(`报告期 ${data.report_date}`);
    $("holdingsTitle").textContent = title;
    $("holdingsMeta").textContent = metaParts.filter(Boolean).join(" · ");

    const holdingsBody = $("holdingsBody");
    if (!holdings.length) {
      holdingsBody.innerHTML = `<tr class="is-empty"><td colspan="4">暂无重仓股数据</td></tr>`;
    } else {
      holdingsBody.innerHTML = holdings
        .map(
          (row) => `
          <tr data-code="${esc(row.code || "")}">
            <td>
              <a class="stock-link" href="${esc(stockHref(row, fundVenue))}">
                <span class="fund-name">${esc(row.name || row.code)}</span>
              </a>
              <span class="market-stock-code">${esc(row.code)}${row.market ? ` · ${esc(row.market)}` : ""}</span>
            </td>
            <td class="num">${esc(row.weight || "—")}</td>
            <td>${esc(row.industry || "—")}</td>
            <td class="num">${esc(row.change_type ? `${row.change_type} ${row.change_weight || ""}`.trim() : "—")}</td>
          </tr>`
        )
        .join("");
    }

    const industryBody = $("industryBody");
    if (!industries.length) {
      industryBody.innerHTML = `<tr class="is-empty"><td colspan="4">暂无行业分布数据</td></tr>`;
    } else {
      industryBody.innerHTML = industries
        .map(
          (row) => `
          <tr>
            <td>${esc(row.name || row.code || "—")}</td>
            <td class="num">${esc(row.weight || "—")}</td>
            <td class="num">${esc(row.peer_avg || "—")}</td>
            <td class="num" data-tone="${tone(row.peer_diff)}">${esc(row.peer_diff || "—")}</td>
          </tr>`
        )
        .join("");
    }
  }

  async function openHoldings(row) {
    if (!row?.code || state.holdingsLoading) return;
    const fundVenue = rowVenue(row);
    state.holdingsCode = row.code;
    state.holdingsVenue = fundVenue;
    if (state.searchMode) highlightCategory(inferCategory(row));
    $("holdingsPane")?.classList.remove("hidden");
    $("fundLayout")?.classList.add("has-holdings");
    $("tableBody")?.querySelectorAll("tr.fund-row").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.code === row.code);
    });

    setHoldingsLoading(true);
    $("holdingsTitle").textContent = row.name || row.code;
    $("holdingsMeta").textContent = `${row.code}${row.market ? ` · ${row.market}` : ""}`;
    try {
      const json = await api(`/api/funds/${encodeURIComponent(row.code)}/holdings`);
      renderHoldings(
        { ...json.data, name: json.data?.name || row.name, market: row.market },
        fundVenue
      );
      setHoldingsError("");
    } catch (err) {
      setHoldingsError(err.message || String(err));
    } finally {
      setHoldingsLoading(false);
    }
  }

  function tagVenue(nodes, venue) {
    return (nodes || []).map((node) => ({
      ...node,
      venue,
      children: node.children ? tagVenue(node.children, venue) : undefined,
    }));
  }

  function mergeTrees(listedTree, otcTree) {
    const listed = (listedTree || []).map((group) => ({
      ...group,
      name: GROUP_LABELS[group.code] || group.name,
      venue: VENUE_LISTED,
      children: tagVenue(group.children, VENUE_LISTED),
    }));
    const otcRoot = otcTree?.[0];
    const otc = otcRoot
      ? [
          {
            ...otcRoot,
            code: "open",
            name: GROUP_LABELS.open,
            venue: VENUE_OTC,
            children: tagVenue(otcRoot.children, VENUE_OTC),
          },
        ]
      : [];
    return [...listed, ...otc];
  }

  function mergeCategories(listedCats, otcCats) {
    return [
      ...(listedCats || []).map((item) => ({ ...item, venue: VENUE_LISTED })),
      ...(otcCats || []).map((item) => ({ ...item, venue: VENUE_OTC })),
    ];
  }

  function countCategories(tree) {
    let n = 0;
    for (const group of tree) n += (group.children || []).length;
    return n;
  }

  function renderTree() {
    const root = $("tree");
    root.innerHTML = "";
    for (const group of state.tree) {
      root.appendChild(buildGroupNode(group));
    }
    $("treeMeta").textContent = `${state.tree.length} 大类 · ${countCategories(state.tree)} 分类`;
  }

  function buildGroupNode(group) {
    const wrap = document.createElement("div");
    wrap.className = "tree-item";

    const row = document.createElement("button");
    row.type = "button";
    row.className = "tree-row level-1";
    row.dataset.code = group.code;
    row.dataset.venue = group.venue || "";

    const chevron = document.createElement("span");
    chevron.className = "chevron open";
    chevron.textContent = "▸";

    const label = document.createElement("span");
    label.textContent = group.name;

    const count = document.createElement("span");
    count.className = "count";
    count.textContent = group.count ?? "";

    row.append(chevron, label, count);
    wrap.appendChild(row);

    const childBox = document.createElement("div");
    childBox.className = "children open";
    for (const child of group.children || []) {
      childBox.appendChild(buildCategoryNode(child));
    }
    wrap.appendChild(childBox);

    row.addEventListener("click", () => {
      const open = childBox.classList.toggle("open");
      chevron.classList.toggle("open", open);
    });

    return wrap;
  }

  function buildCategoryNode(node) {
    const wrap = document.createElement("div");
    wrap.className = "tree-item";

    const row = document.createElement("button");
    row.type = "button";
    row.className = "tree-row level-2";
    row.dataset.code = node.code;
    row.dataset.venue = node.venue || "";
    if (state.selectedCode === node.code && !state.searchMode) {
      row.classList.add("active");
    }

    const chevron = document.createElement("span");
    chevron.className = "chevron";
    chevron.textContent = "·";

    const label = document.createElement("span");
    label.textContent = node.name;

    const count = document.createElement("span");
    count.className = "count";
    count.textContent = node.count ?? "";

    row.append(chevron, label, count);
    wrap.appendChild(row);

    row.addEventListener("click", () => {
      selectCategory(node.code, node.name, row);
    });

    return wrap;
  }

  function clearTreeActive() {
    $("tree")?.querySelectorAll(".tree-row.active").forEach((el) => {
      el.classList.remove("active");
    });
  }

  function highlightCategory(code) {
    clearTreeActive();
    if (!code) return;
    $("tree")?.querySelector(`.tree-row[data-code="${code}"]`)?.classList.add("active");
  }

  function treeRow(code) {
    return $("tree")?.querySelector(`.tree-row[data-code="${code}"]`);
  }

  function changeField() {
    if (state.searchMode) return "day_change";
    return state.venue === VENUE_OTC ? "day_pct" : "change_pct";
  }

  function renderSummary() {
    const items = visibleItems(false);
    const field = changeField();
    let up = 0;
    let down = 0;
    for (const row of items) {
      const n = parsePct(field === "day_change" ? dayChange(row) : row[field]);
      if (n == null || n === 0) continue;
      if (n > 0) up += 1;
      else down += 1;
    }
    const flat = items.length - up - down;
    $("summaryBar").innerHTML = `
      <span>共 <strong>${items.length}</strong> 只</span>
      <span class="is-up">涨 ${up}</span>
      <span class="is-down">跌 ${down}</span>
      <span>平 ${flat}</span>`;
  }

  function renderIndexMeta() {
    const listed = state.listedIndex;
    const otc = state.otcIndex;
    if (state.searchMode) {
      const parts = [];
      if (listed) parts.push(`场内 ${listed.count || 0}`);
      if (otc) parts.push(`场外 ${otc.count || 0}`);
      $("indexMeta").textContent = parts.join(" · ");
      return;
    }
    const status = state.venue === VENUE_OTC ? otc : listed;
    if (!status) {
      $("indexMeta").textContent = "";
      return;
    }
    const prefix = state.venue === VENUE_OTC ? "场外索引" : "场内索引";
    const parts = [`${prefix} ${status.count || 0}`];
    if (status.complete) parts.push("已完整");
    else if (status.building) parts.push("构建中");
    if (status.updated_at) parts.push(status.updated_at);
    $("indexMeta").textContent = parts.join(" · ");
  }

  function haystack(row) {
    return [
      row.code,
      row.name,
      row.market,
      row.type_name,
      row.venue === VENUE_OTC ? "场外" : "场内",
      categoryLabel(row.category_code),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
  }

  function visibleItems(paginate = true) {
    const q = state.filter.trim().toLowerCase();
    let rows = state.items.slice();
    if (q) rows = rows.filter((row) => haystack(row).includes(q));

    const field = state.sort;
    rows.sort((a, b) => {
      const va = sortValue(a, field);
      const vb = sortValue(b, field);
      if (va == null && vb == null) return String(a.code).localeCompare(String(b.code));
      if (va == null) return 1;
      if (vb == null) return -1;
      return vb - va;
    });

    if (!paginate || isOtcCategoryMode()) return rows;

    const totalPages = Math.max(1, Math.ceil(rows.length / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;
    const start = (state.page - 1) * state.pageSize;
    return rows.slice(start, start + state.pageSize);
  }

  function filteredCount() {
    const q = state.filter.trim().toLowerCase();
    if (!q) return state.items.length;
    return state.items.filter((row) => haystack(row).includes(q)).length;
  }

  function cellValue(row, col) {
    if (col.key === "name") return "";
    if (col.key === "price_or_nav") return priceOrNav(row);
    if (col.key === "day_change") return dayChange(row) || "—";
    if (col.key === "type_name") {
      return row.type_name || categoryLabel(row.category_code) || "—";
    }
    return row[col.key] || "—";
  }

  function renderNameCell(row) {
    const venue = rowVenue(row);
    const badge = state.searchMode
      ? `<span class="fund-venue-tag">${venue === VENUE_OTC ? "场外" : "场内"}</span>`
      : "";
    const name = `<span class="fund-name-row"><span class="fund-name">${esc(
      row.name || row.code
    )}</span>${badge}</span>`;
    const meta = `<span class="market-stock-code">${esc(row.code)}${
      row.market ? ` · ${esc(row.market)}` : ""
    }</span>`;
    if (venue === VENUE_LISTED) {
      return `<a class="fund-name-link" href="${esc(companyHref(row))}">${name}</a>${meta}`;
    }
    return `${name}${meta}`;
  }

  function renderList() {
    const columns = currentColumns();
    const pageRows = visibleItems(true);
    const localTotal = filteredCount();
    const total = isOtcCategoryMode() && !state.filter.trim() ? state.total : localTotal;
    const pageSource = isOtcCategoryMode() ? state.total : localTotal;
    const totalPages = Math.max(1, Math.ceil(pageSource / state.pageSize));

    if (state.searchMode) {
      $("listTitle").textContent = "搜索结果";
      $("listMeta").textContent = `场内 + 场外 · ${total} 条`;
    } else if (state.selectedCode) {
      $("listTitle").textContent = state.selectedName || categoryLabel(state.selectedCode);
      $("listMeta").textContent = `${categoryLabel(state.selectedCode)} · ${
        isOtcCategoryMode() ? `共 ${state.total}` : total
      } 只`;
    } else {
      $("listTitle").textContent = "基金列表";
      $("listMeta").textContent = "选择左侧分类，或在顶部搜索";
    }

    const body = $("tableBody");
    if (!pageRows.length) {
      body.innerHTML = `<tr class="is-empty"><td colspan="${columns.length}">${
        state.items.length ? "没有匹配的基金" : "暂无数据，请选择分类或搜索"
      }</td></tr>`;
      $("pageInfo").textContent = total ? `0 / ${total}` : "";
      $("prevPage").disabled = true;
      $("nextPage").disabled = true;
      renderSummary();
      return;
    }

    body.innerHTML = pageRows
      .map((row) => {
        const cells = columns
          .map((col) => {
            if (col.key === "name") return `<td>${renderNameCell(row)}</td>`;
            const value = cellValue(row, col);
            const toneAttr = col.tone ? ` data-tone="${tone(value)}"` : "";
            const numClass = col.num ? ' class="num"' : "";
            return `<td${numClass}${toneAttr}>${esc(value)}</td>`;
          })
          .join("");
        return `<tr class="is-row fund-row" data-code="${esc(row.code)}" data-venue="${esc(
          rowVenue(row)
        )}">${cells}</tr>`;
      })
      .join("");

    $("pageInfo").textContent = `第 ${state.page}/${totalPages} 页 · ${
      isOtcCategoryMode() ? state.total : total
    } 只`;
    $("prevPage").disabled = state.page <= 1;
    $("nextPage").disabled = state.page >= totalPages;
    renderSummary();
  }

  function rememberIndex(listed, otc) {
    if (listed) state.listedIndex = listed;
    if (otc) state.otcIndex = otc;
    renderIndexMeta();
  }

  async function loadTree(force = false) {
    const suffix = force ? "?refresh=1" : "";
    const [listedRes, otcRes] = await Promise.allSettled([
      api(`/api/funds/tree${suffix}`),
      api(`/api/otc-funds/tree${suffix}`),
    ]);
    if (listedRes.status === "rejected" && otcRes.status === "rejected") {
      throw listedRes.reason;
    }
    const listedJson = listedRes.status === "fulfilled" ? listedRes.value : { data: [], categories: [] };
    const otcJson = otcRes.status === "fulfilled" ? otcRes.value : { data: [], categories: [] };
    state.tree = mergeTrees(listedJson.data, otcJson.data);
    state.categories = mergeCategories(listedJson.categories, otcJson.categories);
    rememberIndex(listedJson.index, otcJson.index);
    renderTree();
    if (listedRes.status === "rejected") {
      showError(listedRes.reason.message || "场内分类加载失败");
    } else if (otcRes.status === "rejected") {
      showError(otcRes.reason.message || "场外分类加载失败");
    }
  }

  async function loadIndexStatus() {
    const [listed, otc] = await Promise.allSettled([
      api("/api/funds/index/status"),
      api("/api/otc-funds/index/status"),
    ]);
    rememberIndex(
      listed.status === "fulfilled" ? listed.value.data : null,
      otc.status === "fulfilled" ? otc.value.data : null
    );
  }

  async function selectCategory(code, name, rowEl) {
    if (state.fetching) return;
    const leaf = findLeaf(code) || { code, name, venue: venueOfCode(code) };
    state.searchMode = false;
    state.selectedCode = leaf.code;
    state.selectedName = name || leaf.name || categoryLabel(leaf.code);
    state.venue = leaf.venue || venueOfCode(leaf.code);
    state.page = 1;
    state.filter = "";
    $("filterInput").value = "";
    $("nameInput").value = "";
    $("codeInput").value = "";
    closeHoldings();
    applyVenueChrome();
    syncQuery(leaf.code);
    highlightCategory(leaf.code);
    rowEl?.classList.add("active");
    await loadCategoryPage(false);
  }

  async function loadListedPage(force = false) {
    const qs = force ? "?refresh=1" : "";
    const json = await api(`/api/funds/${encodeURIComponent(state.selectedCode)}/list${qs}`);
    const payload = json.data || {};
    state.items = (payload.items || []).map((row) => ({ ...row, venue: VENUE_LISTED }));
    state.total = Number(payload.total || state.items.length);
    rememberIndex(json.index, null);
  }

  async function loadOtcPage(force = false) {
    const params = new URLSearchParams({
      page: String(state.page),
      page_size: String(state.pageSize),
    });
    if (force) params.set("refresh", "1");
    const json = await api(
      `/api/otc-funds/category/${encodeURIComponent(state.selectedCode)}/list?${params}`
    );
    const payload = json.data || {};
    state.items = (payload.items || []).map((row) => ({ ...row, venue: VENUE_OTC }));
    state.total = Number(payload.total || state.items.length);
    rememberIndex(null, json.index);
  }

  async function loadCategoryPage(force = false) {
    if (!state.selectedCode || state.searchMode) return;
    setLoading(true);
    setLive("busy");
    try {
      if (state.venue === VENUE_OTC) await loadOtcPage(force);
      else await loadListedPage(force);
      applyVenueChrome();
      renderList();
      setLive("live");
      showError("");
    } catch (err) {
      showError(err.message || String(err));
      setLive("idle");
    } finally {
      setLoading(false);
    }
  }

  function markSearchRows(rows, venue) {
    return (rows || []).map((row) => ({
      ...row,
      venue,
      unit_nav: row.unit_nav || "",
      day_pct: row.day_pct || row.change_pct || "",
      month_pct: row.month_pct || "",
      year_pct: row.year_pct || "",
    }));
  }

  async function runSearch() {
    const name = $("nameInput").value.trim();
    const code = $("codeInput").value.trim();
    if (!name && !code) {
      if (state.selectedCode) {
        const row = treeRow(state.selectedCode);
        await selectCategory(state.selectedCode, state.selectedName, row);
      }
      return;
    }

    if (state.fetching) return;
    state.searchMode = true;
    state.page = 1;
    clearTreeActive();
    applyVenueChrome();

    const listedParams = new URLSearchParams();
    const otcParams = new URLSearchParams();
    if (name) {
      listedParams.set("name", name);
      otcParams.set("name", name);
    }
    if (code) {
      listedParams.set("code", code);
      otcParams.set("code", code);
    }
    if (state.market) listedParams.set("market", state.market);
    listedParams.set("limit", "500");
    otcParams.set("limit", "500");

    setLoading(true);
    setLive("busy");
    try {
      const [listedRes, otcRes] = await Promise.allSettled([
        api(`/api/funds/search?${listedParams}`),
        api(`/api/otc-funds/search?${otcParams}`),
      ]);
      if (listedRes.status === "rejected" && otcRes.status === "rejected") {
        throw listedRes.reason;
      }
      const listedJson = listedRes.status === "fulfilled" ? listedRes.value : { data: [] };
      const otcJson = otcRes.status === "fulfilled" ? otcRes.value : { data: [] };
      state.items = [
        ...markSearchRows(listedJson.data, VENUE_LISTED),
        ...markSearchRows(otcJson.data, VENUE_OTC),
      ];
      state.total = state.items.length;
      rememberIndex(listedJson.index, otcJson.index);
      renderList();
      setLive("live");
      if (listedRes.status === "rejected") {
        showError(listedRes.reason.message || "场内检索失败");
      } else if (otcRes.status === "rejected") {
        showError(otcRes.reason.message || "场外检索失败");
      } else {
        showError("");
      }
    } catch (err) {
      showError(err.message || String(err));
      setLive("idle");
    } finally {
      setLoading(false);
    }
  }

  async function refreshCurrent(force = false) {
    if (state.searchMode) {
      await runSearch();
      return;
    }
    if (!state.selectedCode) {
      await loadTree(force);
      await loadIndexStatus();
      return;
    }
    await loadCategoryPage(force);
  }

  async function rebuildIndex() {
    setLive("busy");
    try {
      const jobs = [];
      if (state.searchMode || !state.selectedCode) {
        jobs.push(api("/api/funds/index/rebuild?force=1", { method: "POST" }));
        jobs.push(api("/api/otc-funds/index/rebuild", { method: "POST" }));
      } else if (state.venue === VENUE_OTC) {
        jobs.push(api("/api/otc-funds/index/rebuild", { method: "POST" }));
      } else {
        jobs.push(api("/api/funds/index/rebuild?force=1", { method: "POST" }));
      }
      const results = await Promise.all(jobs);
      if (state.searchMode || !state.selectedCode) {
        rememberIndex(results[0]?.data, results[1]?.data);
      } else if (state.venue === VENUE_OTC) {
        rememberIndex(null, results[0]?.data);
      } else {
        rememberIndex(results[0]?.data, null);
      }
      showError("");
    } catch (err) {
      showError(err.message || String(err));
    } finally {
      setLive("idle");
    }
  }

  function turnPage(nextPage) {
    if (nextPage < 1) return;
    state.page = nextPage;
    if (isOtcCategoryMode()) loadCategoryPage(false);
    else renderList();
  }

  function bindEvents() {
    $("refreshBtn").addEventListener("click", () => refreshCurrent(true));
    $("rebuildBtn").addEventListener("click", rebuildIndex);

    let searchTimer = null;
    const queueSearch = () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(runSearch, 320);
    };
    $("nameInput").addEventListener("input", queueSearch);
    $("codeInput").addEventListener("input", queueSearch);

    $("filterInput").addEventListener("input", () => {
      state.filter = $("filterInput").value;
      state.page = 1;
      renderList();
    });

    $("marketSeg").addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-market]");
      if (!btn) return;
      state.market = btn.dataset.market || "";
      $("marketSeg").querySelectorAll("button").forEach((el) => {
        el.classList.toggle("is-active", el === btn);
      });
      if ($("nameInput").value.trim() || $("codeInput").value.trim()) {
        runSearch();
      }
    });

    $("sortSeg").addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-sort]");
      if (!btn) return;
      state.sort = btn.dataset.sort;
      $("sortSeg").querySelectorAll("button").forEach((el) => {
        el.classList.toggle("is-active", el === btn);
      });
      state.page = 1;
      renderList();
    });

    $("pageSize").addEventListener("change", () => {
      state.pageSize = Number($("pageSize").value) || 50;
      state.page = 1;
      if (isOtcCategoryMode()) loadCategoryPage(false);
      else renderList();
    });
    $("prevPage").addEventListener("click", () => turnPage(state.page - 1));
    $("nextPage").addEventListener("click", () => {
      const pageSource = isOtcCategoryMode() ? state.total : filteredCount();
      const totalPages = Math.max(1, Math.ceil(pageSource / state.pageSize));
      if (state.page < totalPages) turnPage(state.page + 1);
    });

    $("tableBody").addEventListener("click", (event) => {
      const row = event.target.closest("tr.fund-row");
      if (!row || event.target.closest("a")) return;
      const code = row.dataset.code;
      const hit = state.items.find((item) => item.code === code);
      if (hit) openHoldings(hit);
    });

    $("holdingsClose")?.addEventListener("click", closeHoldings);
  }

  async function init() {
    bindEvents();
    setLoading(true);
    setLive("busy");
    try {
      await loadTree(false);
      await loadIndexStatus();
      const queryCat = readQueryCat();
      const target = findLeaf(queryCat) || state.tree[0]?.children?.[0];
      applyVenueChrome();
      if (target) {
        await selectCategory(target.code, target.name, treeRow(target.code));
      } else {
        renderList();
      }
      setLive("live");
    } catch (err) {
      showError(err.message || String(err));
      setLive("idle");
    } finally {
      setLoading(false);
      window.OrbitPrefetch?.boot("fund");
      window.OrbitPrefetch?.bindHover($("holdingsBody"), "tr[data-code]");
    }
  }

  init();
})();
