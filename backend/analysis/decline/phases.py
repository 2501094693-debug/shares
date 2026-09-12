"""从涨停日前向识别横盘段与阴跌段。"""

from __future__ import annotations

from typing import Any

from analysis.decline.bars import moving_average, slice_segment
from analysis.decline.config import (
    CONSOLIDATION_DAILY_THRESHOLD,
    DECLINE_DAILY_THRESHOLD,
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def consolidation_daily_score(bar: dict[str, Any], ma5: float | None) -> float:
    """单日横盘相似度 0~1。"""
    close = bar.get("close")
    if close is None or close <= 0:
        return 0.0

    amp = bar.get("amplitude")
    if amp is None:
        high, low = bar.get("high"), bar.get("low")
        if high is not None and low is not None:
            amp = (high - low) / close * 100
        else:
            amp = 5.0

    pct = abs(bar.get("pct_chg") or 0.0)
    amp_score = _clamp01(1.0 - amp / 5.0)
    pct_score = _clamp01(1.0 - pct / 3.0)

    ma_score = 0.5
    if ma5 is not None and ma5 > 0:
        dist = abs(close - ma5) / close * 100
        ma_score = _clamp01(1.0 - dist / 3.0)

    return 0.40 * amp_score + 0.35 * pct_score + 0.25 * ma_score


def decline_daily_score(bar: dict[str, Any], ma5: float | None) -> float:
    """单日阴跌相似度 0~1。"""
    close = bar.get("close")
    if close is None or close <= 0:
        return 0.0

    pct = bar.get("pct_chg") or 0.0

    if pct > 2.0:
        trend_score = _clamp01(0.35 - pct / 15.0)
    elif pct < -6.0:
        trend_score = _clamp01(0.25 + (pct + 6.0) / 30.0)
    elif -3.0 <= pct <= 0.5:
        trend_score = _clamp01(1.0 - abs(pct + 0.8) / 4.0)
    elif pct > 0.5:
        trend_score = _clamp01(0.65 - pct / 8.0)
    else:
        trend_score = _clamp01(0.75 + pct / 20.0)

    ma_score = 0.45
    if ma5 is not None and ma5 > 0:
        if close < ma5:
            ma_score = _clamp01(0.65 + (ma5 - close) / ma5 * 2.0)
        else:
            ma_score = _clamp01(0.55 - (close - ma5) / ma5 * 2.0)

    return 0.60 * trend_score + 0.40 * ma_score


def scan_backward(
    bars: list[dict[str, Any]],
    end_idx: int,
    daily_score_fn,
    threshold: float,
) -> tuple[int, int, list[float]]:
    """从 end_idx 向前扫描，返回 (start_idx, end_idx, daily_scores)。"""
    if end_idx < 0 or end_idx >= len(bars):
        return end_idx + 1, end_idx, []

    daily_scores: list[float] = []
    idx = end_idx
    while idx >= 0:
        ma5 = moving_average(bars, idx, 5)
        score = daily_score_fn(bars[idx], ma5)
        if daily_scores and score < threshold:
            break
        if not daily_scores and score < threshold:
            break
        daily_scores.append(score)
        idx -= 1

    if not daily_scores:
        return end_idx + 1, end_idx, []

    start_idx = idx + 1
    return start_idx, end_idx, daily_scores


def detect_phases(
    bars: list[dict[str, Any]],
    limit_up_idx: int,
) -> dict[str, Any]:
    """识别涨停前的横盘段与阴跌段。"""
    if limit_up_idx <= 0:
        return {
            "consolidation": {"start": -1, "end": -1, "daily_scores": []},
            "decline": {"start": -1, "end": -1, "daily_scores": []},
        }

    cons_start, cons_end, cons_scores = scan_backward(
        bars,
        limit_up_idx - 1,
        consolidation_daily_score,
        CONSOLIDATION_DAILY_THRESHOLD,
    )

    decline_end = cons_start - 1
    if decline_end < 0:
        return {
            "consolidation": {
                "start": cons_start,
                "end": cons_end,
                "daily_scores": cons_scores,
            },
            "decline": {"start": -1, "end": -1, "daily_scores": []},
        }

    dec_start, dec_end, dec_scores = scan_backward(
        bars,
        decline_end,
        decline_daily_score,
        DECLINE_DAILY_THRESHOLD,
    )

    return {
        "consolidation": {
            "start": cons_start,
            "end": cons_end,
            "daily_scores": cons_scores,
        },
        "decline": {
            "start": dec_start,
            "end": dec_end,
            "daily_scores": dec_scores,
        },
    }


def phase_segments(bars: list[dict[str, Any]], phases: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    cons = phases.get("consolidation") or {}
    dec = phases.get("decline") or {}
    cons_seg = slice_segment(bars, int(cons.get("start", -1)), int(cons.get("end", -1)))
    dec_seg = slice_segment(bars, int(dec.get("start", -1)), int(dec.get("end", -1)))
    return cons_seg, dec_seg
