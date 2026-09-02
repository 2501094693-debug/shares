(() => {
  const state = {
    mode: "daily",
    date: "",
    code: "",
    name: "",
    items: [],
    selected: "",
    sort: "net",
    filter: "",
    fetching: false,
    pending: null,
  };

  const $ = (id) => document.getElementById(id);

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
    const sign = n < 0 ? "-" : "";
    if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
    if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(1)}万`;
    return `${sign}${abs.toFixed(0)}`;
  }

  function tone(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n === 0) return "flat";
    return n > 0 ? "up" : "down";
  }

  function num(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setLive(kind) {
    const el = $("liveDot");
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

  function shiftDate(date, days) {
    const d = new Date(`${date}T00:00:00`);
    if (Number.isNaN(d.getTime())) return date;
    d.setDate(d.getDate() + days);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function skipWeekend(date, dir) {
    let next = shiftDate(date, dir);
    for (let i = 0; i < 4; i += 1) {
      const d = new Date(`${next}T00:00:00`);
      if (d.getDay() !== 0 && d.getDay() !== 6) return next;
      next = shiftDate(next, dir);
    }
    return next;
  }

  function rowKey(row) {
    return `${row.code}:${row.date}`;
  }

  function companyHref(row) {
    const qs = new URLSearchParams({
      code: row.code || "",
      name: row.name || "",
      industry: row.l3_code || "",
    });
    return `/company.html?${qs}`;
  }

  function haystack(row) {
    return [
      row.code,
      row.name,
      row.l1_name,
      row.l2_name,
      row.l3_name,
      ...(row.reasons || []),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
  }

  function visibleItems() {
    const q = state.filter.trim().toLowerCase();
    let rows = state.items.slice();
    if (q) rows = rows.filter((row) => haystack(row).includes(q));
    if (state.sort === "date") {
      rows.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
    } else {
      const field = state.sort === "change" ? "change_pct" : state.sort === "turnover" ? "turnover" : "net_amt";
      rows.sort((a, b) => {
        const va = num(a[field]);
        const vb = num(b[field]);
        if (va == null && vb == null) return 0;
        if (va == null) return 1;
        if (vb == null) return -1;
        return vb - va;
      });
    }
    return rows;
  }

  function selectedRow() {
    return state.items.find((row) => rowKey(row) === state.selected) || null;
  }

  function ensureSelected(rows) {
    if (rows.some((row) => rowKey(row) === state.selected)) return;
    state.selected = rows[0] ? rowKey(rows[0]) : "";
  }

  function renderHead() {
    const dateCol = state.mode === "stock" ? "<th>日期</th>" : "";
    $("tableHead").innerHTML = `
      <tr>
        ${dateCol}
        <th>名称</th>
        <th class="num">涨跌</th>
        <th class="num">净买</th>
      </tr>`;
    $("listTitle").textContent = state.mode === "stock" ? "历史上榜" : "上榜股票";
  }

  function renderList() {
    const cols = state.mode === "stock" ? 4 : 3;
    const rows = visibleItems();
    ensureSelected(rows);
    if (!rows.length) {
      $("tableBody").innerHTML = `<tr class="is-empty"><td colspan="${cols}">${
        state.items.length ? "没有匹配的股票" : "暂无龙虎榜数据"
      }</td></tr>`;
      renderDetail();
      return;
    }
    $("tableBody").innerHTML = rows
      .map((row) => {
        const key = rowKey(row);
        const dateCell = state.mode === "stock" ? `<td class="lhb-date">${esc(row.date)}</td>` : "";
        return `
          <tr class="is-row${state.selected === key ? " is-active" : ""}" data-key="${esc(key)}">
            ${dateCell}
            <td>
              <span class="lhb-name">${esc(row.name || row.code)}</span>
              <span class="market-stock-code">${esc(row.code)}</span>
            </td>
            <td class="num" data-tone="${tone(row.change_pct)}">${fmtPct(row.change_pct)}</td>
            <td class="num" data-tone="${tone(row.net_amt)}">${fmtYi(row.net_amt)}</td>
          </tr>`;
      })
      .join("");
    renderDetail();
  }

  function seatTable(title, rows, side) {
    if (!rows.length) {
      return `<div class="lhb-seats"><h4>${title}</h4><p class="muted">无席位数据</p></div>`;
    }
    const body = rows
      .map((seat) => {
        const focus = side === "buy" ? seat.buy : seat.sell;
        return `<tr>
          <td class="num">${seat.rank ?? ""}</td>
          <td><span class="lhb-dept-type" data-type="${esc(seat.dept_type)}">${esc(seat.dept_type)}</span>${esc(seat.dept)}</td>
          <td class="num" data-tone="${tone(seat.buy)}">${fmtYi(seat.buy)}</td>
          <td class="num" data-tone="${tone(seat.sell)}">${fmtYi(seat.sell)}</td>
          <td class="num" data-tone="${tone(seat.net)}">${fmtYi(seat.net)}</td>
          <td class="num">${seat.buy_ratio == null ? "—" : `${Number(seat.buy_ratio).toFixed(2)}%`}</td>
        </tr>`;
      })
      .join("");
    return `
      <div class="lhb-seats">
        <h4>${title}</h4>
        <table class="market-table lhb-seat-table">
          <thead>
            <tr>
              <th class="num">#</th>
              <th>席位</th>
              <th class="num">买入</th>
              <th class="num">卖出</th>
              <th class="num">净额</th>
              <th class="num">买入占比</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  function renderDetail() {
    const row = selectedRow();
    const head = $("detailHead");
    const body = $("detailBody");
    if (!row) {
      head.innerHTML = `<h2>买卖席位</h2><p class="muted">点左侧一行查看买入 / 卖出营业部</p>`;
      body.innerHTML = `<div class="lhb-detail-empty muted">暂无选中股票</div>`;
      return;
    }
    const sw = [row.l1_name, row.l2_name, row.l3_name].filter(Boolean).join(" / ");
    const historyBtn =
      state.mode === "daily"
        ? `<button type="button" class="btn ghost" id="toHistoryBtn">个股历史</button>`
        : "";
    head.innerHTML = `
      <div class="lhb-detail-identity">
        <h2>${esc(row.name || row.code)}</h2>
        <p class="muted">${esc(row.code)} · ${esc(row.date)}${sw ? ` · ${esc(sw)}` : ""}</p>
      </div>
      <div class="lhb-detail-actions">
        <a class="btn ghost" href="${companyHref(row)}">公司详情</a>
        ${historyBtn}
      </div>`;
    const metrics = `
      <div class="lhb-metrics">
        <span>收盘 <b>${row.close == null ? "—" : Number(row.close).toFixed(2)}</b></span>
        <span data-tone="${tone(row.change_pct)}">涨跌 <b>${fmtPct(row.change_pct)}</b></span>
        <span>换手 <b>${row.turnover == null ? "—" : `${Number(row.turnover).toFixed(2)}%`}</b></span>
        <span data-tone="${tone(row.net_amt)}">净买 <b>${fmtYi(row.net_amt)}</b></span>
        <span>买入 <b>${fmtYi(row.buy_amt)}</b></span>
        <span>卖出 <b>${fmtYi(row.sell_amt)}</b></span>
      </div>`;
    const listings = (row.listings || [])
      .map((listing) => {
        return `
          <article class="lhb-listing">
            <div class="lhb-reason-head">
              <strong>${esc(listing.reason || "上榜")}</strong>
              <span class="muted">${esc(listing.explain || "")}</span>
              <span class="muted">成交占比 ${
                listing.deal_ratio == null ? "—" : `${Number(listing.deal_ratio).toFixed(2)}%`
              }</span>
            </div>
            <div class="lhb-seat-grid">
              ${seatTable("买入前五", listing.buyers || [], "buy")}
              ${seatTable("卖出前五", listing.sellers || [], "sell")}
            </div>
          </article>`;
      })
      .join("");
    body.innerHTML = `${metrics}${listings || '<p class="muted">暂无席位</p>'}`;
    const hist = $("toHistoryBtn");
    if (hist) {
      hist.addEventListener("click", () => {
        setMode("stock");
        run(() => loadStock(row.code));
      });
    }
  }

  function renderSummary(data) {
    const bar = $("summaryBar");
    if (state.mode === "daily") {
      const cls = tone(data.net_amt_total);
      bar.innerHTML = `<span>上榜 <b>${data.count ?? 0}</b></span><span>净买合计 <b class="${
        cls === "up" ? "is-up" : cls === "down" ? "is-down" : ""
      }">${fmtYi(data.net_amt_total)}</b></span>`;
    } else {
      bar.innerHTML = `<span>${esc(data.name || data.code || "")}</span><span>历史上榜 <b>${
        data.count ?? 0
      }</b> 次</span>`;
    }
    $("marketMeta").textContent = data.updated_at || "";
  }

  function syncSortButtons() {
    document.querySelectorAll("#sortSeg button").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.sort === state.sort);
    });
  }

  function setMode(mode) {
    state.mode = mode;
    if (mode === "stock" && state.sort === "net") state.sort = "date";
    if (mode === "daily" && state.sort === "date") state.sort = "net";
    document.querySelectorAll("#modeSeg button").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.mode === mode);
    });
    $("dailyControls").classList.toggle("hidden", mode !== "daily");
    $("stockControls").classList.toggle("hidden", mode !== "stock");
    $("suggestBox").classList.add("hidden");
    syncSortButtons();
    renderHead();
  }

  async function fetchJson(url) {
    const resp = await fetch(url, { cache: "no-store" });
    const payload = await resp.json();
    if (!payload.ok) throw new Error(payload.error || "请求失败");
    return payload.data;
  }

  function paint(data, extras) {
    Object.assign(state, extras);
    renderSummary(data);
    renderHead();
    renderList();
  }

  async function loadDaily(date, refresh) {
    const qs = new URLSearchParams();
    if (date) qs.set("date", date);
    if (refresh) qs.set("refresh", "1");
    const data = await fetchJson(`/api/list/daily?${qs}`);
    paint(data, {
      date: data.date || date,
      items: data.items || [],
      selected: "",
    });
    $("dateInput").value = state.date;
    const url = new URL(window.location.href);
    url.searchParams.set("mode", "daily");
    url.searchParams.set("date", state.date);
    url.searchParams.delete("code");
    history.replaceState(null, "", url);
    return data;
  }

  async function loadStock(code, refresh) {
    const qs = new URLSearchParams({ code });
    if (refresh) qs.set("refresh", "1");
    const data = await fetchJson(`/api/list/stock?${qs}`);
    paint(data, {
      code: data.code || code,
      name: data.name || "",
      items: data.items || [],
      selected: "",
    });
    $("stockInput").value = state.name ? `${state.code} ${state.name}` : state.code;
    const url = new URL(window.location.href);
    url.searchParams.set("mode", "stock");
    url.searchParams.set("code", state.code);
    url.searchParams.delete("date");
    history.replaceState(null, "", url);
    return data;
  }

  async function run(task) {
    if (state.fetching) {
      state.pending = task;
      return;
    }
    state.fetching = true;
    setLive("busy");
    $("loading").classList.remove("hidden");
    showError("");
    try {
      await task();
      setLive("live");
    } catch (err) {
      setLive("idle");
      showError(err instanceof Error ? err.message : String(err));
    } finally {
      state.fetching = false;
      $("loading").classList.add("hidden");
      const next = state.pending;
      state.pending = null;
      if (next) run(next);
    }
  }

  async function resolveStock(raw) {
    const text = String(raw || "").trim();
    if (!text) throw new Error("请输入股票代码或名称");
    const digits = text.replace(/\D/g, "");
    if (digits.length === 6) return digits;
    const qs = new URLSearchParams();
    if (/^\d+$/.test(text)) qs.set("code", text);
    else qs.set("name", text);
    const payload = await fetch(`/api/stocks/search?${qs}`, { cache: "no-store" }).then((r) => r.json());
    const items = payload.data || [];
    if (!items.length) throw new Error("没有找到这只股票");
    if (items.length === 1) return items[0].code;
    $("suggestBox").classList.remove("hidden");
    $("suggestBox").innerHTML = items
      .slice(0, 12)
      .map(
        (item) =>
          `<button type="button" class="lhb-suggest-item" data-code="${esc(item.code)}">${esc(
            item.name || ""
          )} <span class="muted">${esc(item.code)}</span></button>`
      )
      .join("");
    throw new Error("请从候选里选一只股票");
  }

  function bind() {
    document.querySelectorAll("#modeSeg button").forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = btn.dataset.mode;
        setMode(mode);
        if (mode === "daily") run(() => loadDaily(state.date || $("dateInput").value));
        else if (state.code) run(() => loadStock(state.code));
        else {
          state.items = [];
          state.selected = "";
          renderSummary({ count: 0 });
          renderList();
        }
      });
    });

    document.querySelectorAll("#sortSeg button").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.sort = btn.dataset.sort;
        document.querySelectorAll("#sortSeg button").forEach((el) => {
          el.classList.toggle("is-active", el === btn);
        });
        renderList();
      });
    });

    $("filterInput").addEventListener("input", () => {
      state.filter = $("filterInput").value;
      renderList();
    });
    $("dateInput").addEventListener("change", () => {
      run(() => loadDaily($("dateInput").value));
    });
    $("prevDayBtn").addEventListener("click", () => {
      run(() => loadDaily(skipWeekend($("dateInput").value || state.date, -1)));
    });
    $("nextDayBtn").addEventListener("click", () => {
      run(() => loadDaily(skipWeekend($("dateInput").value || state.date, 1)));
    });
    $("refreshBtn").addEventListener("click", () => {
      if (state.mode === "stock") {
        if (state.code) run(() => loadStock(state.code, true));
        return;
      }
      run(() => loadDaily($("dateInput").value || state.date, true));
    });
    $("stockSearchBtn").addEventListener("click", () => {
      $("suggestBox").classList.add("hidden");
      run(async () => {
        const code = await resolveStock($("stockInput").value);
        await loadStock(code);
      });
    });
    $("stockInput").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        $("stockSearchBtn").click();
      }
    });
    $("suggestBox").addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-code]");
      if (!btn) return;
      $("suggestBox").classList.add("hidden");
      run(() => loadStock(btn.dataset.code));
    });
    $("tableBody").addEventListener("click", (ev) => {
      const tr = ev.target.closest("tr.is-row");
      if (!tr) return;
      state.selected = tr.dataset.key;
      renderList();
    });
  }

  function boot() {
    const params = new URLSearchParams(window.location.search);
    const mode = params.get("mode") === "stock" ? "stock" : "daily";
    const code = (params.get("code") || "").trim();
    const date = (params.get("date") || "").trim();
    bind();
    setMode(mode);
    if (mode === "stock" && code) run(() => loadStock(code));
    else run(() => loadDaily(date));
  }

  boot();
})();
