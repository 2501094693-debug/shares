(() => {
  const AGENT_DEFS = [
    { id: "init", name: "初始化", subtitle: "解析标的 / 信息丰富度" },
    { id: "business_analyst", name: "商业模式", subtitle: "段永平视角" },
    { id: "financial_analyst", name: "财务估值", subtitle: "巴菲特视角" },
    { id: "industry_researcher", name: "行业竞争", subtitle: "芒格视角" },
    { id: "risk_assessor", name: "风险治理", subtitle: "李录视角" },
    { id: "team_lead", name: "汇总报告", subtitle: "team-lead 综合研判" },
    { id: "save", name: "保存报告", subtitle: "写入 Markdown" },
    { id: "audit", name: "数据抽检", subtitle: "15% 抽样清单" },
  ];

  const STATUS_LABELS = {
    pending: "等待",
    running: "进行中",
    done: "完成",
    failed: "失败",
  };

  const REPORT_NAME_RE = /投资研究报告/;

  const EMPTY_STATE_HTML = `
    <div class="ai-empty-state">
      <div class="ai-empty-icon" aria-hidden="true">◇</div>
      <h3>四角色并行投研</h3>
      <p>输入一家公司，投研团队将并行完成商业模式、财务估值、行业竞争、风险治理四维分析，并由 team-lead 输出最终投资建议。</p>
      <ul class="ai-empty-tips">
        <li>商业模式 & 护城河（段永平）</li>
        <li>财务报表 & 估值（巴菲特）</li>
        <li>行业格局 & 竞争（芒格）</li>
        <li>风险 & 管理层（李录）</li>
      </ul>
    </div>
  `;

  const state = {
    jobId: "",
    polling: false,
    pollTimer: null,
    activeReportFile: "",
    job: null,
    reports: [],
    suggestTimer: null,
    lastLogLen: 0,
    pollFailCount: 0,
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
    board.classList.remove("is-idle", "is-running", "is-result");
    board.classList.add(`is-${mode}`);
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

  async function api(path, options = {}) {
    const { timeoutMs = 0, ...fetchOptions } = options;
    const controller = timeoutMs > 0 ? new AbortController() : null;
    const timer = controller
      ? setTimeout(() => controller.abort(), timeoutMs)
      : null;
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

  function renderMarkdown(text) {
    if (!text) return "<p class='muted'>（暂无内容）</p>";
    let html = esc(text);
    html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
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

  function formatTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function formatJobMeta(job) {
    if (!job) return "";
    const statusMap = { running: "研究中", completed: "已完成", failed: "失败" };
    const label = statusMap[job.status] || job.status;
    const stock = job.stock?.code ? ` · ${job.stock.code}` : "";
    const richness = job.result?.info_richness ? ` · 信息${job.result.info_richness}` : "";
    return `${label} · ${job.company}${stock}${richness}`;
  }

  function updatePipelineProgress(agents) {
    const el = $("pipelineProgress");
    if (!el) return;
    const done = AGENT_DEFS.filter((d) => agents?.[d.id]?.status === "done").length;
    el.textContent = `${done} / ${AGENT_DEFS.length}`;
  }

  function renderAgentBoard(agents) {
    const board = $("agentBoard");
    if (!board) return;
    board.innerHTML = AGENT_DEFS.map((def) => {
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
    const box = $("currentAction");
    if (!box) return;
    const runningAgents = AGENT_DEFS
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
    const list = $("activityLog");
    const panel = $("progressPanel");
    if (!list) return;

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

    if (log.length > state.lastLogLen) {
      list.scrollTop = 0;
      state.lastLogLen = log.length;
    }
  }

  function setRunningStatus(running) {
    const chip = $("reportStatus");
    if (running) {
      chip.textContent = "研究中";
      chip.classList.remove("hidden");
      chip.dataset.state = "busy";
    } else {
      chip.classList.add("hidden");
      chip.dataset.state = "";
      $("progressPanel")?.classList.remove("is-active");
    }
  }

  function showEmptyState() {
    $("reportView").innerHTML = EMPTY_STATE_HTML;
  }

  function renderResult(result) {
    if (!result) return;
    state.activeReportFile = "";
    $("reportTitle").textContent = `${result.stock_name || ""} 投资研究报告`.trim();
    const metaParts = [
      result.stock_code ? `代码 ${result.stock_code}` : "",
      result.info_richness ? `信息丰富度 ${result.info_richness}` : "",
      result.report_path ? "已保存" : "",
    ].filter(Boolean);
    $("reportMeta").textContent = metaParts.join(" · ");
    $("reportView").innerHTML = renderMarkdown(result.final_report || "");
    highlightActiveReport();
  }

  function renderJob(job) {
    state.job = job;
    $("jobMeta").textContent = formatJobMeta(job);

    const mode = !job || job.status === "running"
      ? "running"
      : job.status === "completed" ? "result" : job.status === "failed" ? "result" : "idle";
    setBoardMode(mode);

    renderAgentBoard(job?.agents || {});
    renderCurrentAction(job?.current, job);
    renderActivityLog(job?.activity_log || []);

    const running = job?.status === "running";
    setRunningStatus(running);
    setLive(running ? "busy" : job?.status === "completed" ? "live" : "idle");

    if (job?.status === "failed") {
      showError(job.error || "投研失败");
      setRunningStatus(false);
      $("reportMeta").textContent = "投研失败";
    } else if (job?.status === "completed") {
      showError("");
      setRunningStatus(false);
      const content = job.result?.final_report;
      if (job.result?.ready && !content) {
        $("reportMeta").textContent = "报告已生成，正在加载全文…";
        return;
      }
      renderResult(job.result);
    }
  }

  function highlightActiveReport() {
    document.querySelectorAll(".ai-history-item").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.file === state.activeReportFile);
    });
  }

  async function loadReports() {
    const { data } = await api("/api/ai/research/reports");
    state.reports = (data || []).filter((r) => REPORT_NAME_RE.test(r.filename));
    const list = $("reportList");
    if (!state.reports.length) {
      list.innerHTML = "<li class='muted' style='padding:10px'>暂无历史报告</li>";
      return;
    }
    list.innerHTML = state.reports.map((row) => (
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
          const { data } = await api(`/api/ai/research/reports/${encodeURIComponent(btn.dataset.file)}`);
          state.activeReportFile = btn.dataset.file;
          setBoardMode("result");
          $("reportTitle").textContent = data.filename.replace(/\.md$/i, "");
          $("reportMeta").textContent = "历史报告";
          $("reportView").innerHTML = renderMarkdown(data.content || "");
          highlightActiveReport();
          showError("");
        } catch (err) {
          showError(err.message);
        }
      });
    });
    highlightActiveReport();
  }

  async function pollJob() {
    if (!state.jobId || !state.polling) return;
    try {
      const { data } = await api(
        `/api/ai/research/${state.jobId}?full=0`,
        { timeoutMs: 30000 },
      );
      state.pollFailCount = 0;
      renderJob(data);
      if (data.status === "completed") {
        const full = await api(
          `/api/ai/research/${state.jobId}?full=1`,
          { timeoutMs: 300000 },
        );
        renderJob(full.data);
        stopPoll();
        loadReports();
      } else if (data.status === "failed") {
        stopPoll();
      }
    } catch (err) {
      state.pollFailCount += 1;
      if (state.pollFailCount <= 8) {
        $("jobMeta").textContent = `轮询暂时失败 (${state.pollFailCount}/8) · 后台可能仍在运行`;
        return;
      }
      showError(err.message);
      stopPoll();
    }
  }

  function startPoll() {
    stopPoll();
    state.polling = true;
    state.lastLogLen = 0;
    $("stopPollBtn").classList.remove("hidden");
    state.pollTimer = setInterval(pollJob, 1500);
    pollJob();
  }

  function stopPoll() {
    state.polling = false;
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = null;
    $("stopPollBtn").classList.add("hidden");
  }

  async function startResearch() {
    const company = $("companyInput").value.trim();
    const request = $("requestInput").value.trim();
    if (!company) {
      showError("请输入公司名称或代码");
      return;
    }
    showError("");
    $("startBtn").disabled = true;
    setLive("busy");
    setBoardMode("running");
    state.activeReportFile = "";
    try {
      const qs = new URLSearchParams({ company });
      if (request) qs.set("request", request);
      const { data } = await api(`/api/ai/research?${qs}`, {
        method: "POST",
        timeoutMs: 30000,
      });
      state.jobId = data.id;
      renderJob(data);
      $("reportTitle").textContent = `${company} · 投研中`;
      highlightActiveReport();
      startPoll();
    } catch (err) {
      showError(err.message);
      setLive("idle");
    } finally {
      $("startBtn").disabled = false;
    }
  }

  async function suggestCompanies(keyword) {
    if (!keyword || keyword.length < 2) {
      $("suggestBox").classList.add("hidden");
      return;
    }
    try {
      const { data } = await api(`/api/stocks/search?name=${encodeURIComponent(keyword)}`);
      const items = Array.isArray(data) ? data : [];
      if (!items.length) {
        $("suggestBox").classList.add("hidden");
        return;
      }
      $("suggestBox").innerHTML = items.map((row) => (
        `<button type="button" class="ai-suggest-item" data-code="${esc(row.code)}" data-name="${esc(row.name)}">${esc(row.name)} <span class="muted">${esc(row.code)}</span></button>`
      )).join("");
      $("suggestBox").classList.remove("hidden");
      $("suggestBox").querySelectorAll(".ai-suggest-item").forEach((btn) => {
        btn.addEventListener("click", () => {
          $("companyInput").value = btn.dataset.name || btn.dataset.code;
          $("suggestBox").classList.add("hidden");
        });
      });
    } catch {
      $("suggestBox").classList.add("hidden");
    }
  }

  function bindEvents() {
    $("startBtn").addEventListener("click", startResearch);
    $("stopPollBtn").addEventListener("click", stopPoll);
    $("refreshReportsBtn").addEventListener("click", () => loadReports().catch((e) => showError(e.message)));
    $("companyInput").addEventListener("input", (e) => {
      clearTimeout(state.suggestTimer);
      state.suggestTimer = setTimeout(() => suggestCompanies(e.target.value.trim()), 250);
    });
    $("companyInput").addEventListener("keydown", (e) => {
      if (e.key === "Enter") startResearch();
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".ai-search-wrap")) {
        $("suggestBox").classList.add("hidden");
      }
    });
  }

  async function init() {
    bindEvents();
    setBoardMode("idle");
    renderAgentBoard({});
    renderActivityLog([]);
    showEmptyState();
    try {
      await loadReports();
    } catch (err) {
      showError(err.message);
    }
  }

  init();
})();
