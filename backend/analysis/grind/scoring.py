"""阴跌 / 横盘软评分。无硬门槛，分数只表示像不像。"""

from __future__ import annotations

import math
from typing import Any

from analysis.decline.bars import linear_slope, moving_average, segment_stats
from analysis.grind.config import (
    DUAL_PATTERN_BONUS,
    PATTERN_WEIGHTS,
)
from analysis.grind.phases import consolidation_daily_score, decline_daily_score, recent_daily_scores


def duration_score(days: int, scale: float) -> float:
    """时长分：越久越高，指数饱和至 100。"""
    if days <= 0 or scale <= 0:
        return 0.0
    return round(100.0 * (1.0 - math.exp(-days / scale)), 2)


def _bell(value: float | None, center: float, width: float) -> float:
    if value is None or width <= 0:
        return 0.0
    return math.exp(-((value - center) ** 2) / (2 * width**2))


def _clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _below_ma_ratio(segment: list[dict[str, Any]], bars: list[dict[str, Any]], window: int = 20) -> float | None:
    if not segment or not bars:
        return None
    by_date = {b.get("date"): i for i, b in enumerate(bars)}
    hits = 0
    n = 0
    for bar in segment:
        idx = by_date.get(bar.get("date"))
        if idx is None:
            continue
        ma = moving_average(bars, idx, window)
        close = bar.get("close")
        if ma is None or not close:
            continue
        n += 1
        if close < ma:
            hits += 1
    if not n:
        return None
    return hits / n


def _close_location(segment: list[dict[str, Any]]) -> float | None:
    if not segment:
        return None
    close = segment[-1].get("close")
    highs = [b["high"] for b in segment if b.get("high") is not None]
    lows = [b["low"] for b in segment if b.get("low") is not None]
    if close is None or not highs or not lows:
        return None
    hi, lo = max(highs), min(lows)
    if hi <= lo:
        return None
    return (close - lo) / (hi - lo)


def decline_quality_score(
    segment: list[dict[str, Any]],
    daily_scores: list[float],
    window: list[dict[str, Any]],
    bars: list[dict[str, Any]],
) -> float:
    """阴跌质量：慢跌、斜率为负、波动不大、多数时间在均线下方、收在区间下沿。"""
    sample = segment or window
    if not sample:
        return 0.0

    daily_mean = (sum(daily_scores) / len(daily_scores) * 100) if daily_scores else 0.0
    stats = segment_stats(segment) if segment else segment_stats(window)
    win_stats = segment_stats(window) if window else stats
    total_pct = win_stats.get("total_pct")
    if total_pct is None:
        total_pct = stats.get("total_pct")

    grind_fit = _bell(total_pct, center=-14.0, width=11.0) * 100 if total_pct is not None else 0.0
    if total_pct is not None and total_pct >= 0:
        grind_fit *= 0.18
    elif total_pct is not None and total_pct > -4:
        grind_fit *= 0.55

    closes = [b["close"] for b in sample if b.get("close") is not None]
    slope = linear_slope(closes)
    slope_score = 0.0
    if slope is not None and closes and closes[0]:
        slope_pct = slope / closes[0] * 100
        if slope_pct < 0:
            slope_score = _clip(abs(slope_pct) * 90.0)
        else:
            slope_score = _clip(12.0 - slope_pct * 40.0)

    pcts = [b["pct_chg"] for b in sample if b.get("pct_chg") is not None]
    down_ratio = (sum(1 for p in pcts if p < 0) / len(pcts)) if pcts else 0.0
    down_score = _clip(100.0 * (1.0 - abs(down_ratio - 0.62) / 0.48))

    volatility = win_stats.get("volatility")
    if volatility is None:
        volatility = stats.get("volatility")
    vol_score = _clip(100.0 - float(volatility) * 16.0) if volatility is not None else 40.0

    crash_days = sum(1 for p in pcts if p <= -7.0)
    crash_penalty = min(40.0, crash_days * 8.0)

    below = _below_ma_ratio(sample, bars, 20)
    ma_score = below * 100.0 if below is not None else 45.0

    loc = _close_location(window or sample)
    loc_score = _clip(100.0 * (1.0 - loc) ) if loc is not None else 50.0

    seg_part = (
        0.22 * daily_mean
        + 0.24 * grind_fit
        + 0.16 * slope_score
        + 0.12 * vol_score
        + 0.12 * down_score
        + 0.14 * loc_score
    )
    blended = 0.62 * seg_part + 0.38 * ma_score
    if total_pct is not None and total_pct >= 8:
        blended *= 0.12
    elif total_pct is not None and total_pct >= 2:
        blended *= 0.32
    return round(_clip(blended - crash_penalty * 0.40), 2)


def consolidation_quality_score(
    segment: list[dict[str, Any]],
    daily_scores: list[float],
    window: list[dict[str, Any]],
) -> float:
    """横盘质量：区间窄、涨跌接近 0、振幅和波动都低。"""
    if not segment and not window:
        return 0.0

    daily_mean = (sum(daily_scores) / len(daily_scores) * 100) if daily_scores else 0.0
    stats = segment_stats(segment or window)
    win_stats = segment_stats(window) if window else stats

    range_pct = stats.get("range_pct")
    if range_pct is None:
        range_pct = win_stats.get("range_pct")
    range_score = _clip(100.0 - max(0.0, float(range_pct) - 6.0) * 6.0) if range_pct is not None else 0.0

    total_pct = win_stats.get("total_pct")
    if total_pct is None:
        total_pct = stats.get("total_pct")
    flat_score = _clip(100.0 - abs(float(total_pct)) * 6.5) if total_pct is not None else 0.0

    sample = segment or window
    closes = [b["close"] for b in sample if b.get("close") is not None]
    slope = linear_slope(closes)
    slope_score = 50.0
    if slope is not None and closes and closes[0]:
        slope_pct = abs(slope / closes[0] * 100)
        slope_score = _clip(100.0 - slope_pct * 90.0)

    volatility = stats.get("volatility")
    if volatility is None:
        volatility = win_stats.get("volatility")
    vol_score = _clip(100.0 - float(volatility) * 24.0) if volatility is not None else 40.0

    avg_amp = stats.get("avg_amplitude")
    amp_score = _clip(100.0 - float(avg_amp) * 18.0) if avg_amp is not None else 40.0

    score = (
        0.24 * daily_mean
        + 0.24 * range_score
        + 0.20 * flat_score
        + 0.12 * slope_score
        + 0.10 * vol_score
        + 0.10 * amp_score
    )
    if range_pct is not None and range_pct >= 28:
        score *= 0.35
    if total_pct is not None and abs(total_pct) >= 14:
        score *= 0.40
    return round(_clip(score), 2)


def persistence_score(bars: list[dict[str, Any]], kind: str) -> float:
    """最近几天是否还停在该形态上。"""
    fn = decline_daily_score if kind == "decline" else consolidation_daily_score
    scores = recent_daily_scores(bars, fn, 8)
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores) * 100.0, 2)


def pattern_score(duration: float, quality: float, persistence: float) -> float:
    w = PATTERN_WEIGHTS
    return round(
        duration * w["duration"] + quality * w["quality"] + persistence * w["persistence"],
        2,
    )


def classify(decline: float, consolidation: float) -> tuple[str, str]:
    if decline >= consolidation + 8:
        return "decline", "阴跌"
    if consolidation >= decline + 8:
        return "consolidation", "横盘"
    if decline < 22 and consolidation < 22:
        return "none", "不明显"
    return "mixed", "阴跌横盘"


def combine_scores(
    *,
    decline: float,
    consolidation: float,
    name: str = "",
) -> float:
    primary = max(decline, consolidation)
    if decline >= 38 and consolidation >= 38:
        extra = min(DUAL_PATTERN_BONUS, 3.0 + 0.07 * min(decline, consolidation))
        primary = min(100.0, primary + extra)
    if "ST" in str(name or "").upper():
        primary *= 0.85
    return round(_clip(primary), 2)
