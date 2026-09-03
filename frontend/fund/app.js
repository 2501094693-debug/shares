(() => {
  const state = {
    tree: [],
    categories: [],
    selectedCode: "",
    selectedName: "",
    items: [],
    searchMode: false,
    market: "",
    sort: "change_pct",
    filter: "",
    page: 1,
    pageSize: 50,
    fetching: false,
    indexStatus: null,
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
    if (field === "change_pct" || field === "premium" || field === "turnover") {
      return parsePct(row[field]);
    }
    if (field === "amount" || field === "main_net") {
      return parseYi(row[field]);
    }
    if (field === "price") {
      const n = parseFloat(row.price);
      return Number.isFinite(n) ? n : null;
    }
    return null;
  }

  function categoryLabel(code) {
    const hit = state.categories.find((item) => item.code === code);
    return hit?.name || code || "";
  }

  function companyHref(row) {
    const qs = new URLSearchParams({
      code: row.code || "",
      name: row.name || "",
    });
    return `/company.html?${qs}`;
  }

  function countCategories(tree) {
    let n = 0;
    for (const group of tree) {
      n += (group.children || []).length;
    }
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
      <span>共 <strong>${items.length}</strong> 只</span>
      <span class="is-up">涨 ${up}</span>
      <span class="is-down">跌 ${down}</span>
      <span>平 ${flat}</span>`;
  }

  function renderIndexMeta() {
    const status = state.indexStatus;
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
    return [row.code, row.name, row.market, categoryLabel(row.category_code)]
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

    if (!paginate) return rows;

    const totalPages = Math.max(1, Math.ceil(rows.length / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;
    const start = (state.page - 1) * state.pageSize;
    return rows.slice(start, start + state.pageSize);
  }

  function renderList() {
    const allRows = (() => {
      const q = state.filter.trim().toLowerCase();
      let rows = state.items.slice();
      if (q) rows = rows.filter((row) => haystack(row).includes(q));
      return rows;
    })();
    const total = allRows.length;
    const totalPages = Math.max(1, Math.ceil(total / state.pageSize));
    const rows = visibleItems(true);

    if (state.searchMode) {
      $("listTitle").textContent = "搜索结果";
      $("listMeta").textContent = `全市场检索 · ${total} 条`;
    } else if (state.selectedCode) {
      $("listTitle").textContent = state.selectedName || categoryLabel(state.selectedCode);
      $("listMeta").textContent = `${categoryLabel(state.selectedCode)} · ${total} 只`;
    } else {
      $("listTitle").textContent = "基金列表";
      $("listMeta").textContent = "选择左侧分类，或在顶部搜索";
    }

    const body = $("tableBody");
    if (!rows.length) {
      body.innerHTML = `<tr class="is-empty"><td colspan="7">${
        state.items.length ? "没有匹配的基金" : "暂无数据，请选择分类或搜索"
      }</td></tr>`;
      $("pageInfo").textContent = total ? `0 / ${total}` : "";
      $("prevPage").disabled = true;
      $("nextPage").disabled = true;
      renderSummary();
      return;
    }

    body.innerHTML = rows
      .map(
        (row) => `
        <tr class="is-row fund-row" data-code="${esc(row.code)}">
          <td>
            <a class="fund-name-link" href="${esc(companyHref(row))}">
              <span class="fund-name">${esc(row.name || row.code)}</span>
            </a>
            <span class="market-stock-code">${esc(row.code)}${row.market ? ` · ${esc(row.market)}` : ""}</span>
          </td>
          <td class="num">${esc(row.price || "—")}</td>
          <td class="num" data-tone="${tone(row.change_pct)}">${esc(row.change_pct || "—")}</td>
          <td class="num">${esc(row.amount || "—")}</td>
          <td class="num" data-tone="${tone(row.premium)}">${esc(row.premium || "—")}</td>
          <td class="num" data-tone="${tone(row.main_net)}">${esc(row.main_net || "—")}</td>
          <td class="num">${esc(row.turnover || "—")}</td>
        </tr>`
      )
      .join("");

    $("pageInfo").textContent = `第 ${state.page}/${totalPages} 页 · ${total} 只`;
    $("prevPage").disabled = state.page <= 1;
    $("nextPage").disabled = state.page >= totalPages;
    renderSummary();
  }

  async function loadTree(force = false) {
    const json = await api(`/api/funds/tree${force ? "?refresh=1" : ""}`);
    state.tree = json.data || [];
    state.categories = json.categories || [];
    renderTree();
  }

  async function loadIndexStatus() {
    try {
      const json = await api("/api/funds/index/status");
      state.indexStatus = json.data || null;
      renderIndexMeta();
    } catch {
      /* ignore */
    }
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

    setLoading(true);
    setLive("busy");
    try {
      const json = await api(`/api/funds/${encodeURIComponent(code)}/list`);
      const payload = json.data || {};
      state.items = payload.items || [];
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
    if (state.market) params.set("market", state.market);
    params.set("limit", "500");

    setLoading(true);
    setLive("busy");
    try {
      const json = await api(`/api/funds/search?${params}`);
      state.items = json.data || [];
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
    const row = $("tree")?.querySelector(`.tree-row[data-code="${state.selectedCode}"]`);
    if (force) {
      setLoading(true);
      setLive("busy");
      try {
        const json = await api(
          `/api/funds/${encodeURIComponent(state.selectedCode)}/list?refresh=1`
        );
        const payload = json.data || {};
        state.items = payload.items || [];
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
      return;
    }
    await selectCategory(state.selectedCode, state.selectedName, row);
  }

  async function rebuildIndex() {
    setLive("busy");
    try {
      const json = await api("/api/funds/index/rebuild?force=1", { method: "POST" });
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
      renderList();
    });
    $("prevPage").addEventListener("click", () => {
      if (state.page > 1) {
        state.page -= 1;
        renderList();
      }
    });
    $("nextPage").addEventListener("click", () => {
      state.page += 1;
      renderList();
    });

    $("tableBody").addEventListener("click", (event) => {
      const row = event.target.closest("tr.fund-row");
      if (!row || event.target.closest("a")) return;
      const code = row.dataset.code;
      const hit = state.items.find((item) => item.code === code);
      if (hit) window.location.href = companyHref(hit);
    });
  }

  async function init() {
    bindEvents();
    setLoading(true);
    setLive("busy");
    try {
      await loadTree(false);
      await loadIndexStatus();
      const firstGroup = state.tree[0];
      const firstCat = firstGroup?.children?.[0];
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
