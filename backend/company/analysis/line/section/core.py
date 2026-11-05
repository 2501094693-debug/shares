"""日线段划分：日线 → 最小段 → 同向合并 → 涨跌交替归并为横盘。

- 最小段：相邻两根 K 线 ``[i, i+1]``，两边闭区间；前段终点 == 后段起点。
- 同向合并：连续同方向（涨/跌）的最小段并为一段；flat 视为不改变方向的噪声。
- 横盘：涨跌交替的若干段若整体落在 ``band_pct`` 带宽内，合并为横盘段。

每段带 ``children`` 子段，形成 level 0/1/2 三级树::

    level 0  最小段（相邻交易日）
    level 1  同向合并段（连续涨 / 连续跌）
    level 2  最终段（涨 / 跌 / 横盘），children 为 level 1 段

纯函数，无网络依赖，便于单测。
"""

from __future__ import annotations

from typing import Any

from core.fmt import to_float

DIR_UP = "up"
DIR_DOWN = "down"
DIR_FLAT = "flat"
DIR_LABEL = {DIR_UP: "涨", DIR_DOWN: "跌", DIR_FLAT: "横盘"}

SERIES_OPTIONS: tuple[str, ...] = ("open", "close", "high", "low", "ohlc4")
SERIES_LABELS: dict[str, str] = {
    "open": "开盘价",
    "close": "收盘价",
    "high": "最高价",
    "low": "最低价",
    "ohlc4": "OHLC4 均价",
}


def _bar_date(bar: dict[str, Any]) -> str:
    return str(bar.get("time") or bar.get("date") or "")[:10]


def _sign(change: float) -> str:
    if change > 0:
        return DIR_UP
    if change < 0:
        return DIR_DOWN
    return DIR_FLAT


def _extract_series(bars: list[dict[str, Any]], series: str) -> list[float]:
    out: list[float] = []
    for bar in bars:
        if series == "ohlc4":
            vals = [to_float(bar.get(f)) for f in ("open", "high", "low", "close")]
            vals = [v for v in vals if v is not None]
            out.append(sum(vals) / len(vals) if vals else float("nan"))
        else:
            v = to_float(bar.get(series))
            out.append(v if v is not None else float("nan"))
    return out


def _clean(values: list[float]) -> list[float]:
    out: list[float] = []
    last: float | None = None
    for v in values:
        if v != v:  # nan → 用前值填充
            out.append(last if last is not None else 0.0)
        else:
            out.append(v)
            last = v
    return out


def _prepare(
    bars: list[dict[str, Any]], series: str
) -> tuple[list[dict[str, Any]], list[str], list[float]]:
    ordered = sorted(bars, key=_bar_date)
    dates = [_bar_date(b) for b in ordered]
    values = _clean(_extract_series(ordered, series))
    return ordered, dates, values


def _segment(
    begin: str,
    end: str,
    begin_idx: int,
    end_idx: int,
    begin_price: float,
    end_price: float,
    *,
    level: int,
    children: list[dict[str, Any]] | None = None,
    direction: str | None = None,
) -> dict[str, Any]:
    change = end_price - begin_price
    ratio = (end_price / begin_price - 1.0) if begin_price else 0.0
    d = direction if direction is not None else _sign(change)
    return {
        "begin": begin,
        "end": end,
        "begin_idx": begin_idx,
        "end_idx": end_idx,
        "begin_price": round(begin_price, 6),
        "end_price": round(end_price, 6),
        "direction": d,
        "flag": DIR_LABEL[d],
        "change_price": round(change, 6),
        "change_ratio": round(ratio, 6),
        "change_pct": round(ratio * 100.0, 4),
        "days": end_idx - begin_idx,
        "level": level,
        "children": list(children or []),
    }


def _wrap(
    children: list[dict[str, Any]],
    level: int,
    *,
    direction: str | None = None,
) -> dict[str, Any]:
    first, last = children[0], children[-1]
    return _segment(
        first["begin"],
        last["end"],
        first["begin_idx"],
        last["end_idx"],
        first["begin_price"],
        last["end_price"],
        level=level,
        children=children,
        direction=direction,
    )


def build_minimal_segments(
    bars: list[dict[str, Any]], *, series: str = "close"
) -> list[dict[str, Any]]:
    """阶段 0：相邻两根 K 线为最小段，闭区间共享端点。"""
    _, dates, values = _prepare(bars, series)
    if len(values) < 2:
        raise ValueError("交易日不足两个，无法划分最小段")
    return [
        _segment(
            dates[i],
            dates[i + 1],
            i,
            i + 1,
            values[i],
            values[i + 1],
            level=0,
        )
        for i in range(len(values) - 1)
    ]


def _merge_same_direction(
    minimal: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """阶段 1：连续同方向（含 flat 噪声）合并为一段。"""
    groups: list[list[dict[str, Any]]] = []
    for s in minimal:
        if not groups:
            groups.append([s])
            continue
        g = groups[-1]
        gdir = g[0]["direction"]
        if s["direction"] == DIR_FLAT or s["direction"] == gdir:
            g.append(s)
        else:
            groups.append([s])
    return [_wrap(g, 1) for g in groups]


def _merge_sideways(
    runs: list[dict[str, Any]],
    *,
    band_pct: float,
    min_runs: int,
) -> list[dict[str, Any]]:
    """阶段 2：涨跌交替且整体落在带宽内 → 横盘。"""
    out: list[dict[str, Any]] = []
    i, n = 0, len(runs)
    while i < n:
        cur = runs[i]
        if cur["direction"] == DIR_FLAT:
            out.append(_wrap([cur], 2))
            i += 1
            continue

        begin_price = cur["begin_price"]
        lo = hi = begin_price
        best_end: int | None = None
        j = i
        while j < n and runs[j]["direction"] != DIR_FLAT:
            p = runs[j]["end_price"]
            lo2 = lo if lo <= p else p
            hi2 = hi if hi >= p else p
            if begin_price and (hi2 - lo2) / begin_price > band_pct:
                # range 单调不减，超出带宽后继续加段也不会再是横盘
                break
            lo, hi = lo2, hi2
            if j - i + 1 >= min_runs:
                best_end = j
            j += 1

        if best_end is not None:
            block = runs[i : best_end + 1]
            seg = _wrap(block, 2, direction=DIR_FLAT)
            seg["amplitude_pct"] = round((hi - lo) / begin_price * 100.0, 4)
            out.append(seg)
            i = best_end + 1
        else:
            out.append(_wrap([cur], 2))
            i += 1
    return out


def compute_sections(
    bars: list[dict[str, Any]],
    *,
    series: str = "close",
    band_pct: float = 0.05,
    min_runs: int = 3,
) -> dict[str, Any]:
    """纯函数主入口：日线 → 三级段树。"""
    if not bars:
        raise ValueError("无日线数据")
    if series not in SERIES_OPTIONS:
        raise ValueError(f"不支持的序列 {series!r}，可选 {SERIES_OPTIONS}")
    if band_pct <= 0:
        raise ValueError(f"band_pct 须为正，收到 {band_pct!r}")
    min_runs = max(2, int(min_runs))

    minimal = build_minimal_segments(bars, series=series)
    runs = _merge_same_direction(minimal)
    segments = _merge_sideways(runs, band_pct=band_pct, min_runs=min_runs)

    return {
        "series": series,
        "series_label": SERIES_LABELS.get(series, series),
        "band_pct": band_pct,
        "min_runs": min_runs,
        "bar_count": len(bars),
        "minimal_count": len(minimal),
        "run_count": len(runs),
        "segment_count": len(segments),
        "segments": segments,
    }
