(() => {
  const POLL_MS = 15000;

  const state = {
    items: [],
    industries: [],
    updatedAt: "",
    live: false,
    query: "",
    industry: { l1: "", l2: "", l3: "" },
    expanded: {},
    menuOpen: false,
    tone: "",
    fetching: false,
    pendingLoad: null,
    pollTimer: 0,
    totalCount: 0,
    lite: false,
    renderFrom: 0,
    view: "list",
  };

  const ROW_H = 37;
  const OVERSCAN = 18;
  const CARD_GAP = 10;
  const CARD_OVERSCAN = 2;
  const VIEW_KEY = "shares:view";

  const $ = (id) => document.getElementById(id);

  function escapeHtml(text) {
    return String(text ?? "")
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

  function setLive(kind) {
    const el = $("liveDot");
    el.dataset.state = kind;
    el.textContent = kind === "live" ? "LIVE" : kind === "busy" ? "SYNC" : "IDLE";
  }

  function emptyRow(text) {
    return `<tr class="is-empty"><td colspan="11">${text}</td></tr>`;
  }

  function industryText(row) {
    return [row.l1_name, row.l3_name].filter(Boolean).join(" / ") || "—";
  }

  function industryPath(filter) {
    return [filter.l1, filter.l2, filter.l3].filter(Boolean);
  }

  function industryLabel(filter) {
    const parts = industryPath(filter);
    return parts.length ? parts.join(" / ") : "全部行业";
  }

  function emptyIndustry() {
    return { l1: "", l2: "", l3: "" };
  }

  function isIndustrySelected(filter, l1, l2, l3) {
    return (filter.l1 || "") === (l1 || "")
      && (filter.l2 || "") === (l2 || "")
      && (filter.l3 || "") === (l3 || "");
  }

  function isNestedTree(list) {
    return Array.isArray(list) && list.some((node) => Array.isArray(node?.children) && node.children.length);
  }

  function sortIndustryNodes(nodes) {
    nodes.sort((a, b) => (b.count || 0) - (a.count || 0) || String(a.name || "").localeCompare(String(b.name || ""), "zh"));
    nodes.forEach((node) => {
      if (node.children?.length) sortIndustryNodes(node.children);
    });
    return nodes;
  }

  function treeFromItems(items) {
    const roots = new Map();
    for (const row of items || []) {
      const l1 = String(row.l1_name || "").trim();
      if (!l1) continue;
      let l1Node = roots.get(l1);
      if (!l1Node) {
        l1Node = { name: l1, level: 1, count: 0, children: [] };
        roots.set(l1, l1Node);
      }
      l1Node.count += 1;
      const l2 = String(row.l2_name || "").trim();
      if (!l2) continue;
      let l2Node = l1Node.children.find((n) => n.name === l2);
      if (!l2Node) {
        l2Node = { name: l2, level: 2, count: 0, children: [] };
        l1Node.children.push(l2Node);
      }
      l2Node.count += 1;
      const l3 = String(row.l3_name || "").trim();
      if (!l3) continue;
      let l3Node = l2Node.children.find((n) => n.name === l3);
      if (!l3Node) {
        l3Node = { name: l3, level: 3, count: 0 };
        l2Node.children.push(l3Node);
      }
      l3Node.count += 1;
    }
    return sortIndustryNodes([...roots.values()]);
  }

  function resolveIndustries(raw, items) {
    if (isNestedTree(raw)) return raw;
    if (items?.length) return treeFromItems(items);
    return Array.isArray(raw) ? raw.map((node) => ({ ...node, level: node.level || 1, children: node.children || [] })) : [];
  }

  function findIndustryNode(tree, filter) {
    if (!filter.l1) return null;
    const l1 = (tree || []).find((node) => node.name === filter.l1);
    if (!l1 || !filter.l2) return l1 || null;
    const l2 = (l1.children || []).find((node) => node.name === filter.l2);
    if (!l2 || !filter.l3) return l2 || null;
    return (l2.children || []).find((node) => node.name === filter.l3) || null;
  }

  function expandSelectedPath() {
    const { l1, l2 } = state.industry;
    if (l1) state.expanded[l1] = true;
    if (l1 && l2) state.expanded[`${l1}/${l2}`] = true;
  }

  function filtered() {
    const q = state.query.trim().toLowerCase();
    const { l1, l2, l3 } = state.industry;
    return (state.items || []).filter((row) => {
      const chg = Number(row.change_pct);
      if (state.tone === "up" && !(Number.isFinite(chg) && chg > 0)) return false;
      if (state.tone === "down" && !(Number.isFinite(chg) && chg < 0)) return false;
      if (l1 && row.l1_name !== l1) return false;
      if (l2 && row.l2_name !== l2) return false;
      if (l3 && row.l3_name !== l3) return false;
      if (!q) return true;
      const hay = [row.name, row.code, row.l1_name, row.l2_name, row.l3_name]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }

  function renderTone() {
    $("toneSeg").querySelectorAll("button[data-tone]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.tone === state.tone);
    });
  }

  function updateIndustryTrigger() {
    const label = $("industryLabel");
    const trigger = $("industryTrigger");
    const text = industryLabel(state.industry);
    if (label) label.textContent = text;
    if (trigger) trigger.title = text;
  }

  function treeNodeHtml(node, l1, l2) {
    const level = node.level || (l2 ? 3 : l1 ? 2 : 1);
    const name = node.name || "";
    const thisL1 = level === 1 ? name : l1;
    const thisL2 = level === 2 ? name : (level === 3 ? l2 : "");
    const thisL3 = level === 3 ? name : "";
    const key = level === 1 ? thisL1 : `${thisL1}/${thisL2}`;
    const children = node.children || [];
    const hasChildren = children.length > 0;
    const open = !!state.expanded[key];
    const selected = isIndustrySelected(state.industry, thisL1, thisL2, thisL3);
    const chevron = hasChildren
      ? `<button type="button" class="shares-tree-chevron${open ? " is-open" : ""}" data-toggle="${escapeHtml(key)}" aria-label="${open ? "收起" : "展开"}">▸</button>`
      : `<span class="shares-tree-chevron" aria-hidden="true">·</span>`;
    const kids = hasChildren
      ? `<div class="children${open ? " open" : ""}">${children.map((child) => treeNodeHtml(child, thisL1, thisL2 || (level === 2 ? name : ""))).join("")}</div>`
      : "";
    return `<div class="shares-tree-item">
      <div class="shares-tree-row level-${level}${selected ? " is-active" : ""}">
        ${chevron}
        <button type="button" class="shares-tree-pick" role="treeitem" data-l1="${escapeHtml(thisL1)}" data-l2="${escapeHtml(thisL2)}" data-l3="${escapeHtml(thisL3)}" aria-selected="${selected}">
          <span class="shares-tree-name">${escapeHtml(name)}</span>
          <span class="count">${node.count || 0}</span>
        </button>
      </div>
      ${kids}
    </div>`;
  }

  function renderIndustryTree() {
    const treeEl = $("industryTree");
    const allBtn = document.querySelector(".shares-tree-all");
    if (allBtn) allBtn.classList.toggle("is-active", !industryPath(state.industry).length);
    if (!treeEl) return;
    treeEl.innerHTML = (state.industries || []).map((node) => treeNodeHtml(node, "", "")).join("");
  }

  function setIndustryMenu(open) {
    state.menuOpen = !!open;
    const picker = $("industryPicker");
    const menu = $("industryMenu");
    const trigger = $("industryTrigger");
    picker?.classList.toggle("is-open", state.menuOpen);
    if (menu) menu.hidden = !state.menuOpen;
    trigger?.setAttribute("aria-expanded", String(state.menuOpen));
    if (state.menuOpen) {
      expandSelectedPath();
      renderIndustryTree();
    }
  }

  function applyIndustryFilter(next) {
    state.industry = next;
    expandSelectedPath();
    updateIndustryTrigger();
    renderIndustryTree();
    renderView({ resetScroll: true });
  }

  function renderIndustries() {
    if (!findIndustryNode(state.industries, state.industry) && industryPath(state.industry).length) {
      state.industry = emptyIndustry();
    }
    updateIndustryTrigger();
    if (state.menuOpen) renderIndustryTree();
  }

  function renderSummary(visible) {
    const total = state.totalCount || state.items.length;
    const up = visible.filter((r) => Number(r.change_pct) > 0).length;
    const down = visible.filter((r) => Number(r.change_pct) < 0).length;
    $("summaryBar").innerHTML = `
      <span>显示 <b>${visible.length}</b> / ${total}</span>
      <span><b class="is-up">${up}</b> 涨</span>
      <span><b class="is-down">${down}</b> 跌</span>
    `;
    const tag = state.live ? "盘口实时" : state.lite ? "首屏" : "全量";
    $("marketMeta").textContent = `${state.updatedAt || ""} · ${tag}`;
  }

  function stockRow(row) {
    return `<tr class="is-row is-stock" data-code="${escapeHtml(row.code || "")}" data-industry="${escapeHtml(row.l3_code || "")}">
      <td class="num shares-rank">${row.rank || "—"}</td>
      <td>
        <span class="market-stock-name">${escapeHtml(row.name || "—")}</span>
        <span class="market-stock-code">${escapeHtml(row.code || "")}</span>
      </td>
      <td class="num" data-tone="${tone(row.change_pct)}">${fmtPct(row.change_pct)}</td>
      <td class="num">${fmtPrice(row.price)}</td>
      <td class="shares-industry">${escapeHtml(industryText(row))}</td>
      <td class="num">${fmtRatio(row.pe_ttm)}</td>
      <td class="num">${fmtRatio(row.pb)}</td>
      <td class="num market-fund-cell" data-tone="${tone(row.main_net)}">${fmtYi(row.main_net)}</td>
      <td class="num market-fund-cell" data-tone="${tone(row.main_net_5d)}">${fmtYi(row.main_net_5d)}</td>
      <td class="num market-fund-cell" data-tone="${tone(row.main_net_10d)}">${fmtYi(row.main_net_10d)}</td>
      <td class="num">${fmtCap(row.market_cap)}</td>
    </tr>`;
  }

  function stockHref(row) {
    const qs = new URLSearchParams({ code: row.code || "", from: "shares" });
    if (row.l3_code) qs.set("industry", row.l3_code);
    return `/company.html?${qs}`;
  }

  function klineBlock(code) {
    return `<article class="chart-card chart-card--kline" data-kline-code="${escapeHtml(code)}">
      <header class="chart-card__head">
        <div class="chart-card__head-main">
          <div class="chart-card__title">
            <span class="chart-card__mark" aria-hidden="true"></span>
            <h3>走势</h3>
          </div>
          <div class="chart-kline-hover chart-hover-card hidden" aria-hidden="true"></div>
        </div>
        <p class="chart-card__meta muted">日K · 前复权</p>
        <div class="chart-card__controls">
          <div class="chart-select-group">
            <label class="chart-select-wrap" aria-label="周期">
              <select class="chart-select" disabled>
                <option selected>日K</option>
              </select>
            </label>
            <label class="chart-select-wrap" aria-label="复权">
              <select class="chart-select" disabled>
                <option selected>前复权</option>
              </select>
            </label>
          </div>
        </div>
      </header>
      <div class="chart-card__stage">
        <div class="chart-canvas-wrap">
          <canvas width="960" height="360" aria-label="行情走势图"></canvas>
          <p class="muted chart-empty hidden">暂无走势数据</p>
        </div>
      </div>
      <footer class="chart-card__foot">
        <div class="chart-axis-scroll is-disabled">
          <input class="chart-scroll-bar" type="range" min="0" max="0" value="0" step="1" aria-label="时间轴滑动" disabled />
        </div>
      </footer>
    </article>`;
  }

  function stockCard(row) {
    const code = row.code || "";
    const chgTone = tone(row.change_pct);
    return `<article class="screen-card is-stock" data-code="${escapeHtml(code)}" data-industry="${escapeHtml(row.l3_code || "")}" tabindex="0">
      <a class="screen-card-head" href="${escapeHtml(stockHref(row))}" title="打开公司详情">
        <span class="screen-rank">${row.rank || ""}</span>
        <div class="screen-card-name">
          <strong>${escapeHtml(row.name || "—")}</strong>
          <span>${escapeHtml(code)}</span>
          <em>${escapeHtml(industryText(row))}</em>
        </div>
        <div class="screen-card-score">
          <b data-tone="${chgTone}">${fmtPct(row.change_pct)}</b>
          <span>${fmtPrice(row.price)}</span>
        </div>
      </a>
      ${klineBlock(code)}
      <footer class="screen-card-meta">
        <span>PE <b>${fmtRatio(row.pe_ttm)}</b></span>
        <span>PB <b>${fmtRatio(row.pb)}</b></span>
        <span>市值 <b>${fmtCap(row.market_cap)}</b></span>
        <span>今日 <b data-tone="${tone(row.main_net)}">${fmtYi(row.main_net)}</b></span>
        <span>5日 <b data-tone="${tone(row.main_net_5d)}">${fmtYi(row.main_net_5d)}</b></span>
        <span>10日 <b data-tone="${tone(row.main_net_10d)}">${fmtYi(row.main_net_10d)}</b></span>
      </footer>
    </article>`;
  }

  function htmlToCard(row) {
    const wrap = document.createElement("div");
    wrap.innerHTML = stockCard(row).trim();
    return wrap.firstElementChild;
  }

  function patchCard(el, row) {
    const rank = el.querySelector(".screen-rank");
    if (rank) rank.textContent = String(row.rank || "");
    const name = el.querySelector(".screen-card-name strong");
    if (name) name.textContent = row.name || "—";
    const score = el.querySelector(".screen-card-score b");
    if (score) {
      score.textContent = fmtPct(row.change_pct);
      score.dataset.tone = tone(row.change_pct);
    }
    const price = el.querySelector(".screen-card-score span");
    if (price) price.textContent = fmtPrice(row.price);
    const metas = el.querySelectorAll(".screen-card-meta span b");
    if (metas[0]) metas[0].textContent = fmtRatio(row.pe_ttm);
    if (metas[1]) metas[1].textContent = fmtRatio(row.pb);
    if (metas[2]) metas[2].textContent = fmtCap(row.market_cap);
    if (metas[3]) {
      metas[3].textContent = fmtYi(row.main_net);
      metas[3].dataset.tone = tone(row.main_net);
    }
    if (metas[4]) {
      metas[4].textContent = fmtYi(row.main_net_5d);
      metas[4].dataset.tone = tone(row.main_net_5d);
    }
    if (metas[5]) {
      metas[5].textContent = fmtYi(row.main_net_10d);
      metas[5].dataset.tone = tone(row.main_net_10d);
    }
  }

  function mountCardKline(card) {
    const kline = card.querySelector(".chart-card--kline");
    const code = kline && kline.dataset.klineCode;
    if (kline && code && window.OrbitKline) window.OrbitKline.mount(kline, { code, carousel: true });
  }

  function cardList() {
    return $("sharesCardList");
  }

  function ensurePad(list, side) {
    let el = list.querySelector(`.shares-card-pad.is-${side}`);
    if (!el) {
      el = document.createElement("div");
      el.className = `shares-card-pad is-${side}`;
      el.setAttribute("aria-hidden", "true");
    }
    return el;
  }

  function cardPitch(list) {
    const card = list.querySelector(".screen-card");
    if (card) return Math.round(card.getBoundingClientRect().width) + CARD_GAP;
    const probe = document.createElement("article");
    probe.className = "screen-card";
    probe.style.visibility = "hidden";
    probe.style.pointerEvents = "none";
    probe.setAttribute("aria-hidden", "true");
    list.appendChild(probe);
    const w = probe.getBoundingClientRect().width;
    probe.remove();
    return Math.round(w || 560) + CARD_GAP;
  }

  function scrollBox() {
    return document.querySelector(".shares-board-scroll");
  }

  function windowSlice(rows) {
    const box = scrollBox();
    const viewH = box ? box.clientHeight : 640;
    const scrollTop = box ? box.scrollTop : 0;
    const start = Math.max(0, Math.floor(scrollTop / ROW_H) - OVERSCAN);
    const count = Math.ceil(viewH / ROW_H) + OVERSCAN * 2;
    state.renderFrom = start;
    return {
      start,
      rows: rows.slice(start, start + count),
      top: start * ROW_H,
      bottom: Math.max(0, (rows.length - start - count) * ROW_H),
    };
  }

  function paintList(rows) {
    if (!rows.length) {
      $("tableBody").innerHTML = emptyRow(state.items.length ? "没有匹配的股票" : "暂无数据");
      return;
    }
    if (rows.length <= 120) {
      $("tableBody").innerHTML = rows.map(stockRow).join("");
      return;
    }
    const slice = windowSlice(rows);
    $("tableBody").innerHTML = `${
      slice.top ? `<tr class="shares-pad" aria-hidden="true"><td colspan="11" style="height:${slice.top}px;padding:0;border:0"></td></tr>` : ""
    }${slice.rows.map(stockRow).join("")}${
      slice.bottom ? `<tr class="shares-pad" aria-hidden="true"><td colspan="11" style="height:${slice.bottom}px;padding:0;border:0"></td></tr>` : ""
    }`;
  }

  function paintCards(rows) {
    const list = cardList();
    if (!list) return;
    if (!rows.length) {
      list.innerHTML = `<p class="screen-empty muted">${state.items.length ? "没有匹配的股票" : "暂无数据"}</p>`;
      return;
    }
    const empty = list.querySelector(".screen-empty");
    if (empty) empty.remove();
    const pitch = cardPitch(list);
    const viewW = list.clientWidth || 800;
    const start = Math.max(0, Math.floor((list.scrollLeft || 0) / pitch) - CARD_OVERSCAN);
    const count = Math.ceil(viewW / pitch) + CARD_OVERSCAN * 2;
    const slice = rows.slice(start, start + count);
    const left = start * pitch;
    const right = Math.max(0, (rows.length - start - slice.length) * pitch);
    const leftPad = ensurePad(list, "left");
    const rightPad = ensurePad(list, "right");
    leftPad.style.flexBasis = `${left}px`;
    leftPad.style.width = `${left}px`;
    rightPad.style.flexBasis = `${right}px`;
    rightPad.style.width = `${right}px`;
    if (leftPad.parentNode !== list || list.firstChild !== leftPad) list.prepend(leftPad);
    const keep = new Map();
    list.querySelectorAll("article.is-stock").forEach((el) => keep.set(el.dataset.code, el));
    const used = new Set();
    const fresh = [];
    let cursor = leftPad;
    slice.forEach((row) => {
      const code = row.code || "";
      used.add(code);
      let el = keep.get(code);
      if (!el) {
        el = htmlToCard(row);
        fresh.push(el);
      } else {
        patchCard(el, row);
      }
      if (cursor.nextSibling !== el) list.insertBefore(el, cursor.nextSibling);
      cursor = el;
    });
    keep.forEach((el, code) => {
      if (!used.has(code)) el.remove();
    });
    if (cursor.nextSibling !== rightPad) list.insertBefore(rightPad, cursor.nextSibling);
    if (fresh.length) {
      requestAnimationFrame(() => fresh.forEach(mountCardKline));
    }
  }

  function renderViewSeg() {
    $("viewSeg")?.querySelectorAll("button[data-view]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.view === state.view);
    });
  }

  function applyViewChrome() {
    const board = document.querySelector(".shares-board");
    board?.setAttribute("data-view", state.view);
    renderViewSeg();
  }

  function persistView() {
    try {
      localStorage.setItem(VIEW_KEY, state.view);
    } catch {
      /* ignore */
    }
  }

  function readView() {
    try {
      return localStorage.getItem(VIEW_KEY) === "cards" ? "cards" : "list";
    } catch {
      return "list";
    }
  }

  function renderView({ resetScroll = false } = {}) {
    const rows = filtered();
    renderTone();
    renderSummary(rows);
    applyViewChrome();
    if (state.view === "cards") {
      const list = cardList();
      if (resetScroll && list) list.scrollLeft = 0;
      paintCards(rows);
    } else {
      const box = scrollBox();
      if (resetScroll && box) box.scrollTop = 0;
      paintList(rows);
    }
  }

  function setView(next) {
    const view = next === "cards" ? "cards" : "list";
    if (view === state.view) return;
    state.view = view;
    persistView();
    renderView({ resetScroll: true });
  }

  function renderTable() {
    renderView();
  }

  function render() {
    renderIndustries();
    renderTable();
  }

  async function fetchShares({ refresh = false, live = false, lite = false } = {}) {
    const q = new URLSearchParams();
    if (refresh) q.set("refresh", "1");
    if (live) q.set("live", "1");
    if (lite) q.set("lite", "1");
    const path = `/api/market/shares${q.toString() ? `?${q}` : ""}`;
    if (window.OrbitHttp) return OrbitHttp.get(path);
    const resp = await fetch(path, { cache: "no-store" });
    const body = await resp.json();
    if (!body.ok) throw new Error(body.error || "加载失败");
    return body;
  }

  function applyPayload(data, { lite = false } = {}) {
    const items = data.items || [];
    if ((lite || data.lite) && state.items.length > items.length) return;
    state.items = items;
    const nextTree = resolveIndustries(data.industries, items);
    if (nextTree.length) state.industries = nextTree;
    state.updatedAt = data.updated_at || "";
    state.live = !!data.live;
    state.totalCount = Number(data.count) || items.length;
    state.lite = !!(data.lite || lite);
    render();
    const errs = data.errors || [];
    if (errs.length) {
      $("errorBox").textContent = errs.join("；");
      $("errorBox").classList.remove("hidden");
    } else {
      $("errorBox").classList.add("hidden");
    }
  }

  async function paintFromCache() {
    if (!window.OrbitHttp) return false;
    const full = await OrbitHttp.peek("/api/market/shares", { allowStale: true });
    if (full?.data?.items?.length) {
      applyPayload(full.data);
      return true;
    }
    const lite = await OrbitHttp.peek("/api/market/shares?lite=1", { allowStale: true });
    if (lite?.data?.items?.length) {
      applyPayload(lite.data, { lite: true });
      return true;
    }
    return false;
  }

  async function load({ silent = false, refresh = false, live = false } = {}) {
    if (state.fetching) {
      state.pendingLoad = { silent, refresh, live };
      return;
    }
    if (!silent && !refresh && !live && !state.items.length) {
      const hit = await paintFromCache();
      if (!hit) {
        void fetchShares({ lite: true })
          .then((json) => {
            if (json?.data?.items?.length) {
              applyPayload(json.data, { lite: true });
              $("loading").classList.add("hidden");
              setLive("busy");
            }
          })
          .catch(() => {});
      }
    }
    state.fetching = true;
    if (!silent && !state.items.length) $("loading").classList.remove("hidden");
    if (!silent) $("errorBox").classList.add("hidden");
    setLive("busy");
    try {
      const json = await fetchShares({ refresh, live });
      applyPayload(json.data || {});
      setLive("live");
    } catch (exc) {
      if (!silent && !state.items.length) {
        $("errorBox").textContent = String(exc.message || exc);
        $("errorBox").classList.remove("hidden");
      }
      setLive(state.items.length ? "live" : "idle");
    } finally {
      state.fetching = false;
      $("loading").classList.add("hidden");
      if (state.pendingLoad) {
        const next = state.pendingLoad;
        state.pendingLoad = null;
        void load(next);
      }
    }
  }

  function startPoll() {
    window.clearInterval(state.pollTimer);
    state.pollTimer = window.setInterval(() => {
      if (document.hidden) return;
      void load({ silent: true, live: true });
    }, POLL_MS);
  }

  function bindCardGestures(list) {
    let swipe = null;
    const canScrollX = () => list.scrollWidth > list.clientWidth + 1;

    list.addEventListener(
      "wheel",
      (ev) => {
        if (state.view !== "cards") return;
        if (ev.ctrlKey) return;
        if (ev.target.closest(".chart-canvas-wrap, canvas")) return;
        if (!canScrollX()) return;
        ev.preventDefault();
        ev.stopPropagation();
        const delta = Math.abs(ev.deltaX) > Math.abs(ev.deltaY) ? ev.deltaX : ev.deltaY;
        list.scrollLeft += delta;
      },
      { passive: false, capture: true },
    );

    list.addEventListener(
      "pointerdown",
      (ev) => {
        if (state.view !== "cards") return;
        if (ev.button != null && ev.button !== 0) return;
        if (ev.target.closest("input, select, button, a, .chart-scroll-bar, .chart-canvas-wrap, canvas")) return;
        if (!canScrollX()) return;
        swipe = {
          id: ev.pointerId,
          x: ev.clientX,
          scroll: list.scrollLeft,
          moved: false,
        };
        list.classList.add("is-swiping");
      },
      true,
    );

    list.addEventListener("pointermove", (ev) => {
      if (!swipe || ev.pointerId !== swipe.id) return;
      const dx = ev.clientX - swipe.x;
      if (!swipe.moved && Math.abs(dx) < 6) return;
      if (!swipe.moved) {
        swipe.moved = true;
        try {
          list.setPointerCapture(ev.pointerId);
        } catch {
          /* ignore */
        }
      }
      ev.preventDefault();
      list.scrollLeft = swipe.scroll - dx;
    });

    const endSwipe = (ev) => {
      if (!swipe || (ev && ev.pointerId !== swipe.id)) return;
      const moved = swipe.moved;
      swipe = null;
      list.classList.remove("is-swiping");
      list.dataset.swiped = moved ? "1" : "";
    };
    list.addEventListener("pointerup", endSwipe);
    list.addEventListener("pointercancel", endSwipe);

    list.addEventListener("click", (ev) => {
      if (list.dataset.swiped === "1") {
        list.dataset.swiped = "";
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      const head = ev.target.closest(".screen-card-head");
      if (head) return;
      if (ev.target.closest(".chart-card")) return;
      const card = ev.target.closest("article.is-stock[data-code]");
      if (!card) return;
      const qs = new URLSearchParams({ code: card.dataset.code, from: "shares" });
      if (card.dataset.industry) qs.set("industry", card.dataset.industry);
      window.location.href = `/company.html?${qs}`;
    });

    list.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      const card = ev.target.closest("article.is-stock[data-code]");
      if (!card) return;
      ev.preventDefault();
      const qs = new URLSearchParams({ code: card.dataset.code, from: "shares" });
      if (card.dataset.industry) qs.set("industry", card.dataset.industry);
      window.location.href = `/company.html?${qs}`;
    });
  }

  function bind() {
    state.view = readView();
    applyViewChrome();
    $("searchInput").addEventListener("input", (ev) => {
      state.query = ev.target.value || "";
      renderView({ resetScroll: true });
    });
    $("industryTrigger").addEventListener("click", (ev) => {
      ev.stopPropagation();
      setIndustryMenu(!state.menuOpen);
    });
    $("industryMenu").addEventListener("click", (ev) => {
      ev.stopPropagation();
      const toggle = ev.target.closest("[data-toggle]");
      if (toggle) {
        const key = toggle.dataset.toggle || "";
        state.expanded[key] = !state.expanded[key];
        renderIndustryTree();
        return;
      }
      if (ev.target.closest("[data-all]")) {
        applyIndustryFilter(emptyIndustry());
        setIndustryMenu(false);
        return;
      }
      const pick = ev.target.closest(".shares-tree-pick");
      if (!pick) return;
      applyIndustryFilter({
        l1: pick.dataset.l1 || "",
        l2: pick.dataset.l2 || "",
        l3: pick.dataset.l3 || "",
      });
      if (pick.dataset.l3) setIndustryMenu(false);
    });
    document.addEventListener("click", (ev) => {
      if (!state.menuOpen) return;
      if ($("industryPicker")?.contains(ev.target)) return;
      setIndustryMenu(false);
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") setIndustryMenu(false);
    });
    $("toneSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-tone]");
      if (!btn) return;
      state.tone = btn.dataset.tone || "";
      renderView({ resetScroll: true });
    });
    $("viewSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-view]");
      if (!btn) return;
      setView(btn.dataset.view);
    });
    scrollBox()?.addEventListener("scroll", () => {
      if (state.view !== "list") return;
      if ((state.items || []).length <= 120) return;
      paintList(filtered());
    }, { passive: true });
    const cards = cardList();
    cards?.addEventListener("scroll", () => {
      if (state.view !== "cards") return;
      paintCards(filtered());
    }, { passive: true });
    if (cards) bindCardGestures(cards);
    window.addEventListener("resize", () => {
      if (state.view === "cards") paintCards(filtered());
    });
    window.OrbitPrefetch?.bindHover($("tableBody"), "tr.is-stock[data-code]");
    window.OrbitPrefetch?.bindHover(cards, "article.is-stock[data-code]");
    $("tableBody").addEventListener("click", (ev) => {
      const row = ev.target.closest("tr.is-stock[data-code]");
      if (!row) return;
      const qs = new URLSearchParams({ code: row.dataset.code, from: "shares" });
      if (row.dataset.industry) qs.set("industry", row.dataset.industry);
      window.location.href = `/company.html?${qs}`;
    });
    $("refreshBtn").addEventListener("click", () => {
      void load({ silent: true, refresh: true, live: false });
    });
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) void load({ silent: true, live: true });
    });
  }

  bind();
  window.OrbitPrefetch?.boot("shares");
  void load().then(() => {
    startPoll();
    window.OrbitPrefetch?.intent({ stocks: filtered().slice(0, 3) });
  });
})();
