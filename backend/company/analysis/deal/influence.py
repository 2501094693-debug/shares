"""大单影响区间 `I(o)` 与「最小连续区间簇」。

两层含义
--------
1. **影响区间**：一张大单的全部手数必须落在一个连续块里，块右端又必须落在
   它的候选截止窗内，于是「块可能触及」的手数区间是

       I(o) = [ L* + 1 - q , R* )

   其中 ``L* = min{L_d}``、``R* = max{R_d}``，`q` 是手数。

2. **连续区间簇**：按**窗口粒度**做连通分量 —— 两张单的影响区间触及同一
   分时窗就并簇，簇跨度 = 覆盖到的最外两个窗口的完整区间。

为什么按窗而不是按手数区间合并
------------------------------
- 按手数区间合并得到的凸包可能从窗口中间起止，于是同一个分时窗被两个簇共享，
  窗的笔数预算 ``count_w`` 变成耦合资源，逐簇独立求解就不成立了。
- 按窗口合并的跨度都是完整窗口，**每个窗只属于一个簇**，簇间零耦合：
  全局可行 ⟺ 各簇分别可行。
- 这也不损失最小性：影响区间严格重叠的两张单必然落在同一窗里，按窗合并本来
  就会并；把同窗内两个不相交的影响区间拆开，两个簇的跨度都将被迫覆盖整窗而
  互相重叠 —— 所以「按窗合并」就是跨度意义下的最小划分。

**命题**（唯一性）：若簇 C 含 `o` 而 `o' ∉ C`，且 `I(o) ∩ I(o') ≠ ∅`，则
`I(o')` 与 `span(C)` 相交，违反「包含或不相交」。故任何合法划分必然把重叠的
影响区间放进同一簇 —— 连通分量划分既必要又唯一。
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Any

from company.analysis.deal.util import _deadline_indices, _lots_int


class AxisIndex:
    """窗坐标索引：把「影响区间 → 触及窗 / 截止窗」的定位降到对数级。"""

    __slots__ = ("windows", "stamps", "lefts", "rights")

    def __init__(self, windows: list[dict[str, Any]]) -> None:
        self.windows = windows
        self.stamps = [str(window["time"]) for window in windows]
        self.lefts = [int(window["L"]) for window in windows]
        self.rights = [int(window["R"]) for window in windows]

    def touches(self, lo: int, hi: int) -> list[int]:
        """``[lo, hi)`` 与哪些窗的手数区间相交。"""
        if lo >= hi or not self.rights:
            return []
        start = bisect.bisect_right(self.rights, lo)
        end = bisect.bisect_left(self.lefts, hi)
        if end <= start:
            return []
        return list(range(start, end))

    def window_of(self, pos: int) -> int:
        """``L <= pos < R`` 的窗下标；越界时贴到首/尾窗。"""
        if not self.rights:
            return 0
        index = bisect.bisect_right(self.rights, pos)
        return min(index, len(self.rights) - 1)


def _index_of(
    axis_windows: list[dict[str, Any]], index: AxisIndex | None
) -> AxisIndex:
    return index if index is not None else AxisIndex(axis_windows)


@dataclass
class InfluenceCluster:
    """影响连通分量对应的最小连续手数区间（窗口对齐）。"""

    span: tuple[int, int]
    window_indices: list[int] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1


def _order_deadline_end_bounds(
    order: dict[str, Any],
    axis_windows: list[dict[str, Any]],
    *,
    max_lookback: int = 0,
    index: AxisIndex | None = None,
) -> tuple[list[int], int, int, int] | None:
    """候选截止窗下标 + ``(right_lo, right_hi, left_min)``。

    分时档按两端闭区间衔接，档点完成时刻可归相邻两档，右端域是两档
    ``(L, R]`` 的并集 → ``[min L + 1, max R]``。
    """
    if not axis_windows:
        return None
    idx = _index_of(axis_windows, index)
    indices = [
        i
        for i in _deadline_indices(idx.stamps, str(order.get("time") or ""))
        if 0 <= i < len(axis_windows)
    ]
    if not indices:
        return None
    right_lo = min(idx.lefts[i] for i in indices) + 1
    right_hi = max(idx.rights[i] for i in indices)
    left_min = 0
    if max_lookback and max_lookback > 0:
        earliest = max(0, min(indices) - int(max_lookback))
        left_min = idx.lefts[earliest]
    return indices, right_lo, right_hi, left_min


def order_influence_range(
    order: dict[str, Any],
    axis_windows: list[dict[str, Any]],
    *,
    max_lookback: int = 0,
    index: AxisIndex | None = None,
) -> tuple[int, int]:
    """大单影响区间 ``I(o) = [lo, hi)``（手数坐标，半开）。

    块长 ``q``、右端 ``e ∈ [right_lo, right_hi]``，故块可能触及的区间是
    ``[right_lo - q, right_hi)``（左端不早于 ``left_min`` / 0）。
    """
    if not axis_windows:
        return (0, 0)
    lots = _lots_int(order.get("lots"))
    if lots <= 0:
        return (0, 0)
    idx = _index_of(axis_windows, index)
    bounds = _order_deadline_end_bounds(
        order, axis_windows, max_lookback=max_lookback, index=idx
    )
    if bounds is None:
        return (0, 0)
    _indices, right_lo, right_hi, left_min = bounds
    total_v = idx.rights[-1]
    lo = right_lo - lots
    if left_min > 0:
        lo = max(lo, left_min)
    lo = max(0, lo)
    hi = min(total_v, right_hi)
    if lo >= hi:
        return (lo, lo)
    return (lo, hi)


def order_touched_windows(
    order: dict[str, Any],
    axis_windows: list[dict[str, Any]],
    *,
    max_lookback: int = 0,
    index: AxisIndex | None = None,
) -> list[int]:
    """``W(o)``：影响区间触及的窗下标（升序）。"""
    idx = _index_of(axis_windows, index)
    lo, hi = order_influence_range(
        order, axis_windows, max_lookback=max_lookback, index=idx
    )
    return idx.touches(lo, hi)


def build_influence_clusters(
    orders: list[dict[str, Any]],
    axis_windows: list[dict[str, Any]],
    *,
    max_lookback: int = 0,
) -> list[InfluenceCluster]:
    """按触及窗交集建连通分量；买卖同图；簇跨度是触及窗的最小连续覆盖。"""
    if not axis_windows or not orders:
        return []

    idx = AxisIndex(axis_windows)
    usable: list[dict[str, Any]] = []
    touched: list[list[int]] = []
    for order in orders:
        lo, hi = order_influence_range(
            order, axis_windows, max_lookback=max_lookback, index=idx
        )
        windows = idx.touches(lo, hi)
        if not windows:
            continue
        usable.append(order)
        touched.append(windows)

    n = len(usable)
    if n == 0:
        return []

    uf = _UnionFind(n)
    window_owners: dict[int, list[int]] = {}
    for i, wins in enumerate(touched):
        for w in wins:
            owners = window_owners.setdefault(w, [])
            for j in owners:
                uf.union(i, j)
            owners.append(i)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    clusters: list[InfluenceCluster] = []
    for indices in groups.values():
        win_set: set[int] = set()
        for i in indices:
            win_set.update(touched[i])
        if not win_set:
            continue
        lo_i, hi_i = min(win_set), max(win_set)
        clusters.append(
            InfluenceCluster(
                span=(idx.lefts[lo_i], idx.rights[hi_i]),
                window_indices=list(range(lo_i, hi_i + 1)),
                orders=[usable[i] for i in indices],
            )
        )

    clusters.sort(key=lambda c: (c.span[0], c.span[1]))
    return clusters


__all__ = [
    "AxisIndex",
    "InfluenceCluster",
    "build_influence_clusters",
    "order_influence_range",
    "order_touched_windows",
]
