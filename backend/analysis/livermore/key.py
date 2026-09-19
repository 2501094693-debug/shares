"""六栏市场记录：上升趋势 / 自然回撤 / 二次回撤 / 下降趋势 / 自然回升 / 二次回升。"""

from __future__ import annotations

from typing import Any

from analysis.livermore.atr import atr_series
from analysis.livermore.config import (
    ATR_WINDOW,
    COLUMN_LABELS,
    CONFIRM_ATR,
    REACTION_ATR,
    REVERSAL_ATR,
)


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def walk_key(
    bars: list[dict[str, Any]],
    *,
    reaction_atr: float = REACTION_ATR,
    confirm_atr: float = CONFIRM_ATR,
    reversal_atr: float = REVERSAL_ATR,
    atr_window: int = ATR_WINDOW,
) -> dict[str, Any]:
    """从左到右走日 K，输出最新六栏状态。

    上升趋势里回撤 ≥ reaction×ATR 记入自然回撤，并把离开时的高点标成关键线。
    收盘重新站上关键线 + confirm×ATR 则回到上升趋势。
    从关键线再跌 reversal×ATR 则翻成下降趋势。下跌侧对称。
    """
    empty = {
        "column": "unclear",
        "column_label": COLUMN_LABELS["unclear"],
        "column_since": "",
        "last_switch": "",
        "key_up": None,
        "key_dn": None,
        "extreme": None,
        "reaction_extreme": None,
        "reaction_days": 0,
        "family": "unclear",
        "as_of": bars[-1]["date"] if bars else "",
        "switches": [],
    }
    if len(bars) < atr_window + 2:
        return empty

    atrs = atr_series(bars, atr_window)
    trend = 0
    in_reaction = False
    secondary = False
    had_bounce = False
    extreme: float | None = None
    reaction_ext: float | None = None
    key_up: float | None = None
    key_dn: float | None = None
    column = "unclear"
    column_since = ""
    last_switch = ""
    switches: list[dict[str, Any]] = []
    reaction_start = ""

    def set_column(day: str, next_col: str) -> None:
        nonlocal column, column_since, last_switch
        if next_col == column:
            return
        if column != "unclear" or next_col != "unclear":
            last_switch = day
            switches.append({"date": day, "from": column, "to": next_col})
        column = next_col
        column_since = day

    start = next((i for i, a in enumerate(atrs) if a), atr_window)
    for i in range(start, len(bars)):
        bar = bars[i]
        atr = atrs[i]
        if not atr or atr <= 0:
            continue
        high = _num(bar.get("high"))
        low = _num(bar.get("low"))
        close = _num(bar.get("close"))
        day = str(bar.get("date") or "")
        if high is None or low is None or close is None:
            continue
        react = reaction_atr * atr
        confirm = confirm_atr * atr
        reverse = reversal_atr * atr

        if trend == 0:
            if extreme is None:
                extreme = high
                reaction_ext = low
            else:
                extreme = max(extreme, high)
                reaction_ext = min(reaction_ext or low, low)
            span = (extreme or 0) - (reaction_ext or 0)
            if span >= react:
                mid = ((extreme or 0) + (reaction_ext or 0)) / 2.0
                if close >= mid:
                    trend = 1
                    extreme = high
                    reaction_ext = None
                    in_reaction = False
                    set_column(day, "uptrend")
                else:
                    trend = -1
                    extreme = low
                    reaction_ext = None
                    in_reaction = False
                    set_column(day, "downtrend")
            continue

        if trend > 0:
            if not in_reaction:
                made_high = high >= (extreme or high)
                if made_high:
                    extreme = high
                elif extreme is not None and extreme - low >= react:
                    key_up = extreme
                    in_reaction = True
                    secondary = False
                    had_bounce = False
                    reaction_ext = low
                    reaction_start = day
                    set_column(day, "natural_reaction")
            else:
                if reaction_ext is None or low <= reaction_ext:
                    reaction_ext = low
                resumed = key_up is not None and close >= key_up + confirm
                reversed_ = (
                    key_up is not None
                    and reaction_ext is not None
                    and key_up - close >= reverse
                    and close <= reaction_ext + confirm
                )
                bounced = reaction_ext is not None and high - reaction_ext >= react
                if resumed:
                    trend = 1
                    in_reaction = False
                    secondary = False
                    had_bounce = False
                    extreme = max(high, key_up or high)
                    reaction_ext = None
                    reaction_start = ""
                    set_column(day, "uptrend")
                elif reversed_:
                    trend = -1
                    in_reaction = False
                    secondary = False
                    had_bounce = False
                    key_dn = reaction_ext
                    extreme = low
                    reaction_ext = None
                    reaction_start = ""
                    set_column(day, "downtrend")
                elif bounced:
                    had_bounce = True
                elif had_bounce and not secondary:
                    secondary = True
                    set_column(day, "secondary_reaction")
        else:
            if not in_reaction:
                made_low = low <= (extreme or low)
                if made_low:
                    extreme = low
                elif extreme is not None and high - extreme >= react:
                    key_dn = extreme
                    in_reaction = True
                    secondary = False
                    had_bounce = False
                    reaction_ext = high
                    reaction_start = day
                    set_column(day, "natural_rally")
            else:
                if reaction_ext is None or high >= reaction_ext:
                    reaction_ext = high
                resumed = key_dn is not None and close <= key_dn - confirm
                reversed_ = (
                    key_dn is not None
                    and reaction_ext is not None
                    and close - key_dn >= reverse
                    and close >= reaction_ext - confirm
                )
                bounced = reaction_ext is not None and reaction_ext - low >= react
                if resumed:
                    trend = -1
                    in_reaction = False
                    secondary = False
                    had_bounce = False
                    extreme = min(low, key_dn or low)
                    reaction_ext = None
                    reaction_start = ""
                    set_column(day, "downtrend")
                elif reversed_:
                    trend = 1
                    in_reaction = False
                    secondary = False
                    had_bounce = False
                    key_up = reaction_ext
                    extreme = high
                    reaction_ext = None
                    reaction_start = ""
                    set_column(day, "uptrend")
                elif bounced:
                    had_bounce = True
                elif had_bounce and not secondary:
                    secondary = True
                    set_column(day, "secondary_rally")

    reaction_days = 0
    last_day = str(bars[-1].get("date") or "")
    if reaction_start and column in {
        "natural_reaction",
        "secondary_reaction",
        "natural_rally",
        "secondary_rally",
    }:
        dates = [str(b.get("date") or "") for b in bars]
        try:
            reaction_days = dates.index(last_day) - dates.index(reaction_start) + 1
        except ValueError:
            reaction_days = 0

    family = "unclear"
    if column in {"uptrend", "natural_reaction", "secondary_reaction"}:
        family = "bull"
    elif column in {"downtrend", "natural_rally", "secondary_rally"}:
        family = "bear"

    return {
        "column": column,
        "column_label": COLUMN_LABELS.get(column, column),
        "column_since": column_since,
        "last_switch": last_switch,
        "key_up": round(key_up, 4) if key_up is not None else None,
        "key_dn": round(key_dn, 4) if key_dn is not None else None,
        "extreme": round(extreme, 4) if extreme is not None else None,
        "reaction_extreme": round(reaction_ext, 4) if reaction_ext is not None else None,
        "reaction_days": max(0, reaction_days),
        "family": family,
        "as_of": last_day,
        "switches": switches[-12:],
    }
