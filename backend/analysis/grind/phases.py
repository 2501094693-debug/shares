"""从最近一根 K 线向前识别仍在持续的阴跌段与横盘段。"""

from __future__ import annotations

from typing import Any

from analysis.decline.bars import moving_average, segment_stats, slice_segment
from analysis.grind.config import (
    CONSOLIDATION_DAILY_THRESHOLD,
    CONSOLIDATION_STOP_ABS_TOTAL_PCT,
    CONSOLIDATION_STOP_RANGE_PCT,
    DECLINE_DAILY_THRESHOLD,
    DECLINE_STOP_PEAK_EXCESS,
    DECLINE_STOP_RANGE_PCT,
    DECLINE_STOP_TOTAL_PCT,
    SCAN_MAX_DAYS,
    SCAN_SLACK,
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def consolidation_daily_score(bar: dict[str, Any], ma5: float | None) -> float:
    """单日横盘相似度 0~1：振幅小、涨跌小、贴近均线。"""
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
    amp_score = _clamp01(1.0 - float(amp) / 4.0)
    pct_score = _clamp01(1.0 - pct / 2.2)

    ma_score = 0.5
    if ma5 is not None and ma5 > 0:
        dist = abs(close - ma5) / close * 100
        ma_score = _clamp01(1.0 - dist / 2.5)

    return 0.40 * amp_score + 0.40 * pct_score + 0.20 * ma_score


def decline_daily_score(bar: dict[str, Any], ma5: float | None) -> float:
    """单日阴跌相似度 0~1：慢跌红少、收在均线下方。"""
    close = bar.get("close")
    if close is None or close <= 0:
        return 0.0

    pct = float(bar.get("pct_chg") or 0.0)
    if pct > 1.2:
        trend_score = _clamp01(0.22 - pct / 14.0)
    elif pct > 0:
        trend_score = _clamp01(0.48 - pct / 3.5)
    elif pct >= -3.5:
        trend_score = _clamp01(1.0 - abs(pct + 1.0) / 4.0)
    elif pct >= -6.5:
        trend_score = 0.42
    else:
        trend_score = 0.18

    ma_score = 0.40
    if ma5 is not None and ma5 > 0:
        if close < ma5:
            ma_score = _clamp01(0.70 + (ma5 - close) / ma5 * 1.8)
        else:
            ma_score = _clamp01(0.38 - (close - ma5) / ma5 * 3.2)

    return 0.64 * trend_score + 0.36 * ma_score


def _segment_ok(bars: list[dict[str, Any]], start: int, end: int, kind: str) -> bool:
    seg = slice_segment(bars, start, end)
    if len(seg) < 4:
        return True
    stats = segment_stats(seg)
    if kind == "decline":
        total = stats.get("total_pct")
        if total is not None and total > DECLINE_STOP_TOTAL_PCT:
            return False
        range_pct = stats.get("range_pct")
        if range_pct is not None and range_pct > DECLINE_STOP_RANGE_PCT:
            return False
        closes = [b["close"] for b in seg if b.get("close") is not None]
        if len(closes) >= 4:
            peak = max(closes)
            start_px, end_px = closes[0], closes[-1]
            if start_px and end_px and peak > start_px * (1.0 + DECLINE_STOP_PEAK_EXCESS) and peak > end_px * (
                1.0 + DECLINE_STOP_PEAK_EXCESS
            ):
                return False
        return True

    range_pct = stats.get("range_pct")
    if range_pct is not None and range_pct > CONSOLIDATION_STOP_RANGE_PCT:
        return False
    total = stats.get("total_pct")
    if total is not None and abs(total) > CONSOLIDATION_STOP_ABS_TOTAL_PCT:
        return False
    return True


def scan_backward_soft(
    bars: list[dict[str, Any]],
    end_idx: int,
    daily_score_fn,
    threshold: float,
    *,
    kind: str,
    slack: int = SCAN_SLACK,
    max_days: int = SCAN_MAX_DAYS,
) -> tuple[int, int, list[float]]:
    """从 end_idx 向前扫。允许少量低于阈值的日子，并用累计形态约束截断。"""
    if end_idx < 0 or end_idx >= len(bars):
        return end_idx + 1, end_idx, []

    scores_rev: list[float] = []
    miss = 0
    idx = end_idx
    limit = max(0, end_idx - max(1, max_days) + 1)
    while idx >= limit:
        ma5 = moving_average(bars, idx, 5)
        score = float(daily_score_fn(bars[idx], ma5))
        if score < threshold:
            miss += 1
            if miss > max(0, slack):
                break
        else:
            miss = 0
        if scores_rev and not _segment_ok(bars, idx, end_idx, kind):
            break
        scores_rev.append(score)
        idx -= 1

    while scores_rev and scores_rev[-1] < threshold:
        scores_rev.pop()

    if not scores_rev:
        return end_idx + 1, end_idx, []

    start_idx = end_idx - len(scores_rev) + 1
    return start_idx, end_idx, scores_rev


def detect_phases(bars: list[dict[str, Any]], max_days: int = SCAN_MAX_DAYS) -> dict[str, Any]:
    """识别当前仍在进行的横盘，以及当前或横盘前的阴跌。"""
    empty = {"start": -1, "end": -1, "daily_scores": []}
    if len(bars) < 2:
        return {"consolidation": dict(empty), "decline": dict(empty)}

    last = len(bars) - 1
    cons_start, cons_end, cons_scores = scan_backward_soft(
        bars,
        last,
        consolidation_daily_score,
        CONSOLIDATION_DAILY_THRESHOLD,
        kind="consolidation",
        max_days=max_days,
    )
    dec_now_start, dec_now_end, dec_now_scores = scan_backward_soft(
        bars,
        last,
        decline_daily_score,
        DECLINE_DAILY_THRESHOLD,
        kind="decline",
        max_days=max_days,
    )

    dec_pre_start, dec_pre_end, dec_pre_scores = last + 1, last, []
    if cons_start > 0:
        dec_pre_start, dec_pre_end, dec_pre_scores = scan_backward_soft(
            bars,
            cons_start - 1,
            decline_daily_score,
            DECLINE_DAILY_THRESHOLD,
            kind="decline",
            max_days=max_days,
        )

    now_days = len(dec_now_scores)
    pre_days = len(dec_pre_scores)
    now_mean = (sum(dec_now_scores) / now_days) if now_days else 0.0
    pre_mean = (sum(dec_pre_scores) / pre_days) if pre_days else 0.0
    use_pre = pre_days > now_days or (pre_days >= 8 and pre_mean >= now_mean)
    if use_pre and pre_days:
        dec_start, dec_end, dec_scores = dec_pre_start, dec_pre_end, dec_pre_scores
    else:
        dec_start, dec_end, dec_scores = dec_now_start, dec_now_end, dec_now_scores

    return {
        "consolidation": {
            "start": cons_start if cons_scores else -1,
            "end": cons_end if cons_scores else -1,
            "daily_scores": cons_scores,
        },
        "decline": {
            "start": dec_start if dec_scores else -1,
            "end": dec_end if dec_scores else -1,
            "daily_scores": dec_scores,
        },
    }


def phase_segments(
    bars: list[dict[str, Any]], phases: dict[str, Any]
) -> tuple[list[dict], list[dict]]:
    cons = phases.get("consolidation") or {}
    dec = phases.get("decline") or {}
    cons_seg = slice_segment(bars, int(cons.get("start", -1)), int(cons.get("end", -1)))
    dec_seg = slice_segment(bars, int(dec.get("start", -1)), int(dec.get("end", -1)))
    return cons_seg, dec_seg


def recent_daily_scores(
    bars: list[dict[str, Any]],
    daily_score_fn,
    days: int = 5,
) -> list[float]:
    if not bars or days <= 0:
        return []
    start = max(0, len(bars) - days)
    out: list[float] = []
    for idx in range(start, len(bars)):
        ma5 = moving_average(bars, idx, 5)
        out.append(float(daily_score_fn(bars[idx], ma5)))
    return out
