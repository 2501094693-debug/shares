"""突破量能、回撤缩量。"""

from __future__ import annotations

from typing import Any

from analysis.livermore.bars import mean_volume
from analysis.livermore.config import BREAKOUT_VOLUME_RATIO, VOLUME_LOOKBACK


def volume_state(
    bars: list[dict[str, Any]],
    pivots: list[dict[str, Any]],
) -> dict[str, Any]:
    avg = mean_volume(bars[:-1], VOLUME_LOOKBACK) if len(bars) > 1 else mean_volume(bars, VOLUME_LOOKBACK)
    last_vol = None
    if bars:
        try:
            last_vol = float(bars[-1].get("volume") or 0) or None
        except (TypeError, ValueError):
            last_vol = None
    ratio = None
    if avg and last_vol:
        ratio = round(last_vol / avg, 3)

    cleared = [
        p
        for p in pivots
        if p.get("status") in {"cleared", "failed"} and p.get("kind") != "round"
    ]
    breakout_ok = bool(ratio is not None and ratio >= BREAKOUT_VOLUME_RATIO)
    if not cleared:
        breakout_ok = False

    pullback = bars[-3:] if len(bars) >= 3 else bars
    pull_vols = [b.get("volume") for b in pullback if b.get("volume")]
    dryup = False
    if avg and pull_vols:
        dryup = (sum(float(v) for v in pull_vols) / len(pull_vols)) <= 0.8 * avg

    climax = bool(ratio is not None and ratio >= 3.0)
    return {
        "avg_volume": round(avg, 1) if avg else None,
        "last_volume": last_vol,
        "breakout_ratio": ratio,
        "breakout_ok": breakout_ok,
        "pullback_dryup": dryup,
        "climax": climax,
    }
