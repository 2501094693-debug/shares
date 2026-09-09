(() => {
  const POLL_MS = 2000;

  const state = {
    days: 15,
    top: 30,
    status: "idle",
    items: [],
    updatedAt: "",
    candidateCount: 0,
    pollTimer: 0,
    fetching: false,
  };

  const $ = (id) => document.getElementById(id);

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtNum(value, digits = 1) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(digits);
  }

  function fmtPct(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
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

  function showLoading(show, text) {
    const el = $("loading");
    el.textContent = text || "正在分析…";
    el.classList.toggle("hidden", !show);
  }

  function renderSeg() {
    $("daysSeg").querySelectorAll("button[data-days]").forEach((btn) => {
      btn.classList.toggle("is-active", Number(btn.dataset.days) === state.days);
    });
    $("topSeg").querySelectorAll("button[data-top]").forEach((btn) => {
      btn.classList.toggle("is-active", Number(btn.dataset.top) === state.top);
    });
  }

  function renderSummary() {
    $("summaryBar").innerHTML = `
      <span>候选 <b>${state.candidateCount}</b></span>
      <span>结果 <b>${state.items.length}</b></span>
      <span>窗口 <b>${state.days}</b> 交易日</span>
    `;
    $("marketMeta").textContent = state.updatedAt || "";
  }

  function scoreCell(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '<td class="num">—</td>';
    const width = Math.max(0, Math.min(100, n));
    return `<td class="num screen-score-cell" data-tone="${n >= 70 ? "up" : n >= 45 ? "flat" : "down"}">
      <span class="screen-score-bar" style="width:${width}%"></span>
      <span class="screen-score-text">${fmtNum(n, 0)}</span>
    </td>`;
  }

  function emptyRow(text) {
    return `<tr class="is-empty"><td colspan="16">${esc(text)}</td></tr>`;
  }

  function renderTable() {
    const body = $("resultBody");
    if (!state.items.length) {
      body.innerHTML = emptyRow(state.status === "running" ? "分析进行中，请稍候…" : "暂无结果");
      return;
    }

    body.innerHTML = state.items
      .map((row, index) => {
        const detected = row.detected || {};
        const dec = detected.decline || {};
        const cons = detected.consolidation || {};
        const scores = row.scores || {};
        const industry = [row.l1_name, row.l2_name, row.l3_name].filter(Boolean).join(" / ");
        return `<tr class="is-row is-stock" data-code="${esc(row.code || "")}">
          <td class="num muted">${index + 1}</td>
          <td>
            <span class="market-stock-name">${esc(row.name || "")}</span>
            <span class="market-stock-code">${esc(row.code || "")}</span>
            ${industry ? `<span class="steep-sw-line">${esc(industry)}</span>` : ""}
          </td>
          <td class="num screen-total" data-tone="up"><b>${fmtNum(scores.total, 1)}</b></td>
          <td class="num">${dec.days ?? "—"}</td>
          <td class="num">${cons.days ?? "—"}</td>
          <td class="num" data-tone="${tone(dec.total_pct)}">${fmtPct(dec.total_pct)}</td>
          <td class="num">${fmtNum(cons.range_pct, 1)}</td>
          <td class="num">${esc(row.limit_up_date || "—")}</td>
          <td class="num">${row.board_count ?? "—"}</td>
          ${scoreCell(scores.decline_duration)}
          ${scoreCell(scores.decline_quality)}
          ${scoreCell(scores.consolidation_duration)}
          ${scoreCell(scores.consolidation_quality)}
          ${scoreCell(scores.breakout)}
          ${scoreCell(scores.structure)}
        </tr>`;
      })
      .join("");
  }

  function applyPayload(payload) {
    state.status = payload.status || "idle";
    if (payload.status === "done" && payload.data) {
      const data = payload.data;
      state.items = data.items || [];
      state.updatedAt = data.updated_at || "";
      state.candidateCount = data.candidate_count || 0;
      showLoading(false);
      showError("");
      setLive("live");
      renderSummary();
      renderTable();
      return;
    }

    if (payload.status === "error") {
      showLoading(false);
      showError(payload.error || "分析失败");
      setLive("idle");
      return;
    }

    if (payload.status === "running") {
      const elapsed = payload.elapsed_sec ? `（已 ${fmtNum(payload.elapsed_sec, 0)}s）` : "";
      showLoading(true, `${payload.message || "正在分析…"}${elapsed}`);
      setLive("busy");
    }
  }

  function stopPoll() {
    if (state.pollTimer) {
      clearTimeout(state.pollTimer);
      state.pollTimer = 0;
    }
  }

  function schedulePoll() {
    stopPoll();
    state.pollTimer = setTimeout(() => load(false), POLL_MS);
  }

  async function load(force) {
    if (state.fetching && !force) return;
    state.fetching = true;
    showError("");

    const qs = new URLSearchParams({
      days: String(state.days),
      top: String(state.top),
      refresh: force ? "1" : "0",
    });

    try {
      const res = await fetch(`/api/screen/yindie?${qs}`);
      const json = await res.json();
      if (!json.ok) {
        throw new Error(json.error || "请求失败");
      }
      applyPayload(json.data || {});
      if (state.status === "running") {
        schedulePoll();
      } else {
        stopPoll();
      }
    } catch (err) {
      showLoading(false);
      showError(err.message || String(err));
      setLive("idle");
      stopPoll();
    } finally {
      state.fetching = false;
    }
  }

  function bindEvents() {
    $("refreshBtn").addEventListener("click", () => load(true));

    $("daysSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-days]");
      if (!btn) return;
      const days = Number(btn.dataset.days);
      if (days === state.days) return;
      state.days = days;
      renderSeg();
      load(true);
    });

    $("topSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-top]");
      if (!btn) return;
      const top = Number(btn.dataset.top);
      if (top === state.top) return;
      state.top = top;
      renderSeg();
      load(true);
    });

    $("resultBody").addEventListener("click", (ev) => {
      const row = ev.target.closest("tr.is-stock[data-code]");
      if (!row) return;
      const code = row.dataset.code;
      if (!code) return;
      window.location.href = `/company.html?code=${encodeURIComponent(code)}`;
    });
  }

  renderSeg();
  bindEvents();
  load(false);
})();
