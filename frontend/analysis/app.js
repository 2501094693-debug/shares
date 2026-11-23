(() => {
  const POLL_MS = 1200;
  const WEEK = "日一二三四五六";
  const PAGE_SUB =
    "按交易日复盘申万三级行业轮动：上涨/待涨/领涨均按所选交易日切片；行情与主力净流入（当日/5日/10日）回溯至该日。点击行业进入行情树";

  const industry = {
    days: 20,
    status: "idle",
    dayRows: [],
    selectedDate: "",
    untouched: [],
    ranking: [],
    universe: 0,
    coveredCount: 0,
    untouchedCount: 0,
    note: "",
    updatedAt: "",
    errors: [],
    pollTimer: 0,
    fetching: false,
    started: false,
    error: "",
    message: "",
  };

  const shares = {
    mode: false,
    status: "idle",
    start: "",
    end: "",
    asof: "",
    dayRows: [],
    selectedDate: "",
    nearItems: [],
    underItems: [],
    nearCount: 0,
    underCount: 0,
    loading: false,
    error: "",
    message: "",
    note: "",
    pollTimer: 0,
    fetching: false,
    started: false,
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

  function fmtScore(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(0);
  }

  function scoreTone(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "flat";
    if (n >= 70) return "up";
    if (n <= 60) return "down";
    return "flat";
  }

  function tone(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n === 0) return "flat";
    return n > 0 ? "up" : "down";
  }

  function weekday(date) {
    const d = new Date(`${date}T00:00:00`);
    if (Number.isNaN(d.getTime())) return "";
    return `周${WEEK[d.getDay()]}`;
  }

  function fmtMd(date) {
    return String(date || "").slice(5) || "—";
  }

  function fmtShortDate(date) {
    if (!date) return "—";
    const m = String(date).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return date;
    return `${m[2]}月${m[3]}日`;
  }

  function selectedIndustryDay() {
    return (
      industry.dayRows.find((d) => d.date === industry.selectedDate) || industry.dayRows[0] || null
    );
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

  function syncStatusUi() {
    showError(industry.error || "");
    if (industry.status === "running") {
      showLoading(true, industry.message || "正在分析…");
      setLive("busy");
      return;
    }
    showLoading(false);
    if (industry.status === "done") setLive("live");
    else if (industry.status === "error") setLive("idle");
    else setLive(industry.started ? "live" : "idle");
  }

  function syncUrl() {
    const url = new URL(location.href);
    url.searchParams.delete("view");
    url.searchParams.delete("mode");
    url.searchParams.delete("code");
    url.searchParams.delete("sort");
    url.searchParams.delete("order");
    url.searchParams.delete("band");
    url.searchParams.delete("index");
    url.searchParams.delete("factor");
    url.searchParams.delete("path");
    url.searchParams.delete("adjust");
    history.replaceState({}, "", url);
  }

  function applyChrome() {
    document.title = "ORBIT · 行情研判";
    const board = $("rotBoard");
    const sharesView = $("sharesView");
    const modeBtn = $("modeShareBtn");
    const isShares = shares.mode === true;
    document.body.dataset.screenMode = isShares ? "shares" : "industry";
    if (board) board.classList.toggle("hidden", isShares);
    if (sharesView) sharesView.classList.toggle("hidden", !isShares);
    if (modeBtn) {
      modeBtn.textContent = isShares ? "行业轮动" : "个股分析";
      modeBtn.classList.toggle("is-active", isShares);
    }
    if (isShares) {
      stopPoll();
      syncSharesDateInputs();
      renderShareDays();
      renderShareBoards();
      renderShareStatus();
      const summaryBar = $("summaryBar");
      if (summaryBar) {
        summaryBar.innerHTML = "";
      }
    } else {
      stopSharesPoll();
      syncStatusUi();
      renderAll();
    }
    syncUrl();
  }

  function markSeg(rootId, key, value) {
    const root = $(rootId);
    if (!root) return;
    root.querySelectorAll(`button[data-${key}]`).forEach((btn) => {
      const raw = btn.dataset[key];
      const active = typeof value === "number" ? Number(raw) === value : raw === value;
      btn.classList.toggle("is-active", active);
    });
  }

  function renderSeg() {
    markSeg("industryDaysSeg", "days", industry.days);
  }

  function windowLabel(days) {
    const n = Number(days);
    if (n >= 400) return "两年";
    if (n >= 180) return "一年";
    if (n >= 90) return "近半年";
    if (n >= 40) return "近三个月";
    if (n >= 15) return "近一个月";
    return `${n}日`;
  }

  const WATCH_CHANGE_PCT = 2.0;

  function industryChrono() {
    return [...(industry.dayRows || [])].reverse();
  }

  function paintDayQuote(row, quotes, hasQuotes) {
    if (!row) return row;
    if (!hasQuotes) return row;
    const q = row.code && quotes && quotes[row.code];
    const merged = { ...row };
    if (q) {
      Object.assign(merged, q);
    }
    for (const key of ["main_net", "main_net_5d", "main_net_10d"]) {
      merged[key] = q && Object.prototype.hasOwnProperty.call(q, key) ? q[key] : null;
    }
    return merged;
  }

  function updateWaitTableHeaders(day) {
    const table = $("indWaitBody")?.closest("table");
    const ths = table?.querySelectorAll("thead th");
    if (!ths || ths.length < 9) return;
    const latest = industry.dayRows[0]?.date;
    const hist = day && day.date && day.date !== latest;
    ths[3].textContent = hist ? "当日涨跌" : "涨跌";
    ths[6].textContent = hist ? "当日" : "今日";
    ths[7].textContent = hist ? "近5日" : "5日";
    ths[8].textContent = hist ? "近10日" : "10日";
  }

  function untouchedTag(row) {
    const flow5 = row.main_net_5d;
    const flow10 = row.main_net_10d;
    const d5 = row.change_5d;
    const money =
      flow5 != null && Number(flow5) > 0 && flow10 != null && Number(flow10) > 0;
    if (money && (d5 == null || Number(d5) < WATCH_CHANGE_PCT)) {
      return { tag: "资金先行", reason: "窗口内没被点名，但5日和10日资金都在进" };
    }
    if (d5 != null && Number(d5) >= WATCH_CHANGE_PCT) {
      return { tag: "近5日跟上", reason: "窗口内没被点名，近5日已经转强" };
    }
    return { tag: "", reason: "窗口内从未达到轮动分数线" };
  }

  function industryBoardsAsOf(selectedDate) {
    const chrono = industryChrono();
    if (!chrono.length) {
      return { wait: [], ranking: [], coveredCount: 0, untouchedCount: 0 };
    }
    const date = selectedDate || chrono[chrono.length - 1]?.date || "";
    const datePos = {};
    chrono.forEach((d, i) => {
      if (d.date) datePos[d.date] = i;
    });
    const endPos = datePos[date];
    if (endPos === undefined) {
      return { wait: [], ranking: [], coveredCount: 0, untouchedCount: 0 };
    }

    const hitsMap = {};
    for (let i = 0; i <= endPos; i++) {
      const day = chrono[i];
      const risen = [...(day.first || []), ...(day.again || [])];
      for (const item of risen) {
        const code = item.code;
        if (!code) continue;
        if (!hitsMap[code]) hitsMap[code] = [];
        hitsMap[code].push(day.date);
      }
    }

    const selectedDay = chrono[endPos];
    const hasQuotes =
      selectedDay && Object.prototype.hasOwnProperty.call(selectedDay, "quotes");
    const dayQuotes = hasQuotes ? selectedDay.quotes || {} : null;
    const risenToday = new Set(
      [...(selectedDay.first || []), ...(selectedDay.again || [])]
        .map((r) => r.code)
        .filter(Boolean),
    );

    const base =
      industry.ranking && industry.ranking.length
        ? industry.ranking
        : [...(industry.untouched || [])];

    const ranking = base
      .map((row) => {
        const hitDates = hitsMap[row.code] || [];
        return paintDayQuote(
          {
            ...row,
            hits: hitDates.length,
            first_date: hitDates[0] || "",
            last_date: hitDates[hitDates.length - 1] || "",
          },
          dayQuotes,
          hasQuotes,
        );
      })
      .sort((a, b) => {
        const ah = Number(a.hits) || 0;
        const bh = Number(b.hits) || 0;
        if (bh !== ah) return bh - ah;
        const ad = String(a.last_date || "");
        const bd = String(b.last_date || "");
        if (ad !== bd) return bd.localeCompare(ad);
        return String(a.name || "").localeCompare(String(b.name || ""), "zh");
      });

    const coveredCount = ranking.filter((r) => Number(r.hits) > 0).length;

    const wait = ranking
      .filter((row) => !risenToday.has(row.code))
      .map((row) => {
        const last = row.last_date || "";
        let idleDays;
        if (last) {
          idleDays = endPos - (datePos[last] ?? endPos);
        } else {
          idleDays = endPos + 1;
        }
        const { tag, reason } = untouchedTag(row);
        const item = {
          ...row,
          idle_days: idleDays,
          tag: tag || "待涨",
        };
        if (last) {
          item.reason = `距上次上榜 ${idleDays} 个交易日（${last}）${tag ? `；${reason}` : ""}`;
        } else if (!tag) {
          item.reason = "窗口内从未上榜";
        } else {
          item.reason = reason;
        }
        return item;
      })
      .sort((a, b) => {
        const ai = Number(a.idle_days) || 0;
        const bi = Number(b.idle_days) || 0;
        if (bi !== ai) return bi - ai;
        return String(a.last_date || "").localeCompare(String(b.last_date || ""));
      });

    return { wait, ranking, coveredCount, untouchedCount: wait.length };
  }

  function renderIndustrySummary() {
    const boards = industryBoardsAsOf(industry.selectedDate);
    const coveredN = boards.coveredCount || 0;
    const leftN = boards.untouchedCount || 0;
    $("summaryBar").innerHTML = `
      <span>扫描 <b>${industry.universe || 0}</b> 个三级</span>
      <span><b class="is-up">${coveredN}</b> 已上榜</span>
      <span>待涨 <b>${leftN}</b></span>
      <span>窗口 <b>${windowLabel(industry.days)}</b></span>
    `;
    $("marketMeta").textContent = "";
  }

  function renderRotDays() {
    const rail = $("rotDayRail");
    const hint = $("rotDaysHint");
    if (hint) hint.textContent = industry.dayRows.length ? `${industry.dayRows.length} 天` : "";
    if (!rail) return;
    if (!industry.dayRows.length) {
      rail.innerHTML = `<div class="rot-empty">暂无交易日</div>`;
      return;
    }
    rail.innerHTML = industry.dayRows
      .map((day) => {
        const active = day.date === industry.selectedDate ? " is-active" : "";
        const n =
          day.risen_count ||
          ((day.first || []).length + (day.again || []).length) ||
          0;
        return `<button type="button" class="rot-day${active}" data-date="${esc(day.date)}">
          <span class="rot-day-when">
            <b>${esc(fmtMd(day.date))}</b>
            <em>${esc(weekday(day.date))}</em>
          </span>
          <span class="rot-day-n">${n}</span>
        </button>`;
      })
      .join("");
  }

  function renderIndustryHead(day) {
    const boards = industryBoardsAsOf(industry.selectedDate || day?.date);
    const waitN = boards.untouchedCount;
    const againN = risenList(day).length;
    const rankN = boards.ranking.length;
    const when = day ? `${fmtMd(day.date)} ${weekday(day.date)}` : "";
    const waitHint = $("rotWaitHint");
    const againHint = $("rotAgainHint");
    const rankHint = $("indRankHint");
    if (waitHint) waitHint.textContent = waitN ? `${waitN}` : "";
    if (againHint) againHint.textContent = day ? `${when} · ${againN}` : "";
    if (rankHint) rankHint.textContent = rankN ? `${rankN} 个` : "";
  }

  function tagTone(bucket, tag) {
    const key = String(bucket || tag || "");
    if (key === "首次" || key === "新轮到" || key === "近5日跟上" || key === "may_rotate" || key === "may_turn") return "up";
    if (key === "上涨" || key === "续涨" || key === "risen_hot") return "up";
    if (key === "待涨") return "down";
    if (key === "资金先行" || key === "watch") return "flat";
    if (key === "risen_cool") return "down";
    return "flat";
  }

  function fmtIdle(days, lastDate) {
    if (!lastDate) return "从未";
    const n = Number(days);
    if (!Number.isFinite(n)) return "—";
    return `${n}日`;
  }

  function fmtCountPair(total, limit) {
    const up = Number(total);
    const lim = Number(limit);
    if (!Number.isFinite(up) && !Number.isFinite(lim)) return "—";
    const a = Number.isFinite(up) ? up : 0;
    const b = Number.isFinite(lim) ? lim : 0;
    return `${a}(${b})`;
  }

  function fmtBreadth(up, sample) {
    const a = Number(up);
    const b = Number(sample);
    if (!Number.isFinite(a) || !Number.isFinite(b) || b <= 0) return "—";
    return `${a}/${b}`;
  }

  function breadthTone(up, sample, pct) {
    const a = Number(up);
    const b = Number(sample);
    const ratio = Number.isFinite(a) && Number.isFinite(b) && b > 0 ? a / b : Number(pct) / 100;
    if (!Number.isFinite(ratio)) return "flat";
    if (ratio >= 0.7) return "up";
    if (ratio <= 0.4) return "down";
    return "flat";
  }

  function fmtHits(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "0";
    return String(n);
  }

  function risenList(day) {
    const first = ((day && day.first) || []).map((row) => ({
      ...row,
      tag: "首次",
    }));
    const again = (day && day.again) || [];
    return first.concat(again);
  }

  function industryRows(items, kind) {
    if (!items.length) {
      const cols = kind === "wait" ? 9 : kind === "again" ? 6 : 3;
      const empty =
        kind === "rank"
          ? "还没有领涨行业"
          : kind === "wait"
            ? "没有待涨行业"
            : "这一天没有上涨行业";
      return `<tr class="is-empty"><td colspan="${cols}">${empty}</td></tr>`;
    }
    return items
      .map((n) => {
        const tag = String(n.tag || "").trim() === "续涨" ? "上涨" : String(n.tag || "").trim();
        const showTag = tag === "首次" || (kind === "wait" && tag);
        const tagHtml = showTag
          ? `<span class="rot-tag" data-tone="${tagTone(n.bucket, tag)}">${esc(tag)}</span>`
          : "";
        const tier = kind === "wait" ? "" : String(n.cap_tier || "").trim();
        const tierHtml = tier
          ? `<span class="rot-tag" data-tone="flat">${esc(tier)}</span>`
          : "";
        const sub = [n.l2_name, n.leader].filter(Boolean).join(" · ");
        const strong = n.strong_1d == null ? n.limit_up_1d : n.strong_1d;
        const extra =
          kind === "wait"
            ? `<td class="num">${esc(fmtHits(n.hits))}</td>
          <td class="num" data-tone="${n.tag === "首次" ? "up" : n.last_date ? "flat" : "down"}">${
              n.tag === "首次" ? "当天" : esc(fmtIdle(n.idle_days, n.last_date))
            }</td>
          <td class="num" data-tone="${tone(n.change_1d)}">${fmtPct(n.change_1d)}</td>
          <td class="num" data-tone="up">${esc(fmtCountPair(n.up_1d, n.limit_up_1d))}</td>
          <td class="num" data-tone="down">${esc(fmtCountPair(n.down_1d, n.limit_down_1d))}</td>
          <td class="num" data-tone="${tone(n.main_net)}">${fmtYi(n.main_net)}</td>
          <td class="num" data-tone="${tone(n.main_net_5d)}">${fmtYi(n.main_net_5d)}</td>
          <td class="num" data-tone="${tone(n.main_net_10d)}">${fmtYi(n.main_net_10d)}</td>`
            : kind === "rank"
              ? `<td class="num" data-tone="${Number(n.hits) > 0 ? "up" : "flat"}">${esc(fmtHits(n.hits))}</td>
          <td class="num">${esc(n.last_date ? fmtMd(n.last_date) : "从未")}</td>`
              : `<td class="num">${esc(fmtHits(n.hits))}</td>
          <td class="num" data-tone="${scoreTone(n.score)}">${fmtScore(n.score)}</td>
          <td class="num" data-tone="${tone(n.change_1d)}">${fmtPct(n.change_1d)}</td>
          <td class="num" data-tone="${breadthTone(n.up_1d, n.sample_count, n.breadth)}" title="${esc(
            n.breadth == null ? "上涨家数/样本" : `上涨 ${fmtBreadth(n.up_1d, n.sample_count)} · ${Number(n.breadth).toFixed(0)}%`
          )}">${esc(fmtBreadth(n.up_1d, n.sample_count))}</td>
          <td class="num" data-tone="${Number(strong) > 0 ? "up" : "flat"}">${strong == null ? "—" : esc(strong)}</td>`;
        return `<tr class="is-row" data-code="${esc(n.code || "")}" data-l1="${esc(n.l1_code || "")}" data-l2="${esc(n.l2_code || "")}" title="${esc(n.reason || "")}">
          <td>
            <div class="rot-name"><strong>${esc(n.name || n.code || "—")}</strong>${tagHtml}${tierHtml}</div>
            <div class="rot-sub">${esc(sub)}</div>
          </td>
          ${extra}
        </tr>`;
      })
      .join("");
  }

  function renderIndustry() {
    const day = selectedIndustryDay();
    const boards = industryBoardsAsOf(industry.selectedDate || day?.date);
    const wait = boards.wait;
    const again = risenList(day);
    const ranking = boards.ranking;
    updateWaitTableHeaders(day);
    const waitBody = $("indWaitBody");
    const againBody = $("indAgainBody");
    const rankBody = $("indRankBody");
    if (waitBody) waitBody.innerHTML = industryRows(wait, "wait");
    if (againBody) againBody.innerHTML = industryRows(again, "again");
    if (rankBody) rankBody.innerHTML = industryRows(ranking, "rank");
  }

  function renderAll() {
    renderSeg();
    renderIndustrySummary();
    renderRotDays();
    renderIndustryHead(selectedIndustryDay());
    renderIndustry();
  }

  /* ---------- 个股分析：区间回测（参照涨跌停左右分栏） ---------- */

  function localIso(date) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }

  function syncSharesDateInputs() {
    const now = new Date();
    const today = localIso(now);
    const monthAgo = localIso(new Date(now.getTime() - 30 * 86400000));
    const startEl = $("shareStartDate");
    const endEl = $("shareEndDate");
    const asofEl = $("shareAsOfDate");
    if (startEl && shares.start) startEl.value = shares.start;
    else if (startEl && !startEl.value) startEl.value = monthAgo;
    if (endEl && shares.end) endEl.value = shares.end;
    else if (endEl && !endEl.value) endEl.value = today;
    if (asofEl && shares.asof) asofEl.value = shares.asof;
    else if (asofEl && !asofEl.value) asofEl.value = today;
  }

  function fmtGainPct(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    const pct = n * 100;
    const sign = pct > 0 ? "+" : pct < 0 ? "-" : "";
    return `${sign}${Math.abs(pct).toFixed(1)}%`;
  }

  function isNearSignal(row) {
    const signals = Array.isArray(row.macd_signals) ? row.macd_signals : [];
    const primary = String(row.macd_signal || "");
    return signals.includes("即将水下金叉") || primary === "即将水下金叉";
  }

  function isUnderCross(row) {
    const signals = Array.isArray(row.macd_signals) ? row.macd_signals : [];
    const primary = String(row.macd_signal || "");
    return signals.includes("水下金叉") || primary === "水下金叉";
  }

  function partitionShareItems(items) {
    const near = [];
    const under = [];
    for (const row of items || []) {
      if (!row || !row.code) continue;
      if (isNearSignal(row)) near.push(row);
      else if (isUnderCross(row)) under.push(row);
    }
    return { near, under };
  }

  function renderShareDays() {
    const list = $("shareDateList");
    if (!list) return;
    if (!shares.dayRows.length) {
      list.innerHTML = `<div class="share-date-empty">暂无交易日</div>`;
      return;
    }
    list.innerHTML = shares.dayRows
      .map((day) => {
        const active = day.date === shares.selectedDate ? " is-active" : "";
        const n = Number(day.found_count || 0);
        return `<button type="button" class="share-day${active}" data-date="${esc(day.date)}">
          <span class="share-day-when">
            <b>${esc(fmtMd(day.date))}</b>
            <em>${esc(weekday(day.date))}</em>
          </span>
          <span class="share-day-n">${n}</span>
        </button>`;
      })
      .join("");
  }

  function renderShareBoard(kind) {
    const bodyId = kind === "near" ? "shareNearBody" : "shareUnderBody";
    const items = kind === "near" ? shares.nearItems : shares.underItems;
    const title = kind === "near" ? "即将水下金叉" : "水下金叉";
    const body = $(bodyId);
    if (!body) return;

    const countEl = body.closest(".judgment-shares-row")?.querySelector(".judgment-shares-row-count");
    if (countEl) countEl.textContent = items.length;

    if (!items.length) {
      body.innerHTML = `<tr class="is-empty"><td colspan="8">今天没有${title}股票</td></tr>`;
      return;
    }

    body.innerHTML = items.map((row) => {
      const gapOk = row.near_by_relative_gap === true;
      const velOk = row.near_by_prediction === true;
      const scoreClose = scoreTone(row.score_close);
      const scoreLow = scoreTone(row.score_low);
      const lastGain = fmtGainPct(row.last_close_gain);
      const maxGain = fmtGainPct(row.max_close_gain);
      const closeDate = row.low_close_date ? fmtShortDate(row.low_close_date) : "—";
      const closePrice = Number.isFinite(row.low_close_price) ? row.low_close_price.toFixed(2) : "—";
      const lowDate = row.low_low_date ? fmtShortDate(row.low_low_date) : "—";
      const lowPrice = Number.isFinite(row.low_low_price) ? row.low_low_price.toFixed(2) : "—";
      return `<tr class="is-row is-clickable" data-code="${esc(row.code)}" data-name="${esc(row.name || row.code)}" title="${esc(row.name || row.code)} 点击查看公司详情">
        <td>
          <div class="share-name"><strong>${esc(row.name || row.code)}</strong></div>
          <div class="share-code">${esc(row.code)}</div>
        </td>
        <td class="share-bool" data-tone="${gapOk ? "up" : "down"}">${gapOk ? "满足" : "不满足"}</td>
        <td class="share-bool" data-tone="${velOk ? "up" : "down"}">${velOk ? "满足" : "不满足"}</td>
        <td>
          <div class="share-kv">${esc(row.beg || "—")} → ${esc(row.end || "—")}</div>
          <div class="share-kv muted">${Number(row.count || 0)} 日</div>
        </td>
        <td class="share-kv" data-tone="${tone(row.reverse_count)}">${row.reverse_count == null ? "—" : row.reverse_count}</td>
        <td class="share-kv">${closeDate}<br>${closePrice}<br>${fmtScore(row.score_close)}</td>
        <td class="share-kv">${lowDate}<br>${lowPrice}<br>${fmtScore(row.score_low)}</td>
        <td class="share-kv" data-tone="${tone(row.max_close_gain)}">${maxGain}（${esc(row.max_close_date ? fmtShortDate(row.max_close_date) : "—")}）<br>${lastGain}</td>
      </tr>`;
    }).join("");
  }

  function renderShareBoards() {
    renderShareBoard("near");
    renderShareBoard("under");
  }

  function renderShareStatus() {
    const box = $("shareErrorBox");
    const loading = $("shareLoading");
    const live = $("liveDot");
    const meta = $("marketMeta");
    if (shares.error) {
      box.textContent = shares.error;
      box.classList.remove("hidden");
    } else {
      box.classList.add("hidden");
      box.textContent = "";
    }
    if (shares.status === "running") {
      loading.textContent = shares.message || "正在分析…";
      loading.classList.remove("hidden");
      live.dataset.state = "busy";
      live.textContent = "SYNC";
    } else {
      loading.classList.add("hidden");
      if (shares.status === "done") {
        live.dataset.state = "live";
        live.textContent = "LIVE";
      } else if (shares.status === "error") {
        live.dataset.state = "idle";
        live.textContent = "IDLE";
      } else {
        live.dataset.state = shares.started ? "live" : "idle";
        live.textContent = "IDLE";
      }
    }
    if (meta) meta.textContent = shares.message || "";
    if (shares.note) {
      const hint = $("sharesHint");
      if (hint) hint.textContent = shares.note;
    }
  }

  function stopSharesPoll() {
    if (shares.pollTimer) {
      clearTimeout(shares.pollTimer);
      shares.pollTimer = 0;
    }
  }

  function scheduleSharesPoll() {
    stopSharesPoll();
    shares.pollTimer = setTimeout(() => loadShares(false), POLL_MS);
  }

  async function loadShares(force) {
    if (shares.fetching && !force) return;
    shares.fetching = true;
    shares.started = true;
    shares.error = "";
    if (!boxHidden($("shareErrorBox"))) $("shareErrorBox").classList.add("hidden");

    const qs = new URLSearchParams();
    qs.set("start", shares.start);
    if (shares.end) qs.set("end", shares.end);
    if (shares.asof) qs.set("asof", shares.asof);
    qs.set("cross_type", "under");
    qs.set("refresh", force ? "1" : "0");

    try {
      const res = await fetch(`/api/screen/macd/range?${qs}`, { cache: "no-store" });
      const json = await res.json();
      if (!json.ok) {
        throw new Error(json.error || "请求失败");
      }
      applySharesPayload(json.data || {});
      if (shares.status === "running") scheduleSharesPoll();
      else stopSharesPoll();
    } catch (err) {
      shares.error = err.message || String(err);
      shares.status = "error";
      renderShareStatus();
      stopSharesPoll();
    } finally {
      shares.fetching = false;
    }
  }

  function boxHidden(el) {
    return el && el.classList.contains("hidden");
  }

  function applySharesPayload(payload) {
    shares.status = payload.status || "idle";
    if (payload.status === "done" && payload.data) {
      shares.error = "";
      shares.message = "";
      applySharesData(payload.data);
      renderShareStatus();
      renderShareDays();
      renderShareBoards();
      return;
    }
    if (payload.status === "error") {
      shares.error = payload.error || "分析失败";
      shares.message = "";
      renderShareStatus();
      return;
    }
    if (payload.status === "running") {
      if (payload.data) applySharesData(payload.data);
      const progress = payload.progress || {};
      const done = Number(progress.done || 0);
      const total = Number(progress.total || 0);
      const hit = (payload.data && payload.data.result_count) || 0;
      shares.message = (progress.phase === "gains"
        ? "正在计算事后最大涨幅…"
        : total
          ? `已分析 ${done}/${total}，命中 ${hit}`
          : "正在准备区间回测…");
      shares.error = "";
      const partial = (shares.dayRows || []).length > 0;
      const loading = $("shareLoading");
      loading.textContent = shares.message;
      loading.classList.remove("hidden");
      $("liveDot").dataset.state = partial ? "live" : "busy";
      $("liveDot").textContent = partial ? "LIVE" : "SYNC";
      renderShareDays();
      renderShareBoards();
      $("marketMeta").textContent = shares.message;
      scheduleSharesPoll();
    }
  }

  function applySharesData(data) {
    const dayRows = data.days || [];
    shares.dayRows = dayRows;
    const allItems = [];
    for (const day of dayRows) {
      for (const item of day.items || []) {
        item._signal_day = day.date;
        allItems.push(item);
      }
    }
    // 事后涨幅字段已由接口回填到每行；直接按信号类别分区。
    const parts = partitionShareItems(allItems);
    shares.nearItems = parts.near;
    shares.underItems = parts.under;
    shares.nearCount = parts.near.length;
    shares.underCount = parts.under.length;
    shares.note = data.note || "";
    shares.updatedAt = data.updated_at || "";

    // 保留用户已选日期；仅当无有效选中时给默认值（区间为升序返回）。
    const valid = shares.dayRows.some((d) => d.date === shares.selectedDate);
    if (!valid) {
      const lastDate = shares.dayRows[shares.dayRows.length - 1]?.date || "";
      let chosen = "";
      // 优先选最近一个「非最新交易日」的有命中日期，保证事后涨幅有统计窗口（否则当天信号涨幅必为 0）。
      for (let i = shares.dayRows.length - 1; i >= 0; i--) {
        const d = shares.dayRows[i];
        if (Number(d.found_count || 0) > 0 && d.date !== lastDate) {
          chosen = d.date;
          break;
        }
      }
      if (!chosen) {
        for (let i = shares.dayRows.length - 1; i >= 0; i--) {
          const d = shares.dayRows[i];
          if (Number(d.found_count || 0) > 0) {
            chosen = d.date;
            break;
          }
        }
      }
      if (!chosen) {
        chosen = lastDate;
      }
      shares.selectedDate = chosen;
    }

    if (shares.selectedDate) {
      const day = shares.dayRows.find((d) => d.date === shares.selectedDate) || {};
      const parts = partitionShareItems(day.items || []);
      shares.nearItems = parts.near;
      shares.underItems = parts.under;
      shares.nearCount = parts.near.length;
      shares.underCount = parts.under.length;
    }
  }

  /* ---------- 个股分析 end ---------- */

  function applyIndustryData(data) {
    industry.dayRows = data.days || [];
    if (!industry.dayRows.some((d) => d.date === industry.selectedDate)) {
      industry.selectedDate = (industry.dayRows[0] && industry.dayRows[0].date) || "";
    }
    industry.untouched = data.untouched || [];
    industry.ranking = data.ranking || data.covered || [];
    industry.universe = data.universe_count || 0;
    industry.coveredCount = data.covered_count || 0;
    industry.untouchedCount = data.untouched_count || industry.untouched.length;
    industry.note = data.note || "";
    industry.updatedAt = data.updated_at || "";
    industry.errors = data.errors || [];
    industry.error = industry.errors.join("；");
    renderAll();
  }

  function applyPayload(payload) {
    industry.status = payload.status || "idle";
    const progress = payload.progress || {};
    if (progress.total) {
      industry.candidateCount = progress.total;
      industry.analyzedCount = progress.done || 0;
    }

    if (payload.status === "done" && payload.data) {
      industry.error = "";
      industry.message = "";
      applyIndustryData(payload.data);
      showLoading(false);
      showError(industry.error || "");
      setLive("live");
      return;
    }

    if (payload.status === "error") {
      industry.error = payload.error || "分析失败";
      industry.message = "";
      showLoading(false);
      showError(industry.error);
      setLive("idle");
      return;
    }

    if (payload.status === "running") {
      if (payload.data) applyIndustryData(payload.data);
      const elapsed = payload.elapsed_sec ? ` · ${fmtNum(payload.elapsed_sec, 0)}s` : "";
      industry.message = `${payload.message || "正在分析…"}${elapsed}`;
      industry.error = "";
      const partial = (industry.dayRows || []).length > 0;
      showLoading(!partial, industry.message);
      setLive(partial ? "live" : "busy");
      if (partial) {
        $("marketMeta").textContent = industry.message;
      }
    }
  }

  function stopPoll() {
    if (industry.pollTimer) {
      clearTimeout(industry.pollTimer);
      industry.pollTimer = 0;
    }
  }

  function schedulePoll() {
    stopPoll();
    industry.pollTimer = setTimeout(() => loadIndustry(false), POLL_MS);
  }

  async function loadIndustry(force) {
    if (industry.fetching && !force) return;
    industry.fetching = true;
    industry.started = true;
    industry.error = "";
    showError("");
    if (force) {
      industry.dayRows = [];
      industry.untouched = [];
      industry.ranking = [];
      industry.coveredCount = 0;
      industry.untouchedCount = 0;
      industry.selectedDate = "";
      renderAll();
      industry.message = "正在统计每天哪些三级轮到了…";
      showLoading(true, industry.message);
      setLive("busy");
    }

    const qs = new URLSearchParams({
      days: String(industry.days),
      refresh: force ? "1" : "0",
    });

    try {
      const res = await fetch(`/api/screen/rotation?${qs}`, { cache: "no-store" });
      const json = await res.json();
      if (!json.ok) {
        throw new Error(json.error || "请求失败");
      }
      applyPayload(json.data || {});
      if (industry.status === "running") schedulePoll();
      else stopPoll();
    } catch (err) {
      industry.error = err.message || String(err);
      industry.status = "error";
      showLoading(false);
      showError(industry.error);
      setLive("idle");
      stopPoll();
    } finally {
      industry.fetching = false;
    }
  }

  function bindEvents() {
    $("refreshBtn").addEventListener("click", () => {
      if (shares.mode) {
        startSharesAnalysis(true);
      } else {
        loadIndustry(true);
      }
    });

    $("industryDaysSeg").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-days]");
      if (!btn) return;
      const days = Number(btn.dataset.days);
      if (days === industry.days) return;
      industry.days = days;
      renderSeg();
      loadIndustry(true);
    });

    function openIndustry(row) {
      const l1 = row.dataset.l1 || "";
      const l2 = row.dataset.l2 || "";
      const l3 = row.dataset.code || "";
      const qs = new URLSearchParams();
      if (l1) qs.set("l1", l1);
      if (l2) qs.set("l2", l2);
      if (l3) qs.set("l3", l3);
      const suffix = qs.toString();
      window.location.href = suffix ? `/market?${suffix}` : "/market";
    }

    function onIndustryRowClick(ev) {
      const row = ev.target.closest("tr.is-row[data-code]");
      if (row) openIndustry(row);
    }

    $("indWaitBody").addEventListener("click", onIndustryRowClick);
    $("indAgainBody").addEventListener("click", onIndustryRowClick);
    $("indRankBody").addEventListener("click", onIndustryRowClick);

    $("rotDayRail").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-date]");
      if (!btn) return;
      const date = btn.dataset.date;
      if (!date || date === industry.selectedDate) return;
      industry.selectedDate = date;
      renderAll();
    });

    $("modeShareBtn").addEventListener("click", () => {
      shares.mode = !shares.mode;
      applyChrome();
      if (shares.mode && !shares.started) {
        startSharesAnalysis(true);
      }
    });

    $("shareRefreshBtn").addEventListener("click", () => {
      startSharesAnalysis(true);
    });

    $("shareStartDate").addEventListener("change", (ev) => {
      shares.start = ev.target.value || "";
    });
    $("shareEndDate").addEventListener("change", (ev) => {
      shares.end = ev.target.value || "";
    });
    $("shareAsOfDate").addEventListener("change", (ev) => {
      shares.asof = ev.target.value || "";
    });

    $("shareDateList").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-date]");
      if (!btn) return;
      const date = btn.dataset.date;
      if (!date || date === shares.selectedDate) return;
      shares.selectedDate = date;
      const day = shares.dayRows.find((d) => d.date === date) || {};
      const parts = partitionShareItems(day.items || []);
      shares.nearItems = parts.near;
      shares.underItems = parts.under;
      renderShareDays();
      renderShareBoards();
    });

    ["shareNearBody", "shareUnderBody"].forEach((id) => {
      const body = $(id);
      if (!body) return;
      body.addEventListener("click", (ev) => {
        const tr = ev.target.closest("tr.is-row");
        if (!tr) return;
        const code = (tr.dataset.code || "").trim();
        if (!code) return;
        const name = tr.dataset.name || code;
        const url = `/company?${new URLSearchParams({ code, name, from: "analysis" }).toString()}`;
        if (ev.metaKey || ev.ctrlKey) window.open(url, "_blank");
        else window.location.href = url;
      });
    });
  }

  function startSharesAnalysis(force) {
    const startEl = $("shareStartDate");
    const endEl = $("shareEndDate");
    const asofEl = $("shareAsOfDate");
    shares.start = (startEl && startEl.value) || shares.start;
    shares.end = (endEl && endEl.value) || "";
    shares.asof = (asofEl && asofEl.value) || "";
    if (!shares.start) {
      shares.error = "请选择起始日";
      renderShareStatus();
      return;
    }
    if (force) {
      shares.dayRows = [];
      shares.nearItems = [];
      shares.underItems = [];
      shares.nearCount = 0;
      shares.underCount = 0;
      shares.selectedDate = "";
      renderShareDays();
      renderShareBoards();
      $("shareLoading").textContent = "正在准备区间回测…";
      $("shareLoading").classList.remove("hidden");
    }
    loadShares(force);
  }

  applyChrome();
  bindEvents();
  window.OrbitPrefetch?.boot("analysis");
  syncStatusUi();
  loadIndustry(false);
})();
