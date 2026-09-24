"""单根日 K 指标：涨跌、最大涨跌幅、实体、影线占比、量能。"""

from __future__ import annotations

from typing import Any

from core.fmt import to_float

VOL_RATIO_WINDOW = 5


def _vol_ratio(bars: list[dict[str, Any]], idx: int, volume: float | None) -> float | None:
    """当日量 / 前 N 日均量（不含当日）。前序不足或均量为 0 时返回 None。"""
    if volume is None or volume < 0 or idx < VOL_RATIO_WINDOW:
        return None
    prior = bars[idx - VOL_RATIO_WINDOW : idx]
    vols = [to_float(b.get("volume")) for b in prior]
    vols = [v for v in vols if v is not None and v > 0]
    if len(vols) < VOL_RATIO_WINDOW:
        return None
    mean = sum(vols) / len(vols)
    if mean <= 0:
        return None
    return round(volume / mean, 4)


def _vol_chg(bars: list[dict[str, Any]], idx: int, volume: float | None) -> float | None:
    """较昨量变化 %：(V / Vprev − 1) × 100。"""
    if volume is None or volume < 0 or idx < 1:
        return None
    prev = to_float(bars[idx - 1].get("volume"))
    if prev is None or prev <= 0:
        return None
    return round((volume / prev - 1.0) * 100.0, 4)


def measure_bar(
    bar: dict[str, Any],
    prev_close: float | None = None,
    *,
    bars: list[dict[str, Any]] | None = None,
    idx: int | None = None,
) -> dict[str, Any] | None:
    """从 OHLC 拆出筛选用指标。缺关键字段或全日跨度为 0 时返回 None。

    传入 bars+idx 时额外计算量比 / 量增幅。
    """
    open_ = to_float(bar.get("open"))
    high = to_float(bar.get("high"))
    low = to_float(bar.get("low"))
    close = to_float(bar.get("close"))
    if open_ is None or high is None or low is None or close is None:
        return None
    if high < low or close <= 0 or open_ <= 0:
        return None

    span = high - low
    if span <= 0:
        return None

    body = abs(close - open_)
    lower = min(open_, close) - low
    upper = high - max(open_, close)
    if lower < 0:
        lower = 0.0
    if upper < 0:
        upper = 0.0

    body_pct = (close - open_) / open_ * 100.0

    prev = to_float(prev_close)
    pct_chg = to_float(bar.get("pct_chg"))
    if pct_chg is None and prev and prev > 0:
        pct_chg = (close / prev - 1.0) * 100.0

    max_gain = None
    max_drop = None
    if prev and prev > 0:
        max_gain = (high / prev - 1.0) * 100.0
        max_drop = (low / prev - 1.0) * 100.0

    volume = to_float(bar.get("volume"))
    vol_ratio = None
    vol_chg = None
    if bars is not None and idx is not None and 0 <= idx < len(bars):
        vol_ratio = _vol_ratio(bars, idx, volume)
        vol_chg = _vol_chg(bars, idx, volume)

    return {
        "date": str(bar.get("date") or ""),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "body_pct": round(body_pct, 4),
        "body_ratio": round(body / span, 4),
        "pct_chg": round(pct_chg, 4) if pct_chg is not None else None,
        "max_gain": round(max_gain, 4) if max_gain is not None else None,
        "max_drop": round(max_drop, 4) if max_drop is not None else None,
        "lower": round(lower, 4),
        "upper": round(upper, 4),
        "lower_ratio": round(lower / span, 4),
        "upper_ratio": round(upper / span, 4),
        "vol_ratio": vol_ratio,
        "vol_chg": vol_chg,
    }


def compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """结果列表里展示用的精简字段。"""
    return {
        "body_pct": metrics.get("body_pct"),
        "body_ratio": metrics.get("body_ratio"),
        "pct_chg": metrics.get("pct_chg"),
        "max_gain": metrics.get("max_gain"),
        "max_drop": metrics.get("max_drop"),
        "lower_ratio": metrics.get("lower_ratio"),
        "upper_ratio": metrics.get("upper_ratio"),
        "vol_ratio": metrics.get("vol_ratio"),
        "vol_chg": metrics.get("vol_chg"),
        "open": metrics.get("open"),
        "high": metrics.get("high"),
        "low": metrics.get("low"),
        "close": metrics.get("close"),
    }
