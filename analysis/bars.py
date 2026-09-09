"""K 线 bar 解析与辅助计算。"""

from __future__ import annotations

import statistics
from typing import Any

from analysis._path import ensure_backend_path

ensure_backend_path()

from core.fmt import to_float


def normalize_date(value: Any) -> str:
    """YYYY-MM-DD。"""
    text = str(value or "").strip().replace("/", "-")
    if len(text) >= 10:
        return text[:10]
    compact = text.replace("-", "")
    if len(compact) == 8 and compact.isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    return text


def parse_bars(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """清洗 K 线，保证按时间升序，并补振幅。"""
    bars: list[dict[str, Any]] = []
    for raw in items:
        close = to_float(raw.get("close"))
        if close is None:
            continue
        high = to_float(raw.get("high"))
        low = to_float(raw.get("low"))
        open_ = to_float(raw.get("open"))
        volume = to_float(raw.get("volume"))
        pct_chg = to_float(raw.get("pct_chg"))
        amplitude = to_float(raw.get("amplitude"))
        if amplitude is None and high is not None and low is not None and close:
            amplitude = round((high - low) / close * 100, 4)
        bars.append(
            {
                "date": normalize_date(raw.get("time")),
                "open": open_,
                "close": close,
                "high": high,
                "low": low,
                "volume": volume,
                "pct_chg": pct_chg,
                "amplitude": amplitude,
            }
        )
    bars.sort(key=lambda b: b["date"])
    return bars


def find_bar_index(bars: list[dict[str, Any]], date: str) -> int | None:
    target = normalize_date(date)
    for idx, bar in enumerate(bars):
        if bar["date"] == target:
            return idx
    return None


def moving_average(bars: list[dict[str, Any]], idx: int, window: int = 5) -> float | None:
    if idx < 0 or window <= 0:
        return None
    start = max(0, idx - window + 1)
    closes = [b["close"] for b in bars[start : idx + 1] if b.get("close") is not None]
    if not closes:
        return None
    return sum(closes) / len(closes)


def slice_segment(bars: list[dict[str, Any]], start: int, end: int) -> list[dict[str, Any]]:
    if start > end or start < 0:
        return []
    return bars[start : end + 1]


def segment_stats(segment: list[dict[str, Any]]) -> dict[str, Any]:
    if not segment:
        return {
            "days": 0,
            "start_date": "",
            "end_date": "",
            "total_pct": None,
            "range_pct": None,
            "volatility": None,
            "avg_amplitude": None,
        }

    closes = [b["close"] for b in segment if b.get("close") is not None]
    highs = [b["high"] for b in segment if b.get("high") is not None]
    lows = [b["low"] for b in segment if b.get("low") is not None]
    pcts = [b["pct_chg"] for b in segment if b.get("pct_chg") is not None]
    amps = [b["amplitude"] for b in segment if b.get("amplitude") is not None]

    total_pct = None
    if len(closes) >= 2 and closes[0]:
        total_pct = round((closes[-1] / closes[0] - 1.0) * 100, 2)

    range_pct = None
    if highs and lows and closes:
        avg_close = sum(closes) / len(closes)
        if avg_close:
            range_pct = round((max(highs) - min(lows)) / avg_close * 100, 2)

    volatility = round(statistics.pstdev(pcts), 2) if len(pcts) >= 2 else None
    avg_amplitude = round(sum(amps) / len(amps), 2) if amps else None

    return {
        "days": len(segment),
        "start_date": segment[0]["date"],
        "end_date": segment[-1]["date"],
        "total_pct": total_pct,
        "range_pct": range_pct,
        "volatility": volatility,
        "avg_amplitude": avg_amplitude,
        "high": max(highs) if highs else None,
        "low": min(lows) if lows else None,
    }


def linear_slope(values: list[float]) -> float | None:
    """简单线性回归斜率（按索引为 x）。"""
    n = len(values)
    if n < 2:
        return None
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den == 0:
        return None
    return num / den


def mean_volume(segment: list[dict[str, Any]]) -> float | None:
    vols = [b["volume"] for b in segment if b.get("volume") is not None and b["volume"] > 0]
    if not vols:
        return None
    return sum(vols) / len(vols)


def _round_price(value: Any, digits: int = 3) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def build_sparkline(
    bars: list[dict[str, Any]],
    limit_up_idx: int,
    phases: dict[str, Any],
    *,
    pad_before: int,
    pad_after: int,
    max_bars: int,
    ma_warmup: int = 0,
) -> dict[str, Any]:
    """截一段日 K 给前端画走势；下标相对切片。ma_warmup 供均线预热，不计入 max_bars。"""
    empty = {
        "bars": [],
        "warmup": 0,
        "decline": [None, None],
        "consolidation": [None, None],
        "limit_up": None,
    }
    if not bars or limit_up_idx < 0 or limit_up_idx >= len(bars):
        return empty

    cons = phases.get("consolidation") or {}
    dec = phases.get("decline") or {}
    dec_start = int(dec.get("start", -1))
    cons_start = int(cons.get("start", -1))

    start = dec_start if dec_start >= 0 else cons_start
    if start < 0:
        start = max(0, limit_up_idx - max(20, max_bars // 2))
    else:
        start = max(0, start - max(0, pad_before))
    end = min(len(bars) - 1, limit_up_idx + max(0, pad_after))
    min_lookback = min(max_bars - (end - limit_up_idx), max_bars)
    start = min(start, max(0, limit_up_idx - max(0, min_lookback - 1)))
    if end - start + 1 > max_bars:
        start = max(0, end - max_bars + 1)

    warmup = max(0, int(ma_warmup or 0))
    warm_start = max(0, start - warmup)
    warmup = start - warm_start

    slice_bars = bars[warm_start : end + 1]
    compact: list[list[Any]] = []
    for bar in slice_bars:
        vol = bar.get("volume")
        try:
            vol_i = int(vol) if vol else 0
        except (TypeError, ValueError):
            vol_i = 0
        compact.append(
            [
                bar.get("date") or "",
                _round_price(bar.get("open")),
                _round_price(bar.get("high")),
                _round_price(bar.get("low")),
                _round_price(bar.get("close")),
                vol_i,
            ]
        )

    def rel(idx: Any) -> int | None:
        try:
            raw = int(idx)
        except (TypeError, ValueError):
            return None
        if raw < 0:
            return None
        pos = raw - warm_start
        if 0 <= pos < len(compact):
            return pos
        return None

    return {
        "bars": compact,
        "warmup": warmup,
        "decline": [rel(dec.get("start", -1)), rel(dec.get("end", -1))],
        "consolidation": [rel(cons.get("start", -1)), rel(cons.get("end", -1))],
        "limit_up": rel(limit_up_idx),
    }
