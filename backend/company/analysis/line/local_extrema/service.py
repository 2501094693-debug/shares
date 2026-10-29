"""个股日线局部极值点（波峰 / 波谷）检测。

规则（朴素相邻比较，允许相等）：

- **波峰**：某日价格大于等于左右相邻各一个交易日；
- **波谷**：某日价格小于等于左右相邻各一个交易日。

运行前先**合并连续相同值**（平台只保留一个点），因此 ``1,2,2,2,1`` 只产生
一个波峰，不会把平台里每个等值点都当成极值。

对每个极值点，额外记录它「作为极值」向左右各延续了多少个交易日：

- 波峰向左 / 向右，连续多少个交易日价格都不更高，直到遇到一个严格更高
  的交易日为止；
- 波谷向左 / 向右，连续多少个交易日价格都不更低，直到遇到一个严格更低
  的交易日为止。

即 ``left_span`` / ``right_span`` 表示该极值在左右两侧「覆盖」的天数，
``span_days = left_span + 1 + right_span`` 表示这段极值形态覆盖的总交易日数。

- ``compute_local_extrema``  纯函数：在已排序日线序列上检测极值点
- ``analyze_local_extrema``  主入口：拉取日线并组装结果

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
    """简单移动平均；window<=1 时原样返回。"""
    if window is None or window <= 1:
        return list(values)
    n = len(values)
    out: list[float] = []
    half = window // 2
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        chunk = [x for x in values[lo:hi] if x == x]  # 过滤 nan
        out.append(sum(chunk) / len(chunk) if chunk else values[i])
    return out


def _clean_nan(values: list[float]) -> list[float]:
    """nan 用前值填充（序列首位无前值时用其后第一个有效值或 0）。"""
    out: list[float] = []
    last: float | None = None
    for v in values:
        if v != v:  # nan
            out.append(last if last is not None else 0.0)
        else:
            out.append(v)
            last = v
    return out


def _left_span(series: list[float], i: int, kind: str) -> int:
    """极值点 i 向左连续保持极值的交易日数（允许相等）。

    - peak：左侧连续“不更高”的天数，遇到严格更高停止；
    - trough：左侧连续“不更低”的天数，遇到严格更低停止。
    """
    target = series[i]
    span = 0
    j = i - 1
    if kind == "peak":
        while j >= 0 and series[j] <= target:
            span += 1
            j -= 1
    else:
        while j >= 0 and series[j] >= target:
            span += 1
            j -= 1
    return span


def _right_span(series: list[float], i: int, kind: str) -> int:
    """极值点 i 向右连续保持极值的交易日数（规则同左向）。"""
    target = series[i]
    span = 0
    j = i + 1
    n = len(series)
    if kind == "peak":
        while j < n and series[j] <= target:
            span += 1
            j += 1
    else:
        while j < n and series[j] >= target:
            span += 1
            j += 1
    return span


def _compress_plateaus(series: list[float]) -> tuple[list[float], list[int]]:
    """合并连续相同值（平台）：相同值只保留一个。

    返回 ``(压缩后序列, 每个压缩点对应的原始下标)``。
    代表下标取该段连续相同值中的**第一个**交易日。
    """
    if not series:
        return [], []
    comp: list[float] = [series[0]]
    rep: list[int] = [0]
    for i in range(1, len(series)):
        if series[i] != series[i - 1]:
            comp.append(series[i])
            rep.append(i)
    return comp, rep


def _detect(
    series: list[float],
) -> list[tuple[str, int]]:
    """相邻比较（允许相等）：返回 [(kind, index), ...]，仅内部点。

    - peak：series[i] >= series[i-1] 且 series[i] >= series[i+1]
    - trough：series[i] <= series[i-1] 且 series[i] <= series[i+1]

    注意：``series`` 应是合并平台后的压缩序列（相邻值互不相等），
    此时平台只贡献一个点，不会出现「连续同值都被判为极值」。
    """
    n = len(series)
    hits: list[tuple[str, int]] = []
    for i in range(1, n - 1):
        cur, prev, nxt = series[i], series[i - 1], series[i + 1]
        if cur >= prev and cur >= nxt:
            hits.append(("peak", i))
        elif cur <= prev and cur <= nxt:
            hits.append(("trough", i))
    return hits


def compute_local_extrema(
    bars: list[dict[str, Any]],
    *,
    series: str = "close",
    smooth_window: int = 1,
) -> dict[str, Any]:
    """在已排序日线序列上检测局部极值点（纯函数，便于单测）。

    返回按交易日从远到近排列的单一峰谷序列 ``extrema``，
    每个点包含 ``type`` / ``label`` / ``date`` / ``price`` /
    ``index`` / ``left_span`` / ``right_span`` / ``span_days``。
    """
    if not bars:
        raise ValueError("无日线数据")
    if series not in SERIES_OPTIONS:
        raise ValueError(f"不支持的序列 {series!r}，可选 {SERIES_OPTIONS}")

    ordered = sorted(bars, key=_bar_date)
    values = _clean_nan(_extract_series(ordered, series))
    detect_series = _smooth(values, smooth_window)

    # 算法运行前先合并连续相同值（平台只取一个点）
    comp_values, comp_rep = _compress_plateaus(detect_series)

    hits = _detect(comp_values)

    extrema: list[dict[str, Any]] = []
    for kind, c in hits:
        i = comp_rep[c]  # 压缩点映射回原始交易日下标
        bar = ordered[i]
        left = _left_span(detect_series, i, kind)
        right = _right_span(detect_series, i, kind)

        # 成交量相对前 20 个交易日均量（可选）
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
            "type": kind,
            "label": "波峰" if kind == "peak" else "波谷",
            "date": _bar_date(bar),
            "price": values[i],
            "index": i,
            "left_span": left,
            "right_span": right,
            "span_days": left + 1 + right,
            "volume_ratio": vol_ratio,
        }
        extrema.append(point)

    peak_count = sum(1 for e in extrema if e["type"] == "peak")
    trough_count = sum(1 for e in extrema if e["type"] == "trough")
    return {
        "series": series,
        "series_label": SERIES_LABELS.get(series, series),
        "smooth_window": smooth_window,
        "extrema_count": len(extrema),
        "peak_count": peak_count,
        "trough_count": trough_count,
        "extrema": extrema,
    }


def compute_alternating_extrema(
    bars: list[dict[str, Any]],
    *,
    series: str = "close",
    smooth_window: int = 1,
    **_ignored: Any,
) -> dict[str, Any]:
    """峰谷序列：接收第一接口输出，合并连续出现的同类型极值，
    峰保留价格最高者、谷保留价格最低者，输出峰谷交替序列。

    不进行任何过滤，仅合并连续出现的同类型极值。
    """
    base = compute_local_extrema(bars, series=series, smooth_window=smooth_window)

    merged: list[dict[str, Any]] = [dict(x) for x in base.get("extrema", [])]
    merged.sort(key=lambda x: x["index"])

    # 仅合并连续同类型极值：峰保留价格最高者，谷保留价格最低者
    alt: list[dict[str, Any]] = []
    for x in merged:
        if alt and alt[-1]["type"] == x["type"]:
            more_extreme = (
                (x["type"] == "peak" and x["price"] > alt[-1]["price"])
                or (x["type"] == "trough" and x["price"] < alt[-1]["price"])
            )
            if more_extreme:
                alt[-1] = x
        else:
            alt.append(x)

    peaks = [x for x in alt if x["type"] == "peak"]
    troughs = [x for x in alt if x["type"] == "trough"]
    return {
        "series": series,
        "series_label": SERIES_LABELS.get(series, series),
        "smooth_window": smooth_window,
        "extrema_count": len(alt),
        "peak_count": len(peaks),
        "trough_count": len(troughs),
        "extrema": alt,
    }


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
) -> dict[str, Any]:
    """主入口：个股区间内局部极值点检测（默认前复权日线）。"""
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
    **_ignored: Any,
) -> dict[str, Any]:
    """主入口：个股区间内峰谷序列（合并连续同类型极值，无过滤）。"""
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
