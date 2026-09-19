"""真实波幅。用 SMA，便于回放复现。"""

from __future__ import annotations

from typing import Any

from analysis.livermore.config import ATR_WINDOW


def true_range(bar: dict[str, Any], prev_close: float | None) -> float | None:
    high = bar.get("high")
    low = bar.get("low")
    if high is None or low is None:
        return None
    span = float(high) - float(low)
    if prev_close is None:
        return span
    return max(span, abs(float(high) - prev_close), abs(float(low) - prev_close))


def atr_series(bars: list[dict[str, Any]], window: int = ATR_WINDOW) -> list[float | None]:
    """与 bars 等长。前 window-1 根为 None。"""
    out: list[float | None] = [None] * len(bars)
    if window <= 0 or len(bars) < 2:
        return out
    trs: list[float] = []
    prev = bars[0].get("close")
    for i, bar in enumerate(bars):
        if i == 0:
            tr = true_range(bar, None)
        else:
            tr = true_range(bar, float(prev) if prev is not None else None)
            prev = bar.get("close")
        if tr is None:
            out[i] = out[i - 1] if i else None
            continue
        trs.append(tr)
        if len(trs) < window:
            continue
        window_trs = trs[-window:]
        out[i] = sum(window_trs) / len(window_trs)
    return out


def last_atr(bars: list[dict[str, Any]], window: int = ATR_WINDOW) -> float | None:
    series = atr_series(bars, window)
    for value in reversed(series):
        if value is not None and value > 0:
            return float(value)
    return None
