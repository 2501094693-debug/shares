(() => {
  const MODES = window.AI_MODES || {};
  const MODE_ORDER = window.AI_MODE_ORDER || ["business", "earnings", "competition", "risk"];

  const STATUS_LABELS = {
    pending: "等待",
    running: "进行中",
    done: "完成",
    failed: "失败",
  };

  function emptyModeState() {
    return {
      seq: 0,
      jobId: "",
      polling: false,
      pollTimer: null,
      pollFailCount: 0,
      pollInFlight: false,
      lastLogLen: 0,
      lastLogSignature: "",
      activeReportFile: "",
      renderedReportKey: "",
      ready: false,
      job: null,
      reports: [],
    };
  }

  const params = new URLSearchParams(window.location.search);
  const state = {
    mode: "business",
    identity: {
      code: (params.get("code") || "").trim(),
      name: (params.get("name") || "").trim(),
      ready: false,
    },
    modes: Object.fromEntries(MODE_ORDER.map((id) => [id, emptyModeState()])),
  };

  const $ = (id) => document.getElementById(id);

  function getConfig(mode = state.mode) {
    return MODES[mode] || MODES.business;
  }

  function getModeState(mode = state.mode) {
    return state.modes[mode] || emptyModeState();
  }

  function digitCode(raw) {
    const m = String(raw || "").match(/(\d{6})/);
    return m ? m[1] : String(raw || "").trim();
  }

  function meaningfulName(name, code) {
    const n = String(name || "").trim();
    if (!n || n === "-" || n === code) return "";
    if (/^\d{6}(\.\w+)?$/.test(n)) return "";
    return n;
  }

  function companyQuery() {
    const code = digitCode(state.identity.code);
    const name = meaningfulName(state.identity.name, code);
    return [name, code].filter(Boolean).join(" ").trim() || code;
  }

  function identityKeys() {
    const code = digitCode(state.identity.code);
    const name = meaningfulName(state.identity.name, code);
    return { code, name };
  }

  function reportMatches(filename) {
    const raw = String(filename || "");
    const { code, name } = identityKeys();
    if (code && raw.includes(code)) return true;
    if (name && raw.includes(name)) return true;
    return false;
  }

  function jobMatches(job) {
    if (!job) return false;
    const { code, name } = identityKeys();
    const jobCode = job?.stock?.code || job?.result?.stock_code || "";
    const jobName = job?.stock?.name || job?.result?.stock_name || job?.company || "";
    const blob = `${job.company || ""} ${jobCode} ${jobName}`;
    if (code && blob.includes(code)) return true;
    if (name && blob.includes(name)) return true;
    return false;
  }

  function reportsListUrl(cfg) {
    return cfg.reportsApi || `${cfg.apiRoot}/reports`;
  }

  function reportReadUrl(cfg, filename) {
    return `${reportsListUrl(cfg)}/${encodeURIComponent(filename)}`;
  }

  function analysisVisible() {
    const panel = $("panel-analysis");
    return Boolean(panel && !panel.hidden);
  }

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderMarkdown(text) {
    if (!text) return "<p class='muted'>（暂无内容）</p>";
    let html = esc(text);
    html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/〔来源：(.+?)〕/g, '<cite class="ai-source" title="$1">〔来源：$1〕</cite>');
    html = html.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");
    html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`);
    html = html.replace(/\|(.+)\|\n\|[-| :]+\|\n((?:\|.*\|\n?)+)/g, (_, head, body) => {
      const ths = head.split("|").filter(Boolean).map((c) => `<th>${c.trim()}</th>`).join("");
      const rows = body.trim().split("\n").map((line) => {
        const tds = line.split("|").filter(Boolean).map((c) => `<td>${c.trim()}</td>`).join("");
        return `<tr>${tds}</tr>`;
      }).join("");
      return `<table><thead><tr>${ths}</tr></thead><tbody>${rows}</tbody></table>`;
    });
    html = html.replace(/\n{2,}/g, "</p><p>");
    html = `<p>${html}</p>`;
    html = html.replace(/<p><\/p>/g, "");
    return html;
  }

  function resultText(result) {
    return result?.brief || result?.report || result?.explanation || result?.content || "";
  }

  function reportFilename(result) {
    if (result?.filename) return result.filename;
    const path = result?.report_path || "";
    const parts = String(path).split(/[/\\]/);
    return parts.pop() || "";
  }

  async function api(path, options = {}) {
    const { timeoutMs = 0, ...fetchOptions } = options;
    const controller = timeoutMs > 0 ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
    try {
      const res = await fetch(path, {
        ...fetchOptions,
        signal: controller?.signal,
        cache: "no-store",
      });
      let json;
      try {
        json = await res.json();
      } catch {
        throw new Error(`服务器返回非 JSON（${res.status}）`);
      }
      if (!res.ok || !json.ok) {
        throw new Error(json.error || `请求失败 (${res.status})`);
      }
      return json;
    } catch (err) {
      if (err?.name === "AbortError") {
        throw new Error("请求超时，但后台任务可能仍在运行，请稍候继续查看进度");
      }
      throw err;
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  function setLive(kind) {
    const el = $("liveDot");
    if (!el) return;
    el.dataset.state = kind;
    if (kind === "live") {
      el.textContent = "LIVE";
      el.classList.remove("hidden");
    } else if (kind === "busy") {
      el.textContent = "SYNC";
      el.classList.remove("hidden");
    } else {
      el.textContent = "";
      el.classList.add("hidden");
    }
  }

  function setBoardMode(mode) {
    const board = $("aiBoard");
    if (!board) return;
    const next = `is-${mode}`;
    if (board.classList.contains(next)) return;
    board.classList.remove("is-idle", "is-running", "is-result");
    board.classList.add(next);
  }

  function showError(message) {
    const box = $("analysisErrorBox");
    if (!box) return;
    if (!message) {
      box.classList.add("hidden");
      box.textContent = "";
      return;
    }
    box.textContent = message;
    box.classList.remove("hidden");
  }

  function formatTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function formatJobMeta(job) {
    if (!job) return "";
    const statusMap = { running: "生成中", completed: "已完成", failed: "失败" };
    const label = statusMap[job.status] || job.status;
    const stock = job.stock?.code ? ` · ${job.stock.code}` : "";
    const industry = job.result?.industry_name ? ` · ${job.result.industry_name}` : "";
    return `${label} · ${job.company}${stock}${industry}`;
  }

  function updatePipelineProgress(agents) {
    const cfg = getConfig();
    const el = $("pipelineProgress");
    if (!el) return;
    const done = cfg.agentDefs.filter((d) => agents?.[d.id]?.status === "done").length;
    el.textContent = `${done} / ${cfg.agentDefs.length}`;
  }

  function renderAgentBoard(agents) {
    const cfg = getConfig();
    const board = $("agentBoard");
    if (!board) return;
    board.innerHTML = cfg.agentDefs.map((def) => {
      const info = agents?.[def.id] || { status: "pending", message: "等待中", phase_label: "" };
      const status = info.status || "pending";
      const phase = info.phase_label
        ? `<span class="ai-pipeline-phase">${esc(info.phase_label)}</span>`
        : "";
      return `
        <article class="ai-pipeline-step" data-status="${esc(status)}" data-agent="${esc(def.id)}">
          <span class="ai-pipeline-dot" aria-hidden="true"></span>
          <div class="ai-pipeline-body">
            <div class="ai-pipeline-row">
              <strong>${esc(def.name)}</strong>
              <span class="ai-pipeline-badge">${esc(STATUS_LABELS[status] || status)}</span>
            </div>
            <p class="ai-pipeline-sub">${esc(def.subtitle)}</p>
            <p class="ai-pipeline-msg">${esc(info.message || "等待中")}</p>
            ${phase}
          </div>
        </article>
      `;
    }).join("");
    updatePipelineProgress(agents);
  }

  function renderCurrentAction(current, job) {
    const cfg = getConfig();
    const box = $("currentAction");
    if (!box) return;
    const runningAgents = cfg.agentDefs
      .map((d) => ({ ...d, ...(job?.agents?.[d.id] || {}) }))
      .filter((a) => a.status === "running");

    if (job?.status === "running" && (current?.message || runningAgents.length)) {
      box.classList.remove("hidden");
      if (current?.label) {
        $("currentAgent").textContent = current.label;
        const phase = current.phase_label ? `【${current.phase_label}】` : "";
        $("currentMessage").textContent = `${phase}${current.message || ""}`;
      } else if (runningAgents[0]) {
        $("currentAgent").textContent = runningAgents[0].name;
        $("currentMessage").textContent = runningAgents[0].message || "";
      }
    } else {
      box.classList.add("hidden");
    }
  }

  function renderActivityLog(log) {
    const ms = getModeState();
    const list = $("activityLog");
    const panel = $("progressPanel");
    if (!list) return;

    const signature = JSON.stringify(log || []);
    if (signature === ms.lastLogSignature) return;
    ms.lastLogSignature = signature;

    if (!log?.length) {
      list.innerHTML = "<li class='muted' style='padding:8px'>启动后，此处将显示每个步骤的详细日志</li>";
      panel?.classList.remove("is-active");
      return;
    }

    panel?.classList.add("is-active");
    list.innerHTML = log.slice().reverse().map((item) => {
      const time = formatTime(item.at);
      const phase = item.phase_label ? `<span class="ai-log-phase">${esc(item.phase_label)}</span>` : "";
      const level = item.level === "error" ? " is-error" : "";
      return `
        <li class="ai-log-item${level}">
          <div class="ai-log-head">
            <time>${esc(time)}</time>
            <strong>${esc(item.label || item.node)}</strong>
            ${phase}
          </div>
          <p>${esc(item.message || "")}</p>
        </li>
      `;
    }).join("");

    if (log.length > ms.lastLogLen) {
      list.scrollTop = 0;
      ms.lastLogLen = log.length;
    }
  }

  function syncActionButtons(running) {
    $("startBtn")?.classList.toggle("hidden", Boolean(running));
    $("stopPollBtn")?.classList.toggle("hidden", !running);
  }

  function setRunningStatus(running) {
    const chip = $("reportStatus");
    if (running) {
      if (chip) {
        chip.textContent = "生成中";
        chip.classList.remove("hidden");
        chip.dataset.state = "busy";
      }
    } else {
      if (chip) {
        chip.classList.add("hidden");
        chip.dataset.state = "";
      }
      $("progressPanel")?.classList.remove("is-active");
    }
    syncActionButtons(running);
  }

  function focusReportPane() {
    const scroller = document.querySelector("#panel-analysis .ai-report-scroll");
    if (scroller) scroller.scrollTop = 0;
  }

  function showEmptyState() {
    const cfg = getConfig();
    if ($("reportView")) $("reportView").innerHTML = cfg.emptyStateHtml;
  }

  function applyChrome(mode = state.mode) {
    const cfg = getConfig(mode);
    const { code, name } = identityKeys();
    const label = [name, code].filter(Boolean).join(" · ") || "当前公司";
    if ($("analysisCompanyLabel")) $("analysisCompanyLabel").textContent = label;
    if ($("startBtn")) $("startBtn").textContent = cfg.startBtn;
    if ($("historyHead")) $("historyHead").textContent = cfg.historyHead;
    if ($("pipelineProgress")) $("pipelineProgress").textContent = `0 / ${cfg.agentDefs.length}`;
    document.querySelectorAll("#companyAnalysisTabs [data-panel]").forEach((tab) => {
      const active = tab.getAttribute("data-panel") === mode;
      tab.classList.toggle("is-active", active && analysisVisible());
      tab.setAttribute("aria-selected", active && analysisVisible() ? "true" : "false");
    });
  }

  function showReportLoading(message) {
    setBoardMode("result");
    if ($("reportMeta")) $("reportMeta").textContent = message;
    if ($("reportView")) {
      $("reportView").innerHTML = `
        <div class="ai-empty-state">
          <h3>报告已生成</h3>
          <p>${esc(message)}</p>
        </div>
      `;
    }
  }

  function highlightActiveReport() {
    const ms = getModeState();
    document.querySelectorAll("#panel-analysis .ai-history-item").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.file === ms.activeReportFile);
    });
  }

  function renderResult(result) {
    const cfg = getConfig();
    const ms = getModeState();
    if (!result) return;
    const filename = reportFilename(result);
    const text = resultText(result);
    const reportKey = `${filename}|${text.length}`;
    if (filename) ms.activeReportFile = filename;
    if ($("reportTitle")) $("reportTitle").textContent = cfg.resultTitle?.(result) || String(filename).replace(/\.md$/i, "");
    if ($("reportMeta")) $("reportMeta").textContent = cfg.resultMeta?.(result) || "已保存";
    if (ms.renderedReportKey !== reportKey && $("reportView")) {
      $("reportView").innerHTML = renderMarkdown(text);
      ms.renderedReportKey = reportKey;
    }
    ms.ready = true;
    highlightActiveReport();
  }

  function renderJob(job) {
    const cfg = getConfig();
    const ms = getModeState();
    ms.job = job;
    if ($("jobMeta")) $("jobMeta").textContent = formatJobMeta(job);

    const boardMode = !job || job.status === "running"
      ? "running"
      : job.status === "completed" || job.status === "failed" ? "result" : "idle";
    setBoardMode(boardMode);

    renderAgentBoard(job?.agents || {});
    renderCurrentAction(job?.current, job);
    renderActivityLog(job?.activity_log || []);

    const running = job?.status === "running";
    setRunningStatus(running);
    setLive(running ? "busy" : job?.status === "completed" ? "live" : "idle");

    if (job?.status === "failed") {
      showError(job.error || "生成失败");
      setRunningStatus(false);
      if ($("reportMeta")) $("reportMeta").textContent = "生成失败";
    } else if (job?.status === "completed") {
      showError("");
      setRunningStatus(false);
      const content = resultText(job.result);
      if (!content) {
        showReportLoading("报告已生成，正在打开…");
        return;
      }
      renderResult(job.result);
      focusReportPane();
    }
  }

  async function loadReports() {
    const cfg = getConfig();
    const ms = getModeState();
    const { data } = await api(reportsListUrl(cfg));
    ms.reports = (data || []).filter((r) => cfg.reportNameRe.test(r.filename) && reportMatches(r.filename));
    const list = $("reportList");
    if (!list) return ms.reports;
    if (!ms.reports.length) {
      list.innerHTML = `<li class='muted' style='padding:10px'>${esc(cfg.emptyReports)}</li>`;
      return ms.reports;
    }
    list.innerHTML = ms.reports.map((row) => (
      `<li>
        <button type="button" class="ai-history-item" data-file="${esc(row.filename)}">
          <span class="ai-history-name">${esc(row.filename)}</span>
          <span class="ai-history-time">${esc(row.modified_at || "")}</span>
        </button>
      </li>`
    )).join("");
    list.querySelectorAll(".ai-history-item").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          const { data: file } = await api(reportReadUrl(cfg, btn.dataset.file));
          ms.activeReportFile = btn.dataset.file;
          setBoardMode("result");
          if ($("reportTitle")) $("reportTitle").textContent = file.filename.replace(/\.md$/i, "");
          if ($("reportMeta")) $("reportMeta").textContent = cfg.historyMeta;
          if ($("reportView")) $("reportView").innerHTML = renderMarkdown(file.content || "");
          ms.renderedReportKey = `${btn.dataset.file}|${(file.content || "").length}`;
          ms.ready = true;
          highlightActiveReport();
          showError("");
        } catch (err) {
          showError(err.message);
        }
      });
    });
    highlightActiveReport();
    return ms.reports;
  }

  function stopPollForMode(modeId) {
    const ms = state.modes[modeId];
    if (!ms) return;
    ms.polling = false;
    if (ms.pollTimer) clearInterval(ms.pollTimer);
    ms.pollTimer = null;
  }

  function stopPoll() {
    stopPollForMode(state.mode);
    $("stopPollBtn")?.classList.add("hidden");
    setRunningStatus(false);
  }

  async function fetchJob(cfg, jobId, full) {
    const { data } = await api(
      `${cfg.apiRoot}/${jobId}?full=${full ? "1" : "0"}`,
      { timeoutMs: full ? 180000 : 30000 },
    );
    return data;
  }

  async function loadReportContent(job) {
    const cfg = getConfig();
    const result = job?.result || {};
    let content = resultText(result);
    const filename = reportFilename(result);
    if (!content && filename) {
      const { data } = await api(reportReadUrl(cfg, filename));
      content = data.content || "";
    }
    if (!content && job?.id) {
      const full = await fetchJob(cfg, job.id, true);
      content = resultText(full.result);
      return {
        ...(full.result || result),
        report: content,
        filename: filename || reportFilename(full.result),
      };
    }
    return { ...result, report: content, filename };
  }

  async function revealCompleted(job) {
    try {
      const result = await loadReportContent(job);
      renderResult(result);
      focusReportPane();
    } catch (err) {
      showError(err.message);
      if ($("reportMeta")) $("reportMeta").textContent = "报告已生成，请点左侧历史报告打开";
    }
  }

  async function pollJob(mode) {
    const cfg = getConfig(mode);
    const ms = getModeState(mode);
    if (!ms.jobId || !ms.polling || ms.pollInFlight) return;
    ms.pollInFlight = true;
    try {
      const job = await fetchJob(cfg, ms.jobId, false);
      ms.pollFailCount = 0;
      ms.job = job;
      if (state.mode === mode) renderJob(job);
      if (job.status === "completed") {
        stopPollForMode(mode);
        if (state.mode === mode) {
          $("stopPollBtn")?.classList.add("hidden");
          const hasInline = Boolean(resultText(job.result));
          renderJob(job);
          if (!hasInline) await revealCompleted(job);
          getModeState(mode).ready = true;
          await loadReports().catch(() => {});
        }
      } else if (job.status === "failed") {
        stopPollForMode(mode);
        if (state.mode === mode) {
          $("stopPollBtn")?.classList.add("hidden");
          renderJob(job);
        }
      }
    } catch (err) {
      ms.pollFailCount += 1;
      if (ms.pollFailCount <= 8) {
        if (state.mode === mode && $("jobMeta")) {
          $("jobMeta").textContent = `轮询暂时失败 (${ms.pollFailCount}/8) · 后台可能仍在运行`;
        }
        return;
      }
      stopPollForMode(mode);
      if (state.mode === mode) {
        $("stopPollBtn")?.classList.add("hidden");
        showError(err.message);
      }
    } finally {
      ms.pollInFlight = false;
    }
  }

  function startPoll(mode = state.mode) {
    const ms = getModeState(mode);
    stopPollForMode(mode);
    ms.polling = true;
    ms.lastLogLen = 0;
    if (mode === state.mode) $("stopPollBtn")?.classList.remove("hidden");
    ms.pollTimer = setInterval(() => pollJob(mode), 1000);
    pollJob(mode);
  }

  async function startTask() {
    const cfg = getConfig();
    const ms = getModeState();
    const company = companyQuery();
    if (!company) {
      showError("缺少公司代码");
      return;
    }
    showError("");
    setLive("busy");
    setBoardMode("running");
    syncActionButtons(true);
    ms.activeReportFile = "";
    ms.ready = false;
    ms.renderedReportKey = "";
    ms.lastLogSignature = "";
    try {
      const qs = new URLSearchParams({ company });
      const { data } = await api(`${cfg.apiRoot}?${qs}`, {
        method: "POST",
        timeoutMs: 30000,
      });
      ms.jobId = data.id;
      ms.job = data;
      renderJob(data);
      if ($("reportTitle")) $("reportTitle").textContent = cfg.runningTitle(company);
      highlightActiveReport();
      startPoll(state.mode);
    } catch (err) {
      showError(err.message);
      setLive("idle");
      setBoardMode("idle");
      syncActionButtons(false);
      showEmptyState();
    }
  }

  async function waitForIdentity(timeoutMs = 4000) {
    if (state.identity.ready || meaningfulName(state.identity.name, state.identity.code)) return;
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      await new Promise((r) => setTimeout(r, 200));
      if (state.identity.ready || meaningfulName(state.identity.name, state.identity.code)) return;
    }
  }

  async function findRunningJob(cfg) {
    try {
      const { data } = await api(`${cfg.apiRoot}/jobs`, { timeoutMs: 15000 });
      const jobs = Array.isArray(data) ? data : [];
      return jobs.find((job) => job.status === "running" && jobMatches(job)) || null;
    } catch {
      return null;
    }
  }

  function paintIdle() {
    const cfg = getConfig();
    setBoardMode("idle");
    setLive("idle");
    setRunningStatus(false);
    showError("");
    if ($("jobMeta")) $("jobMeta").textContent = "";
    if ($("reportTitle")) $("reportTitle").textContent = cfg.reportTitle;
    if ($("reportMeta")) $("reportMeta").textContent = cfg.reportMetaDefault;
    renderAgentBoard({});
    renderActivityLog([]);
    showEmptyState();
  }

  async function ensureForMode(mode, { force = false } = {}) {
    const cfg = getConfig(mode);
    const ms = getModeState(mode);
    const token = ++ms.seq;
    const stillCurrent = () => token === ms.seq && (force || state.mode === mode);

    applyChrome(mode);

    if (!force && ms.ready) {
      if (state.mode === mode) {
        if (ms.job) renderJob(ms.job);
        else if (ms.activeReportFile) {
          setBoardMode("result");
          highlightActiveReport();
        }
      }
      return;
    }

    if (ms.job?.status === "running" && ms.polling && !force) {
      if (state.mode === mode) renderJob(ms.job);
      ms.ready = true;
      return;
    }

    if (!force && ms.job?.status === "completed" && resultText(ms.job.result)) {
      if (state.mode === mode) {
        renderJob(ms.job);
        await loadReports().catch(() => {});
      }
      ms.ready = true;
      return;
    }

    if (state.mode === mode && !force) {
      const view = $("reportView");
      const empty = !view?.textContent?.trim() || view.querySelector(".ai-empty-state");
      if (empty) showReportLoading("正在加载…");
    }

    if (!force) await waitForIdentity();
    if (!stillCurrent()) return;

    try {
      const running = await findRunningJob(cfg);
      if (!stillCurrent()) return;
      if (running?.id) {
        ms.jobId = running.id;
        ms.job = await fetchJob(cfg, running.id, false);
        if (!stillCurrent()) return;
        if (state.mode === mode) renderJob(ms.job);
        startPoll(mode);
        return;
      }
    } catch {
      /* ignore */
    }

    let reports = [];
    try {
      reports = await loadReports();
      if (!stillCurrent()) return;
    } catch (err) {
      if (state.mode === mode) showError(err.message);
    }

    if (!force && reports?.length) {
      try {
        const latest = reports[0];
        const { data } = await api(reportReadUrl(cfg, latest.filename));
        if (!stillCurrent()) return;
        ms.activeReportFile = latest.filename;
        setBoardMode("result");
        if ($("reportTitle")) $("reportTitle").textContent = data.filename.replace(/\.md$/i, "");
        if ($("reportMeta")) $("reportMeta").textContent = latest.modified_at ? `已保存 · ${latest.modified_at}` : cfg.historyMeta;
        if ($("reportView")) $("reportView").innerHTML = renderMarkdown(data.content || "");
        ms.renderedReportKey = `${latest.filename}|${(data.content || "").length}`;
        highlightActiveReport();
        showError("");
        setLive("live");
        ms.ready = true;
        return;
      } catch (err) {
        if (state.mode === mode) showError(err.message);
      }
    }

    if (state.mode === mode) {
      paintIdle();
      if ($("reportMeta")) $("reportMeta").textContent = "暂无该公司报告，点击生成确认";
    }
    ms.ready = true;
  }

  async function onPanel(mode) {
    if (!MODES[mode]) return;
    if (mode !== state.mode) stopPollForMode(state.mode);
    state.mode = mode;
    applyChrome(mode);
    await ensureForMode(mode);
  }

  function syncIdentity(next = {}) {
    const code = String(next.code || state.identity.code || "").trim();
    const name = String(next.name || state.identity.name || "").trim();
    const ready = Boolean(next.ready) || state.identity.ready;
    const changed = code !== state.identity.code || name !== state.identity.name;
    state.identity = { code, name, ready: ready || Boolean(meaningfulName(name, code)) };
    applyChrome(state.mode);
    if (!analysisVisible()) return;
    if (!changed) return;
    const ms = getModeState();
    if (ms.ready) return;
    ensureForMode(state.mode);
  }

  function bind() {
    $("startBtn")?.addEventListener("click", () => {
      startTask().catch((err) => showError(err.message || String(err)));
    });
    $("stopPollBtn")?.addEventListener("click", stopPoll);
    $("refreshReportsBtn")?.addEventListener("click", () => {
      loadReports().catch((err) => showError(err.message));
    });
  }

  bind();
  paintIdle();

  window.CompanyAnalysis = {
    onPanel,
    syncIdentity,
    regenerate: startTask,
  };
})();
