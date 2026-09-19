"""关键点：前高、箱顶、52 周高、整数关。"""

from __future__ import annotations

from typing import Any

from analysis.livermore.config import (
    APPROACH_ATR,
    BOX_MIN_DAYS,
    FAIL_ATR,
    FOLLOW_DAYS,
    HIGH_52W_BARS,
    SWING_LEFT,
)


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_level(price: float) -> float | None:
    if price <= 0:
        return None
    if price >= 100:
        step = 10.0
    elif price >= 30:
        step = 5.0
    elif price >= 10:
        step = 1.0
    else:
        step = 0.5
    return round(round(price / step) * step, 4)


def swing_highs(bars: list[dict[str, Any]], left: int = SWING_LEFT) -> list[dict[str, Any]]:
    """左看 left 根的摆动高点（含尚未走完右侧的最近高点）。"""
    out: list[dict[str, Any]] = []
    if left <= 0 or len(bars) < left + 1:
        return out
    last = len(bars) - 1
    for i in range(left, last + 1):
        high = _num(bars[i].get("high"))
        if high is None:
            continue
        window = bars[max(0, i - left) : min(last, i + left) + 1]
        highs = [_num(b.get("high")) for b in window]
        highs = [h for h in highs if h is not None]
        if highs and high >= max(highs) - 1e-9:
            if i + left > last and i != last:
                continue
            out.append({"date": bars[i]["date"], "price": high, "index": i})
    return out


def classify_status(
    *,
    close: float,
    high: float,
    atr: float,
    pivot: float,
    cleared_ago: int | None,
    later_close: float | None,
) -> str:
    if atr <= 0:
        atr = 1.0
    dist = (close - pivot) / atr
    if cleared_ago is not None and later_close is not None:
        if later_close < pivot - FAIL_ATR * atr:
            return "failed"
    if close >= pivot + 0.05 * atr or (high >= pivot and close >= pivot):
        return "cleared"
    if abs(dist) <= 0.15:
        return "touched"
    if -APPROACH_ATR <= dist < 0:
        return "approaching"
    if dist > 0:
        return "held"
    return "below"


def detect_pivots(
    bars: list[dict[str, Any]],
    raw_bars: list[dict[str, Any]],
    atr: float,
    key_state: dict[str, Any],
) -> list[dict[str, Any]]:
    """当前关键点列表，按距离从近到远。"""
    if not bars or not atr or atr <= 0:
        return []
    last = bars[-1]
    close = _num(last.get("close"))
    high = _num(last.get("high"))
    if close is None or high is None:
        return []
    raw_close = _num((raw_bars[-1] if raw_bars else last).get("close")) or close
    last_idx = len(bars) - 1
    items: list[dict[str, Any]] = []

    def push(kind: str, price: float | None, side: str = "long") -> None:
        if price is None or price <= 0:
            return
        cleared_ago = None
        later_close = close
        for back in range(1, min(FOLLOW_DAYS, last_idx) + 1):
            bar = bars[last_idx - back]
            prev_close = _num(bar.get("close"))
            prev_high = _num(bar.get("high"))
            if prev_close is None:
                continue
            if prev_high is not None and prev_close >= price and prev_high >= price:
                cleared_ago = back
                break
        status = classify_status(
            close=close,
            high=high,
            atr=atr,
            pivot=price,
            cleared_ago=cleared_ago,
            later_close=later_close,
        )
        items.append(
            {
                "kind": kind,
                "price": round(price, 4),
                "side": side,
                "dist_atr": round((close - price) / atr, 3),
                "status": status,
                "cleared_ago": cleared_ago,
            }
        )

    swings = swing_highs(bars)
    if swings:
        last_swing = swings[-1]
        if last_swing["index"] < last_idx:
            push("swing_high", last_swing["price"])
        elif len(swings) >= 2:
            push("swing_high", swings[-2]["price"])

    key_up = _num(key_state.get("key_up"))
    reaction_days = int(key_state.get("reaction_days") or 0)
    if key_up and reaction_days >= BOX_MIN_DAYS:
        push("box_high", key_up)
    elif key_up:
        push("key_up", key_up)

    window = bars[-min(HIGH_52W_BARS, len(bars)) :]
    highs = [_num(b.get("high")) for b in window]
    highs = [h for h in highs if h is not None]
    if highs:
        push("high_52w", max(highs))

    push("round", _round_level(raw_close))

    # 去重：价格过近的保留更具体的 kind
    ranked = []
    seen: list[float] = []
    order = ["box_high", "key_up", "swing_high", "high_52w", "round"]
    for kind in order:
        for item in items:
            if item["kind"] != kind:
                continue
            if any(abs(item["price"] - p) <= 0.15 * atr for p in seen):
                continue
            seen.append(item["price"])
            ranked.append(item)
    ranked.sort(key=lambda r: abs(float(r.get("dist_atr") or 99)))
    return ranked[:6]
