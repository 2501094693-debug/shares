"""关键点穿过后的跟随 / 滞涨 / 失败。"""

from __future__ import annotations

from typing import Any

from analysis.livermore.config import FAIL_ATR, FOLLOW_DAYS, STALL_DAYS


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def follow_through(
    bars: list[dict[str, Any]],
    pivots: list[dict[str, Any]],
    atr: float,
) -> dict[str, Any]:
    empty = {
        "pivot": None,
        "after_clear_days": None,
        "status": "none",
        "follow_ok": False,
    }
    if not bars or not atr or atr <= 0:
        return empty
    candidates = [
        p
        for p in pivots
        if p.get("status") in {"cleared", "held", "failed"}
        and p.get("kind") != "round"
        and p.get("cleared_ago") is not None
    ]
    if not candidates:
        just = [
            p
            for p in pivots
            if p.get("status") == "cleared"
            and p.get("kind") != "round"
            and p.get("cleared_ago") is None
        ]
        if just:
            return {
                "pivot": just[0],
                "after_clear_days": 0,
                "status": "cleared",
                "follow_ok": True,
            }
        return empty

    pivot = min(candidates, key=lambda p: int(p.get("cleared_ago") or 99))
    ago = int(pivot.get("cleared_ago") or 0)
    price = _num(pivot.get("price"))
    if price is None:
        return empty
    start = max(0, len(bars) - 1 - min(ago, FOLLOW_DAYS))
    window = bars[start:]
    highs = [_num(b.get("high")) for b in window]
    highs = [h for h in highs if h is not None]
    last_close = _num(bars[-1].get("close"))
    failed = last_close is not None and last_close < price - FAIL_ATR * atr
    if failed or pivot.get("status") == "failed":
        return {
            "pivot": pivot,
            "after_clear_days": ago,
            "status": "fail",
            "follow_ok": False,
        }
    if ago >= STALL_DAYS and highs and max(highs) <= price + 0.15 * atr:
        return {
            "pivot": pivot,
            "after_clear_days": ago,
            "status": "stall",
            "follow_ok": False,
        }
    status = "follow_ok" if ago > 0 else "cleared"
    return {
        "pivot": pivot,
        "after_clear_days": ago,
        "status": status,
        "follow_ok": True,
    }
