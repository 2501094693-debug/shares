(() => {
  const VIEW_SIZE = 90;
  const FETCH_LIMIT = 720;
  const MA_LINES = [
    { period: 5, key: "ma5", label: "MA5", color: "#f0b429" },
    { period: 10, key: "ma10", label: "MA10", color: "#5b9dff" },
    { period: 20, key: "ma20", label: "MA20", color: "#d48cff" },
  ];
  const klineCache = new Map();
  const views = new WeakMap();

  function cssVar(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  function chartColors() {
    return {
      accent: cssVar("--accent", "#2ad4b8"),
      muted: cssVar("--muted", "#8494a8"),
      up: cssVar("--up", "#ff5d6c"),
      down: cssVar("--down", "#3dd68c"),
      upSoft: "rgba(255, 93, 108, 0.45)",
      downSoft: "rgba(61, 214, 140, 0.45)",
      avg: cssVar("--accent-hot", "#f0b429"),
      grid: "rgba(42, 212, 184, 0.08)",
      ref: "rgba(132, 148, 168, 0.55)",
      cross: "rgba(232, 238, 247, 0.35)",
    };
  }

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtNum(n, digits = 2) {
    if (n == null || !Number.isFinite(Number(n))) return "-";
    return Number(n).toFixed(digits);
  }

  function fmtVol(n) {
    if (n == null || !Number.isFinite(Number(n))) return "-";
    const v = Number(n);
    if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
    if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(1)}万`;
    return String(Math.round(v));
  }

  function shortTimeLabel(t) {
    const s = String(t || "");
    if (s.length >= 10) return s.slice(0, 10);
    return s;
  }

  function niceNum(range, round) {
    const r = Math.abs(Number(range)) || 1;
    const exp = Math.floor(Math.log10(r));
    const frac = r / 10 ** exp;
    let nice;
    if (round) {
      if (frac < 1.5) nice = 1;
      else if (frac < 3) nice = 2;
      else if (frac < 7) nice = 5;
      else nice = 10;
    } else if (frac <= 1) nice = 1;
    else if (frac <= 2) nice = 2;
    else if (frac <= 5) nice = 5;
    else nice = 10;
    return nice * 10 ** exp;
  }

  function roundToStep(value, step) {
    if (!Number.isFinite(value) || !Number.isFinite(step) || step <= 0) return value;
    const decimals = Math.min(8, Math.max(0, Math.ceil(-Math.log10(step) + 1)));
    const n = Math.round(value / step) * step;
    return Number(n.toFixed(decimals));
  }

  function fmtAxisPrice(value, step) {
    if (!Number.isFinite(value)) return "-";
    let digits = 2;
    if (Number.isFinite(step) && step > 0) {
      if (step >= 1) digits = Math.abs(step % 1) < 1e-8 ? 0 : 2;
      else if (step >= 0.1) digits = 2;
      else if (step >= 0.01) digits = 2;
      else if (step >= 0.001) digits = 3;
      else digits = 4;
    }
    return value.toFixed(digits);
  }

  function buildPriceScale(dataMin, dataMax, { tickCount = 5, padRatio = 0.02 } = {}) {
    let lo = Number(dataMin);
    let hi = Number(dataMax);
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
      return { min: 0, max: 1, ticks: [0, 0.25, 0.5, 0.75, 1], step: 0.25 };
    }
    if (hi < lo) {
      const t = lo;
      lo = hi;
      hi = t;
    }
    if (hi <= lo) {
      const d = Math.max(Math.abs(hi) * 0.005, 0.02);
      lo -= d;
      hi += d;
    }
    const pad = Math.max((hi - lo) * padRatio, 0.005);
    lo -= pad;
    hi += pad;
    const target = Math.max(4, Math.min(7, tickCount));
    let step = niceNum((hi - lo) / Math.max(1, target - 1), false);
    if (step < 0.01) step = 0.01;
    const ticks = [];
    const fillTicks = () => {
      ticks.length = 0;
      const startI = Math.ceil(lo / step - 1e-9);
      const endI = Math.floor(hi / step + 1e-9);
      for (let i = startI; i <= endI; i += 1) {
        const v = roundToStep(i * step, step);
        if (v >= lo - step * 1e-6 && v <= hi + step * 1e-6) ticks.push(v);
      }
    };
    fillTicks();
    let guard = 0;
    while (ticks.length > 8 && guard < 6) {
      guard += 1;
      step = niceNum(step * 1.8, false);
      if (step < 0.01) step = 0.01;
      fillTicks();
    }
    if (ticks.length === 0) {
      ticks.push(roundToStep(lo, step), roundToStep(hi, step));
    } else if (ticks.length === 1) {
      if (Math.abs(ticks[0] - lo) > Math.abs(ticks[0] - hi)) ticks.unshift(roundToStep(lo, step));
      else ticks.push(roundToStep(hi, step));
    }
    return { min: lo, max: hi, ticks, step };
  }

  function priceScaleTickCount(priceH) {
    return Math.max(4, Math.min(7, Math.round(Number(priceH) / 42) || 5));
  }

  function chartLayout(w, h) {
    const pad = { top: 8, right: 8, bottom: 22, left: 52 };
    const innerW = Math.max(10, w - pad.left - pad.right);
    const innerH = Math.max(10, h - pad.top - pad.bottom);
    const volH = Math.max(36, Math.floor(innerH * 0.16));
    const gap = 10;
    const priceH = Math.max(100, innerH - volH - gap);
    return {
      pad,
      price: { x: pad.left, y: pad.top, w: innerW, h: priceH },
      volume: { x: pad.left, y: pad.top + priceH + gap, w: innerW, h: volH },
    };
  }

  function computeSmaSeries(closes, period) {
    const n = closes.length;
    const out = new Array(n).fill(null);
    if (period <= 0 || n < period) return out;
    for (let i = period - 1; i < n; i += 1) {
      let sum = 0;
      let ok = true;
      for (let j = i - period + 1; j <= i; j += 1) {
        const v = Number(closes[j]);
        if (!Number.isFinite(v)) {
          ok = false;
          break;
        }
        sum += v;
      }
      if (ok) out[i] = sum / period;
    }
    return out;
  }

  function maPoint(vals, index) {
    if (!Array.isArray(vals) || index == null || index < 0 || index >= vals.length) return null;
    const raw = vals[index];
    if (raw == null || raw === "") return null;
    const v = Number(raw);
    return Number.isFinite(v) ? v : null;
  }

  function drawGrid(ctx, rect, yTicks, xTicks, colors) {
    ctx.save();
    ctx.strokeStyle = colors.grid;
    ctx.lineWidth = 1;
    for (const y of yTicks) {
      ctx.beginPath();
      ctx.moveTo(rect.x, y);
      ctx.lineTo(rect.x + rect.w, y);
      ctx.stroke();
    }
    for (const x of xTicks) {
      ctx.beginPath();
      ctx.moveTo(x, rect.y);
      ctx.lineTo(x, rect.y + rect.h);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawMaLines(ctx, maVisible, yAt, xAt, n) {
    for (const line of MA_LINES) {
      const vals = maVisible[line.key] || [];
      ctx.save();
      ctx.strokeStyle = line.color;
      ctx.lineWidth = 1.25;
      ctx.beginPath();
      let started = false;
      for (let i = 0; i < n; i += 1) {
        const v = maPoint(vals, i);
        if (v == null) {
          started = false;
          continue;
        }
        const x = xAt(i);
        const y = yAt(v);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
      ctx.restore();
    }
  }

  function drawAxesLabels(ctx, layout, priceScale, items, colors) {
    const { price, volume } = layout;
    const range = priceScale.max - priceScale.min || 1;
    const ticks = Array.isArray(priceScale.ticks) ? priceScale.ticks : [];
    const yOf = (val) => price.y + ((priceScale.max - val) / range) * price.h;

    ctx.save();
    ctx.font = '11px "JetBrains Mono", Consolas, monospace';
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    ctx.fillStyle = colors.muted;
    for (const val of ticks) {
      const y = yOf(val);
      if (y < price.y - 1 || y > price.y + price.h + 1) continue;
      ctx.fillText(fmtAxisPrice(val, priceScale.step), price.x - 6, y);
    }

    ctx.fillStyle = colors.muted;
    ctx.textBaseline = "top";
    const n = items.length;
    if (n > 0) {
      const idxs = [0, Math.floor((n - 1) / 2), n - 1];
      const seen = new Set();
      const plotLeft = price.x;
      const plotRight = price.x + price.w;
      for (const i of idxs) {
        if (seen.has(i)) continue;
        seen.add(i);
        const label = shortTimeLabel(items[i].time);
        let x = plotLeft + ((i + 0.5) / n) * price.w;
        if (i === 0) {
          ctx.textAlign = "left";
          x = plotLeft;
        } else if (i === n - 1) {
          ctx.textAlign = "right";
          x = plotRight;
        } else {
          ctx.textAlign = "center";
          const approxHalf = Math.min(48, label.length * 3.4);
          x = Math.min(plotRight - approxHalf, Math.max(plotLeft + approxHalf, x));
        }
        ctx.fillText(label, x, volume.y + volume.h + 6);
      }
    }
    ctx.restore();
  }

  function drawKlineChart(ctx, layout, items, state, colors, hoverIndex) {
    const n = items.length;
    if (!n) return;
    const viewStart = state.viewStart || 0;

    const maFull = state.maFull || {};
    const maVisible = {};
    for (const line of MA_LINES) {
      maVisible[line.key] = (maFull[line.key] || []).slice(viewStart, viewStart + n);
    }

    const highs = items.map((d) => Number(d.high)).filter(Number.isFinite);
    const lows = items.map((d) => Number(d.low)).filter(Number.isFinite);
    const maNums = [];
    for (const line of MA_LINES) {
      const vals = maVisible[line.key] || [];
      for (let i = 0; i < vals.length; i += 1) {
        const v = maPoint(vals, i);
        if (v != null) maNums.push(v);
      }
    }
    const lo = Math.min(...lows, ...(maNums.length ? maNums : lows));
    const hi = Math.max(...highs, ...(maNums.length ? maNums : highs));
    const { price, volume } = layout;
    const priceScale = buildPriceScale(lo, hi, {
      tickCount: priceScaleTickCount(price.h),
      padRatio: 0.02,
    });
    const vols = items.map((d) => Number(d.volume) || 0);
    const maxVol = Math.max(...vols, 1);
    const slot = price.w / n;
    const bodyW = Math.max(2, Math.min(14, slot * 0.62));
    const xAt = (i) => price.x + (i + 0.5) * slot;
    const yAt = (p) =>
      price.y + ((priceScale.max - p) / (priceScale.max - priceScale.min || 1)) * price.h;

    const yTicks = (priceScale.ticks || []).map(yAt);
    const xTicks = [0, 0.5, 1].map((t) => price.x + price.w * t);
    drawGrid(ctx, price, yTicks, xTicks, colors);
    drawGrid(ctx, volume, [volume.y, volume.y + volume.h], xTicks, colors);

    for (let i = 0; i < n; i += 1) {
      const d = items[i];
      const o = Number(d.open);
      const c = Number(d.close);
      const h = Number(d.high);
      const l = Number(d.low);
      if (![o, c, h, l].every(Number.isFinite)) continue;
      const up = c >= o;
      const color = up ? colors.up : colors.down;
      const soft = up ? colors.upSoft : colors.downSoft;
      const x = xAt(i);

      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, yAt(h));
      ctx.lineTo(x, yAt(l));
      ctx.stroke();

      const y1 = yAt(Math.max(o, c));
      const y2 = yAt(Math.min(o, c));
      const bh = Math.max(1, y2 - y1);
      if (up) ctx.strokeRect(x - bodyW / 2, y1, bodyW, bh);
      else ctx.fillRect(x - bodyW / 2, y1, bodyW, bh);

      const vh = (vols[i] / maxVol) * volume.h;
      ctx.fillStyle = soft;
      ctx.fillRect(x - bodyW / 2, volume.y + volume.h - vh, bodyW, vh);
    }

    drawMaLines(ctx, maVisible, yAt, xAt, n);

    if (hoverIndex != null && hoverIndex >= 0 && hoverIndex < n) {
      const x = xAt(hoverIndex);
      ctx.save();
      ctx.strokeStyle = colors.cross;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(x, price.y);
      ctx.lineTo(x, volume.y + volume.h);
      ctx.stroke();
      ctx.restore();
    }

    drawAxesLabels(ctx, layout, priceScale, items, colors);
    return { maFull, maVisible, layout };
  }

  function sourceLabel(source) {
    const s = String(source || "").toLowerCase();
    if (s.includes("tencent") || s.includes("qq") || s === "腾讯") return "腾讯";
    if (s.includes("eastmoney") || s.includes("em") || s === "东财") return "东财";
    return source || "";
  }

  function viewWindow(state) {
    const all = state.allItems || [];
    const total = all.length;
    let size = Number(state.viewSize) || 0;
    if (size <= 0 || size >= total) size = total;
    const maxStart = Math.max(0, total - size);
    const start = Math.min(Math.max(0, Number(state.viewStart) || 0), maxStart);
    return {
      total,
      size,
      maxStart,
      start,
      items: total ? all.slice(start, start + size) : [],
    };
  }

  function fillHover(state, absIndex) {
    const box = state.hoverEl;
    if (!box) return;
    const all = state.allItems || [];
    if (absIndex == null || absIndex < 0 || absIndex >= all.length) {
      box.classList.add("hidden");
      box.setAttribute("aria-hidden", "true");
      box.innerHTML = "";
      return;
    }
    const d = all[absIndex];
    const row = (label, valueHtml, valueCls = "") =>
      `<span class="chart-hover-item"><span class="k">${esc(label)}</span><span class="v ${valueCls}">${valueHtml}</span></span>`;
    let pct = Number(d.pct_chg);
    if (!Number.isFinite(pct) && absIndex > 0) {
      const prevClose = Number(all[absIndex - 1].close);
      const close = Number(d.close);
      if (Number.isFinite(prevClose) && prevClose && Number.isFinite(close)) {
        pct = ((close - prevClose) / prevClose) * 100;
      }
    }
    const closeCls = Number.isFinite(pct) && pct > 0 ? "change-up" : Number.isFinite(pct) && pct < 0 ? "change-down" : "";
    const pctCls = closeCls ? `chart-hover-pct ${closeCls}` : "";
    const pctText = Number.isFinite(pct) ? `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%` : null;
    const maRows = MA_LINES.map((line) => {
      const v = maPoint((state.maFull || {})[line.key] || [], absIndex);
      if (v == null) return "";
      return row(line.label, `<span style="color:${line.color}">${esc(fmtNum(v))}</span>`);
    }).filter(Boolean);
    const rows = [
      row("开盘", esc(fmtNum(d.open))),
      row("最低", esc(fmtNum(d.low))),
      row("最高", esc(fmtNum(d.high))),
      row("收盘", esc(fmtNum(d.close)), closeCls),
      pctText ? row("涨跌幅", esc(pctText), pctCls) : "",
      ...maRows,
      row("成交量", esc(fmtVol(d.volume))),
    ].filter(Boolean);
    box.innerHTML = `<div class="chart-hover-card-rows chart-hover-card-rows--inline"><span class="chart-hover-card-time">${esc(d.time || "")}</span>${rows.join("")}</div>`;
    box.classList.remove("hidden");
    box.setAttribute("aria-hidden", "false");
  }

  function render(state, hoverIndex = null) {
    const canvas = state.canvas;
    const wrap = state.wrap;
    if (!canvas || !wrap) return;
    const dpr = window.devicePixelRatio || 1;
    const cssW = Math.max(320, wrap.clientWidth || 640);
    const cssH = Math.max(240, wrap.clientHeight || 320);
    canvas.width = Math.floor(cssW * dpr);
    canvas.height = Math.floor(cssH * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const colors = chartColors();
    ctx.clearRect(0, 0, cssW, cssH);
    ctx.fillStyle = "rgba(4, 8, 14, 0.15)";
    ctx.fillRect(0, 0, cssW, cssH);

    const win = viewWindow(state);
    state.viewStart = win.start;
    state.viewSize = win.size;
    state.items = win.items;
    if (!win.items.length) return;
    const layout = chartLayout(cssW, cssH);
    state.layout = layout;
    drawKlineChart(ctx, layout, win.items, state, colors, hoverIndex);
    syncScrollBar(state);
    const abs =
      hoverIndex != null && hoverIndex >= 0
        ? win.start + hoverIndex
        : state.allItems.length
          ? state.allItems.length - 1
          : null;
    fillHover(state, abs);
  }

  function pointerIndex(state, evt) {
    const items = state.items || [];
    const canvas = state.canvas;
    if (!canvas || !items.length) return null;
    const rect = canvas.getBoundingClientRect();
    const x = evt.clientX - rect.left;
    const layout = state.layout || chartLayout(rect.width, rect.height);
    if (x < layout.price.x || x > layout.price.x + layout.price.w) return null;
    const t = (x - layout.price.x) / layout.price.w;
    return Math.min(items.length - 1, Math.max(0, Math.floor(t * items.length)));
  }

  function setViewStart(state, nextStart, hoverIndex = null) {
    const win = viewWindow(state);
    const start = Math.min(Math.max(0, Math.round(nextStart)), win.maxStart);
    state.viewStart = start;
    render(state, hoverIndex);
  }

  function zoomViewport(state, anchorRatio, factor) {
    const total = (state.allItems || []).length;
    if (total <= 1) return;
    const win = viewWindow(state);
    const minSize = Math.min(total, 20);
    const ratio = Math.min(1, Math.max(0, Number(anchorRatio) || 0.5));
    let nextSize = Math.round(win.size * factor);
    nextSize = Math.max(minSize, Math.min(total, nextSize));
    if (nextSize === win.size) return;
    const anchorIndex = win.start + ratio * win.size;
    let nextStart = Math.round(anchorIndex - ratio * nextSize);
    nextStart = Math.max(0, Math.min(nextStart, total - nextSize));
    state.viewSize = nextSize;
    state.viewStart = nextStart;
    render(state);
  }

  async function loadDayKline(code) {
    if (klineCache.has(code)) return klineCache.get(code);
    const pending = fetch(
      `/api/stocks/line?code=${encodeURIComponent(code)}&period=day&adjust=qfq&limit=${FETCH_LIMIT}`
    )
      .then((res) => res.json())
      .then((json) => {
        if (!json.ok) throw new Error(json.error || "K线加载失败");
        const data = json.data || {};
        return {
          items: data.items || [],
          source: data.source || "",
        };
      })
      .catch((err) => {
        klineCache.delete(code);
        throw err;
      });
    klineCache.set(code, pending);
    return pending;
  }

  function panByPixels(state, dx, canvasWidth) {
    const win = viewWindow(state);
    if (win.maxStart <= 0 || win.size <= 0) return false;
    const layout = chartLayout(canvasWidth, 300);
    const barW = layout.price.w / win.size;
    if (barW <= 0) return false;
    const deltaBars = Math.round(-dx / barW);
    if (!deltaBars) return false;
    setViewStart(state, state.viewStart + deltaBars);
    return true;
  }

  function syncScrollBar(state) {
    const bar = state.scrollBar;
    const wrap = state.scrollWrap;
    if (!bar) return;
    const { maxStart, start, total, size } = viewWindow(state);
    const canScroll = total > size && maxStart > 0;
    if (wrap) wrap.classList.toggle("is-disabled", !canScroll);
    bar.disabled = !canScroll;
    bar.min = "0";
    bar.max = String(Math.max(0, maxStart));
    bar.value = String(start);
    const ratio = total > 0 ? Math.min(1, size / total) : 1;
    const thumbPx = Math.max(28, Math.round(48 + ratio * 72));
    bar.style.setProperty("--thumb-w", `${thumbPx}px`);
  }

  function bind(state) {
    const canvas = state.canvas;
    const wrap = state.wrap;
    let hoverIdx = null;
    let pan = null;

    if (state.scrollBar) {
      state.scrollBar.addEventListener("input", () => {
        hoverIdx = null;
        setViewStart(state, Number(state.scrollBar.value) || 0);
      });
      state.scrollBar.addEventListener("click", (evt) => evt.stopPropagation());
    }

    const onMove = (evt) => {
      if (pan) {
        const dx = evt.clientX - pan.lastX;
        if (Math.abs(evt.clientX - pan.originX) > 4) pan.moved = true;
        if (pan.moved && Math.abs(dx) >= 1) {
          hoverIdx = null;
          panByPixels(state, dx, pan.width);
          pan.lastX = evt.clientX;
        }
        return;
      }
      const idx = pointerIndex(state, evt);
      if (idx === hoverIdx) return;
      hoverIdx = idx;
      render(state, idx);
    };

    const onLeave = () => {
      if (pan) return;
      hoverIdx = null;
      render(state, null);
    };

    const onDown = (evt) => {
      if (evt.button != null && evt.button !== 0) return;
      evt.preventDefault();
      const rect = canvas.getBoundingClientRect();
      pan = {
        originX: evt.clientX,
        lastX: evt.clientX,
        width: rect.width,
        moved: false,
      };
      wrap?.classList.add("is-panning");
      try {
        canvas.setPointerCapture(evt.pointerId);
      } catch {
        /* ignore */
      }
    };

    const onUp = (evt) => {
      if (!pan) return;
      const wasPan = pan.moved;
      pan = null;
      wrap?.classList.remove("is-panning");
      try {
        canvas.releasePointerCapture(evt.pointerId);
      } catch {
        /* ignore */
      }
      if (!wasPan) {
        hoverIdx = pointerIndex(state, evt);
        render(state, hoverIdx);
      } else {
        hoverIdx = null;
        render(state);
      }
    };

    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointercancel", onUp);
    canvas.addEventListener("pointerleave", onLeave);

    canvas.addEventListener(
      "wheel",
      (evt) => {
        const win = viewWindow(state);
        if (!win.total) return;
        evt.preventDefault();
        evt.stopPropagation();
        hoverIdx = null;
        const rect = canvas.getBoundingClientRect();
        const layout = chartLayout(rect.width, rect.height);
        const x = evt.clientX - rect.left;
        let anchorRatio = 0.5;
        if (x >= layout.price.x && x <= layout.price.x + layout.price.w) {
          anchorRatio = (x - layout.price.x) / layout.price.w;
        }
        if (Math.abs(evt.deltaX) > Math.abs(evt.deltaY) * 1.15) {
          if (win.maxStart <= 0) return;
          const step = Math.max(1, Math.round(Math.abs(evt.deltaX) / 40));
          setViewStart(state, win.start + (evt.deltaX > 0 ? step : -step));
          return;
        }
        const steps = Math.max(1, Math.min(5, Math.round(Math.abs(evt.deltaY) / 72) || 1));
        const base = evt.deltaY > 0 ? 1.14 : 1 / 1.14;
        zoomViewport(state, anchorRatio, base ** steps);
      },
      { passive: false }
    );
    if (typeof ResizeObserver !== "undefined" && wrap) {
      let timer = 0;
      state.ro = new ResizeObserver(() => {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => render(state, hoverIdx), 60);
      });
      state.ro.observe(wrap);
    }
  }

  function mount(cardEl, { code, carousel } = {}) {
    if (!cardEl || !code) return;
    if (views.has(cardEl)) {
      const prev = views.get(cardEl);
      prev.carousel = !!carousel;
      render(prev);
      return;
    }
    const canvas = cardEl.querySelector("canvas");
    const wrap = cardEl.querySelector(".chart-canvas-wrap");
    const hoverEl = cardEl.querySelector(".chart-kline-hover");
    const metaEl = cardEl.querySelector(".chart-card__meta");
    const emptyEl = cardEl.querySelector(".chart-empty");
    const scrollBar = cardEl.querySelector(".chart-scroll-bar");
    const scrollWrap = cardEl.querySelector(".chart-axis-scroll");
    const state = {
      cardEl,
      canvas,
      wrap,
      hoverEl,
      metaEl,
      emptyEl,
      scrollBar,
      scrollWrap,
      carousel: !!carousel,
      allItems: [],
      items: [],
      viewSize: VIEW_SIZE,
      viewStart: 0,
      layout: null,
    };
    views.set(cardEl, state);
    bind(state);
    if (metaEl) metaEl.textContent = "加载中…";
    if (emptyEl) {
      emptyEl.textContent = "正在加载日K…";
      emptyEl.classList.remove("hidden");
    }
    loadDayKline(code)
      .then((pack) => {
        state.allItems = pack.items || [];
        const closes = state.allItems.map((d) => Number(d.close));
        state.maFull = {};
        for (const line of MA_LINES) {
          state.maFull[line.key] = computeSmaSeries(closes, line.period);
        }
        const total = state.allItems.length;
        state.viewSize = VIEW_SIZE;
        state.viewStart = Math.max(0, total - (VIEW_SIZE < total ? VIEW_SIZE : total));
        if (emptyEl) emptyEl.classList.toggle("hidden", total > 0);
        if (metaEl) {
          const src = sourceLabel(pack.source);
          metaEl.textContent = src ? `日K · 前复权 · ${src}` : "日K · 前复权";
        }
        render(state);
      })
      .catch((err) => {
        if (emptyEl) {
          emptyEl.textContent = err.message || "暂无走势数据";
          emptyEl.classList.remove("hidden");
        }
        if (metaEl) metaEl.textContent = "加载失败";
      });
  }

  window.OrbitKline = { mount, VIEW_SIZE };
})();
