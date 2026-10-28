"""个股日线局部极值点（波峰 / 波谷）检测。

把日线图看作离散函数 ``P(t)``（默认收盘价），找出所有局部极大 / 极小值点，
并经过平台压缩、prominence（突出度）过滤、距离约束与交替性修正，只保留有交易
意义的波峰 / 波谷。

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


def _compress_plateaus(values: list[float]) -> tuple[list[float], list[int]]:
    """压缩连续相等值，返回压缩序列与原始索引映射。"""
    if not values:
        return [], []
    out: list[float] = [values[0]]
    idx: list[int] = [0]
    for i in range(1, len(values)):
        if values[i] != values[i - 1]:
            out.append(values[i])
            idx.append(i)
    return out, idx


def _prominence(series: list[float], i: int, kind: str) -> float:
    """计算位置 i 的突出度（peak: 向下突出；trough: 向上突出）。"""
    n = len(series)
    if i <= 0 or i >= n - 1:
        return 0.0
    # 找左右最近的 >=（peak）/ <=（trough）边界
    if kind == "peak":
        left = i - 1
        while left >= 0 and series[left] < series[i]:
            left -= 1
        right = i + 1
        while right < n and series[right] < series[i]:
            right += 1
        left_min = min(series[left + 1:i]) if left + 1 <= i - 1 else series[i]
        right_min = min(series[i + 1:right]) if i + 1 <= right - 1 else series[i]
        base = max(left_min, right_min)
        return float(series[i] - base)
    # trough
    left = i - 1
    while left >= 0 and series[left] > series[i]:
        left -= 1
    right = i + 1
    while right < n and series[right] > series[i]:
        right += 1
    left_max = max(series[left + 1:i]) if left + 1 <= i - 1 else series[i]
    right_max = max(series[i + 1:right]) if i + 1 <= right - 1 else series[i]
    base = min(left_max, right_max)
    return float(base - series[i])


def compute_local_extrema(
    bars: list[dict[str, Any]],
    *,
    series: str = "close",
    w: int = 5,
    prominence: float | None = None,
    prominence_pct: float | None = None,
    min_distance: int = 3,
    smooth_window: int = 1,
    include_endpoints: bool = True,
) -> dict[str, Any]:
    """在已排序日线序列上检测局部极值点（纯函数，便于单测）。

    返回 ``{"series", "values", "extrema": [...]}``。
    """
    if not bars:
        raise ValueError("无日线数据")
    if series not in SERIES_OPTIONS:
        raise ValueError(f"不支持的序列 {series!r}，可选 {SERIES_OPTIONS}")

    ordered = sorted(bars, key=_bar_date)
    raw_values = _extract_series(ordered, series)
    # nan 清理：用前值填充
    values: list[float] = []
    last: float | None = None
    for v in raw_values:
        if v != v:  # nan
            values.append(last if last is not None else 0.0)
        else:
            values.append(v)
            last = v

    smoothed = _smooth(values, smooth_window)

    # 平台压缩
    comp, idx_map = _compress_plateaus(smoothed)

    # Pivot 检测
    raw: list[tuple[str, int, float]] = []
    n = len(comp)
    for i in range(n):
        if i < w or i >= n - w:
            continue
        left = comp[i - w:i]
        right = comp[i + 1:i + w + 1]
        neigh = left + right
        if comp[i] >= max(neigh) and any(comp[i] > x for x in neigh):
            raw.append(("peak", i, comp[i]))
        if comp[i] <= min(neigh) and any(comp[i] < x for x in neigh):
            raw.append(("trough", i, comp[i]))

    # 端点：若为全局极值，则作为候选
    if include_endpoints and n >= 2:
        if comp[0] == max(comp):
            raw.append(("peak", 0, comp[0]))
        if comp[0] == min(comp):
            raw.append(("trough", 0, comp[0]))
        if comp[-1] == max(comp):
            raw.append(("peak", n - 1, comp[-1]))
        if comp[-1] == min(comp):
            raw.append(("trough", n - 1, comp[-1]))

    # prominence 过滤
    if prominence is not None:
        kept: list[tuple[str, int, float]] = []
        for kind, i, price in raw:
            if _prominence(comp, i, kind) >= prominence:
                kept.append((kind, i, price))
        raw = kept
    if prominence_pct is not None:
        kept = []
        for kind, i, price in raw:
            p = _prominence(comp, i, kind)
            base = abs(price) if price != 0 else 1.0
            if (p / base * 100.0) >= prominence_pct:
                kept.append((kind, i, price))
        raw = kept

    # 距离约束
    raw_sorted = sorted(raw, key=lambda x: x[1])
    filtered: list[tuple[str, int, float]] = []
    for kind, i, price in raw_sorted:
        if filtered and filtered[-1][0] == kind and (i - filtered[-1][1]) < min_distance:
            last_kind, last_i, last_price = filtered[-1]
            if (kind == "peak" and price > last_price) or (kind == "trough" and price < last_price):
                filtered[-1] = (kind, i, price)
        else:
            filtered.append((kind, i, price))

    # 交替性修正
    alt: list[tuple[str, int, float]] = []
    for item in filtered:
        if alt and alt[-1][0] == item[0]:
            if (item[0] == "peak" and item[2] > alt[-1][2]) or (
                item[0] == "trough" and item[2] < alt[-1][2]
            ):
                alt[-1] = item
        else:
            alt.append(item)

    # 组装输出
    extrema: list[dict[str, Any]] = []
    for kind, ci, _ in alt:
        orig_i = idx_map[ci]
        bar = ordered[orig_i]
        prom = _prominence(comp, ci, kind)
        # 成交量相对均量（可选）
        vol_ratio = None
        vol = to_float(bar.get("volume"))
        if vol is not None:
            window_vols = []
            for j in range(max(0, orig_i - 20), orig_i):
                vj = to_float(ordered[j].get("volume"))
                if vj is not None:
                    window_vols.append(vj)
            if window_vols:
                avg = sum(window_vols) / len(window_vols)
                if avg > 0:
                    vol_ratio = round(vol / avg, 4)
        is_endpoint = ci == 0 or ci == n - 1
        extrema.append(
            {
                "type": kind,
                "label": "波峰" if kind == "peak" else "波谷",
                "compressed_index": ci,
                "index": orig_i,
                "date": _bar_date(bar),
                "price": values[orig_i],
                "smoothed_price": comp[ci],
                "prominence": round(prom, 6),
                "prominence_pct": round(prom / abs(comp[ci]) * 100.0, 4) if comp[ci] != 0 else None,
                "endpoint": is_endpoint,
                "volume_ratio": vol_ratio,
            }
        )

    # 派生指标
    peaks = [e for e in extrema if e["type"] == "peak"]
    troughs = [e for e in extrema if e["type"] == "trough"]
    bands: list[dict[str, Any]] = []
    # 交替配对：谷->峰 或 峰->谷
    for a, b in zip(extrema, extrema[1:]):
        if a["type"] != b["type"]:
            amp = b["price"] - a["price"]
            bands.append(
                {
                    "from": a["date"],
                    "to": b["date"],
                    "from_type": a["type"],
                    "to_type": b["type"],
                    "amplitude": round(amp, 6),
                    "amplitude_pct": round(amp / a["price"] * 100.0, 4) if a["price"] else None,
                    "days": b["index"] - a["index"],
                }
            )

    return {
        "series": series,
        "series_label": SERIES_LABELS.get(series, series),
        "smooth_window": smooth_window,
        "w": w,
        "min_distance": min_distance,
        "extrema_count": len(extrema),
        "peak_count": len(peaks),
        "trough_count": len(troughs),
        "extrema": extrema,
        "bands": bands,
        "first": extrema[0] if extrema else None,
        "last": extrema[-1] if extrema else None,
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
    w: int = 5,
    prominence: float | None = None,
    prominence_pct: float | None = None,
    min_distance: int = 3,
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
        w=w,
        prominence=prominence,
        prominence_pct=prominence_pct,
        min_distance=min_distance,
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
