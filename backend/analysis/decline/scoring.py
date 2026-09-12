"""各维度软评分。"""

from __future__ import annotations

import math
from typing import Any

from analysis.decline.bars import linear_slope, mean_volume, segment_stats
from analysis.decline.config import (
    CONSOLIDATION_DURATION_SCALE,
    DECLINE_DURATION_SCALE,
    WEIGHTS,
)


def duration_score(days: int, scale: float) -> float:
    """时长分：越久越高，指数饱和至 100。"""
    if days <= 0 or scale <= 0:
        return 0.0
    return round(100.0 * (1.0 - math.exp(-days / scale)), 2)


def _bell(value: float | None, center: float, width: float) -> float:
    if value is None:
        return 0.0
    return math.exp(-((value - center) ** 2) / (2 * width ** 2))


def consolidation_quality_score(segment: list[dict[str, Any]], daily_scores: list[float]) -> float:
    stats = segment_stats(segment)
    if not segment:
        return 0.0

    daily_mean = (sum(daily_scores) / len(daily_scores) * 100) if daily_scores else 0.0
    range_pct = stats.get("range_pct")
    volatility = stats.get("volatility")
    avg_amp = stats.get("avg_amplitude")

    range_score = 0.0
    if range_pct is not None:
        range_score = max(0.0, 100.0 - max(0.0, range_pct - 5.0) * 6.0)

    vol_score = 0.0
    if volatility is not None:
        vol_score = max(0.0, 100.0 - volatility * 25.0)

    amp_score = 0.0
    if avg_amp is not None:
        amp_score = max(0.0, 100.0 - avg_amp * 20.0)

    return round(0.35 * daily_mean + 0.30 * range_score + 0.20 * vol_score + 0.15 * amp_score, 2)


def decline_quality_score(segment: list[dict[str, Any]], daily_scores: list[float]) -> float:
    stats = segment_stats(segment)
    if not segment:
        return 0.0

    daily_mean = (sum(daily_scores) / len(daily_scores) * 100) if daily_scores else 0.0
    total_pct = stats.get("total_pct")
    volatility = stats.get("volatility")

    decline_fit = _bell(total_pct, center=-16.0, width=12.0) * 100 if total_pct is not None else 0.0

    closes = [b["close"] for b in segment if b.get("close") is not None]
    slope = linear_slope(closes)
    slope_score = 0.0
    if slope is not None and closes:
        slope_pct = slope / closes[0] * 100
        if slope_pct < 0:
            slope_score = min(100.0, abs(slope_pct) * 80.0)

    vol_score = 0.0
    if volatility is not None:
        vol_score = max(0.0, 100.0 - volatility * 20.0)

    return round(0.30 * daily_mean + 0.30 * decline_fit + 0.25 * slope_score + 0.15 * vol_score, 2)


def breakout_score(
    limit_up_bar: dict[str, Any],
    limit_up_meta: dict[str, Any],
    consolidation_segment: list[dict[str, Any]],
    lookback_days: int,
) -> float:
    score = 0.0

    board = int(limit_up_meta.get("board_count") or 0)
    if board == 1:
        score += 30.0
    elif board == 2:
        score += 15.0
    elif board > 0:
        score += 5.0

    breaks = int(limit_up_meta.get("break_count") or 0)
    if breaks == 0:
        score += 20.0
    elif breaks <= 2:
        score += 10.0

    cons_high = None
    if consolidation_segment:
        highs = [b["high"] for b in consolidation_segment if b.get("high") is not None]
        if highs:
            cons_high = max(highs)

    close = limit_up_bar.get("close")
    if cons_high and close and close > cons_high:
        gap = (close - cons_high) / cons_high * 100
        score += min(25.0, 15.0 + gap * 2.0)
    elif close and limit_up_meta.get("change_pct"):
        score += min(15.0, float(limit_up_meta["change_pct"]))

    cons_vol = mean_volume(consolidation_segment)
    limit_vol = limit_up_bar.get("volume")
    if cons_vol and limit_vol and cons_vol > 0:
        ratio = limit_vol / cons_vol
        score += min(25.0, ratio * 8.0)

    days_ago = int(limit_up_meta.get("days_since_limit_up") or lookback_days)
    if lookback_days > 0:
        recency = max(0.0, 1.0 - (days_ago - 1) / lookback_days)
        score += recency * 10.0

    name = str(limit_up_meta.get("name") or "")
    if "ST" in name.upper():
        score *= 0.7

    return round(min(100.0, score), 2)


def structure_score(
    decline_segment: list[dict[str, Any]],
    consolidation_segment: list[dict[str, Any]],
    limit_up_bar: dict[str, Any],
) -> float:
    score = 0.0
    dec_stats = segment_stats(decline_segment)
    cons_stats = segment_stats(consolidation_segment)

    dec_days = dec_stats.get("days") or 0
    cons_days = cons_stats.get("days") or 0

    if dec_days > 0 and cons_days > 0:
        score += 40.0
        overlap = min(dec_days, cons_days)
        score += min(20.0, overlap * 0.5)

    cons_high = cons_stats.get("high")
    close = limit_up_bar.get("close")
    if cons_high and close and close > cons_high:
        score += 25.0

    dec_vol = dec_stats.get("volatility")
    cons_vol = cons_stats.get("volatility")
    if dec_vol is not None and cons_vol is not None and cons_vol < dec_vol:
        score += 15.0

    dec_total = dec_stats.get("total_pct")
    if dec_total is not None and dec_total < 0 and cons_days > 0:
        score += 10.0

    return round(min(100.0, score), 2)


def total_score(parts: dict[str, float]) -> float:
    total = 0.0
    for key, weight in WEIGHTS.items():
        total += float(parts.get(key) or 0.0) * weight
    return round(total, 2)
