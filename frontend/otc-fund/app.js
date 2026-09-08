(() => {
  const state = {
    tree: [],
    categories: [],
    selectedCode: "gp",
    selectedName: "",
    items: [],
    searchMode: false,
    sort: "day_pct",
    filter: "",
    page: 1,
    pageSize: 50,
    total: 0,
    fetching: false,
    indexStatus: null,
    holdingsCode: "",
    holdingsLoading: false,
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

  function tone(value) {
    const n = parsePct(value);
    if (n == null || n === 0) return "flat";
    return n > 0 ? "up" : "down";
  }

  function sortValue(row, field) {
    return parsePct(row[field]);
  }

  function categoryLabel(code) {
    const hit = state.categories.find((item) => item.code === code);
    return hit?.name || code || "";
  }

  function stockHref(row) {
    const qs = new URLSearchParams({ code: row.code || "", name: row.name || "" });
    return `/company.html?${qs}`;
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
    $("holdingsPane")?.classList.add("hidden");
    $("fundLayout")?.classList.remove("has-holdings");
    $("tableBody")?.querySelectorAll("tr.fund-row.is-active").forEach((el) => {
      el.classList.remove("is-active");
    });
    setHoldingsError("");
    setHoldingsLoading(false);
  }

  function renderHoldings(data) {
    const holdings = data?.holdings || [];
    const industries = data?.industries || [];
    $("holdingsTitle").textContent = data?.name || data?.code || "持仓详情";
    const metaParts = [data?.code || ""];
    if (data?.report_date) metaParts.push(`报告期 ${data.report_date}`);
    $("holdingsMeta").textContent = metaParts.filter(Boolean).join(" · ");

    const holdingsBody = $("holdingsBody");
    holdingsBody.innerHTML = holdings.length
      ? holdings
          .map(
            (row) => `
          <tr>
            <td>
              <a class="stock-link" href="${esc(stockHref(row))}">
                <span class="fund-name">${esc(row.name || row.code)}</span>
              </a>
              <span class="market-stock-code">${esc(row.code)}${row.market ? ` · ${esc(row.market)}` : ""}</span>
            </td>
            <td class="num">${esc(row.weight || "—")}</td>
            <td>${esc(row.industry || "—")}</td>
            <td class="num">${esc(row.change_type ? `${row.change_type} ${row.change_weight || ""}`.trim() : "—")}</td>
          </tr>`
          )
          .join("")
      : `<tr class="is-empty"><td colspan="4">暂无重仓股数据</td></tr>`;

    const industryBody = $("industryBody");
    industryBody.innerHTML = industries.length
      ? industries
          .map(
            (row) => `
          <tr>
            <td>${esc(row.name || row.code || "—")}</td>
            <td class="num">${esc(row.weight || "—")}</td>
            <td class="num">${esc(row.peer_avg || "—")}</td>
            <td class="num" data-tone="${tone(row.peer_diff)}">${esc(row.peer_diff || "—")}</td>
          </tr>`
          )
          .join("")
      : `<tr class="is-empty"><td colspan="4">暂无行业分布数据</td></tr>`;
  }

  async function openHoldings(row) {
    if (!row?.code || state.holdingsLoading) return;
    state.holdingsCode = row.code;
    $("holdingsPane")?.classList.remove("hidden");
    $("fundLayout")?.classList.add("has-holdings");
    $("tableBody")?.querySelectorAll("tr.fund-row").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.code === row.code);
    });

    setHoldingsLoading(true);
    $("holdingsTitle").textContent = row.name || row.code;
    $("holdingsMeta").textContent = row.code;
    try {
      const json = await api(`/api/funds/${encodeURIComponent(row.code)}/holdings`);
      renderHoldings({ ...json.data, name: json.data?.name || row.name });
      setHoldingsError("");
    } catch (err) {
      setHoldingsError(err.message || String(err));
    } finally {
      setHoldingsLoading(false);
    }
  }

  function renderTree() {
    const root = $("tree");
    root.innerHTML = "";
    for (const group of state.tree) {
      root.appendChild(buildGroupNode(group));
    }
    const childCount = state.tree[0]?.children?.length || 0;
    $("treeMeta").textContent = `${childCount} 个分类`;
  }

  function buildGroupNode(group) {
    const wrap = document.createElement("div");
    wrap.className = "tree-item";

    const row = document.createElement("button");
    row.type = "button";
    row.className = "tree-row level-1";
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
    row.addEventListener("click", () => selectCategory(node.code, node.name, row));
    return wrap;
  }

  function clearTreeActive() {
    $("tree")?.querySelectorAll(".tree-row.active").forEach((el) => {
      el.classList.remove("active");
    });
  }

  function renderIndexMeta() {
    const status = state.indexStatus;
    if (!status) {
      $("indexMeta").textContent = "";
      return;
    }
    const parts = [`索引 ${status.count || 0}`];
    if (status.updated_at) parts.push(status.updated_at);
    $("indexMeta").textContent = parts.join(" · ");
  }

  function haystack(row) {
    return [row.code, row.name, row.type_name, categoryLabel(row.category_code)]
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

    if (!paginate || state.searchMode) return rows;

    const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;
    return rows;
  }

  function renderList() {
    const rows = visibleItems(!state.searchMode);
    const total = state.searchMode ? rows.length : state.total;
    const totalPages = Math.max(1, Math.ceil(total / state.pageSize));

    if (state.searchMode) {
      $("listTitle").textContent = "搜索结果";
      $("listMeta").textContent = `全市场检索 · ${total} 条`;
    } else if (state.selectedCode) {
      $("listTitle").textContent = state.selectedName || categoryLabel(state.selectedCode);
      $("listMeta").textContent = `${categoryLabel(state.selectedCode)} · 共 ${total} 只`;
    } else {
      $("listTitle").textContent = "基金列表";
      $("listMeta").textContent = "选择左侧分类，或在顶部搜索";
    }

    const body = $("tableBody");
    const displayRows = state.searchMode
      ? rows.slice((state.page - 1) * state.pageSize, state.page * state.pageSize)
      : rows;

    if (!displayRows.length) {
      body.innerHTML = `<tr class="is-empty"><td colspan="6">${
        state.items.length ? "没有匹配的基金" : "暂无数据，请选择分类或搜索"
      }</td></tr>`;
      $("pageInfo").textContent = total ? `0 / ${total}` : "";
      $("prevPage").disabled = true;
      $("nextPage").disabled = true;
      return;
    }

    body.innerHTML = displayRows
      .map(
        (row) => `
        <tr class="is-row fund-row" data-code="${esc(row.code)}">
          <td>
            <span class="fund-name">${esc(row.name || row.code)}</span>
            <span class="market-stock-code">${esc(row.code)}</span>
          </td>
          <td class="num">${esc(row.unit_nav || "—")}</td>
          <td class="num" data-tone="${tone(row.day_pct)}">${esc(row.day_pct || "—")}</td>
          <td class="num" data-tone="${tone(row.month_pct)}">${esc(row.month_pct || "—")}</td>
          <td class="num" data-tone="${tone(row.year_pct)}">${esc(row.year_pct || "—")}</td>
          <td>${esc(row.type_name || categoryLabel(row.category_code) || "—")}</td>
        </tr>`
      )
      .join("");

    $("pageInfo").textContent = `第 ${state.page}/${totalPages} 页 · ${total} 只`;
    $("prevPage").disabled = state.page <= 1;
    $("nextPage").disabled = state.page >= totalPages;
  }

  async function loadTree() {
    const json = await api("/api/otc-funds/tree");
    state.tree = json.data || [];
    state.categories = json.categories || [];
    if (json.index) {
      state.indexStatus = json.index;
      renderIndexMeta();
    }
    renderTree();
  }

  async function selectCategory(code, name, rowEl) {
    if (state.fetching) return;
    state.searchMode = false;
    state.selectedCode = code;
    state.selectedName = name || categoryLabel(code);
    state.page = 1;
    state.filter = "";
    $("filterInput").value = "";
    $("nameInput").value = "";
    $("codeInput").value = "";
    clearTreeActive();
    rowEl?.classList.add("active");
    await loadCategoryPage(false);
  }

  async function loadCategoryPage(force = false) {
    if (!state.selectedCode || state.searchMode) return;
    setLoading(true);
    setLive("busy");
    try {
      const params = new URLSearchParams({
        page: String(state.page),
        page_size: String(state.pageSize),
      });
      if (force) params.set("refresh", "1");
      const json = await api(
        `/api/otc-funds/category/${encodeURIComponent(state.selectedCode)}/list?${params}`
      );
      const payload = json.data || {};
      state.items = payload.items || [];
      state.total = Number(payload.total || state.items.length);
      if (json.index) {
        state.indexStatus = json.index;
        renderIndexMeta();
      }
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
        state.searchMode = false;
        const row = $("tree")?.querySelector(`.tree-row[data-code="${state.selectedCode}"]`);
        await selectCategory(state.selectedCode, state.selectedName, row);
      }
      return;
    }

    if (state.fetching) return;
    state.searchMode = true;
    state.page = 1;
    clearTreeActive();

    const params = new URLSearchParams();
    if (name) params.set("name", name);
    if (code) params.set("code", code);
    params.set("limit", "500");

    setLoading(true);
    setLive("busy");
    try {
      const json = await api(`/api/otc-funds/search?${params}`);
      state.items = (json.data || []).map((row) => ({
        ...row,
        unit_nav: row.unit_nav || "",
        day_pct: row.day_pct || "",
        month_pct: row.month_pct || "",
        year_pct: row.year_pct || "",
      }));
      state.total = state.items.length;
      if (json.index) {
        state.indexStatus = json.index;
        renderIndexMeta();
      }
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

  async function rebuildIndex() {
    setLive("busy");
    try {
      const json = await api("/api/otc-funds/index/rebuild", { method: "POST" });
      state.indexStatus = json.data || state.indexStatus;
      renderIndexMeta();
      showError("");
    } catch (err) {
      showError(err.message || String(err));
    } finally {
      setLive("idle");
    }
  }

  function bindEvents() {
    $("refreshBtn").addEventListener("click", () => {
      if (state.searchMode) runSearch();
      else loadCategoryPage(true);
    });
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
      if (state.searchMode) {
        state.page = 1;
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
      renderList();
    });

    $("pageSize").addEventListener("change", () => {
      state.pageSize = Number($("pageSize").value) || 50;
      state.page = 1;
      if (state.searchMode) renderList();
      else loadCategoryPage(false);
    });
    $("prevPage").addEventListener("click", () => {
      if (state.page > 1) {
        state.page -= 1;
        if (state.searchMode) renderList();
        else loadCategoryPage(false);
      }
    });
    $("nextPage").addEventListener("click", () => {
      state.page += 1;
      if (state.searchMode) renderList();
      else loadCategoryPage(false);
    });

    $("tableBody").addEventListener("click", (event) => {
      const row = event.target.closest("tr.fund-row");
      if (!row) return;
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
      await loadTree();
      const firstCat = state.tree[0]?.children?.[0];
      if (firstCat) {
        const row = $("tree")?.querySelector(`.tree-row[data-code="${firstCat.code}"]`);
        await selectCategory(firstCat.code, firstCat.name, row);
      } else {
        renderList();
      }
      setLive("live");
    } catch (err) {
      showError(err.message || String(err));
      setLive("idle");
    } finally {
      setLoading(false);
    }
  }

  init();
})();
