"""个股日线局部极值点（波峰 / 波谷）检测（多层）。

规则（朴素相邻比较，允许相等）：

- **波峰**：某日价格大于等于左右相邻各一个交易日；
- **波谷**：某日价格小于等于左右相邻各一个交易日。

端点只检测一侧。

对每个极值点，额外记录它「作为极值」向左右各延续了多少个交易日：

- 波峰向左 / 向右，连续多少个交易日价格都不更高，直到遇到一个严格更高
  的交易日为止；
- 波谷向左 / 向右，连续多少个交易日价格都不更低，直到遇到一个严格更低
  的交易日为止。

即 ``left_span`` / ``right_span`` 表示该极值在左右两侧「覆盖」的天数，
``span_days = left_span + 1 + right_span``。

多层：
- 第一层：在日线序列上找出所有峰值 / 谷值，按时间排序，合并连续同类型
  极值（峰取最高、谷取最低）。
- 后续层：将上一层得到的峰值序列与谷值序列分别作为两个序列，继续找出
  极值，合并回一个序列并合并连续同类型极值。
- 最终输出峰值 / 谷值严格交替的序列。

日线数据走系统现有 ``company.line.fetcher.fetch_kline``（前复权）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float

from company.analysis.line.extremum.service import _bar_date, _iso


SERIES_OPTIONS: tuple[str, ...] = ("open", "close", "high", "low", "ohlc4")
SERIES_LABELS: dict[str, str] = {
    "open": "开盘价",
    "close": "收盘价",
    "high": "最高价",
    "low": "最低价",
    "ohlc4": "OHLC4 均价",
}


def _resolve_layers(
    layers: Any = None,
    level: Any = None,
    levels: Any = None,
    depth: Any = None,
    layer_count: Any = None,
    n_layers: Any = None,
    num_layers: Any = None,
    layer: Any = None,
    **_ignored: Any,
) -> int:
    for v in (layers, level, levels, depth, layer_count, n_layers, num_layers, layer):
        if v is None:
            continue
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n < 1:
            n = 1
        return n
    return 1


def _extract_series(bars: list[dict[str, Any]], series: str) -> list[float]:
    out: list[float] = []
    for bar in bars:
        if series == "ohlc4":
            vals = [to_float(bar.get(f)) for f in ("open", "high", "low", "close")]
            vals = [v for v in vals if v is not None]
            if not vals:
                out.append(float("nan"))
                continue
            out.append(sum(vals) / len(vals))
        else:
            v = to_float(bar.get(series))
            out.append(v if v is not None else float("nan"))
    return out


def _smooth(values: list[float], window: int) -> list[float]:
    if window is None or window <= 1:
        return list(values)
    n = len(values)
    out: list[float] = []
    half = window // 2
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        chunk = [x for x in values[lo:hi] if x == x]
        out.append(sum(chunk) / len(chunk) if chunk else values[i])
    return out


def _clean_nan(values: list[float]) -> list[float]:
    out: list[float] = []
    last: float | None = None
    for v in values:
        if v != v:
            out.append(last if last is not None else 0.0)
        else:
            out.append(v)
            last = v
    return out


def _strict_neighbor_bounds(values: list[float]) -> tuple[list[int], list[int], list[int], list[int]]:
    """一次预处理：每个位置左侧/右侧最近的严格更大、严格更小下标。

    语义对齐朴素 span 扫描：
    - 波峰 left/right_span = 到最近严格更高点之间的距离（不含该更高点）；
    - 波谷同理对应严格更低点。
    单调栈四趟，总 O(n)，避免每个极值点各自向左右扫描的 O(n²)。
    """
    n = len(values)
    prev_gt = [-1] * n
    next_gt = [n] * n
    prev_lt = [-1] * n
    next_lt = [n] * n

    stack: list[int] = []
    for i in range(n):
        while stack and values[stack[-1]] <= values[i]:
            stack.pop()
        prev_gt[i] = stack[-1] if stack else -1
        stack.append(i)

    stack = []
    for i in range(n - 1, -1, -1):
        while stack and values[stack[-1]] <= values[i]:
            stack.pop()
        next_gt[i] = stack[-1] if stack else n
        stack.append(i)

    stack = []
    for i in range(n):
        while stack and values[stack[-1]] >= values[i]:
            stack.pop()
        prev_lt[i] = stack[-1] if stack else -1
        stack.append(i)

    stack = []
    for i in range(n - 1, -1, -1):
        while stack and values[stack[-1]] >= values[i]:
            stack.pop()
        next_lt[i] = stack[-1] if stack else n
        stack.append(i)

    return prev_gt, next_gt, prev_lt, next_lt


def _find_extrema_points(values: list[float]) -> list[dict[str, Any]]:
    """相邻比较（允许相等），含端点一侧检测。返回含 idx/type/price/spans 的列表。"""
    n = len(values)
    hits: list[dict[str, Any]] = []
    if n < 2:
        return hits

    prev_gt, next_gt, prev_lt, next_lt = _strict_neighbor_bounds(values)

    for i in range(n):
        is_peak = False
        is_trough = False
        if i == 0:
            if values[0] >= values[1]:
                is_peak = True
            if values[0] <= values[1]:
                is_trough = True
        elif i == n - 1:
            if values[-1] >= values[-2]:
                is_peak = True
            if values[-1] <= values[-2]:
                is_trough = True
        else:
            cur, prev, nxt = values[i], values[i - 1], values[i + 1]
            if cur >= prev and cur >= nxt:
                is_peak = True
            if cur <= prev and cur <= nxt:
                is_trough = True
        # 平台/相等：峰优先
        if is_peak and is_trough:
            is_trough = False
        if not (is_peak or is_trough):
            continue
        kind = "peak" if is_peak else "trough"
        if kind == "peak":
            left = i - prev_gt[i] - 1
            right = next_gt[i] - i - 1
        else:
            left = i - prev_lt[i] - 1
            right = next_lt[i] - i - 1
        hits.append(
            {
                "idx": i,
                "type": kind,
                "price": values[i],
                "left_span": left,
                "right_span": right,
                "span_days": left + 1 + right,
            }
        )
    return hits


def _merge_consecutive(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(points, key=lambda x: x.get("index", x.get("idx", 0)))
    alt: list[dict[str, Any]] = []
    for x in ordered:
        item = dict(x)
        if alt and alt[-1]["type"] == item["type"]:
            more_extreme = (
                (item["type"] == "peak" and item["price"] > alt[-1]["price"])
                or (item["type"] == "trough" and item["price"] < alt[-1]["price"])
            )
            if more_extreme:
                alt[-1] = item
        else:
            alt.append(item)
    return alt


def _to_extrema_points(
    ordered: list[dict[str, Any]],
    detect_series: list[float],
    values: list[float],
    hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    extrema: list[dict[str, Any]] = []
    for pt in hits:
        i = pt["idx"]
        bar = ordered[i]
        vol_ratio = None
        vol = to_float(bar.get("volume"))
        if vol is not None:
            window_vols = []
            for j in range(max(0, i - 20), i):
                vj = to_float(ordered[j].get("volume"))
                if vj is not None:
                    window_vols.append(vj)
            if window_vols:
                avg = sum(window_vols) / len(window_vols)
                if avg > 0:
                    vol_ratio = round(vol / avg, 4)
        point = {
            "type": pt["type"],
            "label": "波峰" if pt["type"] == "peak" else "波谷",
            "date": _bar_date(bar),
            "price": values[i],
            "index": i,
            "left_span": pt["left_span"],
            "right_span": pt["right_span"],
            "span_days": pt["span_days"],
            "volume_ratio": vol_ratio,
        }
        extrema.append(point)
    return extrema


def _layer_once(seq: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """对上一层序列做一次分层：按峰值/谷值拆分，分别找极值，合并。"""
    peaks_seq = [p for p in seq if p["type"] == "peak"]
    valleys_seq = [p for p in seq if p["type"] == "trough"]

    new_points: list[dict[str, Any]] = []
    # 峰序列中只保留「峰」（峰中的极大值），谷序列中只保留「谷」（谷中的极小值）。
    # 类型由所属子序列决定，层间不允许峰/谷翻转。
    for subseq, forced_type in ((peaks_seq, "peak"), (valleys_seq, "trough")):
        if not subseq:
            continue
        prices = [p["price"] for p in subseq]
        pts = _find_extrema_points(prices)
        for pt in pts:
            if pt["type"] != forced_type:
                continue
            orig = dict(subseq[pt["idx"]])
            orig["type"] = forced_type
            orig["label"] = "波峰" if forced_type == "peak" else "波谷"
            orig["left_span"] = pt["left_span"]
            orig["right_span"] = pt["right_span"]
            orig["span_days"] = pt["span_days"]
            orig["price"] = subseq[pt["idx"]]["price"]
            new_points.append(orig)

    new_points.sort(key=lambda x: x.get("index", 0))
    return _merge_consecutive(new_points)


def compute_local_extrema(
    bars: list[dict[str, Any]],
    layers: int = 1,
    *,
    series: str = "close",
    smooth_window: int = 1,
    **kw: Any,
) -> dict[str, Any]:
    smooth_alias = kw.pop("smooth", None)
    if smooth_alias is not None:
        smooth_window = int(smooth_alias)
    layers = _resolve_layers(layers, **kw)
    if not bars:
        raise ValueError("无日线数据")
    if series not in SERIES_OPTIONS:
        raise ValueError(f"不支持的序列 {series!r}，可选 {SERIES_OPTIONS}")

    ordered = sorted(bars, key=_bar_date)
    values = _clean_nan(_extract_series(ordered, series))
    detect_series = _smooth(values, smooth_window)

    hits = _find_extrema_points(detect_series)
    extrema = _to_extrema_points(ordered, detect_series, values, hits)

    # raw：不合并；但 layers>1 时按分层处理（最终仍可能含连续同类型，保持 raw 语义不合并）
    seq = extrema
    if layers and layers > 1:
        # 对 raw 序列也做分层，但不强制合并？这里仍合并以与层定义一致
        # 先合并一次作为第一层基底
        seq = _merge_consecutive(list(seq))
        for _ in range(layers - 1):
            seq = _layer_once(seq)

    peak_count = sum(1 for e in seq if e["type"] == "peak")
    trough_count = sum(1 for e in seq if e["type"] == "trough")
    return {
        "series": series,
        "series_label": SERIES_LABELS.get(series, series),
        "smooth_window": smooth_window,
        "layers": layers,
        "extrema_count": len(seq),
        "peak_count": peak_count,
        "trough_count": trough_count,
        "extrema": seq,
    }


def compute_alternating_extrema(
    bars: list[dict[str, Any]],
    layers: int = 1,
    *,
    series: str = "close",
    smooth_window: int = 1,
    **kw: Any,
) -> dict[str, Any]:
    layers = _resolve_layers(layers, **kw)
    if not bars:
        raise ValueError("无日线数据")
    if series not in SERIES_OPTIONS:
        raise ValueError(f"不支持的序列 {series!r}，可选 {SERIES_OPTIONS}")

    ordered = sorted(bars, key=_bar_date)
    values = _clean_nan(_extract_series(ordered, series))
    detect_series = _smooth(values, smooth_window)

    hits = _find_extrema_points(detect_series)
    extrema = _to_extrema_points(ordered, detect_series, values, hits)

    # 第一层：合并连续同类型
    seq = _merge_consecutive(extrema)
    # 后续层
    for _ in range(layers - 1):
        seq = _layer_once(seq)

    peaks = [x for x in seq if x["type"] == "peak"]
    troughs = [x for x in seq if x["type"] == "trough"]
    return {
        "series": series,
        "series_label": SERIES_LABELS.get(series, series),
        "smooth_window": smooth_window,
        "layers": layers,
        "extrema_count": len(seq),
        "peak_count": len(peaks),
        "trough_count": len(troughs),
        "extrema": seq,
    }


# 别名
compute_layered_extrema = compute_alternating_extrema
compute_multilevel_extrema = compute_alternating_extrema
compute_extrema_layers = compute_alternating_extrema
compute_hierarchical_extrema = compute_alternating_extrema


# 通用别名
compute_extrema = compute_alternating_extrema
compute_extremes = compute_alternating_extrema
compute_waves = compute_alternating_extrema

def _today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _fetch_day_range(
    code: str,
    *,
    beg_iso: str,
    end_iso: str,
    adjust: str = "qfq",
) -> dict[str, Any]:
    from company.line.fetcher import fetch_kline

    pack = fetch_kline(
        code,
        period="day",
        adjust=adjust,
        beg=beg_iso.replace("-", ""),
        end=end_iso.replace("-", ""),
        limit=10000,
    )
    items = list(pack.get("items") or [])
    items.sort(key=_bar_date)
    return {
        "code": str(pack.get("code") or code),
        "name": str(pack.get("name") or ""),
        "source": str(pack.get("source") or ""),
        "items": items,
    }


def analyze_local_extrema(
    code: str,
    beg: str,
    end: str = "",
    *,
    series: str = "close",
    smooth_window: int = 1,
    adjust: str = "qfq",
    layers: int = 1,
    **kw: Any,
) -> dict[str, Any]:
    layers = _resolve_layers(layers, **kw)
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    beg_iso = _iso(beg)
    end_iso = _iso(end) if end else _today_iso()
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")

    hist = _fetch_day_range(norm, beg_iso=beg_iso, end_iso=end_iso, adjust=adjust)
    items = list(hist.get("items") or [])
    if not items:
        raise ValueError("无日线数据")
    result = compute_local_extrema(
        items,
        layers=layers,
        series=series,
        smooth_window=smooth_window,
    )

    return {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adjust,
        "beg": beg_iso,
        "end": _bar_date(items[-1]),
        "input_end": end_iso,
        "snapped": (end_iso != _bar_date(items[-1])) if end else False,
        "count": len(items),
        **result,
    }


def analyze_alternating_extrema(
    code: str,
    beg: str,
    end: str = "",
    *,
    series: str = "close",
    smooth_window: int = 1,
    adjust: str = "qfq",
    layers: int = 1,
    **kw: Any,
) -> dict[str, Any]:
    layers = _resolve_layers(layers, **kw)
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    beg_iso = _iso(beg)
    end_iso = _iso(end) if end else _today_iso()
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")

    hist = _fetch_day_range(norm, beg_iso=beg_iso, end_iso=end_iso, adjust=adjust)
    items = list(hist.get("items") or [])
    if not items:
        raise ValueError("无日线数据")
    result = compute_alternating_extrema(
        items,
        layers=layers,
        series=series,
        smooth_window=smooth_window,
    )

    return {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adjust,
        "beg": beg_iso,
        "end": _bar_date(items[-1]),
        "input_end": end_iso,
        "snapped": (end_iso != _bar_date(items[-1])) if end else False,
        "count": len(items),
        **result,
    }


analyze_layered_extrema = analyze_alternating_extrema
analyze_multilevel_extrema = analyze_alternating_extrema
analyze_extrema_layers = analyze_alternating_extrema
analyze_hierarchical_extrema = analyze_alternating_extrema

# analyze ͨ�ñ���
analyze_extrema = analyze_alternating_extrema
analyze_extremes = analyze_alternating_extrema
analyze_waves = analyze_alternating_extrema

