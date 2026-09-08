(() => {
  const AGENT_DEFS = [
    { id: "er_init", name: "解析公司", subtitle: "识别代码与名称" },
    { id: "er_fetch", name: "采集财报", subtitle: "东财F10报表 / 估值 / 巨潮" },
    { id: "er_explain", name: "生成简述", subtitle: "每段附原始数据 · 巴菲特视角" },
    { id: "er_save", name: "保存报告", subtitle: "写入 Markdown" },
  ];

  const STATUS_LABELS = {
    pending: "等待",
    running: "进行中",
    done: "完成",
    failed: "失败",
  };

  const REPORT_NAME_RE = /财报解读|财报简述/;
  const JOB_STORE_KEY = "orbit.earnings.activeJob";
  const API_ROOT = "/api/ai/earnings-brief";

  const EMPTY_STATE_HTML = `
    <div class="ai-empty-state">
      <div class="ai-empty-icon" aria-hidden="true">▤</div>
      <h3>先看数字，再谈判断</h3>
      <p>输入一家公司，智能体拉取近一年年报/半年报/季报原始科目，每段解释都附带财报数据，最后从巴菲特视角评估安全边际。</p>
      <ul class="ai-empty-tips">
        <li>近3-5年营收、净利润、经营利润</li>
        <li>ROE / ROA / 毛利率 / 经营利润率</li>
        <li>经营现金流、自由现金流、资本开支</li>
        <li>资产负债、估值与内在价值</li>
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
    pollInFlight: false,
  };

  const $ = (id) => document.getElementById(id);

  function readJobHandle() {
    try {
      const raw = localStorage.getItem(JOB_STORE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function saveJobHandle(job) {
    if (!job?.id) return;
    try {
      localStorage.setItem(JOB_STORE_KEY, JSON.stringify({
        id: job.id,
        company: job.company || "",
        savedAt: Date.now(),
      }));
    } catch {
      /* ignore quota / private mode */
    }
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
    return `${label} · ${job.company}${stock}`;
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
      chip.textContent = "生成中";
      chip.classList.remove("hidden");
      chip.dataset.state = "busy";
    } else {
      chip.classList.add("hidden");
      chip.dataset.state = "";
      $("progressPanel")?.classList.remove("is-active");
    }
  }

  function reportFilename(result) {
    if (result?.filename) return result.filename;
    const path = result?.report_path || "";
    const parts = String(path).split(/[/\\]/);
    return parts.pop() || "";
  }

  function focusReportPane() {
    const pane = document.querySelector(".ai-pane-report");
    const scroller = document.querySelector(".ai-report-scroll");
    pane?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    if (scroller) scroller.scrollTop = 0;
  }

  function showReportLoading(message) {
    setBoardMode("result");
    $("reportMeta").textContent = message;
    $("reportView").innerHTML = `
      <div class="ai-empty-state">
        <h3>简述已生成</h3>
        <p>${esc(message)}</p>
      </div>
    `;
  }

  async function loadReportContent(job) {
    const result = job?.result || {};
    let content = resultText(result);
    const filename = reportFilename(result);
    if (!content && filename) {
      const { data } = await api(`${API_ROOT}/reports/${encodeURIComponent(filename)}`);
      content = data.content || "";
    }
    if (!content && job?.id) {
      const full = await fetchJob(job.id, true);
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
    showReportLoading("正在打开报告…");
    try {
      const result = await loadReportContent(job);
      renderResult(result);
      const filename = reportFilename(result);
      if (filename) {
        state.activeReportFile = filename;
        highlightActiveReport();
      }
      focusReportPane();
    } catch (err) {
      showError(err.message);
      $("reportMeta").textContent = "报告已生成，请点左侧历史简述打开";
    }
  }

  function showEmptyState() {
    $("reportView").innerHTML = EMPTY_STATE_HTML;
  }

  function resultText(result) {
    return result?.brief || result?.report || result?.explanation || "";
  }

  function renderResult(result) {
    if (!result) return;
    state.activeReportFile = "";
    $("reportTitle").textContent = `${result.stock_name || ""} 财报简述`.trim();
    $("reportMeta").textContent = [
      result.stock_code ? `代码 ${result.stock_code}` : "",
      result.report_path ? "已保存" : "",
    ].filter(Boolean).join(" · ");
    $("reportView").innerHTML = renderMarkdown(resultText(result));
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
      showError(job.error || "生成失败");
      setRunningStatus(false);
      $("reportMeta").textContent = "生成失败";
    } else if (job?.status === "completed") {
      showError("");
      setRunningStatus(false);
      const content = resultText(job.result);
      if (!content) {
        showReportLoading("简述已生成，正在打开报告…");
        return;
      }
      renderResult(job.result);
      const filename = reportFilename(job.result);
      if (filename) {
        state.activeReportFile = filename;
        highlightActiveReport();
      }
      focusReportPane();
    }
  }

  function highlightActiveReport() {
    document.querySelectorAll(".ai-history-item").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.file === state.activeReportFile);
    });
  }

  async function loadReports() {
    const { data } = await api(`${API_ROOT}/reports`);
    state.reports = (data || []).filter((r) => REPORT_NAME_RE.test(r.filename));
    const list = $("reportList");
    if (!state.reports.length) {
      list.innerHTML = "<li class='muted' style='padding:10px'>暂无历史简述</li>";
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
          const { data } = await api(`${API_ROOT}/reports/${encodeURIComponent(btn.dataset.file)}`);
          state.activeReportFile = btn.dataset.file;
          setBoardMode("result");
          $("reportTitle").textContent = data.filename.replace(/\.md$/i, "");
          $("reportMeta").textContent = "历史简述";
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
    if (!state.jobId || !state.polling || state.pollInFlight) return;
    state.pollInFlight = true;
    try {
      const { data } = await api(
        `${API_ROOT}/${state.jobId}?full=0`,
        { timeoutMs: 30000 },
      );
      state.pollFailCount = 0;
      saveJobHandle(data);
      if (data.status === "completed") {
        stopPoll();
        renderJob(data);
        await revealCompleted(data);
        await loadReports().catch(() => {});
      } else if (data.status === "failed") {
        stopPoll();
        renderJob(data);
      } else {
        renderJob(data);
      }
    } catch (err) {
      state.pollFailCount += 1;
      if (state.pollFailCount <= 8) {
        $("jobMeta").textContent = `轮询暂时失败 (${state.pollFailCount}/8) · 后台可能仍在运行`;
        return;
      }
      showError(err.message);
      stopPoll();
    } finally {
      state.pollInFlight = false;
    }
  }

  function startPoll() {
    stopPoll();
    state.polling = true;
    state.lastLogLen = 0;
    $("stopPollBtn").classList.remove("hidden");
    state.pollTimer = setInterval(pollJob, 1000);
    pollJob();
  }

  function stopPoll() {
    state.polling = false;
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = null;
    $("stopPollBtn").classList.add("hidden");
  }

  async function startReview() {
    const company = $("companyInput").value.trim();
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
      const { data } = await api(`${API_ROOT}?${qs}`, {
        method: "POST",
        timeoutMs: 30000,
      });
      state.jobId = data.id;
      saveJobHandle(data);
      renderJob(data);
      $("reportTitle").textContent = `${company} · 财报简述`;
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
          $("companyInput").value = [btn.dataset.name, btn.dataset.code].filter(Boolean).join(" ");
          $("suggestBox").classList.add("hidden");
        });
      });
    } catch {
      $("suggestBox").classList.add("hidden");
    }
  }

  function bindEvents() {
    $("startBtn").addEventListener("click", startReview);
    $("stopPollBtn").addEventListener("click", stopPoll);
    $("refreshReportsBtn").addEventListener("click", () => loadReports().catch((e) => showError(e.message)));
    $("companyInput").addEventListener("input", (e) => {
      clearTimeout(state.suggestTimer);
      state.suggestTimer = setTimeout(() => suggestCompanies(e.target.value.trim()), 250);
    });
    $("companyInput").addEventListener("keydown", (e) => {
      if (e.key === "Enter") startReview();
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".ai-search-wrap")) {
        $("suggestBox").classList.add("hidden");
      }
    });
  }

  async function fetchJob(jobId, full) {
    const { data } = await api(
      `${API_ROOT}/${jobId}?full=${full ? "1" : "0"}`,
      { timeoutMs: full ? 180000 : 30000 },
    );
    return data;
  }

  async function resumeActiveJob() {
    const handle = readJobHandle();
    let job = null;
    if (handle?.id) {
      try {
        job = await fetchJob(handle.id, false);
      } catch {
        job = null;
      }
    }
    if (!job) {
      try {
        const { data } = await api(`${API_ROOT}/jobs`, { timeoutMs: 15000 });
        const jobs = Array.isArray(data) ? data : [];
        const running = jobs.find((item) => item.status === "running");
        const latest = running || jobs[0] || null;
        if (latest?.id) job = await fetchJob(latest.id, latest.status === "completed");
      } catch {
        return false;
      }
    }
    if (!job) return false;
    state.jobId = job.id;
    saveJobHandle(job);
    if (job.company && $("companyInput")) $("companyInput").value = job.company;
    renderJob(job);
    if (job.status === "running") {
      $("reportTitle").textContent = `${job.company || ""} · 财报简述`.trim();
      startPoll();
      return true;
    }
    if (job.status === "completed") {
      await revealCompleted(job);
    }
    return true;
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
    try {
      await resumeActiveJob();
    } catch (err) {
      showError(err.message || "恢复财报简述任务失败");
    }
  }

  init();
})();
