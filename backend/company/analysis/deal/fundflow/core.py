"""同花顺大单资金动向统计：四象限汇总 + 定步长分箱（纯计算，无 IO）。

口径与前端 ``bigDealEventType`` 对齐，四象限为 ``active_buy`` /
``active_sell`` / ``passive_buy`` / ``passive_sell``。

分箱只做两种固定步进，均从 0 起：金额 ``AMOUNT_STEP = 1_000_000`` 元、
手数 ``LOTS_STEP = 100`` 手。四堆共用同一套边界（由全部样本最大值决定），
各自计数；这样前端可以把四个象限叠在同一根柱子上比较「这个重量级里是谁在买」。
"""

from __future__ import annotations

import math
from typing import Any, Iterable

from core.fmt import to_float

AMOUNT_STEP = 1_000_000
LOTS_STEP = 100

EVENT_TYPES = ("active_buy", "active_sell", "passive_buy", "passive_sell")
BIN_BY_MODES = ("amount", "lots", "both")
DEFAULT_BIN_BY = "amount"

_BIN_ALIASES = {
    "amount": "amount",
    "amt": "amount",
    "lots": "lots",
    "lot": "lots",
    "volume_lots": "lots",
    "volume-lots": "lots",
    "hands": "lots",
    "both": "both",
}


def classify_event(row: dict[str, Any]) -> str | None:
    """单笔大单归属哪一象限；无法判定返回 ``None``。

    判定顺序与前端一致：先看 ``aggressor`` x ``side``，缺失时退回中文标签，
    最后退回 ``event_name``。
    """
    side = str(row.get("side") or "").strip().lower()
    aggressor = str(row.get("aggressor") or "").strip().lower()
    if not aggressor:
        label = str(row.get("aggressor_label") or "")
        if "主" in label:
            aggressor = "active"
        elif "被" in label:
            aggressor = "passive"
    if aggressor in {"active", "passive"} and side in {"buy", "sell"}:
        return f"{aggressor}_{side}"

    name = str(row.get("event_name") or "")
    if "主动买" in name:
        return "active_buy"
    if "主动卖" in name:
        return "active_sell"
    if "被动买" in name:
        return "passive_buy"
    if "被动卖" in name:
        return "passive_sell"
    return None


def normalize_bin_by(value: str) -> str:
    """``bin_by`` 归一化：``amount``（默认）/ ``lots`` / ``both``。"""
    key = str(value or "").strip().lower()
    if not key:
        return DEFAULT_BIN_BY
    mode = _BIN_ALIASES.get(key)
    if mode is None:
        raise ValueError(f"bin_by 须为 {'|'.join(BIN_BY_MODES)}")
    return mode

def build_step_edges(max_value: float, step: int) -> list[tuple[float, float]]:
    """从 0 起按 ``step`` 铺满到覆盖 ``max_value`` 的区间序列。

    档数 ``N = floor(max/step) + 1``，与 ``ceil(max/step)`` 等价，唯一差别是
    ``max`` 恰为 ``step`` 整数倍时多出一档——这样最大那笔不会落在末档右端
    之外，末档恒满足 ``hi > max``。无样本（``max <= 0``）返回空列表。
    """
    peak = to_float(max_value) or 0.0
    width = float(step)
    if peak <= 0 or width <= 0:
        return []
    count = int(math.floor(round(peak / width, 9))) + 1
    return [(i * width, (i + 1) * width) for i in range(max(count, 1))]


def _num(value: float) -> float | int:
    """整数值输出 int（``6100000`` 而不是 ``6100000.0``），其余保留 2 位。"""
    number = round(float(value), 2)
    return int(number) if number.is_integer() else number


def _new_bins(edges: list[tuple[float, float]]) -> list[dict[str, Any]]:
    return [
        {"lo": _num(lo), "hi": _num(hi), "count": 0, "amount": 0, "volume_lots": 0}
        for lo, hi in edges
    ]


def _bin_index(value: float, edges: list[tuple[float, float]]) -> int | None:
    if not edges:
        return None
    width = edges[0][1] - edges[0][0]
    if width <= 0:
        return None
    index = int(value // width)
    if index < 0:
        return 0
    if index >= len(edges):
        return len(edges) - 1
    return index


def _add_to_bins(
    bins: list[dict[str, Any]],
    edges: list[tuple[float, float]],
    value: float,
    amount: float,
    lots: float,
) -> None:
    index = _bin_index(value, edges)
    if index is None:
        return
    cell = bins[index]
    cell["count"] += 1
    cell["amount"] += amount
    cell["volume_lots"] += lots


def _finalize_bins(bins: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "lo": cell["lo"],
            "hi": cell["hi"],
            "count": cell["count"],
            "amount": _num(cell["amount"]),
            "volume_lots": _num(cell["volume_lots"]),
        }
        for cell in bins
    ]


def _samples(rows: Iterable[dict[str, Any]], floor_amount: float) -> list[tuple[str, float, float]]:
    """门槛过滤 + 象限归类，返回 ``(event, amount, lots)``。"""
    out: list[tuple[str, float, float]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        amount = to_float(row.get("amount")) or 0.0
        if amount <= 0 or amount < floor_amount:
            continue
        event = classify_event(row)
        if not event:
            continue
        lots = to_float(row.get("volume_lots")) or 0.0
        if lots <= 0:
            lots = (to_float(row.get("volume")) or 0.0) / 100.0
        out.append((event, amount, lots))
    return out


def aggregate_big_deals(
    rows: Iterable[dict[str, Any]],
    *,
    min_amount: float = 10_000_000,
    bin_by: str = DEFAULT_BIN_BY,
) -> dict[str, Any]:
    """对「门槛过滤后」的全量明细做四象限汇总与分箱。

    返回四象限（含可选 ``amount_bins`` / ``lots_bins``）、买卖合计、
    ``net_amount`` / ``active_net_amount`` 与 ``total_count``。买卖合计只给
    总量不挂分箱；无法归类的明细不计入任何统计。
    """
    mode = normalize_bin_by(bin_by)
    floor_amount = max(to_float(min_amount) or 0.0, 0.0)
    samples = _samples(rows, floor_amount)

    amount_edges = build_step_edges(max((a for _, a, _ in samples), default=0.0), AMOUNT_STEP)
    lots_edges = build_step_edges(max((v for _, _, v in samples), default=0.0), LOTS_STEP)
    want_amount_bins = mode in {"amount", "both"}
    want_lots_bins = mode in {"lots", "both"}

    buckets: dict[str, dict[str, Any]] = {}
    for event in EVENT_TYPES:
        bucket: dict[str, Any] = {"count": 0, "amount": 0.0, "volume_lots": 0.0}
        if want_amount_bins:
            bucket["amount_bins"] = _new_bins(amount_edges)
        if want_lots_bins:
            bucket["lots_bins"] = _new_bins(lots_edges)
        buckets[event] = bucket

    for event, amount, lots in samples:
        bucket = buckets[event]
        bucket["count"] += 1
        bucket["amount"] += amount
        bucket["volume_lots"] += lots
        if want_amount_bins:
            _add_to_bins(bucket["amount_bins"], amount_edges, amount, amount, lots)
        if want_lots_bins:
            _add_to_bins(bucket["lots_bins"], lots_edges, lots, amount, lots)

    def _side(side: str) -> dict[str, Any]:
        keys = (f"active_{side}", f"passive_{side}")
        return {
            "count": sum(buckets[key]["count"] for key in keys),
            "amount": _num(sum(buckets[key]["amount"] for key in keys)),
            "volume_lots": _num(sum(buckets[key]["volume_lots"] for key in keys)),
        }

    quadrants: dict[str, Any] = {}
    for event in EVENT_TYPES:
        bucket = buckets[event]
        item: dict[str, Any] = {
            "count": bucket["count"],
            "amount": _num(bucket["amount"]),
            "volume_lots": _num(bucket["volume_lots"]),
        }
        if want_amount_bins:
            item["amount_bins"] = _finalize_bins(bucket["amount_bins"])
        if want_lots_bins:
            item["lots_bins"] = _finalize_bins(bucket["lots_bins"])
        quadrants[event] = item

    buy = _side("buy")
    sell = _side("sell")
    net_amount = _num(float(buy["amount"]) - float(sell["amount"]))
    active_net = _num(
        float(quadrants["active_buy"]["amount"]) - float(quadrants["active_sell"]["amount"])
    )

    return {
        "total_count": len(samples),
        "bin_by": mode,
        "amount_step": AMOUNT_STEP,
        "lots_step": LOTS_STEP,
        **quadrants,
        "buy": buy,
        "sell": sell,
        "net_amount": net_amount,
        "active_net_amount": active_net,
    }