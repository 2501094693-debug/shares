(() => {
  const state = {
    groups: [],
    selectedId: "",
    group: null,
    filter: "",
    fetching: false,
    suggestTimer: 0,
    suggestItems: [],
    suggestOpen: false,
  };

  const $ = (id) => document.getElementById(id);

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtPct(value) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
  }

  function fmtYi(value) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    const abs = Math.abs(n);
    const sign = n < 0 ? "-" : n > 0 ? "+" : "";
    if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
    if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(1)}万`;
    return `${sign}${abs.toFixed(0)}`;
  }

  function fmtCap(value) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    const abs = Math.abs(n);
    if (abs >= 1e8) return `${(abs / 1e8).toFixed(2)}亿`;
    if (abs >= 1e4) return `${(abs / 1e4).toFixed(1)}万`;
    return abs.toFixed(0);
  }

  function fmtRatio(value) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(2);
  }

  function fmtPrice(value) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(2);
  }

  function tone(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n === 0) return "flat";
    return n > 0 ? "up" : "down";
  }

  function industryText(row) {
    return [row.l1_name, row.l3_name].filter(Boolean).join(" / ") || "—";
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
    const headers = { ...(options.headers || {}) };
    if (options.body && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    const res = await fetch(path, { ...options, headers, cache: "no-store" });
    const json = await res.json();
    if (!res.ok || json.ok === false) {
      throw new Error(json.error || `请求失败 (${res.status})`);
    }
    return json;
  }

  function readGroupFromUrl() {
    try {
      return new URLSearchParams(location.search).get("group") || "";
    } catch {
      return "";
    }
  }

  function writeGroupToUrl(groupId) {
    const url = new URL(location.href);
    if (groupId) url.searchParams.set("group", groupId);
    else url.searchParams.delete("group");
    history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }

  function stockHref(row) {
    const qs = new URLSearchParams({ code: row.code || "", from: "mine" });
    if (row.l3_code) qs.set("industry", row.l3_code);
    return `/company.html?${qs}`;
  }

  function parseCodes(text) {
    return String(text || "")
      .split(/[,，\s;；|]+/)
      .map((part) => part.trim())
      .filter(Boolean);
  }

  function filteredStocks() {
    const stocks = state.group?.stocks || [];
    const kw = state.filter.trim().toLowerCase();
    if (!kw) return stocks;
    return stocks.filter((row) => {
      const hay = [row.name, row.code, row.l1_name, row.l2_name, row.l3_name]
        .join(" ")
        .toLowerCase();
      return hay.includes(kw);
    });
  }

  function renderSummary() {
    const bar = $("summaryBar");
    const meta = $("marketMeta");
    const totalGroups = state.groups.length;
    const totalStocks = state.groups.reduce((sum, g) => sum + Number(g.count || 0), 0);
    const current = state.group ? Number(state.group.count || 0) : 0;
    const stocks = state.group?.stocks || [];
    const up = stocks.filter((r) => Number(r.change_pct) > 0).length;
    const down = stocks.filter((r) => Number(r.change_pct) < 0).length;
    if (bar) {
      bar.innerHTML = `
        <span>分组 <b>${totalGroups}</b></span>
        <span>合计 <b>${totalStocks}</b></span>
        <span>当前 <b>${current}</b></span>
        ${
          state.group
            ? `<span><b class="is-up">${up}</b> 涨</span><span><b class="is-down">${down}</b> 跌</span>`
            : ""
        }
      `;
    }
    if (meta) {
      const quoteAt = state.group?.quote_updated_at || "";
      meta.textContent = state.group
        ? `${state.group.name} · 行情 ${quoteAt || state.group.updated_at || "—"}`
        : "未选择分组";
    }
    $("groupMeta").textContent = `${totalGroups} 个`;
  }

  function renderGroups() {
    const root = $("groupList");
    if (!state.groups.length) {
      root.innerHTML = `<p class="mine-empty muted">还没有分组</p>`;
      return;
    }
    root.innerHTML = state.groups
      .map((g) => {
        const active = g.id === state.selectedId ? " is-active" : "";
        return `<button type="button" class="mine-group-item${active}" role="option" aria-selected="${
          g.id === state.selectedId ? "true" : "false"
        }" data-group-id="${esc(g.id)}">
          <span class="mine-group-name">${esc(g.name)}</span>
          <span class="mine-group-count">${Number(g.count || 0)}</span>
        </button>`;
      })
      .join("");
  }

  function setStockPaneEnabled(on) {
    $("filterInput").disabled = !on;
    $("addInput").disabled = !on;
    $("addStockBtn").disabled = !on;
    $("deleteGroupBtn").disabled = !on;
  }

  function renderStocks() {
    const body = $("stockBody");
    const empty = $("stockEmpty");
    const title = $("stockTitle");
    const meta = $("stockMeta");

    if (!state.selectedId || !state.group) {
      title.textContent = "股票";
      meta.textContent = "选择左侧分组";
      body.innerHTML = "";
      empty.textContent = state.groups.length ? "选择左侧分组查看成分" : "暂无分组，先在左侧新建一个";
      empty.hidden = false;
      setStockPaneEnabled(false);
      return;
    }

    setStockPaneEnabled(true);
    title.textContent = state.group.name || "股票";
    const all = state.group.stocks || [];
    const rows = filteredStocks();
    meta.textContent = state.filter.trim()
      ? `显示 ${rows.length} / ${all.length}`
      : `${all.length} 只`;

    if (!all.length) {
      body.innerHTML = "";
      empty.textContent = "分组为空，在上方搜索并添加股票";
      empty.hidden = false;
      return;
    }
    if (!rows.length) {
      body.innerHTML = "";
      empty.textContent = "没有匹配的股票";
      empty.hidden = false;
      return;
    }

    empty.hidden = true;
    body.innerHTML = rows
      .map((row, index) => {
        const code = esc(row.code);
        return `<tr class="is-row is-stock" data-code="${code}" data-industry="${esc(row.l3_code || "")}">
          <td class="num shares-rank">${row.rank || index + 1}</td>
          <td>
            <a class="mine-stock-link" href="${esc(stockHref(row))}" title="打开公司详情">
              <span class="market-stock-name">${esc(row.name || "—")}</span>
              <span class="market-stock-code">${code}</span>
            </a>
          </td>
          <td class="num" data-tone="${tone(row.change_pct)}">${fmtPct(row.change_pct)}</td>
          <td class="num">${fmtPrice(row.price)}</td>
          <td class="shares-industry">${esc(industryText(row))}</td>
          <td class="num">${fmtRatio(row.pe_ttm)}</td>
          <td class="num">${fmtRatio(row.pb)}</td>
          <td class="num market-fund-cell" data-tone="${tone(row.main_net)}">${fmtYi(row.main_net)}</td>
          <td class="num market-fund-cell" data-tone="${tone(row.main_net_5d)}">${fmtYi(row.main_net_5d)}</td>
          <td class="num market-fund-cell" data-tone="${tone(row.main_net_10d)}">${fmtYi(row.main_net_10d)}</td>
          <td class="num">${fmtCap(row.market_cap)}</td>
          <td class="num">
            <button type="button" class="btn ghost mine-row-btn" data-remove="${code}" title="移出分组">移除</button>
          </td>
        </tr>`;
      })
      .join("");
  }

  function renderSuggest() {
    const box = $("suggestBox");
    if (!state.suggestOpen || !state.suggestItems.length) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }
    box.hidden = false;
    box.innerHTML = state.suggestItems
      .map((item) => {
        const code = esc(item.code || "");
        const name = esc(item.name || "");
        const industry = esc(item.l3_name || item.l2_name || "");
        return `<button type="button" class="mine-suggest-item" role="option" data-code="${code}" data-name="${name}">
          <span class="mine-suggest-main"><b>${name || code}</b><span class="mono">${code}</span></span>
          <span class="muted">${industry}</span>
        </button>`;
      })
      .join("");
  }

  function closeSuggest() {
    state.suggestOpen = false;
    state.suggestItems = [];
    renderSuggest();
  }

  function paint() {
    renderGroups();
    renderStocks();
    renderSummary();
  }

  async function loadGroups({ keepSelection = true } = {}) {
    const json = await api("/api/mine/groups", { bypassCache: true });
    state.groups = json.data?.groups || [];
    const prefer = keepSelection ? state.selectedId || readGroupFromUrl() : readGroupFromUrl();
    if (prefer && state.groups.some((g) => g.id === prefer)) {
      state.selectedId = prefer;
    } else if (state.groups.length) {
      state.selectedId = state.groups[0].id;
    } else {
      state.selectedId = "";
      state.group = null;
    }
    writeGroupToUrl(state.selectedId);
  }

  async function loadGroupDetail(groupId) {
    if (!groupId) {
      state.group = null;
      return;
    }
    const json = await api(`/api/mine/groups/${encodeURIComponent(groupId)}`, {
      bypassCache: true,
    });
    state.group = json.data || null;
    state.selectedId = state.group?.id || "";
    writeGroupToUrl(state.selectedId);
  }

  async function refreshAll() {
    if (state.fetching) return;
    state.fetching = true;
    setLoading(true);
    setLive("busy");
    try {
      await loadGroups();
      if (state.selectedId) await loadGroupDetail(state.selectedId);
      paint();
      showError("");
      setLive("live");
      window.OrbitPrefetch?.boot("mine", {
        stocks: (state.group?.stocks || []).slice(0, 8),
        from: "mine",
      });
    } catch (err) {
      showError(err.message || String(err));
      setLive("idle");
      paint();
    } finally {
      setLoading(false);
      state.fetching = false;
    }
  }

  async function selectGroup(groupId) {
    if (!groupId) return;
    if (groupId === state.selectedId && state.group) {
      paint();
      return;
    }
    state.selectedId = groupId;
    writeGroupToUrl(groupId);
    setLive("busy");
    try {
      await loadGroupDetail(groupId);
      showError("");
      setLive("live");
    } catch (err) {
      showError(err.message || String(err));
      setLive("idle");
    }
    paint();
  }

  async function createGroup(name) {
    const json = await api("/api/mine/groups", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    const group = json.data;
    state.selectedId = group.id;
    state.group = group;
    await loadGroups({ keepSelection: true });
    writeGroupToUrl(state.selectedId);
    paint();
  }

  async function deleteSelectedGroup() {
    if (!state.selectedId || !state.group) return;
    const name = state.group.name || state.selectedId;
    if (!window.confirm(`确定删除分组「${name}」？其中股票也会一并移除。`)) return;
    await api(`/api/mine/groups/${encodeURIComponent(state.selectedId)}`, {
      method: "DELETE",
    });
    state.selectedId = "";
    state.group = null;
    await loadGroups({ keepSelection: false });
    if (state.selectedId) await loadGroupDetail(state.selectedId);
    paint();
  }

  async function addCodes(codes, names) {
    if (!state.selectedId) throw new Error("请先选择分组");
    const payload = { codes };
    if (names && Object.keys(names).length) payload.names = names;
    const json = await api(`/api/mine/groups/${encodeURIComponent(state.selectedId)}/stocks`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.group = json.data?.group || state.group;
    await loadGroups({ keepSelection: true });
    paint();
    return json.data;
  }

  async function removeCode(code) {
    if (!state.selectedId) return;
    const json = await api(`/api/mine/groups/${encodeURIComponent(state.selectedId)}/stocks`, {
      method: "DELETE",
      body: JSON.stringify({ codes: [code] }),
    });
    state.group = json.data?.group || state.group;
    await loadGroups({ keepSelection: true });
    paint();
  }

  async function searchSuggest(q) {
    const text = String(q || "").trim();
    if (!text || parseCodes(text).length > 1) {
      closeSuggest();
      return;
    }
    const params = new URLSearchParams();
    if (/^\d{1,6}$/.test(text) || /^[a-z]{0,2}\d{4,6}$/i.test(text)) {
      params.set("code", text);
    } else {
      params.set("name", text);
    }
    try {
      const json = await api(`/api/stocks/search?${params.toString()}`);
      state.suggestItems = (json.data || []).slice(0, 12);
      state.suggestOpen = state.suggestItems.length > 0;
      renderSuggest();
    } catch {
      closeSuggest();
    }
  }

  function bind() {
    $("refreshBtn").addEventListener("click", () => {
      void refreshAll();
    });

    $("createForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = $("groupNameInput");
      const name = input.value.trim();
      if (!name) return;
      setLive("busy");
      try {
        await createGroup(name);
        input.value = "";
        showError("");
        setLive("live");
      } catch (err) {
        showError(err.message || String(err));
        setLive("idle");
      }
    });

    $("groupList").addEventListener("click", (event) => {
      const btn = event.target.closest("[data-group-id]");
      if (!btn) return;
      void selectGroup(btn.dataset.groupId);
    });

    $("deleteGroupBtn").addEventListener("click", async () => {
      setLive("busy");
      try {
        await deleteSelectedGroup();
        showError("");
        setLive("live");
      } catch (err) {
        showError(err.message || String(err));
        setLive("idle");
      }
    });

    $("filterInput").addEventListener("input", () => {
      state.filter = $("filterInput").value;
      renderStocks();
    });

    $("addInput").addEventListener("input", () => {
      const value = $("addInput").value;
      window.clearTimeout(state.suggestTimer);
      state.suggestTimer = window.setTimeout(() => {
        void searchSuggest(value);
      }, 220);
    });

    $("addInput").addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeSuggest();
    });

    $("addInput").addEventListener("blur", () => {
      window.setTimeout(closeSuggest, 150);
    });

    $("suggestBox").addEventListener("mousedown", (event) => {
      event.preventDefault();
    });

    $("suggestBox").addEventListener("click", async (event) => {
      const item = event.target.closest("[data-code]");
      if (!item) return;
      const code = item.dataset.code;
      const name = item.dataset.name || "";
      closeSuggest();
      $("addInput").value = "";
      setLive("busy");
      try {
        await addCodes([code], name ? { [code]: name } : undefined);
        showError("");
        setLive("live");
      } catch (err) {
        showError(err.message || String(err));
        setLive("idle");
      }
    });

    $("addForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = $("addInput");
      const codes = parseCodes(input.value);
      if (!codes.length) return;
      closeSuggest();
      setLive("busy");
      try {
        await addCodes(codes);
        input.value = "";
        showError("");
        setLive("live");
      } catch (err) {
        showError(err.message || String(err));
        setLive("idle");
      }
    });

    $("stockBody").addEventListener("click", async (event) => {
      const btn = event.target.closest("[data-remove]");
      if (btn) {
        event.preventDefault();
        event.stopPropagation();
        const code = btn.dataset.remove;
        setLive("busy");
        try {
          await removeCode(code);
          showError("");
          setLive("live");
        } catch (err) {
          showError(err.message || String(err));
          setLive("idle");
        }
        return;
      }
      if (event.target.closest("a")) return;
      const row = event.target.closest("tr.is-stock[data-code]");
      if (!row) return;
      const qs = new URLSearchParams({ code: row.dataset.code, from: "mine" });
      if (row.dataset.industry) qs.set("industry", row.dataset.industry);
      window.location.href = `/company.html?${qs}`;
    });

    window.OrbitPrefetch?.bindHover($("stockBody"), "tr.is-stock[data-code]");
  }

  bind();
  state.selectedId = readGroupFromUrl();
  void refreshAll();
})();
