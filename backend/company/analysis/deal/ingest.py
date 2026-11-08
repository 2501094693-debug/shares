"""逐笔快照 / 资金动向的入库归一。

把东财、同花顺等源头的逐笔快照聚合成**分时窗口**，把资金动向每行转成
**订单**，并剔除集合竞价期间的累计虚拟撮合快照与开盘撮合后的空窗行。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from company.analysis.deal.constants import (
    AUCTION_SIDES,
    AUCTION_WINDOWS,
    BUY_SIDES,
    DEFAULT_AVG_LOTS_PER_TICK,
    DEFAULT_TRADE_THRESHOLD,
    PRE_CONTINUOUS_GAP,
    SHARES_PER_LOT,
)
from company.analysis.deal.util import (
    _f,
    _is_call_auction_match,
    _lots_int,
    _stamp_key,
)


# ---------------------------------------------------------------------------
# 方向 / 集合竞价过滤
# ---------------------------------------------------------------------------

def _is_buy(row: Mapping[str, Any]) -> bool:
    side = row.get("side")
    if side is not None and str(side).strip().lower() in BUY_SIDES:
        return True
    label = str(row.get("side_label") or "").strip().lower()
    return label in BUY_SIDES


def _is_auction_snapshot(row: Mapping[str, Any]) -> bool:
    """集合竞价窗口内的 auction 行（累计虚拟撮合快照）。"""
    side = "" if row.get("side") is None else str(row.get("side")).strip().lower()
    label = str(row.get("side_label") or "").strip().lower()
    if side not in AUCTION_SIDES and label not in AUCTION_SIDES:
        return False
    stamp = _stamp_key(row.get("time"))
    return any(start <= stamp < end for start, end in AUCTION_WINDOWS)


def _is_pre_continuous_gap(stamp: Any) -> bool:
    """开盘撮合后、09:30 连续竞价前的空窗（不应有新成交）。"""
    key = _stamp_key(stamp)
    if not key:
        return False
    return any(start <= key < end for start, end in PRE_CONTINUOUS_GAP)


def filter_auction_ticks(
    ticks: Iterable[Mapping[str, Any]] | None,
) -> tuple[list[Mapping[str, Any]], int]:
    """剔除集合竞价虚拟撮合快照，以及 09:26–09:30 不应有成交的空窗行。

    东财 ``details`` 在 09:15–09:25 / 14:57–15:00 给的是「累计虚拟撮合量」，
    逐行相加会把同一批委托重复计入。真实开盘成交落在 09:25（偶有几秒内的拆行），
    收盘成交落在 15:00；09:25 撮合之后到 09:30 连续竞价开始前通常没有新成交。
    """
    kept: list[Mapping[str, Any]] = []
    dropped = 0
    for row in ticks or []:
        if not isinstance(row, Mapping):
            continue
        if _is_auction_snapshot(row) or _is_pre_continuous_gap(row.get("time")):
            dropped += 1
            continue
        kept.append(row)
    return kept, dropped


# ---------------------------------------------------------------------------
# 1. 分时成交 → 窗口
# ---------------------------------------------------------------------------

def build_windows(
    ticks: Iterable[Mapping[str, Any]] | None,
    *,
    avg_lots_per_tick: float = DEFAULT_AVG_LOTS_PER_TICK,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """逐笔快照按时间戳聚合成窗口，返回 ``(windows, stats)``。

    同一秒出现多行时合并（手数相加、笔数相加、按成交额算 VWAP）。
    集合竞价期间的累计虚拟撮合快照由 ``filter_auction_ticks`` 剔除。
    """
    kept, auction_dropped = filter_auction_ticks(ticks)
    buckets: dict[str, dict[str, Any]] = {}
    for row in kept:
        if not isinstance(row, Mapping):
            continue
        stamp = _stamp_key(row.get("time"))
        if not stamp:
            continue
        lots = float(_lots_int(row.get("volume")))
        price = _f(row.get("price"))
        amount = _f(row.get("amount"))
        if amount <= 0 and price > 0:
            amount = price * lots * SHARES_PER_LOT
        if price <= 0 and lots > 0 and amount > 0:
            price = amount / (lots * SHARES_PER_LOT)
        bucket = buckets.get(stamp)
        if bucket is None:
            bucket = buckets[stamp] = {
                "time": stamp,
                "lots": 0,
                "amount": 0.0,
                "count": 0.0,
                "buy_lots": 0,
                "sell_lots": 0,
                "price_sum": 0.0,
                "price_rows": 0,
            }
        bucket["lots"] += int(lots)
        bucket["amount"] += amount
        bucket["count"] += _f(row.get("count"))
        if _is_buy(row):
            bucket["buy_lots"] += int(lots)
        else:
            bucket["sell_lots"] += int(lots)
        if price > 0:
            bucket["price_sum"] += price
            bucket["price_rows"] += 1

    windows: list[dict[str, Any]] = []
    estimated_windows = 0
    for stamp in sorted(buckets):
        bucket = buckets[stamp]
        lots = int(bucket["lots"])
        if lots <= 0:
            continue
        amount = bucket["amount"]
        price = amount / (lots * SHARES_PER_LOT) if amount > 0 else 0.0
        if price <= 0 and bucket["price_rows"]:
            price = bucket["price_sum"] / bucket["price_rows"]
        count = int(round(bucket["count"]))
        estimated = False
        if count <= 0:
            share = max(1.0, float(avg_lots_per_tick or DEFAULT_AVG_LOTS_PER_TICK))
            count = max(1, int(round(lots / share)))
            estimated = True
            estimated_windows += 1
        windows.append(
            {
                "time": stamp,
                "lots": float(lots),
                "count": count,
                "amount": round(amount, 2),
                "price": round(price, 4),
                "side": "buy" if bucket["buy_lots"] >= bucket["sell_lots"] else "sell",
                "buy_lots": float(bucket["buy_lots"]),
                "sell_lots": float(bucket["sell_lots"]),
                "estimated": estimated,
                "auction": _is_call_auction_match(stamp),
            }
        )
    stats = {
        "windows": len(windows),
        "auction_dropped": auction_dropped,
        "estimated_windows": estimated_windows,
        "lots": float(sum(int(w["lots"]) for w in windows)),
        "count": sum(w["count"] for w in windows),
    }
    return windows, stats


# ---------------------------------------------------------------------------
# 2. 资金动向 → 订单
# ---------------------------------------------------------------------------

def normalize_orders(
    big_deals: Iterable[Mapping[str, Any]] | None,
    *,
    threshold: float = DEFAULT_TRADE_THRESHOLD,
    view: str = "all",
) -> list[dict[str, Any]]:
    """资金动向每行转成一张订单。

    同花顺 HQ 大资金动向的每一行是**一张独立订单**（主买 / 主卖 / 被买 /
    被卖），手数各不相同，不是同一笔成交的双边镜像。默认 ``view="all"``
    全部纳入；买卖两侧各自占用窗口容量（见 ``place_orders``），不会把
    买+卖加总去跟分时手数打架。

    - ``all`` / ``both``：主/被、买/卖全部保留（默认）
    - ``aggressor``：只保留主动方
    - ``buy`` / ``sell``：只保留买 / 卖方
    """
    mode = (view or "all").strip().lower()
    if mode == "both":
        mode = "all"
    orders: list[dict[str, Any]] = []
    for row in big_deals or []:
        if not isinstance(row, Mapping):
            continue
        aggression = str(row.get("aggressor") or "").strip().lower()
        is_buy = _is_buy(row)
        if mode == "aggressor":
            if aggression:
                if aggression != "active":
                    continue
            elif not is_buy:
                continue
        elif mode == "buy":
            if not is_buy:
                continue
        elif mode == "sell":
            if is_buy:
                continue
        elif mode != "all":
            continue

        lots = _lots_int(row.get("volume_lots"))
        if lots <= 0:
            lots = _lots_int(_f(row.get("volume")) / SHARES_PER_LOT)
        if lots <= 0:
            continue
        price = _f(row.get("price"))
        amount = _f(row.get("amount"))
        if amount <= 0 and price > 0:
            amount = price * lots * SHARES_PER_LOT
        if price <= 0 and amount > 0:
            price = amount / (lots * SHARES_PER_LOT)
        stamp = _stamp_key(row.get("time"))
        orders.append(
            {
                "time": stamp,
                "price": round(price, 4),
                "lots": float(lots),
                "amount": round(amount, 2),
                "side": "buy" if is_buy else "sell",
                "view": aggression or ("active" if mode == "aggressor" else mode),
                "super": amount >= threshold * 10,
                # 与资金动向列表对齐的外部事件键：逐笔行带上它，前端即可联动高亮
                "event_id": str(row.get("event_id") or ""),
            }
        )
    orders.sort(key=lambda order: (order["time"], -order["lots"]))
    for index, order in enumerate(orders):
        order["order_id"] = f"O{index + 1:05d}"
    return orders


__all__ = [
    "_is_auction_snapshot",
    "_is_buy",
    "_is_pre_continuous_gap",
    "build_windows",
    "filter_auction_ticks",
    "normalize_orders",
]
