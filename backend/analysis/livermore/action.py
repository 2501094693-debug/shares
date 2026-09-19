"""试探 / 加码 / 持有 / 等待 / 离场 / 空仓。"""

from __future__ import annotations

from typing import Any

from analysis.livermore.config import ACTION_LABELS, BULL_COLUMNS, FAIL_ATR


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def decide_action(
    *,
    gate: dict[str, Any],
    key_state: dict[str, Any],
    pivots: list[dict[str, Any]],
    volume: dict[str, Any],
    follow: dict[str, Any],
    liveliness: str,
    industry_leading: bool,
    rs_leader: bool,
    atr: float | None,
    close: float | None,
) -> dict[str, Any]:
    reasons: list[str] = []
    column = str(key_state.get("column") or "unclear")
    family = str(key_state.get("family") or "unclear")
    follow_status = str(follow.get("status") or "none")
    after_days = follow.get("after_clear_days")
    cleared = any(
        p.get("status") == "cleared" and p.get("kind") != "round"
        for p in pivots
    )
    approaching = any(p.get("status") in {"approaching", "touched"} for p in pivots)
    failed = follow_status == "fail" or any(
        p.get("status") == "failed" and p.get("kind") != "round" for p in pivots
    )

    invalidation = None
    long_pivots = [p for p in pivots if p.get("side") == "long" and _num(p.get("price"))]
    if long_pivots:
        held = [p for p in long_pivots if p.get("status") in {"cleared", "held", "failed"}]
        use = held[0] if held else long_pivots[0]
        price = _num(use.get("price"))
        if price is not None:
            pad = (atr or 0) * FAIL_ATR
            invalidation = round(price - pad, 4)

    stop = None
    if close is not None and atr:
        stop = round(close - 1.2 * atr, 4)
        if invalidation is not None:
            stop = min(stop, invalidation)

    action = "wait"

    if not gate.get("allow"):
        action = "cash"
        reasons.append(gate.get("reason") or "gate.blocked")
    elif column == "unclear" or family == "unclear":
        action = "cash"
        reasons.append("column.unclear")
    elif liveliness != "live":
        action = "wait"
        reasons.append("stock.dead")
    elif not industry_leading:
        action = "wait"
        reasons.append("industry.lag")
    elif not rs_leader:
        action = "wait"
        reasons.append("rs.laggard")
    elif failed:
        action = "exit"
        reasons.append("pivot.failed")
    elif follow_status == "stall":
        action = "wait"
        reasons.append("follow.stall")
    elif cleared and volume.get("breakout_ok") and follow.get("follow_ok"):
        if column in BULL_COLUMNS or column == "uptrend":
            if after_days in (None, 0, 1, 2):
                since = str(key_state.get("column_since") or "")
                last_switch = str(key_state.get("last_switch") or "")
                if column == "uptrend" and since and last_switch and since != last_switch:
                    action = "pyramid"
                    reasons.append("pivot.cleared")
                    reasons.append("trend.working")
                else:
                    action = "probe"
                    reasons.append("pivot.cleared")
            else:
                action = "hold"
                reasons.append("follow.ok")
        else:
            action = "wait"
            reasons.append("column.not_long")
    elif approaching and family == "bull":
        action = "wait"
        reasons.append("pivot.approaching")
    elif family == "bull" and column == "uptrend":
        action = "hold" if follow.get("follow_ok") else "wait"
        reasons.append("column.uptrend" if action == "hold" else "column.uptrend_no_follow")
    else:
        action = "wait"
        reasons.append(f"column.{column}")

    if action in {"probe", "pyramid", "hold"} and not volume.get("breakout_ok") and cleared:
        if action == "hold":
            pass
        else:
            action = "wait"
            reasons.append("volume.thin")

    return {
        "action": action,
        "action_label": ACTION_LABELS.get(action, action),
        "reason": reasons,
        "invalidation": invalidation,
        "stop": stop,
    }
