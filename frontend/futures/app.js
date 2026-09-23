(() => {
  const COLUMNS = [
    { key: "name", label: "名称" },
    { key: "price", label: "最新", num: true },
    { key: "change_pct", label: "涨跌", num: true, tone: true },
    { key: "volume", label: "成交量", num: true },
    { key: "amount", label: "成交额", num: true },
    { key: "open_interest", label: "持仓", num: true },
    { key: "oi_change_pct", label: "仓差%", num: true, tone: true },
  ];

  const DETAIL_FIELDS = [
    { key: "code", label: "代码" },
    { key: "full_code", label: "完整代码" },
    { key: "name", label: "名称" },
    { key: "venue", label: "交易所" },
    { key: "category_code", label: "分类" },
    { key: "is_main", label: "主力" },
    { key: "price", label: "最新价" },
    { key: "change", label: "涨跌额" },
    { key: "change_pct", label: "涨跌幅" },
    { key: "open", label: "开盘" },
    { key: "high", label: "最高" },
    { key: "low", label: "最低" },
    { key: "prev_close", label: "昨收" },
    { key: "amplitude", label: "振幅" },
    { key: "volume", label: "成交量" },
    { key: "amount", label: "成交额" },
    { key: "open_interest", label: "持仓量" },
    { key: "oi_change_pct", label: "仓差%" },
  ];

  const state = {
    tree: [],
    categories: [],
    selectedCode: "",
    selectedName: "",
    items: [],
    searchMode: false,
    venue: "",
    mainOnly: false,
    sort: "change_pct",
    filter: "",
    page: 1,
    pageSize: 50,
    total: 0,
    index: null,
    detailCode: "",
    detailLoading: false,
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

  function sortValue(row, field) {
    if (field === "change_pct" || field === "oi_change_pct" || field === "amplitude") {
      return parsePct(row[field]);
    }
    if (field === "amount" || field === "volume" || field === "open_interest") {
      return parseYi(row[field]);
    }
    if (field === "price" || field === "change") {
      const n = parseFloat(row[field]);
      return Number.isFinite(n) ? n : null;
    }
    return null;
  }

  function categoryLabel(code) {
    const hit = state.categories.find((item) => item.code === code);
    return hit?.name || code || "";
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
    $("treeMeta").textContent = `${state.tree.length} 大类 · ${countCategories(state.tree)} 交易所`;
  }

  function buildGroupNode(group) {
    const wrap = document.createElement("div");
    wrap.className = "tree-item";

    const row = document.createElement("button");
    row.type = "button";
    row.className = "tree-row level-1";
    row.dataset.code = group.code;

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
    $("tree")?.querySelector(`.tree-row[data-code="${CSS.escape(code)}"]`)?.classList.add("active");
  }

  function treeRow(code) {
    return $("tree")?.querySelector(`.tree-row[data-code="${CSS.escape(code)}"]`);
  }

  function rememberIndex(index) {
    if (index) state.index = index;
    renderIndexMeta();
  }

  function renderIndexMeta() {
    const status = state.index;
    if (!status) {
      $("indexMeta").textContent = "";
      return;
    }
    const parts = [`索引 ${status.count || 0}`];
    if (status.complete) parts.push("已完整");
    else if (status.building) parts.push("构建中");
    if (status.updated_at) parts.push(status.updated_at);
    $("indexMeta").textContent = parts.join(" · ");
  }

  function haystack(row) {
    return [row.code, row.name, row.venue, row.full_code, categoryLabel(row.category_code)]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
  }

  function baseItems() {
    let rows = state.items.slice();
    if (!state.searchMode && state.mainOnly) {
      rows = rows.filter((row) => row.is_main);
    }
    return rows;
  }

  function visibleItems(paginate = true) {
    const q = state.filter.trim().toLowerCase();
    let rows = baseItems();
    if (q) rows = rows.filter((row) => haystack(row).includes(q));

    const field = state.sort;
    rows.sort((a, b) => {
      const va = sortValue(a, field);
      const vb = sortValue(b, field);
      if (va == null && vb == null) {
        return String(a.code || "").localeCompare(String(b.code || ""), undefined, {
          sensitivity: "base",
        });
      }
      if (va == null) return 1;
      if (vb == null) return -1;
      return vb - va;
    });

    if (!paginate) return rows;
    const totalPages = Math.max(1, Math.ceil(rows.length / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;
    const start = (state.page - 1) * state.pageSize;
    return rows.slice(start, start + state.pageSize);
  }

  function filteredCount() {
    const q = state.filter.trim().toLowerCase();
    let rows = baseItems();
    if (!q) return rows.length;
    return rows.filter((row) => haystack(row).includes(q)).length;
  }

  function renderSummary() {
    const items = visibleItems(false);
    let up = 0;
    let down = 0;
    for (const row of items) {
      const n = parsePct(row.change_pct);
      if (n == null || n === 0) continue;
      if (n > 0) up += 1;
      else down += 1;
    }
    const flat = items.length - up - down;
    $("summaryBar").innerHTML = `
      <span>共 <strong>${items.length}</strong> 个</span>
      <span class="is-up">涨 ${up}</span>
      <span class="is-down">跌 ${down}</span>
      <span>平 ${flat}</span>`;
  }

  function renderNameCell(row) {
    const badges = [];
    if (row.is_main) badges.push('<span class="fund-venue-tag">主力</span>');
    if (row.venue) badges.push(`<span class="fund-venue-tag">${esc(row.venue)}</span>`);
    const badgeHtml = badges.join("");
    return `<span class="fund-name-row"><span class="fund-name">${esc(
      row.name || row.code
    )}</span>${badgeHtml}</span><span class="market-stock-code">${esc(row.code)}${
      row.full_code && row.full_code !== row.code ? ` · ${esc(row.full_code)}` : ""
    }</span>`;
  }

  function renderList() {
    const pageRows = visibleItems(true);
    const total = filteredCount();
    const totalPages = Math.max(1, Math.ceil(total / state.pageSize));

    if (state.searchMode) {
      $("listTitle").textContent = "搜索结果";
      const bits = [];
      if (state.venue) bits.push(state.venue);
      if (state.mainOnly) bits.push("仅主力");
      bits.push(`${total} 条`);
      $("listMeta").textContent = bits.join(" · ");
    } else if (state.selectedCode) {
      $("listTitle").textContent = state.selectedName || categoryLabel(state.selectedCode);
      const bits = [categoryLabel(state.selectedCode)];
      if (state.mainOnly) bits.push("仅主力");
      bits.push(`${total} 个`);
      $("listMeta").textContent = bits.join(" · ");
    } else {
      $("listTitle").textContent = "期货列表";
      $("listMeta").textContent = "选择左侧交易所，或在顶部搜索";
    }

    const body = $("tableBody");
    if (!pageRows.length) {
      body.innerHTML = `<tr class="is-empty"><td colspan="${COLUMNS.length}">${
        state.items.length ? "没有匹配的合约" : "暂无数据，请选择分类或搜索"
      }</td></tr>`;
      $("pageInfo").textContent = total ? `0 / ${total}` : "";
      $("prevPage").disabled = true;
      $("nextPage").disabled = true;
      renderSummary();
      return;
    }

    body.innerHTML = pageRows
      .map((row) => {
        const cells = COLUMNS.map((col) => {
          if (col.key === "name") return `<td>${renderNameCell(row)}</td>`;
          const value = row[col.key] || "—";
          const toneAttr = col.tone ? ` data-tone="${tone(value)}"` : "";
          const numClass = col.num ? ' class="num"' : "";
          return `<td${numClass}${toneAttr}>${esc(value)}</td>`;
        }).join("");
        const active = state.detailCode && state.detailCode === row.code ? " is-active" : "";
        return `<tr class="is-row fund-row${active}" data-code="${esc(row.code)}">${cells}</tr>`;
      })
      .join("");

    $("pageInfo").textContent = `第 ${state.page}/${totalPages} 页 · ${total} 个`;
    $("prevPage").disabled = state.page <= 1;
    $("nextPage").disabled = state.page >= totalPages;
    renderSummary();
  }

  function setDetailError(message) {
    const box = $("detailError");
    if (!box) return;
    if (!message) {
      box.classList.add("hidden");
      box.textContent = "";
      return;
    }
    box.textContent = message;
    box.classList.remove("hidden");
  }

  function setDetailLoading(on) {
    $("detailLoading")?.classList.toggle("hidden", !on);
    if (on) setDetailError("");
  }

  function closeDetail() {
    state.detailCode = "";
    $("detailPane")?.classList.add("hidden");
    $("futuresLayout")?.classList.remove("has-holdings");
    $("tableBody")?.querySelectorAll("tr.fund-row.is-active").forEach((el) => {
      el.classList.remove("is-active");
    });
    setDetailError("");
    setDetailLoading(false);
  }

  function formatDetailValue(key, value) {
    if (key === "is_main") return value ? "是" : "否";
    if (key === "category_code") return categoryLabel(value) || value || "—";
    if (value == null || value === "") return "—";
    return String(value);
  }

  function renderDetail(data) {
    $("detailTitle").textContent = data?.name || data?.code || "合约详情";
    const meta = [data?.code, data?.venue, data?.is_main ? "主力" : ""]
      .filter(Boolean)
      .join(" · ");
    $("detailMeta").textContent = meta || "—";

    const body = $("detailBody");
    body.innerHTML = DETAIL_FIELDS.map((field) => {
      const raw = data?.[field.key];
      const text = formatDetailValue(field.key, raw);
      const toneAttr =
        field.key === "change_pct" || field.key === "change" || field.key === "oi_change_pct"
          ? ` data-tone="${tone(String(raw ?? ""))}"`
          : "";
      return `<div class="futures-detail-item"><dt>${esc(field.label)}</dt><dd${toneAttr}>${esc(
        text
      )}</dd></div>`;
    }).join("");
  }

  async function openDetail(row) {
    if (!row?.code || state.detailLoading) return;
    state.detailCode = row.code;
    if (state.searchMode && row.category_code) highlightCategory(row.category_code);

    $("detailPane")?.classList.remove("hidden");
    $("futuresLayout")?.classList.add("has-holdings");
    $("tableBody")?.querySelectorAll("tr.fund-row").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.code === row.code);
    });

    setDetailLoading(true);
    $("detailTitle").textContent = row.name || row.code;
    $("detailMeta").textContent = [row.code, row.venue].filter(Boolean).join(" · ");
    renderDetail(row);

    try {
      const json = await api(`/api/futures/${encodeURIComponent(row.code)}`);
      renderDetail({ ...row, ...(json.data || {}) });
      setDetailError("");
    } catch (err) {
      setDetailError(err.message || String(err));
    } finally {
      setDetailLoading(false);
    }
  }

  async function loadTree(force = false) {
    const suffix = force ? "?refresh=1" : "";
    const json = await api(`/api/futures/tree${suffix}`);
    state.tree = json.data || [];
    state.categories = json.categories || [];
    rememberIndex(json.index);
    renderTree();
  }

  async function loadCategories() {
    try {
      const json = await api("/api/futures/categories");
      if (Array.isArray(json.data) && json.data.length) {
        state.categories = json.data;
      }
    } catch {
      /* tree 已带 categories，失败可忽略 */
    }
  }

  async function loadIndexStatus() {
    try {
      const json = await api("/api/futures/index/status");
      rememberIndex(json.data);
    } catch {
      /* ignore */
    }
  }

  async function selectCategory(code, name, rowEl) {
    const leaf = findLeaf(code) || { code, name };
    state.searchMode = false;
    state.selectedCode = leaf.code;
    state.selectedName = name || leaf.name || categoryLabel(leaf.code);
    state.page = 1;
    state.filter = "";
    $("filterInput").value = "";
    $("nameInput").value = "";
    $("codeInput").value = "";
    closeDetail();
    syncQuery(leaf.code);
    highlightCategory(leaf.code);
    rowEl?.classList.add("active");
    await loadCategoryPage(false);
  }

  async function loadCategoryPage(force = false) {
    if (!state.selectedCode || state.searchMode) return;
    setLoading(true);
    setLive("busy");
    try {
      const qs = force ? "?refresh=1" : "";
      const json = await api(`/api/futures/${encodeURIComponent(state.selectedCode)}/list${qs}`);
      const payload = json.data || {};
      state.items = payload.items || [];
      state.total = Number(payload.total || state.items.length);
      rememberIndex(json.index);
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

  async function runSearch() {
    const name = $("nameInput").value.trim();
    const code = $("codeInput").value.trim();
    if (!name && !code) {
      if (state.selectedCode) {
        await selectCategory(state.selectedCode, state.selectedName, treeRow(state.selectedCode));
      }
      return;
    }

    state.searchMode = true;
    state.page = 1;
    clearTreeActive();

    const params = new URLSearchParams({ limit: "500" });
    if (name) params.set("name", name);
    if (code) params.set("code", code);
    if (state.venue) params.set("venue", state.venue);
    if (state.mainOnly) params.set("main_only", "1");

    setLoading(true);
    setLive("busy");
    try {
      const json = await api(`/api/futures/search?${params}`);
      state.items = json.data || [];
      state.total = state.items.length;
      rememberIndex(json.index);
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

  async function refreshCurrent(force = false) {
    if (state.searchMode) {
      await runSearch();
      return;
    }
    if (!state.selectedCode) {
      await loadTree(force);
      await loadCategories();
      await loadIndexStatus();
      return;
    }
    await loadCategoryPage(force);
    await loadIndexStatus();
  }

  async function rebuildIndex() {
    setLive("busy");
    try {
      const json = await api("/api/futures/index/rebuild?force=1", { method: "POST" });
      rememberIndex(json.data);
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
    renderList();
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

    $("venueSeg").addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-venue]");
      if (!btn) return;
      state.venue = btn.dataset.venue || "";
      $("venueSeg").querySelectorAll("button").forEach((el) => {
        el.classList.toggle("is-active", el === btn);
      });
      if ($("nameInput").value.trim() || $("codeInput").value.trim()) {
        runSearch();
      }
    });

    $("mainSeg").addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-main]");
      if (!btn) return;
      state.mainOnly = btn.dataset.main === "1";
      $("mainSeg").querySelectorAll("button").forEach((el) => {
        el.classList.toggle("is-active", el === btn);
      });
      state.page = 1;
      if (state.searchMode && ($("nameInput").value.trim() || $("codeInput").value.trim())) {
        runSearch();
      } else {
        renderList();
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
      renderList();
    });
    $("prevPage").addEventListener("click", () => turnPage(state.page - 1));
    $("nextPage").addEventListener("click", () => {
      const totalPages = Math.max(1, Math.ceil(filteredCount() / state.pageSize));
      if (state.page < totalPages) turnPage(state.page + 1);
    });

    $("tableBody").addEventListener("click", (event) => {
      const row = event.target.closest("tr.fund-row");
      if (!row) return;
      const code = row.dataset.code;
      const hit = state.items.find((item) => item.code === code);
      if (hit) openDetail(hit);
    });

    $("detailClose")?.addEventListener("click", closeDetail);
  }

  async function init() {
    bindEvents();
    setLoading(true);
    setLive("busy");
    try {
      await loadTree(false);
      await loadCategories();
      await loadIndexStatus();
      const queryCat = readQueryCat();
      const target = findLeaf(queryCat) || state.tree[0]?.children?.[0];
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
      window.OrbitPrefetch?.boot("futures");
    }
  }

  init();
})();
