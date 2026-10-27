(() => {
  const MODES = window.AI_MODES || {};
  const MODE_ORDER = window.AI_MODE_ORDER || ["business", "zhang-views", "peers", "risk", "sentiment"];
  const BUSINESS_FAMILY_VIEWS = new Set(["business", "bizprofile"]);
  const EARNINGS_VIEWS = new Set(["zhang-views"]);

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
    mode: "bizprofile",
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
    if (BUSINESS_FAMILY_VIEWS.has(mode)) return "business";
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
    if (!panel || panel.hidden) return false;
    // 研判 · K线分析 / 成交分析占用同一 panel，AI 壳不应抢源栏 / family
    const family = panel.dataset.judgmentFamily || "";
    if (family === "kline" || family === "deal") return false;
    const lc = $("lineComparePage");
    if (lc && !lc.hidden) return false;
    const deal = $("dealAnalysisPage");
    if (deal && !deal.hidden) return false;
    return true;
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
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    html = html.replace(/〔来源：(.+?)〕/g, '<cite class="ai-source" title="$1">〔来源：$1〕</cite>');
    html = html.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");
    html = html.replace(/^[ \t]*- (.+)$/gm, "<li>$1</li>");
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
    const stockCode = job.stock?.code || job.result?.stock_code || "";
    const stock = stockCode ? ` · ${stockCode}` : "";
    const industry = job.result?.industry_name ? ` · ${job.result.industry_name}` : "";
    const m = job.result?.metrics || {};
    const sentiment = Number.isFinite(Number(m.n_retail_users))
      ? ` · 散户 ${m.n_retail_users} · 买${m.buy_users ?? 0}/卖${m.sell_users ?? 0}/观望${m.wait_users ?? 0}`
      : "";
    return `${label} · ${job.company}${stock}${industry}${sentiment}`;
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
    if ($("reportParams")) {
      $("reportParams").innerHTML = "";
      $("reportParams").classList.remove("is-active");
    }
  }

  function applyChrome(mode = state.mode) {
    const cfg = getConfig(mode);
    const { code, name } = identityKeys();
    const label = [name, code].filter(Boolean).join(" · ") || "当前公司";
    if ($("analysisCompanyLabel")) $("analysisCompanyLabel").textContent = label;
    if ($("startBtn")) $("startBtn").textContent = cfg.startBtn;
    if ($("reportParams") && mode !== "zhang-views" && mode !== "peers") {
      $("reportParams").innerHTML = "";
      $("reportParams").classList.remove("is-active");
    }
    if ($("historyHead")) $("historyHead").textContent = cfg.historyHead;
    const agentCount = cfg.agentDefs?.length || 0;
    if ($("pipelineProgress")) $("pipelineProgress").textContent = `0 / ${agentCount}`;
    const family = judgmentFamily(mode);
    const visible = analysisVisible();
    const panel = $("panel-judgment");
    // K线分析可见时不要回写 judgmentFamily / 源栏，否则会盖掉「K线分析」高亮
    if (visible) {
      if (panel) {
        panel.dataset.judgmentView = mode;
        panel.dataset.judgmentFamily = family;
      }
      document.querySelectorAll("#judgmentSourceBar [data-source]").forEach((tab) => {
        const active = tab.getAttribute("data-source") === family;
        tab.classList.toggle("is-active", active);
        tab.setAttribute("aria-selected", active ? "true" : "false");
      });
    }
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
      : "";
    const reportKey = `${filename}|${text.length}|${metricsKey}`;
    if (filename) ms.activeReportFile = filename;
    if ($("reportTitle")) $("reportTitle").textContent = cfg.resultTitle?.(result) || String(filename).replace(/\.md$/i, "");
    if ($("reportMeta")) $("reportMeta").textContent = cfg.resultMeta?.(result) || "已保存";
    if (ms.renderedReportKey !== reportKey && $("reportView")) {
      const metrics = cfg.id === "sentiment" ? sentimentMetricsHtml(result) : "";
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

  const ZHANG_REPORT_TYPES = [
    ["annual", "年报"],
    ["semi", "半年报"],
    ["q1", "一季报"],
    ["q3", "三季报"],
  ];

  function zhangViewsFormParams() {
    const pick = (id) => String(document.getElementById(id)?.value || "").trim();
    const extra = {};
    const reportType = pick("zvReportType");
    if (reportType) extra.report_type = reportType;
    return extra;
  }

  function zhangRiskBody(view) {
    const m = (view && view.metrics) || {};
    const items = Array.isArray(m.items) ? m.items : [];
    const cardsHtml = items.length
      ? `<div class="zv-risk-grid">${items.map((it) => {
          const cls = it.triggered ? "is-hit" : "is-ok";
          const tag = it.triggered ? "触发" : "正常";
          return `<div class="zv-risk-card ${cls}">`
            + `<div class="zv-risk-card-head"><span class="zv-risk-dot"></span><strong>${esc(it.name)}</strong><span class="zv-risk-tag">${tag}</span></div>`
            + `<div class="zv-risk-value">${esc(it.value || "—")}</div>`
            + `<div class="zv-risk-threshold">阈值：${esc(it.threshold || "—")}</div>`
            + `</div>`;
        }).join("")}</div>`
      : "";
    const fs = Array.isArray(view.formulas) ? view.formulas : [];
    const formulaHtml = fs.length
      ? `<h4>判定规则</h4><ul class="zv-formula">${fs.map((f) => {
          const notes = [];
          if (f.meaning) notes.push(`<li><span class="zv-formula-tag">含义</span>${esc(f.meaning)}</li>`);
          if (f.reading) notes.push(`<li><span class="zv-formula-tag">怎么看</span>${esc(f.reading)}</li>`);
          const noteHtml = notes.length ? `<ul class="zv-formula-note">${notes.join("")}</ul>` : "";
          return `<li><strong>${esc(f.name)}</strong>：${esc(f.formula)}${noteHtml}</li>`;
        }).join("")}</ul>`
      : "";
    return `${cardsHtml}${formulaHtml}`;
  }

  function zhangSummaryBody(view) {
    const dims = Array.isArray(view.dimensions) ? view.dimensions : [];
    const weights = Array.isArray(view.score_weights) ? view.score_weights : [];
    const score = view.score_total;
    let scoreHtml = "";
    if (Number.isFinite(Number(score))) {
      const s = Math.max(0, Math.min(100, Math.round(Number(score))));
      const cls = s >= 80 ? "is-good" : (s >= 60 ? "is-mid" : "is-bad");
      scoreHtml = `<div class="zv-sum-score ${cls}"><span class="zv-sum-score-num">${s}</span><span class="zv-sum-score-label">综合评分 / 100</span></div>`;
    }
    const cardsHtml = dims.length
      ? `<div class="zv-sum-list">${dims.map(([aspect, evaluation, evidence], i) => {
          let cls = "is-neutral";
          if (evaluation === "优") cls = "is-good";
          else if (evaluation === "中") cls = "is-mid";
          else if (evaluation === "差") cls = "is-bad";
          const w = Number(weights[i]) > 0 ? ` · ${weights[i]}%` : "";
          const headTitle = `${esc(aspect || "")}<span class="zv-sum-weight">${esc(w)}</span>`;
          let evidenceHtml = "";
          if (evidence) {
            if (String(aspect || "").includes("七看") || String(aspect || "").includes("八看")) {
              const items = String(evidence).split("；").map((s) => s.trim()).filter(Boolean);
              evidenceHtml = `<ul class="zv-sum-risk">${items.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>`;
            } else {
              evidenceHtml = `<div class="zv-sum-evidence">${esc(evidence)}</div>`;
            }
          }
          return `<div class="zv-sum-card ${cls}">`
            + `<div class="zv-sum-head"><strong>${headTitle}</strong><span class="zv-sum-badge">${esc(evaluation || "—")}</span></div>`
            + evidenceHtml
            + `</div>`;
        }).join("")}</div>`
      : "";
    const fs = Array.isArray(view.formulas) ? view.formulas : [];
    const formulaHtml = fs.length
      ? `<h4>判定口径</h4><ul class="zv-formula">${fs.map((f) => {
          const notes = [];
          if (f.meaning) notes.push(`<li><span class="zv-formula-tag">含义</span>${esc(f.meaning)}</li>`);
          if (f.reading) notes.push(`<li><span class="zv-formula-tag">怎么看</span>${esc(f.reading)}</li>`);
          const noteHtml = notes.length ? `<ul class="zv-formula-note">${notes.join("")}</ul>` : "";
          return `<li><strong>${esc(f.name)}</strong>：${esc(f.formula)}${noteHtml}</li>`;
        }).join("")}</ul>`
      : "";
    return `${scoreHtml}${cardsHtml}${formulaHtml}`;
  }

  function zhangViewBody(view) {
    if (view && view.layout === "risk") return zhangRiskBody(view);
    if (view && view.key === "summary") return zhangSummaryBody(view);
    if (view && (view.raw != null || view.results != null || view.formulas)) {
      const rawText = (view.raw || "").trim();
      const rawHtml = rawText ? renderMarkdown(view.raw) : "";
      const rawSection = rawText ? `${"<h4>原始数据</h4>"}${rawHtml}` : "";
      const fs = Array.isArray(view.formulas) ? view.formulas : [];
      const formulaHtml = fs.length
        ? `<ul class="zv-formula">${fs.map((f) => {
            const notes = [];
            if (f.meaning) notes.push(`<li><span class="zv-formula-tag">含义</span>${esc(f.meaning)}</li>`);
            if (f.reading) notes.push(`<li><span class="zv-formula-tag">怎么看</span>${esc(f.reading)}</li>`);
            const noteHtml = notes.length ? `<ul class="zv-formula-note">${notes.join("")}</ul>` : "";
            return `<li><strong>${esc(f.name)}</strong>：${esc(f.formula)}${noteHtml}</li>`;
          }).join("")}</ul>`
        : "<p class='muted'>（本节无二次加工公式）</p>";
      const tableHtml = view.results ? renderMarkdown(view.results) : "";
      const resultsSection = tableHtml ? `${"<h4>计算结果</h4>"}${tableHtml}` : "";
      const formulaSection = `${"<h4>计算公式</h4>"}${formulaHtml}`;
      const conc = (Array.isArray(view.conclusions) ? view.conclusions : []).filter(Boolean);
      const concHtml = conc.length
        ? `${"<h4>结论</h4>"}<ul class="zv-conc">${conc.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`
        : "";
      return `${resultsSection}`
        + `${formulaSection}`
        + `${rawSection}`
        + concHtml;
    }
    if (view && view.text) return renderMarkdown(view.text);
    const conc = (Array.isArray(view?.conclusions) ? view.conclusions : []).filter(Boolean);
    const concHtml = conc.length ? `<ul class="zv-conc">${conc.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : "";
    const tableHtml = view?.table ? renderMarkdown(view.table) : "";
    return `${concHtml}${tableHtml}`;
  }

  const PEERS_REPORT_TYPES = [
    ["annual", "年报"],
    ["semi", "半年报"],
    ["q1", "一季报"],
    ["q3", "三季报"],
  ];

  function peersFormParams() {
    const pick = (id) => String(document.getElementById(id)?.value || "").trim();
    const extra = {};
    const reportType = pick("peersReportType");
    if (reportType) extra.report_type = reportType;
    return extra;
  }

  function peersParamsHtml(pack) {
    const rt = (pack && pack.report_type) || "annual";
    const options = PEERS_REPORT_TYPES
      .map(([value, label]) => `<option value="${value}"${value === rt ? " selected" : ""}>${label}</option>`)
      .join("");
    return `<label class="ai-report-param-label">报告口径<select id="peersReportType" class="chart-select">${options}</select></label>`;
  }

  function peersFmt(value, unit) {
    if (value == null || value === "" || !Number.isFinite(Number(value))) return "—";
    const n = Number(value);
    if (unit === "pct") return `${n.toFixed(1)}%`;
    if (unit === "x") return `${n.toFixed(2)}×`;
    if (unit === "day") return `${n.toFixed(0)}天`;
    if (unit === "yi") {
      const sign = n < 0 ? "-" : "";
      const abs = Math.abs(n);
      return `${sign}${abs.toFixed(2)}亿`;
    }
    if (unit === "num") return Number.isInteger(n) ? String(n) : n.toFixed(2);
    return String(value);
  }

  function peersTone(rank) {
    if (!rank || rank.percentile == null) return "";
    const pct = Number(rank.percentile);
    if (!Number.isFinite(pct)) return "";
    if (pct >= 70) return "is-good";
    if (pct <= 30) return "is-bad";
    return "is-mid";
  }

  function peersDirHint(direction) {
    if (direction === "higher") return "越高越好";
    if (direction === "lower") return "越低越好";
    return "中性观察";
  }

  function peersTargetRankInfo(ind, rows, universeUsed) {
    const target = rows.find((r) => r.is_target);
    if (!target) return null;
    const has = target.all_values && Object.prototype.hasOwnProperty.call(target.all_values, ind.key);
    const raw = has ? target.all_values[ind.key] : (target.values || {})[ind.key];
    const value = Number(raw);
    if (!Number.isFinite(value)) return null;
    const backend = (target.ranks || {})[ind.key];
    if (backend && backend.rank) {
      return {
        value,
        rank: Number(backend.rank),
        total: universeUsed || 0,
        percentile: backend.percentile == null ? null : Number(backend.percentile),
      };
    }
    const peers = [];
    rows.forEach((r) => {
      const h = r.all_values && Object.prototype.hasOwnProperty.call(r.all_values, ind.key);
      const rv = h ? r.all_values[ind.key] : (r.values || {})[ind.key];
      const n = Number(rv);
      if (Number.isFinite(n)) peers.push(n);
    });
    if (peers.length < 2) return { value, rank: null, total: peers.length, percentile: null };
    const better = ind.direction === "higher";
    let worse = 0;
    peers.forEach((o) => { if (better ? o < value : o > value) worse += 1; });
    return { value, rank: peers.length - worse, total: peers.length, percentile: (worse / (peers.length - 1)) * 100 };
  }

  function peersTargetRankList(view, pack) {
    const indicators = (Array.isArray(view.all_indicators) && view.all_indicators.length)
      ? view.all_indicators
      : (Array.isArray(view.indicators) ? view.indicators : []);
    const rows = Array.isArray(view.rows) ? view.rows : [];
    if (!indicators.length || !rows.length) return "";
    const rankable = indicators.filter((ind) => ind.unit !== "text" && ind.direction !== "neutral");
    const items = rankable.map((ind) => {
      const better = ind.direction === "higher";
      const vals = [];
      rows.forEach((r) => {
        const has = r.all_values && Object.prototype.hasOwnProperty.call(r.all_values, ind.key);
        const raw = has ? r.all_values[ind.key] : (r.values || {})[ind.key];
        if (raw === null || raw === undefined || raw === "") return;
        const num = Number(raw);
        if (!Number.isFinite(num)) return;
        vals.push({ num, name: r.name || r.code || "", isTarget: !!r.is_target });
      });
      if (!vals.length) return "";
      const n = vals.length;
      const nums = vals.map((v) => v.num);
      const mn = Math.min(...nums);
      const mx = Math.max(...nums);
      const span = mx - mn;
      const scored = vals.map((v) => {
        let worse = 0;
        vals.forEach((o) => { if (better ? o.num < v.num : o.num > v.num) worse += 1; });
        const pos = span === 0 ? 50 : (better ? (v.num - mn) / span : (mx - v.num) / span) * 100;
        return { ...v, pct: span === 0 ? 50 : (n > 1 ? (worse / (n - 1)) * 100 : 50), pos };
      });
      const tgt = scored.find((p) => p.isTarget);
      const tone = tgt ? (tgt.pct >= 70 ? "is-good" : tgt.pct <= 30 ? "is-bad" : "is-mid") : "";
      const valText = tgt ? peersFmt(tgt.num, ind.unit) : "—";
      // 按显示值分组：相同数值归为一组，共享同一名次
      const groupMap = new Map();
      scored.forEach((p) => {
        const pv = peersFmt(p.num, ind.unit);
        const g = groupMap.get(pv);
        if (g) {
          g.items.push({ name: p.name, num: p.num, target: p.isTarget });
          if (p.isTarget) g.hasTarget = true;
          // 代表值取组内最优的一家，保证名次/位置落在极值端
          const repBetter = better ? p.num > g.num : p.num < g.num;
          if (repBetter) { g.num = p.num; g.pos = p.pos; }
        } else {
          groupMap.set(pv, { pv, num: p.num, pos: p.pos, items: [{ name: p.name, num: p.num, target: p.isTarget }], hasTarget: p.isTarget });
        }
      });
      // 按数值从优到劣为每组排名：名次 = 1 + 前方各组人数之和（同组同名次）
      const ordered = [...groupMap.values()].sort((a, b) => (better ? b.num - a.num : a.num - b.num));
      let cum = 0;
      ordered.forEach((g) => { g.rank = cum + 1; cum += g.items.length; });
      const tgtGroup = tgt ? ordered.find((g) => g.hasTarget) : null;
      const dots = [...groupMap.values()]
        .sort((a, b) => a.pos - b.pos)
        .map((g) => {
          g.items.sort((a, b) => (b.target ? 1 : 0) - (a.target ? 1 : 0));
          g.items.forEach((it) => { it.rank = g.rank; });
          const rows = JSON.stringify(g.items);
          const aria = g.items.map((it) => `${it.name} 第 ${it.rank}/${n} 名`).join("；");
          return `<span class="peers-tr-dot${g.hasTarget ? " is-target" : ""}" style="left:${Math.max(0, Math.min(100, g.pos)).toFixed(1)}%" aria-label="${esc(ind.label)} ${esc(aria)}" data-tip-label="${esc(ind.label)}" data-tip-value="${esc(g.pv)}" data-tip-total="${n}" data-tip-rows="${esc(rows)}"></span>`;
        })
        .join("");
      const rankHtml = tgtGroup
        ? `<b>第 ${tgtGroup.rank}</b><em>/ 共 ${n} 家</em>`
        : `<b class="peers-tr-rank-none">本司无数据</b>`;
      return `<li class="peers-tr ${tone}">
        <span class="peers-tr-name">${esc(ind.label)}<i>${esc(peersDirHint(ind.direction))}</i></span>
        <span class="peers-tr-axis">${dots}</span>
        <span class="peers-tr-val">${esc(valText)}</span>
        <span class="peers-tr-rank">${rankHtml}</span>
      </li>`;
    }).filter(Boolean).join("");
    if (!items) return "";
    return `<div class="peers-tr-wrap">
      <div class="peers-tr-head"><span>可对比指标</span><span>行业相对位置</span><span>本司值</span><span>名次</span></div>
      <ol class="peers-tr-list">${items}</ol>
    </div>`;
  }

  function peersMatrixHtml(view, total) {
    const indicators = (Array.isArray(view.all_indicators) && view.all_indicators.length)
      ? view.all_indicators
      : (Array.isArray(view.indicators) ? view.indicators : []);
    const rows = Array.isArray(view.rows) ? view.rows : [];
    if (!indicators.length || !rows.length) return "";
    const scoreRank = (r) => {
      const info = (r.ranks || {}).score_total;
      return info && info.rank ? info.rank : 999;
    };
    const ordered = rows.slice().sort((a, b) => (Number(b.is_target) - Number(a.is_target)) || (scoreRank(a) - scoreRank(b)));
    const head = `<tr><th class="peers-ind-col">指标</th>${ordered.map((r) => `<th class="peers-co-col${r.is_target ? " is-target" : ""}">${r.is_target ? "★ " : ""}${esc(r.name || r.code)}</th>`).join("")}</tr>`;
    const body = indicators.map((ind) => {
      const isText = ind.unit === "text";
      const cells = ordered.map((r) => {
        const has = r.all_values && Object.prototype.hasOwnProperty.call(r.all_values, ind.key);
        const raw = has ? r.all_values[ind.key] : (r.values || {})[ind.key];
        const v = isText ? (raw == null || raw === "" ? "—" : String(raw)) : peersFmt(raw, ind.unit);
        const rank = (r.ranks || {})[ind.key];
        const tone = isText || ind.direction === "neutral" ? "" : peersTone(rank);
        const rankHtml = isText || ind.direction === "neutral" || !rank || !rank.rank
          ? ""
          : `<span class="peers-rank">${esc(String(rank.rank))}<i>/${esc(String(total))}</i></span>`;
        const cls = isText ? "peers-co-text" : "num";
        return `<td class="${cls}${tone ? " " + tone : ""}${r.is_target ? " is-target" : ""}">${esc(v)}${rankHtml}</td>`;
      }).join("");
      return `<tr><th class="peers-ind-col">${esc(ind.label)}</th>${cells}</tr>`;
    }).join("");
    return `<div class="peers-matrix">
      <div class="peers-matrix-title">同行明细矩阵（${ordered.length} 家 · ${indicators.length} 项结果）</div>
      <div class="peers-table-wrap"><table class="rot-table peers-table"><thead>${head}</thead><tbody>${body}</tbody></table></div>
    </div>`;
  }

  function peersViewSection(view, pack) {
    const total = pack.universe?.used || 0;
    const target = pack.target || {};
    const viewIndicators = Array.isArray(view.indicators) ? view.indicators : [];
    const allIndicators = Array.isArray(view.all_indicators) ? view.all_indicators : [];
    const indicators = viewIndicators.length ? viewIndicators : allIndicators;
    const byInd = target.by_indicator || {};
    const noLabel = view.key === "summary" ? "∑" : String(view.no || "");

    if (!indicators.length) {
      return `<details class="peers-view-card" id="peers-view-${esc(view.key)}" open>
        <summary class="peers-view-head">
          <span class="peers-view-no">${esc(noLabel)}</span>
          <span class="peers-view-name">${esc(view.name || "")}</span>
        </summary>
        <div class="peers-view-body"><p class="peers-dist-empty">本看暂无可用数值</p></div>
      </details>`;
    }

    let good = 0, bad = 0;
    indicators.forEach((ind) => {
      const info = byInd[ind.key];
      if (!info || ind.direction === "neutral") return;
      const pct = Number(info.percentile);
      if (!Number.isFinite(pct)) return;
      if (pct >= 70) good += 1;
      else if (pct <= 30) bad += 1;
    });

    const rankHtml = peersTargetRankList(view, pack);

    return `<details class="peers-view-card" id="peers-view-${esc(view.key)}" open>
      <summary class="peers-view-head">
        <span class="peers-view-no">${esc(noLabel)}</span>
        <span class="peers-view-name">${esc(view.name || "")}</span>
        <span class="peers-view-stats"><i class="is-good">${good}</i> 项优势<i class="peers-dot-sep">·</i><i class="is-bad">${bad}</i> 项短板</span>
      </summary>
      <div class="peers-view-body">
        ${rankHtml}
        ${peersMatrixHtml(view, total)}
      </div>
    </details>`;
  }

  function peersHeroHtml(pack) {
    const ind = pack.industry || {};
    const universe = pack.universe || {};
    const chips = [
      pack.report_type_label ? `<span class="peers-hero-chip">${esc(pack.report_type_label)}</span>` : "",
      pack.latest_period ? `<span class="peers-hero-chip">基准期 ${esc(pack.latest_period)}</span>` : "",
      `<span class="peers-hero-chip is-accent">可比 ${esc(String(universe.used ?? "—"))} 家</span>`,
      `<span class="peers-hero-chip">行业 ${esc(String(universe.total ?? "—"))} 家</span>`,
    ].filter(Boolean).join("");
    const path = [ind.l1_name, ind.l2_name, ind.l3_code].filter(Boolean).map((s) => esc(s)).join(" · ");
    return `<header class="peers-hero">
      <div class="peers-hero-copy">
        <p class="peers-eyebrow">申万三级行业 · 同口径横截面</p>
        <h3 class="peers-hero-title">${esc(ind.l3_name || ind.l3_code || "—")}</h3>
        ${path ? `<p class="peers-hero-path">${path}</p>` : ""}
      </div>
      <div class="peers-hero-chips">${chips}</div>
    </header>`;
  }

  function peersSignalCard(list, kind) {
    const isGood = kind === "good";
    const items = Array.isArray(list) ? list.slice(0, 8) : [];
    const body = items.length
      ? `<ul class="peers-signal-list ${isGood ? "is-good" : "is-bad"}">${items.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>`
      : `<p class="peers-signal-empty">${isGood ? "暂无明显优势项" : "暂无明显短板项"}</p>`;
    return `<article class="peers-signal ${isGood ? "is-good" : "is-bad"}">
      <header class="peers-signal-head">
        <span class="peers-signal-dot"></span>
        <strong>${isGood ? "相对优势" : "相对短板"}</strong>
        <span class="peers-signal-count">${Array.isArray(list) ? list.length : 0} 项</span>
      </header>
      ${body}
    </article>`;
  }

  function peersRankLevel(tone) {
    if (tone === "is-good") return "行业领先";
    if (tone === "is-bad") return "相对落后";
    return "处于中游";
  }

  function peersRankFocusHtml(pack) {
    const t = pack.target || {};
    const n = Number(t.of) || Number(pack.universe?.used) || 0;
    const rank = Number(t.score_rank);
    if (!t.code || !Number.isFinite(rank) || n < 2) return "";
    const frac = (rank - 1) / (n - 1);
    const tone = frac <= 0.3 ? "is-good" : frac >= 0.7 ? "is-bad" : "is-mid";
    const leftPos = Math.max(0, Math.min(100, frac * 100));
    const scoreNum = Number(t.score_total);
    const scoreText = Number.isFinite(scoreNum) ? `综合分 ${Math.round(scoreNum)}` : "综合分 —";
    return `<section class="peers-rank-panel">
      <div class="peers-rank-main">
        <p class="peers-rank-eyebrow">申万三级行业排名</p>
        <div class="peers-rank-figure">
          <span class="peers-rank-num">${esc(String(rank))}</span>
          <span class="peers-rank-of">名 / 共 <b>${esc(String(n))}</b> 家</span>
        </div>
        <div class="peers-rank-tags">
          <span class="peers-rank-level ${tone}">${esc(peersRankLevel(tone))}</span>
          <span class="peers-rank-score">${esc(scoreText)}</span>
        </div>
      </div>
      <div class="peers-rank-ladder" role="img" aria-label="本司在申万三级行业中的排名位置：第 ${esc(String(rank))} 名，共 ${esc(String(n))} 家">
        <div class="peers-rank-ladder-track">
          <span class="peers-rank-ladder-marker ${tone}" style="left:${leftPos.toFixed(1)}%"></span>
        </div>
        <div class="peers-rank-ladder-scale">
          <span>第 1 名</span>
          <span class="peers-rank-ladder-self">本司 · 第 ${esc(String(rank))} 名</span>
          <span>第 ${esc(String(n))} 名</span>
        </div>
      </div>
    </section>`;
  }

  function peersScorecardHtml(pack) {
    const t = pack.target || {};
    if (!t.code && !t.name) return "";
    const rankFocus = peersRankFocusHtml(pack);
    if (!rankFocus) return "";
    return `<div class="peers-dashboard">${rankFocus}</div>`;
  }

  function peersRankCardHtml(pack) {
    const t = pack.target || {};
    const n = Number(t.of) || Number(pack.universe?.used) || 0;
    const rank = Number(t.score_rank);
    if (!t.code || !Number.isFinite(rank) || n < 2) return "";
    const frac = (rank - 1) / (n - 1);
    const tone = frac <= 0.3 ? "is-good" : frac >= 0.7 ? "is-bad" : "is-mid";
    const leftPos = Math.max(0, Math.min(100, ((n - rank) / (n - 1)) * 100));
    const scoreNum = Number(t.score_total);
    const scoreText = Number.isFinite(scoreNum) ? `综合分 ${Math.round(scoreNum)}` : "综合分 —";
    return `<article class="peers-signal is-rank">
      <header class="peers-signal-head">
        <span class="peers-signal-dot"></span>
        <strong>综合排名</strong>
        <span class="peers-signal-count">共 ${n} 家</span>
      </header>
      <div class="peers-rank-card-body">
        <div class="peers-rank-card-figure">
          <span class="peers-rank-num">${esc(String(rank))}</span>
          <span class="peers-rank-of">名 / 共 <b>${esc(String(n))}</b> 家</span>
        </div>
        <div class="peers-rank-tags">
          <span class="peers-rank-level ${tone}">${esc(peersRankLevel(tone))}</span>
          <span class="peers-rank-score">${esc(scoreText)}</span>
        </div>
        <div class="peers-rank-ladder" role="img" aria-label="本司在申万三级行业中的排名位置：第 ${esc(String(rank))} 名，共 ${esc(String(n))} 家">
          <div class="peers-rank-ladder-track">
            <span class="peers-rank-ladder-marker ${tone}" style="left:${leftPos.toFixed(1)}%"></span>
          </div>
          <div class="peers-rank-ladder-scale">
            <span>第 ${esc(String(n))} 名</span>
            <span class="peers-rank-ladder-self">本司 · 第 ${esc(String(rank))} 名</span>
            <span>第 1 名</span>
          </div>
        </div>
      </div>
    </article>`;
  }

  function peersSignalsHtml(pack) {
    const t = pack.target || {};
    if (!t.code && !t.name) return "";
    const rankCard = peersRankCardHtml(pack);
    const cards = `${peersSignalCard(t.strengths, "good")}${peersSignalCard(t.weaknesses, "bad")}`;
    if (!rankCard && !cards) return "";
    return `<div class="peers-dashboard"><div class="peers-signal-grid${rankCard ? " has-rank" : ""}">${rankCard}${cards}</div></div>`;
  }

  function peersLeaderboardHtml(pack) {
    const companies = (Array.isArray(pack.companies) ? pack.companies : [])
      .filter((c) => c && (Number.isFinite(Number(c.score_total)) || Number.isFinite(Number(c.score_rank))));
    if (companies.length < 2) return "";
    const ordered = companies.slice().sort((a, b) => {
      const ra = Number.isFinite(Number(a.score_rank)) ? Number(a.score_rank) : 1e6;
      const rb = Number.isFinite(Number(b.score_rank)) ? Number(b.score_rank) : 1e6;
      if (ra !== rb) return ra - rb;
      return (Number(b.score_total) || 0) - (Number(a.score_total) || 0);
    });
    const rowOf = (c, idx) => {
      const scoreNum = Number(c.score_total);
      const hasScore = Number.isFinite(scoreNum);
      const score = hasScore ? Math.round(scoreNum) : null;
      const rank = Number.isFinite(Number(c.score_rank)) ? Number(c.score_rank) : idx + 1;
      const hits = c.metrics?.risk_hits;
      const medal = rank === 1 ? " is-gold" : rank === 2 ? " is-silver" : rank === 3 ? " is-bronze" : "";
      return `<tr class="peers-lb-row${c.is_target ? " is-target" : ""}">
        <td class="peers-lb-rank${medal}"><span class="peers-lb-rank-num">${rank}</span></td>
        <td class="peers-lb-name"><span class="peers-lb-name-text">${esc(c.name || c.code)}</span>${c.is_target ? '<span class="peers-lb-tag">本司</span>' : ""}</td>
        <td class="num peers-lb-scorecell">${hasScore ? score : "—"}</td>
        <td class="peers-lb-strategy-cell">${c.strategy_type ? esc(c.strategy_type) : "—"}</td>
        <td class="num peers-lb-riskcell">${Number.isFinite(Number(hits)) ? esc(String(hits)) : "—"}</td>
      </tr>`;
    };
    const head = `<thead><tr><th>#</th><th>可比公司</th><th class="num">综合分</th><th>战略类型</th><th class="num">风险命中</th></tr></thead>`;
    const industryName = (pack.industry || {}).l3_name || "申万三级行业";
    return `<section class="peers-board">
      <header class="peers-board-head">
        <h4 class="peers-board-title">${esc(industryName)} · 综合排名</h4>
        <span class="peers-board-hint">按「八看」综合分排序 · 共 ${ordered.length} 家</span>
      </header>
      <div class="peers-lb-wrap"><table class="peers-lb-table">${head}<tbody>${ordered.map((c, i) => rowOf(c, i)).join("")}</tbody></table></div>
    </section>`;
  }

  function peersNotesHtml(pack) {
    const flags = Array.isArray(pack.flags) ? pack.flags : [];
    const excluded = pack.universe?.excluded || [];
    const parts = [];
    if (flags.length) {
      parts.push(`<div class="peers-note is-warn"><strong>口径提示</strong><ul>${flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul></div>`);
    }
    if (excluded.length) {
      parts.push(`<details class="peers-note is-muted"><summary>已剔除 ${excluded.length} 家样本</summary><p>${excluded.slice(0, 60).map((e) => `${esc(e.name)}(${esc(e.code)})：${esc(e.reason)}`).join("；")}</p></details>`);
    }
    return parts.join("");
  }

  function peersNavHtml(pack) {
    const views = (Array.isArray(pack.by_view) ? pack.by_view : []).filter((v) => v.key !== "summary");
    if (!views.length) return "";
    return `<nav class="peers-nav" aria-label="八看导航">${views.map((v) => {
      const shortName = String(v.name || "").replace(/^.*?：/, "");
      return `<button type="button" data-peers-jump="${esc(v.key)}">${esc(String(v.no || ""))}看 · ${esc(shortName)}</button>`;
    }).join("")}</nav>`;
  }

  // ---- 业务简述 · 规则视角（bizprofile）：确定性规则结果，原生卡片 / 表格渲染 ----

  function bizYi(value) {
    if (value == null || value === "" || !Number.isFinite(Number(value))) return "—";
    const n = Number(value);
    const sign = n < 0 ? "-" : "";
    return `${sign}${(Math.abs(n) / 1e8).toFixed(2)}亿`;
  }

  function bizPct(value, digits = 2) {
    if (value == null || value === "" || !Number.isFinite(Number(value))) return "—";
    return `${(Number(value) * 100).toFixed(digits)}%`;
  }

  function bizPp(value) {
    if (value == null || value === "" || !Number.isFinite(Number(value))) return "—";
    return `${Number(value) >= 0 ? "+" : ""}${Number(value).toFixed(2)}pp`;
  }

  function bizHhi(value) {
    if (value == null || value === "" || !Number.isFinite(Number(value))) return "—";
    // HHI 常用 0~1 或 0~10000 两种口径；此处源数据为 0~1，统一放大到 0~10000
    return (Number(value) * 10000).toFixed(0);
  }

  function bizStatusLabel(status) {
    if (status === "匹配") return "延续";
    if (status === "本期新出现") return "新出现";
    if (status === "本期无") return "本期无";
    return status || "—";
  }

  function bizAmountParts(value) {
    if (value == null || value === "" || !Number.isFinite(Number(value))) return { num: "—", unit: "" };
    const n = Number(value) / 1e8;
    return { num: `${n < 0 ? "-" : ""}${Math.abs(n).toFixed(2)}`, unit: "亿" };
  }

  function bizRatioCell(value) {
    const n = Number(value);
    if (value == null || value === "" || !Number.isFinite(n)) return `<span class="biz-ratio-num">—</span>`;
    const width = Math.max(0, Math.min(100, n * 100));
    return `<span class="biz-ratio"><span class="biz-ratio-bar"><i class="biz-ratio-fill" style="width:${width.toFixed(2)}%"></i></span><span class="biz-ratio-num">${bizPct(n)}</span></span>`;
  }

  function bizIntroHtml(pack) {
    const intro = pack.intro || {};
    const rows = [
      ["主营业务", intro.main_business, true],
      ["产品类型", intro.product_type, false],
      ["主要产品", intro.product_name || (intro.product_name_list || []).join("、"), false],
      ["经营范围", intro.scope, false],
    ].filter((r) => String(r[1] || "").trim());
    if (!rows.length) return "";
    return `
      <section class="biz-card biz-intro">
        <header class="biz-card-head"><h3>主营业务速览</h3></header>
        <dl class="biz-intro-list">
          ${rows.map(([k, v, strong]) => `<div class="biz-intro-row${strong ? " is-strong" : ""}"><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}
        </dl>
      </section>`;
  }

  function bizOverviewHtml(pack) {
    const dims = Array.isArray(pack.dimensions) ? pack.dimensions : [];
    if (!dims.length) return "";
    const cards = dims.map((d) => {
      const c = d.concentration || {};
      const total = bizAmountParts(d.total_revenue);
      const isPrimary = d.key === pack.primary;
      return `
        <article class="biz-sum-card${isPrimary ? " is-active" : ""}" data-biz-card="${esc(d.key || "")}" role="button" tabindex="0" aria-pressed="${isPrimary ? "true" : "false"}">
          <header>
            <span class="biz-sum-name">${esc(d.label || d.key || "")}</span>
            <span class="biz-sum-date">${esc(d.report_date || "—")}</span>
          </header>
          <p class="biz-sum-total"><b>${esc(total.num)}</b><span>${esc(total.unit)}</span><em>主营合计</em></p>
          <dl class="biz-sum-metrics">
            <div><dt>一级分部</dt><dd>${d.count ?? "—"}</dd></div>
            <div><dt>占比合计</dt><dd>${bizPct(d.total_ratio)}</dd></div>
            <div><dt>整体毛利率</dt><dd>${bizPct(d.overall_margin)}</dd></div>
            <div><dt>CR3</dt><dd>${bizPct(c.cr3)}</dd></div>
            <div><dt>HHI</dt><dd>${bizHhi(c.hhi)}</dd></div>
          </dl>
        </article>`;
    }).join("");
    return `
      <section class="biz-card biz-overview">
        <header class="biz-card-head">
          <h3>主营构成总览</h3>
        </header>
        <div class="biz-sum-grid">${cards}</div>
      </section>`;
  }

  function bizFormulaHtml() {
    return `
      <details class="biz-card biz-formula">
        <summary>
          <h3>计算公式</h3>
          <span class="biz-formula-chevron" aria-hidden="true">▾</span>
        </summary>
        <div class="biz-formula-body">
          <article class="biz-formula-card">
            <h4>整体毛利率</h4>
            <code>Σ各分部毛利 ÷ Σ各分部收入</code>
            <p><span class="biz-tag">含义</span>主营业务每 100 元收入扣掉直接成本后剩下的毛利，衡量整体盈利能力；不采用接口的 gross_profit_rate 字段（口径不符）。</p>
            <p><span class="biz-tag">怎么看</span>毛利好坏要与同行比：连续多期下滑多为成本上升或价格战；整体被某个负毛利分部拖低时，可看「盈利结构」定位到具体分部。</p>
          </article>
          <article class="biz-formula-card">
            <h4>CR3（收入前三集中度）</h4>
            <code>r₁ + r₂ + r₃（r 为各一级分部收入占比，按降序取前 3）</code>
            <p><span class="biz-tag">含义</span>收入最大的三个业务合计占主营收入的比例，衡量公司是「靠几个主业吃饭」还是业务分散。</p>
            <p><span class="biz-tag">怎么看</span>CR3 越高越依赖少数业务：80% 以上属高度集中，业绩弹性大但抗风险能力弱；50% 以下相对分散。需与 HHI 一起看，不能单看 CR3。</p>
          </article>
          <article class="biz-formula-card">
            <h4>HHI（赫芬达尔指数）</h4>
            <code>10000 × Σrᵢ²（rᵢ 为各一级分部收入占比）</code>
            <p><span class="biz-tag">含义</span>把各分部占比平方求和并放大到 0~10000：10000 表示只有一项业务，越接近 0 越分散；与 CR3 只看前三不同，它把头部以外的分部也纳入。</p>
            <p><span class="biz-tag">怎么看</span>常用经验区间：低于 1500 为低集中，1500~2500 为中等集中，高于 2500 为高集中。CR3 相近时，HHI 更高说明中间规模的分部也不小。</p>
          </article>
        </div>
      </details>`;
  }

  function bizSegmentsHtml(dim) {
    const segs = Array.isArray(dim.segments) ? dim.segments : [];
    if (!segs.length) return "";
    const rows = segs.map((s) => {
      const gm = s.gross_margin;
      const isNeg = Number.isFinite(Number(gm)) && Number(gm) < 0;
      return `
        <tr>
          <td class="biz-cell-name">${esc(s.item_name || "")}</td>
          <td class="num">${bizYi(s.revenue)}</td>
          <td class="num">${bizRatioCell(s.revenue_ratio)}</td>
          <td class="num">${bizYoyCell(s.revenue_yoy)}</td>
          <td class="num"><span class="biz-margin${isNeg ? " is-neg" : ""}">${bizPct(gm)}</span></td>
          <td class="num">${bizPct(s.gross_profit_ratio)}</td>
        </tr>`;
    }).join("");
    return `
      <div class="biz-table-card">
        <header class="biz-table-head"><h4>分部构成</h4></header>
        <div class="biz-table-wrap">
          <table class="biz-table">
            <thead><tr><th>分部</th><th class="num">营业收入</th><th class="num">收入占比</th><th class="num">收入同比</th><th class="num">毛利率</th><th class="num">毛利占比</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
  }

  function bizYoyCell(value) {
    const n = Number(value);
    if (value == null || value === "" || !Number.isFinite(n)) return "—";
    const dir = n > 0 ? " is-up" : n < 0 ? " is-down" : "";
    return `<span class="biz-yoy${dir}">${bizPct(n)}</span>`;
  }

  function bizMigrationHtml(dim) {
    const rows = Array.isArray(dim.migration) ? dim.migration : [];
    if (!rows.length) return "";
    const body = rows.map((r) => {
      const status = r.status || "";
      const cls = status === "本期新出现" ? "is-new" : status === "本期无" ? "is-gone" : "";
      const delta = Number.isFinite(Number(r.delta_pp)) ? bizPp(r.delta_pp) : "—";
      const deltaDir = Number(r.delta_pp) > 0 ? "is-up" : Number(r.delta_pp) < 0 ? "is-down" : "";
      return `
        <tr>
          <td class="biz-cell-name">${esc(r.item_name || "")}</td>
          <td class="num">${bizPct(r.prev_ratio)}</td>
          <td class="num">${bizRatioCell(r.cur_ratio)}</td>
          <td class="num"><span class="biz-delta ${deltaDir}">${delta}</span></td>
          <td class="num">${bizYoyCell(r.revenue_yoy)}</td>
          <td class="num"><span class="biz-status ${cls}">${esc(bizStatusLabel(status))}</span></td>
        </tr>`;
    }).join("");
    return `
      <div class="biz-table-card">
        <header class="biz-table-head"><h4>收入结构迁移</h4></header>
        <div class="biz-table-wrap">
          <table class="biz-table">
            <thead><tr><th>分部</th><th class="num">上期占比</th><th class="num">本期占比</th><th class="num">占比变动</th><th class="num">收入同比</th><th class="num">匹配</th></tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      </div>`;
  }

  function bizDimensionPanelHtml(dim, active) {
    if (!dim) return "";
    return `
      <section class="biz-panel" id="biz-panel-${esc(dim.key || "")}" data-biz-panel="${esc(dim.key || "")}" role="tabpanel" aria-labelledby="biz-tab-${esc(dim.key || "")}"${active ? "" : " hidden"}>
        <header class="biz-panel-head">
          <h3>${esc(dim.label || dim.key || "")}</h3>
          <span class="biz-period">报告期 ${esc(dim.report_date || "—")}</span>
        </header>
        ${bizSegmentsHtml(dim)}
        ${bizMigrationHtml(dim)}
      </section>`;
  }

  function bizDimensionHtml(pack) {
    const dims = Array.isArray(pack.dimensions) ? pack.dimensions : [];
    if (!dims.length) return "";
    const primaryKey = (dims.find((d) => d.key === pack.primary) || dims[0]).key;
    const tabs = dims.map((d) => {
      const active = d.key === primaryKey;
      return `<button type="button" class="biz-tab${active ? " is-active" : ""}" role="tab" id="biz-tab-${esc(d.key || "")}" aria-controls="biz-panel-${esc(d.key || "")}" data-biz-tab="${esc(d.key || "")}" aria-selected="${active ? "true" : "false"}">${esc(d.label || d.key || "")}<em>${esc(d.report_date || "")}</em></button>`;
    }).join("");
    const panels = dims.map((d) => bizDimensionPanelHtml(d, d.key === primaryKey)).join("");
    return `
      <section class="biz-card biz-dim">
        <nav class="biz-tabs" role="tablist" aria-label="主营构成维度">${tabs}</nav>
        <div class="biz-panels">${panels}</div>
      </section>`;
  }

  function bizProfileHtml(pack) {
    if (!pack || !Array.isArray(pack.dimensions) || !pack.dimensions.length) {
      return `<div class="engine-hero"><p class="engine-type">业务简述 · 规则视角</p><p class="muted">${esc(pack?.error || "未取到主营构成数据")}</p></div>`;
    }
    return `
      <div class="biz-profile">
        ${bizIntroHtml(pack)}
        ${bizOverviewHtml(pack)}
        ${bizDimensionHtml(pack)}
        ${bizFormulaHtml()}
      </div>`;
  }

  function activateBizTab(host, key) {
    if (!host || !key) return;
    host.querySelectorAll(".biz-tab").forEach((btn) => {
      const on = btn.getAttribute("data-biz-tab") === key;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    host.querySelectorAll("[data-biz-panel]").forEach((panel) => {
      panel.hidden = panel.getAttribute("data-biz-panel") !== key;
    });
    host.querySelectorAll("[data-biz-card]").forEach((card) => {
      const on = card.getAttribute("data-biz-card") === key;
      card.classList.toggle("is-active", on);
      card.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function peersHtml(pack) {
    if (!pack || !Array.isArray(pack.by_view) || !pack.by_view.length) {
      return `<div class="engine-hero"><p class="engine-type">竞争分析</p><p class="muted">${esc(pack?.text || "未取到可比样本")}</p></div>`;
    }
    const sections = pack.by_view.filter((v) => v.key !== "summary").map((v) => peersViewSection(v, pack)).join("");
    return `${peersSignalsHtml(pack)}${peersNotesHtml(pack)}${peersLeaderboardHtml(pack)}${peersNavHtml(pack)}${sections}`;
  }

  function riskSplitClauses(text) {
    return String(text || "")
      .split(/[；;。]/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function riskProseHtml(text) {
    const parts = riskSplitClauses(text);
    if (!parts.length) return `<p class="muted">—</p>`;
    if (parts.length === 1) return `<p>${esc(parts[0])}</p>`;
    return `<ul class="risk-prose-list">${parts.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`;
  }

  function riskNavHtml(dimensions, summary) {
    if (!dimensions.length) return "";
    const links = dimensions.map((d) => {
      const n = Number(d.count) || 0;
      return `<button type="button" class="risk-nav-link${n ? "" : " is-empty"}" data-risk-dim="${esc(d.key)}">${esc(String(d.no))}. ${esc(d.name)} <i>${esc(String(n))}</i></button>`;
    }).join("");
    const s = summary || {};
    const stat = [];
    if (s.hit_dimensions !== undefined && s.dimension_count !== undefined) {
      stat.push(`有命中 ${esc(String(s.hit_dimensions))}/${esc(String(s.dimension_count))}`);
    }
    if (s.total_items !== undefined) stat.push(`去重后 ${esc(String(s.total_items))}`);
    const statHtml = stat.length ? `<span class="risk-nav-stat">${stat.join(" · ")}</span>` : "";
    return `<nav class="risk-nav" aria-label="七维导航">${links}${statHtml}</nav>`;
  }

  function riskItemRow(item, index) {
    const title = item.title || "（无标题）";
    const titleHtml = item.url
      ? `<a class="risk-ev-title" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(title)}</a>`
      : `<span class="risk-ev-title">${esc(title)}</span>`;
    const metaParts = [item.published_at || "", item.category_cn || ""].filter(Boolean);
    const hitTerms = Array.isArray(item.matched_terms) ? item.matched_terms : [];
    if (hitTerms.length) {
      metaParts.push(`命中 ${hitTerms.join("、")}`);
    }
    const meta = metaParts.join(" · ");
    return `<li class="risk-ev">
      <span class="risk-ev-idx">${esc(String(index))}</span>
      <div class="risk-ev-main">
        ${titleHtml}
        <p class="risk-ev-meta muted">${esc(meta)}</p>
      </div>
    </li>`;
  }

  function riskResultGroupHtml(group) {
    const count = Number(group.count) || 0;
    const items = Array.isArray(group.items) ? group.items : [];
    const listHtml = items.length
      ? `<ol class="risk-ev-list">${items.map((it, i) => riskItemRow(it, i + 1)).join("")}</ol>`
      : `<p class="muted">本组无命中</p>`;
    return `<article class="risk-result-group${count ? "" : " is-empty"}">
      <header class="risk-result-group-head">
        <code class="risk-sm-sym">${esc(group.symbol || "")}</code>
        <span class="risk-result-group-name">${esc(group.label || group.qid || "")}</span>
        <span class="risk-result-group-count">${esc(String(count))} 条</span>
      </header>
      <div class="risk-result-group-body">${listHtml}</div>
    </article>`;
  }

  function riskCellList(values, emptyLabel = "任意") {
    if (!Array.isArray(values) || !values.length) return emptyLabel;
    return values.join("、");
  }

  function riskSearchMethodHtml(sm, queries) {
    // 新 schema：表格 + 直白说明；旧版可能是字符串
    if (!sm || typeof sm === "string") {
      return `${riskProseHtml(sm || "")}${riskLegacyQueryTable(queries)}`;
    }
    const clauses = Array.isArray(sm.clauses) ? sm.clauses : [];
    const hitByQid = {};
    (queries || []).forEach((q) => { hitByQid[q.qid] = q; });

    const rows = clauses.map((c) => {
      const q = hitByQid[c.qid] || {};
      const status = q.ok === false ? "失败" : (q.ok ? "成功" : "—");
      const tone = q.ok === false ? "is-high" : (Number(q.raw_count) > 0 ? "is-mid" : "");
      return `<tr class="${tone}">
        <td class="risk-sm-sym">${esc(c.symbol || "")}</td>
        <td>${esc(c.label || c.qid || "")}</td>
        <td>${esc(c.tab_label || c.tab || "全文")}</td>
        <td>${esc(riskCellList(c.category))}</td>
        <td class="risk-sm-kw">${esc(riskCellList(c.keyword_terms))}</td>
        <td class="num">近 ${esc(String(c.days ?? "—"))} 天</td>
        <td class="num">${esc(String(q.raw_count ?? "—"))}</td>
        <td>${esc(status)}</td>
      </tr>`;
    }).join("");

    return `<div class="risk-sm">
      <div class="peers-table-wrap risk-stats-wrap risk-sm-table-wrap">
        <table class="rot-table peers-table risk-stats-table risk-sm-table">
          <thead><tr>
            <th>编号</th><th>子查询</th><th>通道</th><th>分类</th><th>标题关键词</th><th>时间窗口</th><th>命中</th><th>状态</th>
          </tr></thead>
          <tbody>${rows || `<tr><td colspan="8" class="muted">无子查询</td></tr>`}</tbody>
        </table>
      </div>
    </div>`;
  }

  function riskLegacyQueryTable(queries) {
    if (!Array.isArray(queries) || !queries.length) return "";
    const rows = queries.map((q) => {
      const status = q.ok === false ? "FAIL" : "OK";
      const tone = q.ok === false ? "is-high" : (Number(q.raw_count) > 0 ? "is-mid" : "");
      return `<tr class="${tone}">
        <td>${esc(q.title || q.qid || "")}</td>
        <td>${esc(q.method || "")}</td>
        <td class="num">${esc(String(q.raw_count ?? 0))}</td>
        <td>${esc(status)}</td>
      </tr>`;
    }).join("");
    return `<div class="peers-table-wrap risk-stats-wrap">
      <table class="rot-table peers-table risk-stats-table">
        <thead><tr><th>查询</th><th>方式</th><th>原始命中</th><th>状态</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  }

  function riskDimensionCard(dim) {
    const count = Number(dim.count) || 0;
    const groups = Array.isArray(dim.groups) ? dim.groups : [];
    // 兼容旧包：无 groups 时退回扁平 items
    let resultsHtml;
    if (groups.length) {
      const cols = Math.min(Math.max(groups.length, 1), 4);
      resultsHtml = `<div class="risk-result-groups" style="--risk-cols:${cols}">${groups.map((g) => riskResultGroupHtml(g)).join("")}</div>`;
    } else {
      const items = Array.isArray(dim.items) ? dim.items : [];
      resultsHtml = items.length
        ? `<ol class="risk-ev-list">${items.map((it, i) => riskItemRow(it, i + 1)).join("")}</ol>`
        : `<p class="muted">本维窗口内无命中</p>`;
    }
    const open = count > 0 ? " open" : "";
    return `<details class="risk-dim-card" id="risk-dim-${esc(dim.key)}"${open}>
      <summary class="risk-dim-head">
        <span class="risk-dim-no">${esc(String(dim.no ?? ""))}</span>
        <span class="risk-dim-name">${esc(dim.name || "")}</span>
        <span class="risk-dim-count">${esc(String(count))} 条</span>
      </summary>
      <div class="risk-dim-body">
        <section class="risk-dim-block">
          <h4><span class="risk-block-tag">1</span>检索方式</h4>
          ${riskSearchMethodHtml(dim.search_method, dim.queries)}
        </section>
        <section class="risk-dim-block">
          <h4><span class="risk-block-tag">2</span>检索结果 <span class="risk-section-count">${esc(String(count))}</span></h4>
          ${resultsHtml}
        </section>
      </div>
    </details>`;
  }

  function riskHtml(pack) {
    if (!pack || !Array.isArray(pack.dimensions)) {
      return `<div class="engine-hero"><p class="engine-type">风险评估</p><p class="muted">未取到七维结果</p></div>`;
    }
    const cards = pack.dimensions.map((d) => riskDimensionCard(d)).join("");
    return `${riskNavHtml(pack.dimensions, pack.summary)}<div class="risk-dim-list">${cards}</div>`;
  }

  function zhangParamsHtml(pack) {
    const rt = (pack && pack.report_type) || "annual";
    const options = ZHANG_REPORT_TYPES
      .map(([value, label]) => `<option value="${value}"${value === rt ? " selected" : ""}>${label}</option>`)
      .join("");
    return ``
      + `<label class="ai-report-param-label">报告口径<select id="zvReportType" class="chart-select">${options}</select></label>`;
  }

  function paintReportParams(pack) {
    const slot = $("reportParams");
    if (!slot) return;
    if (state.mode === "zhang-views" && pack) {
      slot.innerHTML = zhangParamsHtml(pack);
      slot.classList.add("is-active");
    } else if (state.mode === "peers" && pack) {
      slot.innerHTML = peersParamsHtml(pack);
      slot.classList.add("is-active");
    } else {
      slot.innerHTML = "";
      slot.classList.remove("is-active");
    }
  }

  function zhangViewsHtml(pack) {
    if (!pack.data_available) {
      return `
        <div class="engine-hero">
          <p class="engine-type">张新民「八看」</p>
          <p class="muted">${esc(pack.text || "未获取到所选口径的定期报告")}</p>
        </div>`;
    }
    const views = (Array.isArray(pack.views) ? pack.views : []).map((view) => (
      `<section class="engine-section"><h3>${esc(view.name || "")}</h3><div class="zv-body">${zhangViewBody(view)}</div></section>`
    )).join("");
    const summary = pack.summary;
    let summaryHtml = "";
    if (summary) {
      summaryHtml = `<section class="engine-section"><h3>${esc(summary.name || "综合诊断")}</h3><div class="zv-body">${zhangViewBody(summary)}</div></section>`;
    }
    return `
      ${summaryHtml}
      ${views}
    `;
  }

  function engineHtml(pack, mode = state.mode) {
    if (mode === "risk" || pack?.module === "riskassessment") return riskHtml(pack);
    if (mode === "bizprofile" || Array.isArray(pack?.dimensions)) return bizProfileHtml(pack);
    if (mode === "zhang-views" || (Array.isArray(pack?.views) && pack?.summary)) return zhangViewsHtml(pack);
    if (mode === "peers" || Array.isArray(pack?.by_view)) return peersHtml(pack);
    const flags = Array.isArray(pack?.flags) ? pack.flags : [];
    const tables = pack?.tables || {};
    const isZhang = !!pack?.strategy_type;

    let kpis;
    let typeLabel;
    let typeValue;
    let typeReason;
    let order;

    if (isZhang) {
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
    paintReportParams(pack);
    if (state.mode === "peers") {
      requestAnimationFrame(() => {
        const wrap = document.querySelector("#panel-judgment .peers-lb-wrap");
        const row = wrap?.querySelector("tr.is-target");
        if (wrap && row && wrap.scrollHeight > wrap.clientHeight) {
          wrap.scrollTop = Math.max(0, row.offsetTop - wrap.clientHeight / 2 + row.offsetHeight / 2);
        }
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
    const loadingMsg = mode === "bizprofile"
      ? "正在取回主营构成三维度（按产品/按行业/按地区）…"
      : mode === "peers"
      ? "正在圈定申万三级行业，并拉取同行定期报告逐项计算八看…"
      : mode === "risk"
      ? "正在按七维从巨潮检索非定期公告…"
      : "正在强制刷新东财最新全量定期报告并计算…";
    showReportLoading(loadingMsg, `${cfg.label}计算中`);
    if ($("reportTitle")) $("reportTitle").textContent = cfg.runningTitle?.(company) || cfg.reportTitle;
    try {
      const qs = new URLSearchParams({ company, ...(extra || {}) });
      const timeoutMs = mode === "peers" || mode === "risk" ? 180000 : mode === "bizprofile" ? 60000 : 90000;
      const { data } = await api(`${cfg.apiRoot}?${qs}`, { timeoutMs });
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
    list.innerHTML = ms.reports.map((row) => {
      return `<li>
        <button type="button" class="ai-history-item" data-file="${esc(row.filename)}">
          <span class="ai-history-name">${esc(row.filename)}</span>
          <span class="ai-history-time">${esc(row.modified_at || "")}</span>
        </button>
      </li>`;
    }).join("");
    list.querySelectorAll(".ai-history-item").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          const { data: file } = await api(reportReadUrl(cfg, btn.dataset.file));
          const row = ms.reports.find((r) => r.filename === btn.dataset.file) || {};
          ms.activeReportFile = btn.dataset.file;
          setBoardMode("result");
          if ($("reportTitle")) $("reportTitle").textContent = file.filename.replace(/\.md$/i, "");
          if ($("reportMeta")) $("reportMeta").textContent = cfg.historyMeta;
          if ($("reportView")) {
            $("reportView").innerHTML = renderMarkdown(file.content || file.markdown || "");
          }
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
        const row = ms.reports.find((r) => r.filename === ms.activeReportFile) || {};
        setBoardMode("result");
        if ($("reportTitle")) $("reportTitle").textContent = data.filename.replace(/\.md$/i, "");
        if ($("reportMeta")) $("reportMeta").textContent = cfg.historyMeta;
        if ($("reportView")) {
          $("reportView").innerHTML = renderMarkdown(data.content || data.markdown || "");
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
      content = data.content || data.markdown || "";
    }
    // 结构化结果只在完整任务里返回，这里补一次。
    let full = null;
    if (job?.id && !result.assessment) {
      try {
        full = await fetchJob(cfg, job.id, true);
      } catch {
        full = null;
      }
    }
    const merged = full?.result || result;
    if (!content) content = resultText(merged);
    return {
      ...merged,
      report: content,
      filename: filename || reportFilename(merged),
    };
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
      const extra = state.mode === "zhang-views" ? { ...zhangViewsFormParams(), refresh: "1" }
        : state.mode === "peers" ? { ...peersFormParams(), refresh: "1" }
        : state.mode === "risk" ? { markdown: "0" }
        : state.mode === "bizprofile" ? { markdown: "0" }
        : undefined;
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
        if ($("reportView")) {
          $("reportView").innerHTML = renderMarkdown(data.content || data.markdown || "");
        }
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
    document.getElementById("panel-judgment")?.addEventListener("click", (ev) => {
      if (!ev.target.closest?.("#zvRecalc")) return;
      ev.preventDefault();
      loadEngine("zhang-views", { force: true, extra: { ...zhangViewsFormParams(), refresh: "1" } })
        .catch((err) => showError(err.message || String(err)));
    });
    $("reportView")?.addEventListener("click", (ev) => {
      const tab = ev.target.closest?.(".biz-tab[data-biz-tab]");
      if (tab) {
        ev.preventDefault();
        const host = tab.closest(".biz-profile") || $("reportView");
        activateBizTab(host, tab.getAttribute("data-biz-tab"));
        return;
      }
      const card = ev.target.closest?.(".biz-sum-card[data-biz-card]");
      if (!card) return;
      const host = card.closest(".biz-profile") || $("reportView");
      activateBizTab(host, card.getAttribute("data-biz-card"));
    });
    $("reportView")?.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      const card = ev.target.closest?.(".biz-sum-card[data-biz-card]");
      if (!card) return;
      ev.preventDefault();
      card.click();
    });
    $("reportView")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest?.("[data-peers-jump]");
      if (!btn) return;
      ev.preventDefault();
      const key = btn.getAttribute("data-peers-jump");
      const target = document.getElementById(`peers-view-${key}`);
      if (!target) return;
      if (target.tagName === "DETAILS" && !target.open) target.open = true;
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    $("reportView")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest?.("[data-risk-dim]");
      if (!btn) return;
      ev.preventDefault();
      const key = btn.getAttribute("data-risk-dim");
      const target = document.getElementById(`risk-dim-${key}`);
      if (!target) return;
      if (target.tagName === "DETAILS" && !target.open) target.open = true;
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    (function peersFloatTooltip() {
      const host = document.getElementById("panel-judgment");
      if (!host) return;
      const float = document.createElement("div");
      float.className = "peers-float";
      document.body.appendChild(float);
      let active = null;
      const show = (dot) => {
        float.innerHTML = "";
        const label = dot.getAttribute("data-tip-label") || "";
        const value = dot.getAttribute("data-tip-value") || "";
        const total = dot.getAttribute("data-tip-total") || "";
        let rows = [];
        try { rows = JSON.parse(dot.getAttribute("data-tip-rows") || "[]"); } catch { rows = []; }
        const head = document.createElement("b");
        head.className = "peers-float-head";
        head.textContent = label;
        float.append(head);
        const sub = document.createElement("span");
        sub.className = "peers-float-sub";
        sub.textContent = `${value} · ${rows.length} 家${rows.length > 1 ? "并列" : ""}`;
        float.append(sub);
        const list = document.createElement("div");
        list.className = "peers-float-rows";
        rows.forEach((it) => {
          const line = document.createElement("div");
          line.className = "peers-float-row" + (it && it.target ? " is-target" : "");
          line.textContent = `${(it && it.name) || ""} · 第 ${(it && it.rank) || ""}/${total} 名`;
          list.append(line);
        });
        float.append(list);
        float.classList.add("is-open");
        const r = dot.getBoundingClientRect();
        const half = float.offsetWidth / 2;
        let cx = r.left + r.width / 2;
        cx = Math.max(half + 4, Math.min(window.innerWidth - half - 4, cx));
        float.style.left = cx + "px";
        const fh = float.offsetHeight;
        let topPos = r.top - 8;
        if (topPos - fh < 4) topPos = fh + 4;
        float.style.top = topPos + "px";
        active = dot;
      };
      const hide = () => { float.classList.remove("is-open"); active = null; };
      host.addEventListener("mouseover", (ev) => {
        const dot = ev.target.closest?.(".peers-tr-dot");
        if (dot) show(dot);
      });
      host.addEventListener("mouseout", (ev) => {
        if (ev.target.closest?.(".peers-tr-dot")) hide();
      });
      host.addEventListener("scroll", () => { if (active) hide(); }, true);
      window.addEventListener("resize", () => { if (active) hide(); });
    })();
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
