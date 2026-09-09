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
