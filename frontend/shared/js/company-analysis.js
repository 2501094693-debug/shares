(() => {
  const MODES = window.AI_MODES || {};
  const MODE_ORDER = window.AI_MODE_ORDER || ["business", "bazhang", "bazhang-rules", "buffett", "buffett-rules", "competition", "chain", "risk", "trend", "fundamentals", "valuation", "sentiment", "chip", "compare"];
  const EARNINGS_VIEWS = new Set(["bazhang", "bazhang-rules", "buffett", "buffett-rules"]);

  const STATUS_LABELS = {
    pending: "等待",
    running: "进行中",
    done: "完成",
    skipped: "跳过",
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
      enginePack: null,
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

  function isEngineMode(mode = state.mode) {
    return getConfig(mode).kind === "engine";
  }

  function judgmentFamily(mode = state.mode) {
    return EARNINGS_VIEWS.has(mode) ? "earnings" : mode;
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
    const panel = $("panel-judgment");
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
    html = html.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
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
    const engine = isEngineMode();
    if (board.classList.contains(next) && board.classList.contains("is-engine") === engine) return;
    board.classList.remove("is-idle", "is-running", "is-result");
    board.classList.add(next);
    board.classList.toggle("is-engine", engine);
  }

  function friendlyError(message) {
    const s = String(message || "");
    if (/Connection aborted|RemoteDisconnected|ConnectionError|Failed to fetch|NetworkError|timeout|503/.test(s)) {
      return "行情接口暂时抖动（东财限流/断连），请等待约10秒后点“重新计算”重试。若反复出现可换个时间再试。";
    }
    return s;
  }

  function showError(message) {
    const box = $("analysisErrorBox");
    if (!box) return;
    if (!message) {
      box.classList.add("hidden");
      box.textContent = "";
      return;
    }
    box.textContent = friendlyError(message);
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
    const m = job.result?.metrics || {};
    const sentiment = Number.isFinite(Number(m.n_retail_users))
      ? ` · 散户 ${m.n_retail_users} · 买${m.buy_users ?? 0}/卖${m.sell_users ?? 0}/观望${m.wait_users ?? 0}`
      : "";
    const v = job.result?.verdict || {};
    const trend = v.lean
      ? ` · ${v.lean}${Number.isFinite(Number(v.confidence)) ? ` · 置信度 ${v.confidence}` : ""}`
      : "";
    return `${label} · ${job.company}${stock}${industry}${sentiment}${trend}`;
  }

  function pctLabel(value) {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    return `${Math.round(Number(value) * 100)}%`;
  }

  function sentimentMetricsHtml(result) {
    const m = result?.metrics;
    if (!m || !Number.isFinite(Number(m.n_retail_users))) return "";
    const by = m.by_source || {};
    const sourceBits = [
      ["eastmoney", "东财"],
      ["tonghuashun", "同花顺"],
      ["xueqiu", "雪球"],
    ].map(([key, title]) => {
      const block = by[key] || {};
      const n = Number(block.n_retail_users);
      return Number.isFinite(n) ? `${title}${n}` : "";
    }).filter(Boolean).join(" / ");
    const kpis = [
      ["发声散户", String(m.n_retail_users ?? "—")],
      ["看多", `${m.bull_users ?? 0}（${pctLabel(m.bull_share)}）`],
      ["看空", `${m.bear_users ?? 0}（${pctLabel(m.bear_share)}）`],
      ["买入", String(m.buy_users ?? 0)],
      ["卖出", String(m.sell_users ?? 0)],
      ["观望", String(m.wait_users ?? 0)],
    ];
    const kpiHtml = kpis.map(([label, value]) => (
      `<div class="engine-kpi sentiment-kpi"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`
    )).join("");
    const note = sourceBits
      ? `<p class="muted sentiment-source-note">分源人数：${esc(sourceBits)}（跨平台可能重复；文本意图 ≠ 成交）</p>`
      : `<p class="muted sentiment-source-note">文本意图 ≠ 成交；跨平台不对齐真人账号</p>`;
    return `<div class="sentiment-metrics"><div class="engine-kpis">${kpiHtml}</div>${note}</div>`;
  }

  function trendMetricsHtml(result) {
    const v = result?.verdict;
    if (!v || !v.lean) return "";
    const main = result.main_force || {};
    const retail = result.retail || {};
    const kpis = [
      ["综合倾向", String(v.lean)],
      ["置信度", Number.isFinite(Number(v.confidence)) ? String(v.confidence) : "—"],
      ["主力", String(main.label || v.main_label || "—")],
      ["散户", `${retail.stance || v.retail_stance || "—"} · ${retail.activity || v.retail_activity || "—"}`],
      ["关系", String(v.relation || retail.relation_to_main || "—")],
      ["大单主动买", Number.isFinite(Number(main.active_buy_share))
        ? `${Math.round(Number(main.active_buy_share) * 100)}%`
        : "—"],
    ];
    const kpiHtml = kpis.map(([label, value]) => (
      `<div class="engine-kpi sentiment-kpi"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`
    )).join("");
    const note = `<p class="muted sentiment-source-note">仅资金与分时；散户为小单活跃度代理，非持仓人数</p>`;
    return `<div class="sentiment-metrics"><div class="engine-kpis">${kpiHtml}</div>${note}</div>`;
  }

  function fmtPrice(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n >= 100 ? n.toFixed(2) : String(Math.round(n * 100) / 100);
  }

  function valuationMetricsHtml(result) {
    if (!result?.stance && !result?.primary) return "";
    const kpis = [
      ["综合态度", String(result.stance || "—")],
      ["主倍数", String(result.primary || "—")],
      ["生意类型", String(result.business_type || "—")],
      ["综合锚股价", fmtPrice(result.anchor_mid_price)],
      ["巴菲特下限", fmtPrice(result.mos_floor_price)],
    ];
    const kpiHtml = kpis.map(([label, value]) => (
      `<div class="engine-kpi sentiment-kpi"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`
    )).join("");
    const note = `<p class="muted sentiment-source-note">数字由规则引擎计算；综合态度不是买卖点</p>`;
    return `<div class="sentiment-metrics"><div class="engine-kpis">${kpiHtml}</div>${note}</div>`;
  }

  function fmtMos(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return `${(n * 100).toFixed(1)}%`;
  }

  function fundamentalsMetricsHtml(result) {
    if (!result?.stance && result?.anchor_iv == null) return "";
    const lightMap = { green: "绿", yellow: "黄", red: "红", gray: "灰" };
    const dims = Array.isArray(result.dims) ? result.dims : [];
    const dimText = dims.length
      ? dims.map((d) => `${d.label || d.key || ""}${lightMap[d.light] || d.light || ""}`).filter(Boolean).join(" · ")
      : "—";
    const kpis = [
      ["规则态度", String(result.stance || "—")],
      ["内在价值锚", fmtPrice(result.anchor_iv)],
      ["安全边际", fmtMos(result.anchor_mos)],
      ["仪表盘", dimText],
    ];
    const kpiHtml = kpis.map(([label, value]) => (
      `<div class="engine-kpi sentiment-kpi"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`
    )).join("");
    const note = `<p class="muted sentiment-source-note">台账与仪表盘规则先算；态度不是买卖点</p>`;
    return `<div class="sentiment-metrics"><div class="engine-kpis">${kpiHtml}</div>${note}</div>`;
  }

  function updatePipelineProgress(agents) {
    const cfg = getConfig();
    const el = $("pipelineProgress");
    if (!el) return;
    const done = (cfg.agentDefs || []).filter((d) => {
      const s = agents?.[d.id]?.status;
      return s === "done" || s === "skipped";
    }).length;
    el.textContent = `${done} / ${(cfg.agentDefs || []).length}`;
  }

  function renderAgentBoard(agents) {
    const cfg = getConfig();
    const board = $("agentBoard");
    if (!board) return;
    board.innerHTML = (cfg.agentDefs || []).map((def) => {
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
    const scroller = document.querySelector("#panel-judgment .ai-report-scroll");
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
    const agentCount = cfg.agentDefs?.length || 0;
    if ($("pipelineProgress")) $("pipelineProgress").textContent = `0 / ${agentCount}`;
    const family = judgmentFamily(mode);
    const visible = analysisVisible();
    const panel = $("panel-judgment");
    if (panel) {
      panel.dataset.judgmentView = mode;
      panel.dataset.judgmentFamily = family;
    }
    document.querySelectorAll("#judgmentSourceBar [data-source]").forEach((tab) => {
      const active = tab.getAttribute("data-source") === family;
      tab.classList.toggle("is-active", active && visible);
      tab.setAttribute("aria-selected", active && visible ? "true" : "false");
    });
    const sub = $("earningsSourceBar");
    if (sub) sub.hidden = family !== "earnings";
    document.querySelectorAll("#earningsSourceBar [data-source]").forEach((tab) => {
      const active = tab.getAttribute("data-source") === mode;
      tab.classList.toggle("is-active", active && visible);
      tab.setAttribute("aria-selected", active && visible ? "true" : "false");
    });
    $("aiBoard")?.classList.toggle("is-engine", cfg.kind === "engine");
    const board = $("aiBoard");
    const idleOrLoading = !board
      || board.classList.contains("is-idle")
      || Boolean($("reportView")?.querySelector(".ai-empty-state"));
    if (idleOrLoading && $("reportTitle")) $("reportTitle").textContent = cfg.reportTitle;
    if (board?.classList.contains("is-idle") && $("reportMeta")) {
      $("reportMeta").textContent = cfg.reportMetaDefault;
    }
    renderAgentBoard(getModeState(mode).job?.agents || {});
  }

  function showReportLoading(message, title = "正在加载") {
    setBoardMode("result");
    if ($("reportMeta")) $("reportMeta").textContent = message;
    if ($("reportView")) {
      $("reportView").innerHTML = `
        <div class="ai-empty-state">
          <div class="ai-empty-icon" aria-hidden="true">◌</div>
          <h3>${esc(title)}</h3>
          <p>${esc(message)}</p>
        </div>
      `;
    }
  }

  function highlightActiveReport() {
    const ms = getModeState();
    document.querySelectorAll("#panel-judgment .ai-history-item").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.file === ms.activeReportFile);
    });
  }

  function renderResult(result) {
    const cfg = getConfig();
    const ms = getModeState();
    if (!result) return;
    const filename = reportFilename(result);
    const text = resultText(result);
    const metricsKey = cfg.id === "sentiment"
      ? JSON.stringify(result.metrics || {})
      : cfg.id === "trend"
        ? JSON.stringify(result.verdict || {})
        : cfg.id === "valuation"
          ? JSON.stringify({ stance: result.stance, primary: result.primary })
          : cfg.id === "fundamentals"
            ? JSON.stringify({ stance: result.stance, anchor_iv: result.anchor_iv, anchor_mos: result.anchor_mos })
            : "";
    const reportKey = `${filename}|${text.length}|${metricsKey}`;
    if (filename) ms.activeReportFile = filename;
    if ($("reportTitle")) $("reportTitle").textContent = cfg.resultTitle?.(result) || String(filename).replace(/\.md$/i, "");
    if ($("reportMeta")) $("reportMeta").textContent = cfg.resultMeta?.(result) || "已保存";
    if (ms.renderedReportKey !== reportKey && $("reportView")) {
      const metrics = cfg.id === "sentiment"
        ? sentimentMetricsHtml(result)
        : cfg.id === "trend"
          ? trendMetricsHtml(result)
          : cfg.id === "valuation"
            ? valuationMetricsHtml(result)
            : cfg.id === "fundamentals"
              ? fundamentalsMetricsHtml(result)
              : "";
      $("reportView").innerHTML = `${metrics}${renderMarkdown(text)}`;
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
        showReportLoading("正在打开…", "报告已生成");
        return;
      }
      renderResult(job.result);
      focusReportPane();
    }
  }

  function fmtEngineNum(value, kind = "yi") {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    if (kind === "pct") return `${n.toFixed(1)}%`;
    if (kind === "x") return `${n.toFixed(2)}×`;
    const sign = n < 0 ? "-" : "";
    const abs = Math.abs(n);
    if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
    if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(2)}万`;
    return `${sign}${abs.toFixed(2)}`;
  }

  function cmpFormParams() {
    const pick = (id) => String(document.getElementById(id)?.value || "").trim();
    const extra = {};
    const index = pick("cmpIndex"), beg = pick("cmpBeg"), end = pick("cmpEnd");
    if (index) extra.index = index;
    if (beg) extra.beg = beg;
    if (end) extra.end = end;
    return extra;
  }

  function cmpHtml(pack) {
    const meta = pack.meta || {};
    const total = pack.total || {};
    const scores = pack.scores || {};
    const weights = { open: 0.15, high: 0.20, low: 0.25, close: 0.40 };
    const names = { open: "开盘", high: "最高", low: "最低", close: "收盘" };
    const scoreRows = ["open", "high", "low", "close"].map((k) => {
      const s = Number(scores[k]);
      const w = weights[k];
      return `<tr>
        <td>${names[k]}</td>
        <td class="num">${Number.isFinite(s) ? s.toFixed(4) : "—"}</td>
        <td class="num">${w.toFixed(2)}</td>
        <td class="num">${Number.isFinite(s) ? (s * w).toFixed(4) : "—"}</td>
      </tr>`;
    }).join("");
    const closes = [...(pack.daily?.close || [])].sort((a, b) => Math.abs(b.dif) - Math.abs(a.dif)).slice(0, 10);
    const dayRows = closes.length ? closes.map((r) => `<tr>
        <td>${esc(r.date || "")}</td>
        <td class="num">${(Number(r.rs) * 100).toFixed(2)}%</td>
        <td class="num">${(Number(r.rb) * 100).toFixed(2)}%</td>
        <td class="num">${(Number(r.dif) * 100).toFixed(2)}%</td>
        <td>${esc(r.dir || "")}</td>
      </tr>`).join("") : `<tr><td colspan="5" class="muted">暂无逐日数据</td></tr>`;
    const dirs = {};
    (pack.daily?.close || []).forEach((r) => { dirs[r.dir] = (dirs[r.dir] || 0) + 1; });
    const dirText = Object.entries(dirs).map(([k, v]) => `${k}${v}`).join(" · ") || "—";
    return `
      <div class="chip-params">
        <label>对比指数<input id="cmpIndex" value="${esc(meta.index || "SH000001")}" /></label>
        <label>区间<input id="cmpBeg" type="date" value="${esc(meta.beg || "")}" /></label>
        <span class="muted">–</span>
        <label>至<input id="cmpEnd" type="date" value="${esc(meta.end || "")}" /></label>
        <button type="button" id="cmpRecalc" class="btn primary">计算</button>
      </div>
      <div class="engine-kpis">
        <div class="engine-kpi"><span>偏离总分</span><strong>${esc(String(total.value ?? "—"))}</strong></div>
        <div class="engine-kpi"><span>等级</span><strong>${esc(total.level || "—")}</strong></div>
        <div class="engine-kpi"><span>对齐交易日</span><strong>${esc(String(meta.n ?? "—"))}</strong></div>
        <div class="engine-kpi"><span>主要贡献</span><strong>${esc((total.top || []).join(" + ") || "—")}</strong></div>
      </div>
      <section class="engine-section"><h3>四图偏离柱状图（X=日期，Y=偏离DIF · 滚轮缩放 · 拖拽左右滚动 · 悬浮看某日数据）</h3>
        <div class="cmp-charts">
          <figure><figcaption>开盘偏离</figcaption><canvas id="cmpChart-open" height="180"></canvas></figure>
          <figure><figcaption>最高偏离</figcaption><canvas id="cmpChart-high" height="180"></canvas></figure>
          <figure><figcaption>最低偏离</figcaption><canvas id="cmpChart-low" height="180"></canvas></figure>
          <figure><figcaption>收盘偏离</figcaption><canvas id="cmpChart-close" height="180"></canvas></figure>
        </div>
      </section>
      <section class="engine-section"><h3>四图得分（${esc(meta.stock_name || meta.stock || "")} vs ${esc(meta.index_name || meta.index || "")}）</h3>
        <div class="rot-scroll"><table class="rot-table">
          <thead><tr><th>类型</th><th class="num">得分</th><th class="num">权重</th><th class="num">加权</th></tr></thead>
          <tbody>${scoreRows}</tbody>
        </table></div>
        <p class="muted sentiment-source-note">收盘方向分布：${esc(dirText)}</p>
      </section>
      <section class="engine-section"><h3>偏离最大的10个交易日（收盘）</h3>
        <div class="rot-scroll"><table class="rot-table">
          <thead><tr><th>日期</th><th class="num">个股</th><th class="num">指数</th><th class="num">偏离</th><th>方向</th></tr></thead>
          <tbody>${dayRows}</tbody>
        </table></div>
      </section>
    `;
  }

  function chipFormParams() {    const pick = (id) => String(document.getElementById(id)?.value || "").trim();
    const extra = {};
    const start = pick("chipStart"), end = pick("chipEnd"), target = pick("chipTarget");
    const order = pick("chipOrder") || "desc";
    if (start) extra.start = start;
    if (end) extra.end = end;
    if (target) extra.target = target;
    if (order) extra.order = order;
    return extra;
  }

  function chipHtml(pack) {
    const res = pack?.result || {};
    const names = { open: "开盘", high: "最高", low: "最低", close: "收盘" };
    const rows = ["open", "high", "low", "close"].map((k) => {
      const r = res[k] || {};
      const pct = Number(r.percent);
      const bar = Number.isFinite(pct) ? Math.max(0, Math.min(100, pct)) : 0;
      return `<tr>
        <td>${names[k]}</td>
        <td class="num">${esc(String(r.value ?? "—"))}</td>
        <td class="num">${esc(String(r.rank ?? "—"))} / ${esc(String(r.total ?? "—"))}</td>
        <td><div class="chip-bar"><i style="width:${bar}%"></i></div></td>
        <td class="num">${Number.isFinite(pct) ? pct.toFixed(2) + "%" : "—"}</td>
      </tr>`;
    }).join("");
    const sub = pack.substituted
      ? `<p class="muted sentiment-source-note">目标日 ${esc(pack.target_requested || "")} 非交易日，已取前一个交易日 ${esc(pack.target || "")}</p>`
      : "";
    return `
      <div class="chip-params">
        <label>区间<input id="chipStart" type="date" value="${esc(pack.start || "")}" /></label>
        <span class="muted">–</span>
        <label>至<input id="chipEnd" type="date" value="${esc(pack.end || "")}" /></label>
        <label>目标日<input id="chipTarget" type="date" value="${esc(pack.target || "")}" /></label>
        <label>排序<select id="chipOrder">
          <option value="desc"${pack.order !== "asc" ? " selected" : ""}>从大到小</option>
          <option value="asc"${pack.order === "asc" ? " selected" : ""}>从小到大</option>
        </select></label>
        <button type="button" id="chipRecalc" class="btn primary">计算</button>
      </div>
      <div class="engine-kpis">
        <div class="engine-kpi"><span>样本交易日</span><strong>${esc(String(pack.N ?? "—"))}</strong></div>
        <div class="engine-kpi"><span>目标日</span><strong>${esc(pack.target || "—")}</strong></div>
        <div class="engine-kpi"><span>复权</span><strong>${esc((pack.adjust || "qfq").toUpperCase())}</strong></div>
      </div>
      <section class="engine-section"><h3>价格位置（百分位越高越接近区间上沿）</h3>
        <div class="rot-scroll"><table class="rot-table">
          <thead><tr><th>类型</th><th class="num">目标价</th><th class="num">排名/样本</th><th>百分位</th><th class="num">值</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
      </section>
      ${sub}
      <p class="muted sentiment-source-note">${esc(pack.note || "")}</p>
    `;
  }

  const CMP_STATE = {};
  const CMP_COLORS = { "股涨指跌": "#c81e3a", "同涨": "#ff8a96", "股跌指涨": "#0f9d63", "同跌": "#7fe0b2" };

  function drawCmpCharts(pack) {
    const css = (name, fallback) => {
      const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return v || fallback;
    };
    const C_LINE = css("--line", "#2a3648"), C_MUT = css("--muted", "#8494a8");
    const dirColor = (d) => CMP_COLORS[d] || C_MUT;
    ["open", "high", "low", "close"].forEach((k) => {
      const cv = document.getElementById(`cmpChart-${k}`);
      if (!cv) return;
      const rows = (pack.daily?.[k] || []).filter((r) => Number.isFinite(Number(r.dif)));
      const st = CMP_STATE[k] || (CMP_STATE[k] = {});
      st.rows = rows;
      if (!rows.length) {
        const ctx0 = cv.getContext("2d");
        ctx0.clearRect(0, 0, cv.width, cv.height);
        ctx0.fillStyle = C_MUT;
        ctx0.font = "12px sans-serif";
        ctx0.fillText("暂无数据", 10, 20);
        return;
      }
      if (!Number.isFinite(st.a) || !Number.isFinite(st.b) || st.n !== rows.length || st.sym !== pack.symbol) {
        st.n = rows.length;
        st.sym = pack.symbol;
        st.b = rows.length;
        st.a = Math.max(0, rows.length - 120);
      }
      st.a = Math.max(0, Math.min(st.a, rows.length - 1));
      st.b = Math.max(st.a + 5, Math.min(st.b, rows.length));
      paintCmpChart(cv, k, st, { C_LINE, C_MUT, dirColor });
      bindCmpChart(cv, k, st, { C_LINE, C_MUT, dirColor });
    });
  }

  function paintCmpChart(cv, k, st, theme) {
    const { C_LINE, C_MUT, dirColor } = theme;
    const rows = st.rows;
    const dpr = window.devicePixelRatio || 1;
    const W = Math.max(200, cv.clientWidth || cv.parentElement.clientWidth || 400);
    const H = 200;
    cv.width = Math.round(W * dpr);
    cv.height = Math.round(H * dpr);
    cv.style.width = "100%";
    cv.style.height = `${H}px`;
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const padL = 46, padR = 10, padT = 14, padB = 20;
    const view = rows.slice(st.a, st.b);
    const vals = view.map((r) => Number(r.dif) * 100);
    let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    if (hi - lo < 1e-9) { hi += 0.05; lo -= 0.05; }
    const plotW = W - padL - padR;
    const bw = Math.max(1.5, plotW / Math.max(1, view.length) - 0.8);
    const X = (i) => padL + ((i + 0.5) / Math.max(1, view.length)) * plotW - bw / 2;
    const Y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
    st.geom = { W, H, padL, padR, padT, padB, bw, X, Y };
    ctx.strokeStyle = C_LINE;
    ctx.lineWidth = 1;
    ctx.beginPath();
    [hi, 0, lo].forEach((v) => { ctx.moveTo(padL, Y(v)); ctx.lineTo(W - padR, Y(v)); });
    ctx.stroke();
    ctx.fillStyle = C_MUT;
    ctx.font = "10px sans-serif";
    ctx.fillText(`${hi.toFixed(2)}%`, 2, Y(hi) + 3);
    ctx.fillText("0", 2, Y(0) + 3);
    ctx.fillText(`${lo.toFixed(2)}%`, 2, Y(lo) + 3);
    ctx.fillText(view[0].date?.slice(5) || "", padL, H - 6);
    ctx.fillText(view[view.length - 1].date?.slice(5) || "", W - padR - 36, H - 6);
    if (st.b < rows.length || st.a > 0) {
      ctx.fillText(`显示 ${st.a + 1}–${st.b} / 共${rows.length}天 · 滚轮缩放 · 拖拽平移`, padL + 4, 11);
    } else {
      ctx.fillText(`共${rows.length}天 · 滚轮缩放 · 拖拽平移`, padL + 4, 11);
    }
    const y0 = Y(0);
    view.forEach((r, i) => {
      const v = Number(r.dif) * 100;
      const y = Y(v);
      ctx.fillStyle = r === st.hover ? "#ffffff" : dirColor(r.dir);
      ctx.globalAlpha = r === st.hover ? 1 : 0.88;
      ctx.fillRect(X(i), Math.min(y, y0), bw, Math.max(1, Math.abs(y - y0)));
    });
    ctx.globalAlpha = 1;
    const counts = { "同涨": 0, "同跌": 0, "股涨指跌": 0, "股跌指涨": 0 };
    rows.forEach((r) => { counts[r.dir] = (counts[r.dir] || 0) + 1; });
    const cap = cv.parentElement?.querySelector("figcaption");
    if (cap && !cap.dataset.base) cap.dataset.base = cap.textContent;
    if (cap) {
      cap.innerHTML = `${esc(cap.dataset.base)} <span class="cmp-legend">` +
        Object.entries(CMP_COLORS).map(([d, c]) =>
          `<span class="cmp-dot" style="background:${c}"></span>${d}${counts[d] || 0}`).join(" ") + "</span>";
    }
    paintCmpTip(cv, st);
  }

  function paintCmpTip(cv, st) {
    let tip = cv.parentElement?.querySelector(".cmp-tip");
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "cmp-tip hidden";
      cv.parentElement?.appendChild(tip);
    }
    const r = st.hover;
    if (!r || !st.geom) { tip.classList.add("hidden"); return; }
    const idx = st.rows.indexOf(r);
    const vi = idx - st.a;
    const x = st.geom.X(Math.max(0, vi)) + 8;
    tip.innerHTML = `<b>${esc(r.date || "")}</b> <span style="color:${CMP_COLORS[r.dir] || "#fff"}">${esc(r.dir || "")}</span><br>` +
      `个股 ${(Number(r.rs) * 100).toFixed(2)}% · 指数 ${(Number(r.rb) * 100).toFixed(2)}%<br>` +
      `偏离 <b>${(Number(r.dif) * 100).toFixed(2)}%</b>`;
    tip.classList.remove("hidden");
    tip.style.left = `${Math.min(x, st.geom.W - 150)}px`;
    tip.style.top = "26px";
  }

  function bindCmpChart(cv, k, st, theme) {
    if (cv.dataset.cmpBound === "1") return;
    cv.dataset.cmpBound = "1";
    const repaint = () => paintCmpChart(cv, k, st, theme);
    const posIdx = (ev) => {
      const rect = cv.getBoundingClientRect();
      const x = ev.clientX - rect.left;
      const g = st.geom;
      if (!g) return -1;
      const n = st.b - st.a;
      const i = Math.floor((x - g.padL) / ((g.W - g.padL - g.padR) / Math.max(1, n)));
      return (i >= 0 && i < n) ? st.a + i : -1;
    };
    cv.addEventListener("wheel", (ev) => {
      ev.preventDefault();
      const n = st.rows.length;
      const c = posIdx(ev);
      const center = c >= 0 ? c : Math.round((st.a + st.b) / 2);
      const span = Math.max(5, st.b - st.a);
      const next = ev.deltaY > 0 ? Math.min(n, Math.round(span * 1.25)) : Math.max(5, Math.round(span * 0.8));
      const ratio = (center - st.a) / span;
      st.a = Math.max(0, Math.min(n - next, Math.round(center - next * ratio)));
      st.b = st.a + next;
      st.hover = null;
      repaint();
    }, { passive: false });
    let dragX = null, dragA = 0, dragB = 0, moved = false;
    cv.addEventListener("mousedown", (ev) => {
      dragX = ev.clientX; dragA = st.a; dragB = st.b; moved = false;
    });
    window.addEventListener("mousemove", (ev) => {
      if (dragX == null || !cv.isConnected) return;
      if (ev.buttons !== 1) { dragX = null; return; }
      const rect = cv.getBoundingClientRect();
      if (ev.clientX < rect.left - 40 || ev.clientX > rect.right + 40) return;
      const n = st.rows.length;
      const span = dragB - dragA;
      const dx = Math.round((ev.clientX - dragX) / rect.width * span);
      if (Math.abs(ev.clientX - dragX) > 3) moved = true;
      const na = Math.max(0, Math.min(n - span, dragA - dx));
      st.a = na; st.b = na + span;
      st.hover = null;
      repaint();
    });
    window.addEventListener("mouseup", () => { dragX = null; });
    cv.addEventListener("mousemove", (ev) => {
      if (dragX != null && moved) return;
      const i = posIdx(ev);
      const r = i >= 0 ? st.rows[i] : null;
      if (r !== st.hover) { st.hover = r; repaint(); }
    });
    cv.addEventListener("mouseleave", () => {
      st.hover = null;
      if (st.geom) repaint();
    });
  }
  function engineHtml(pack, mode = state.mode) {
    if (mode === "compare" || (pack?.scores && pack?.total && pack?.daily)) return cmpHtml(pack);
    if (mode === "chip" || pack?.method === "same_type") return chipHtml(pack);
    const flags = Array.isArray(pack?.flags) ? pack.flags : [];
    const tables = pack?.tables || {};
    const isZhang = mode === "bazhang-rules" || !!pack?.strategy_type;

    let kpis;
    let typeLabel;
    let typeValue;
    let typeReason;
    let order;

    if (isZhang && mode !== "buffett-rules") {
      const profit = pack?.metrics?.profit || {};
      const cash = pack?.metrics?.cash || {};
      const comp = pack?.metrics?.competitiveness || {};
      const strategy = pack?.metrics?.strategy || {};
      typeLabel = "战略类型";
      typeValue = pack.strategy_type || strategy.strategy_type || "未知";
      typeReason = pack.strategy_reason || "";
      kpis = [
        ["战略类型", typeValue, "text"],
        ["核心利润", fmtEngineNum(profit.core_profit), "yi"],
        ["核心利润率", fmtEngineNum(profit.core_margin, "pct"), "pct"],
        ["毛利率", fmtEngineNum(profit.gross_margin, "pct"), "pct"],
        ["OCF/核心利润", fmtEngineNum(cash.ocf_core_ratio, "pct"), "pct"],
        ["销售收现比", fmtEngineNum(cash.cash_collection_ratio, "pct"), "pct"],
        ["两头吃指数", fmtEngineNum(comp.two_ends_index, "x"), "x"],
        ["ROE", fmtEngineNum(profit.roe, "pct"), "pct"],
      ];
      order = [
        ["diagnosis", "综合诊断"],
        ["asset_structure", "资产结构"],
        ["liability_structure", "负债结构"],
        ["core_profit", "核心利润"],
        ["annual_core", "年报核心利润"],
        ["cash_quality", "利润含金量"],
        ["competitiveness", "竞争力"],
        ["cost_structure", "成本结构"],
        ["value", "价值创造"],
        ["annual_value", "年报价值创造"],
        ["recent_all", "近几期定期报告"],
      ];
    } else {
      const latest = pack?.metrics?.latest || {};
      typeLabel = "生意类型";
      typeValue = pack.business_type || "未知";
      typeReason = pack.business_reason || "";
      kpis = [
        ["生意类型", typeValue, "text"],
        ["(a) 归母净利", fmtEngineNum(latest.a), "yi"],
        ["(b) 折旧摊销", latest.da_disclosed ? fmtEngineNum(latest.b) : "未披露", "yi"],
        ["资本开支", fmtEngineNum(latest.capex), "yi"],
        ["所有者盈余上沿", fmtEngineNum(latest.oe_upper), "yi"],
        ["所有者盈余下沿", latest.da_disclosed ? fmtEngineNum(latest.oe_lower) : "未披露", "yi"],
        ["有形 ROE", fmtEngineNum(latest.tangible_roe || latest.roe, "pct"), "pct"],
        ["capex/D&A", latest.da_disclosed ? fmtEngineNum(latest.capex_da, "x") : "未披露", "x"],
      ];
      order = [
        ["diagnosis", "综合诊断"],
        ["owner_earnings", "所有者盈余（最新口径）"],
        ["annual_owner", "年报所有者盈余"],
        ["recent_all", "近几期定期报告"],
        ["capital", "资本与回报"],
        ["allocation", "资本配置"],
      ];
    }

    const kpiHtml = kpis.map(([label, value]) => (
      `<div class="engine-kpi"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`
    )).join("");
    const flagsHtml = flags.length
      ? `<div class="engine-flags"><h3>风险警示</h3><ul>${flags.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></div>`
      : "";
    const tableHtml = order.map(([key, title]) => {
      const body = tables[key];
      if (!body) return "";
      return `<section class="engine-section"><h3>${esc(title)}</h3>${renderMarkdown(body)}</section>`;
    }).join("");
    const errorHtml = (pack.errors || []).length
      ? `<p class="muted">数据缺口：${esc((pack.errors || []).join("；"))}</p>`
      : "";
    return `
      <div class="engine-hero">
        <p class="engine-type">${esc(typeLabel)}：<strong>${esc(typeValue)}</strong></p>
        <p class="muted">${esc([pack.latest_period, pack.period_kind, pack.ytd ? "累计口径" : ""].filter(Boolean).join(" · ") || "最新定期报告")}</p>
        ${pack.coverage ? `<p class="muted">${esc(pack.coverage)}</p>` : ""}
        ${typeReason ? `<p class="muted">${esc(typeReason)}</p>` : ""}
      </div>
      <div class="engine-kpis">${kpiHtml}</div>
      ${flagsHtml}
      ${tableHtml}
      ${errorHtml}
    `;
  }

  function renderEnginePack(pack) {
    const cfg = getConfig();
    const ms = getModeState();
    if (!pack) return;
    setBoardMode("result");
    setLive("live");
    setRunningStatus(false);
    showError("");
    if ($("jobMeta")) $("jobMeta").textContent = "";
    if ($("reportTitle")) $("reportTitle").textContent = cfg.resultTitle?.(pack) || cfg.reportTitle;
    if ($("reportMeta")) $("reportMeta").textContent = cfg.resultMeta?.(pack) || "";
    if ($("reportView")) $("reportView").innerHTML = engineHtml(pack, state.mode);
    if (state.mode === "compare") {
      requestAnimationFrame(() => {
        try { drawCmpCharts(pack); } catch { /* ignore */ }
      });
    }
    ms.enginePack = pack;
    ms.ready = true;
    focusReportPane();
  }

  async function loadEngine(mode = state.mode, { force = false, extra = null } = {}) {
    const cfg = getConfig(mode);
    const ms = getModeState(mode);
    applyChrome(mode);
    if (!force && ms.enginePack && state.mode === mode) {
      renderEnginePack(ms.enginePack);
      return;
    }
    const company = companyQuery();
    if (!company) {
      paintIdle();
      showError("缺少公司代码");
      return;
    }
    showError("");
    setLive("busy");
    setBoardMode("result");
    if (mode === state.mode) $("startBtn")?.classList.add("hidden");
    showReportLoading("正在强制刷新东财最新全量定期报告并计算…", `${cfg.label}计算中`);
    if ($("reportTitle")) $("reportTitle").textContent = cfg.runningTitle?.(company) || cfg.reportTitle;
    try {
      const qs = new URLSearchParams({ company, ...(extra || {}) });
      const { data } = await api(`${cfg.apiRoot}?${qs}`, { timeoutMs: 90000 });
      if (state.mode !== mode) return;
      renderEnginePack(data);
    } catch (err) {
      if (state.mode !== mode) return;
      ms.ready = false;
      setLive("idle");
      setBoardMode("idle");
      setRunningStatus(false);
      showEmptyState();
      showError(err.message || cfg.resumeFail);
    }
  }

  async function loadReports() {
    const cfg = getConfig();
    const ms = getModeState();
    if (cfg.kind === "engine") {
      ms.reports = [];
      paintReportList(cfg, ms);
      return ms.reports;
    }
    const { data } = await api(reportsListUrl(cfg));
    ms.reports = (data || []).filter((r) => cfg.reportNameRe.test(r.filename) && reportMatches(r.filename));
    paintReportList(cfg, ms);
    return ms.reports;
  }

  function paintReportList(cfg = getConfig(), ms = getModeState()) {
    const list = $("reportList");
    if (!list) return;
    if (!ms.reports.length) {
      list.innerHTML = `<li class='muted' style='padding:10px'>${esc(cfg.emptyReports)}</li>`;
      return;
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
  }

  async function paintModeCache(mode) {
    const cfg = getConfig(mode);
    const ms = getModeState(mode);
    applyChrome(mode);
    await loadReports().catch(() => {});
    if (state.mode !== mode) return;

    if (ms.job && (ms.job.status === "running" || ms.polling || ms.job.status === "failed")) {
      renderJob(ms.job);
      return;
    }
    if (ms.job?.status === "completed") {
      renderJob(ms.job);
      if (!resultText(ms.job.result)) await revealCompleted(ms.job);
      return;
    }
    if (ms.activeReportFile) {
      try {
        const { data } = await api(reportReadUrl(cfg, ms.activeReportFile));
        if (state.mode !== mode) return;
        setBoardMode("result");
        if ($("reportTitle")) $("reportTitle").textContent = data.filename.replace(/\.md$/i, "");
        if ($("reportMeta")) $("reportMeta").textContent = cfg.historyMeta;
        if ($("reportView")) {
          $("reportView").innerHTML = renderMarkdown(data.content || "");
          ms.renderedReportKey = `${ms.activeReportFile}|${(data.content || "").length}`;
        }
        highlightActiveReport();
        showError("");
        setLive("live");
      } catch (err) {
        if (state.mode === mode) {
          showError(err.message);
          paintIdle();
        }
      }
      return;
    }
    paintIdle();
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
      showReportLoading("请点左侧历史报告打开", "报告已生成");
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
    if (isEngineMode()) {
      const extra = state.mode === "chip" ? chipFormParams()
        : state.mode === "compare" ? cmpFormParams() : undefined;
      await loadEngine(state.mode, { force: true, extra });
      return;
    }
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
      const qs = new URLSearchParams(
        typeof cfg.startQuery === "function" ? cfg.startQuery(company) : { company },
      );
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
    if (cfg.kind === "engine") {
      applyChrome(mode);
      if (!force) await waitForIdentity();
      if (state.mode !== mode && !force) return;
      await loadEngine(mode, { force });
      return;
    }
    const ms = getModeState(mode);
    const token = ++ms.seq;
    const stillCurrent = () => token === ms.seq && (force || state.mode === mode);

    applyChrome(mode);

    if (!force && ms.ready) {
      if (state.mode === mode) {
        await paintModeCache(mode);
      }
      return;
    }

    if (ms.job?.status === "running" && ms.polling && !force) {
      if (state.mode === mode) {
        await paintModeCache(mode);
      }
      ms.ready = true;
      return;
    }

    if (!force && ms.job?.status === "completed") {
      if (state.mode === mode) {
        renderJob(ms.job);
        if (!resultText(ms.job.result)) await revealCompleted(ms.job);
        await loadReports().catch(() => {});
      }
      ms.ready = true;
      return;
    }

    if (state.mode === mode && !force) {
      const view = $("reportView");
      const empty = !view?.textContent?.trim() || view.querySelector(".ai-empty-state");
      if (empty) showReportLoading("正在读取已有报告…", "正在加载");
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
        if (state.mode === mode) {
          showError(err.message);
          showReportLoading("请点左侧历史报告打开", "报告已生成");
          ms.ready = true;
          return;
        }
      }
    }

    if (state.mode === mode) {
      paintIdle();
      if ($("reportMeta")) $("reportMeta").textContent = "暂无该公司报告，点击生成确认";
    }
    ms.ready = true;
  }

  async function onPanel(mode) {
    const aliases = window.AI_MODE_ALIASES || {};
    mode = aliases[mode] || mode;
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
    let cmpResizeTimer = null;
    window.addEventListener("resize", () => {
      if (state.mode !== "compare") return;
      const pack = getModeState("compare").enginePack;
      if (!pack) return;
      clearTimeout(cmpResizeTimer);
      cmpResizeTimer = setTimeout(() => {
        try { drawCmpCharts(pack); } catch { /* ignore */ }
      }, 200);
    });
    document.getElementById("panel-judgment")?.addEventListener("click", (ev) => {
      if (!ev.target.closest?.("#chipRecalc")) return;
      ev.preventDefault();
      loadEngine("chip", { force: true, extra: chipFormParams() }).catch((err) => showError(err.message || String(err)));
    });
    document.getElementById("panel-judgment")?.addEventListener("click", (ev) => {
      if (!ev.target.closest?.("#cmpRecalc")) return;
      ev.preventDefault();
      loadEngine("compare", { force: true, extra: cmpFormParams() }).catch((err) => showError(err.message || String(err)));
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
