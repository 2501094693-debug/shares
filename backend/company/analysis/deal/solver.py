"""簇内一次性联合落位 + 牺牲降级。

窗内展开见 ``emit`` 模块。
"""

from __future__ import annotations

import bisect
import math
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from company.analysis.deal.constants import (
    DEFAULT_MIN_LOTS,
    DEFAULT_TRADE_THRESHOLD,
    PRICE_EPS,
    ROLE_ACTIVE,
    ROLE_OTHER,
    ROLE_PASSIVE,
)
from company.analysis.deal.cost import (
    count_checked,
    window_cost,
    window_count,
)
from company.analysis.deal.influence import (
    AxisIndex,
    InfluenceCluster,
    build_influence_clusters,
    order_influence_range,
)
from company.analysis.deal.util import (
    _f,
    _lots_int,
    _same_price,
    _stamp_key,
    role_of,
)


def _clip(
    blocks: list[tuple[int, int, str]], left: int, right: int
) -> list[tuple[int, int, str]]:
    """``[left, right)`` 内的块（``blocks`` 按 start 有序 → 二分定位）。"""
    if left >= right or not blocks:
        return []
    hi = bisect.bisect_left(blocks, (right,))
    lo = hi
    while lo > 0 and blocks[lo - 1][1] > left:
        lo -= 1
    return [
        (max(a, left), min(b, right), oid)
        for a, b, oid in blocks[lo:hi]
        if b > left
    ]


def _free_gaps(
    blocks: list[tuple[int, int, str]], left: int, right: int
) -> list[tuple[int, int]]:
    """``[left, right)`` 内的空闲间隙（同层块互不重叠，按 start 有序）。"""
    if left >= right:
        return []
    gaps: list[tuple[int, int]] = []
    cursor = left
    for a, b, _oid in _clip(blocks, left, right):
        if b <= cursor:
            continue
        if a > cursor:
            gaps.append((cursor, a))
        cursor = max(cursor, b)
        if cursor >= right:
            break
    if cursor < right:
        gaps.append((cursor, right))
    return gaps


def _cross_lots(
    opp: list[tuple[int, int, str]],
    prices: Mapping[str, float],
    start: int,
    end: int,
    price: float,
) -> int:
    """候选块与对层**同价**块的重叠手数（交叉原子只算 1 行 → 越多越省笔数）。"""
    if start >= end or price <= 0:
        return 0
    total = 0
    for a, b, oid in _clip(opp, start, end):
        if _same_price(_f(prices.get(oid)), price):
            total += b - a
    return total


class Occupancy:
    """同侧已占用区间（半开，按 start 有序）。"""

    __slots__ = ("intervals",)

    def __init__(self) -> None:
        self.intervals: list[tuple[int, int, str]] = []

    def add(self, start: int, end: int, order_id: str) -> None:
        if start >= end:
            return
        self.intervals.append((start, end, order_id))
        self.intervals.sort(key=lambda item: item[0])

    def get(self, order_id: str) -> tuple[int, int] | None:
        for start, end, oid in self.intervals:
            if oid == order_id:
                return start, end
        return None

    def clip_to_window(self, left: int, right: int) -> list[tuple[int, int, str]]:
        return _clip(self.intervals, left, right)

@dataclass
class _Slot:
    oid: str
    src: Mapping[str, Any]
    side: str
    price: float
    need: int
    lo: int
    hi: int
    role: str
    windows: list[int] = field(default_factory=list)


@dataclass
class SolveResult:
    ok: bool = False
    level: int = 0
    blocks: dict[str, tuple[int, int]] = field(default_factory=dict)
    unplaced: list[dict[str, Any]] = field(default_factory=list)
    sacrifices: list[dict[str, Any]] = field(default_factory=list)
    nodes: int = 0
    reason: str = ""


class _Budget(Exception):
    """搜索预算（节点数 / 墙钟）耗尽。"""


class _Layout:
    """DFS 中的落位状态：两层块 + 价格。"""

    __slots__ = ("buy", "sell", "pos", "prices")

    def __init__(self) -> None:
        self.buy: list[tuple[int, int, str]] = []
        self.sell: list[tuple[int, int, str]] = []
        self.pos: dict[str, tuple[int, int]] = {}
        self.prices: dict[str, float] = {}

    def side(self, side: str) -> list[tuple[int, int, str]]:
        return self.buy if side == "buy" else self.sell

    def other(self, side: str) -> list[tuple[int, int, str]]:
        return self.sell if side == "buy" else self.buy

    def place(self, slot: _Slot, start: int, end: int) -> None:
        blocks = self.side(slot.side)
        index = 0
        while index < len(blocks) and blocks[index][0] < start:
            index += 1
        blocks.insert(index, (start, end, slot.oid))
        self.pos[slot.oid] = (start, end)
        self.prices[slot.oid] = slot.price

    def unplace(self, slot: _Slot) -> None:
        blocks = self.side(slot.side)
        for index, (_a, _b, oid) in enumerate(blocks):
            if oid == slot.oid:
                blocks.pop(index)
                break
        self.pos.pop(slot.oid, None)
        self.prices.pop(slot.oid, None)


class ClusterSolver:
    """单簇联合求解 + 牺牲降级。"""

    def __init__(
        self,
        cluster: InfluenceCluster,
        axis_windows: list[dict[str, Any]],
        *,
        threshold: float = DEFAULT_TRADE_THRESHOLD,
        min_lots: float = DEFAULT_MIN_LOTS,
        max_lookback: int = 0,
        budget_nodes: int = 20_000,
        budget_ms: int = 400,
        candidate_k: int = 8,
        dfs_max_slots: int = 64,
        polish_max_slots: int = 40,
        greedy_max_slots: int = 400,
    ) -> None:
        self.cluster = cluster
        self.axis = axis_windows
        self.threshold = threshold
        self.min_lots = min_lots
        self.max_lookback = max_lookback
        self.budget_nodes = max(64, int(budget_nodes))
        self.budget_ms = max(0, int(budget_ms))
        self.candidate_k = max(1, int(candidate_k))
        self.dfs_max_slots = max(1, int(dfs_max_slots))
        self.polish_max_slots = max(0, int(polish_max_slots))
        self.greedy_max_slots = max(self.dfs_max_slots, int(greedy_max_slots))
        self._k = self.candidate_k
        self._nodes_left = self.budget_nodes
        self._deadline = 0.0
        self.slots: list[_Slot] = []
        self.by_id: dict[str, _Slot] = {}
        self.index = AxisIndex(axis_windows)
        # 窗 → 该窗内出现过的 (side, price)：搜索中途用它做「乐观交叉」下界
        self._win_prices: dict[int, set[tuple[str, float]]] = {}
        for order in cluster.orders:
            oid = str(order.get("order_id") or "")
            need = _lots_int(order.get("lots"))
            if not oid or need <= 0:
                continue
            lo, hi = order_influence_range(
                order, axis_windows, max_lookback=max_lookback, index=self.index
            )
            if lo >= hi:
                continue
            slot = _Slot(
                oid=oid,
                src=order,
                side="buy" if str(order.get("side") or "buy") == "buy" else "sell",
                price=_f(order.get("price")),
                need=need,
                lo=int(lo),
                hi=int(hi),
                role=role_of(order),
                windows=self.index.touches(int(lo), int(hi)),
            )
            self.slots.append(slot)
            self.by_id[oid] = slot
            if slot.price > 0:
                key = (slot.side, round(slot.price, 4))
                opposite = ("sell" if slot.side == "buy" else "buy", round(slot.price, 4))
                for index in slot.windows:
                    self._win_prices.setdefault(index, set()).add(key)
        # 只保留「本窗确有同价对层单」的价格集合（乐观交叉的前提）
        for index, present in list(self._win_prices.items()):
            crossable = {
                (side, px)
                for side, px in present
                if ("sell" if side == "buy" else "buy", px) in present
            }
            if crossable:
                self._win_prices[index] = crossable
            else:
                self._win_prices.pop(index, None)

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    def _expired(self) -> bool:
        return self.budget_ms > 0 and time.monotonic() > self._deadline

    def _budget_out(self) -> bool:
        return self._nodes_left <= 0 or self._expired()

    def _window_cost(
        self, index: int, layout: _Layout, *, optimistic: bool = True
    ) -> WindowCost:
        window = self.axis[index]
        left, right = int(window["L"]), int(window["R"])
        return window_cost(
            window,
            _clip(layout.buy, left, right),
            _clip(layout.sell, left, right),
            threshold=self.threshold,
            min_lots=self.min_lots,
            prices=layout.prices,
            optimistic=self._win_prices.get(index) if optimistic else None,
        )

    def _window_ok(
        self, index: int, layout: _Layout, *, optimistic: bool = True
    ) -> bool:
        window = self.axis[index]
        if not count_checked(window):
            return True
        cost = self._window_cost(index, layout, optimistic=optimistic)
        return cost.rows_min <= window_count(window)

    def _touched_ok(
        self, slot: _Slot, layout: _Layout, *, optimistic: bool = True
    ) -> bool:
        for index in slot.windows:
            if not self._window_ok(index, layout, optimistic=optimistic):
                return False
        return True

    def _leaf_ok(self, layout: _Layout) -> bool:
        """叶子验收：所有波及窗都按「单侧必须拆行」精确判定。"""
        for index in self.cluster.window_indices:
            if not self._window_ok(index, layout, optimistic=False):
                return False
        return True

    def _candidates(self, slot: _Slot, q: int, layout: _Layout) -> list[tuple[int, int]]:
        if q <= 0:
            return []
        same = layout.side(slot.side)
        opp = layout.other(slot.side)
        opp_near = _clip(opp, max(0, slot.lo - q), slot.hi)
        points: list[int] = []
        seen: set[int] = set()
        for gap_l, gap_r in _free_gaps(same, slot.lo, slot.hi):
            lo_s = gap_l
            hi_s = min(gap_r, slot.hi) - q
            if lo_s > hi_s:
                continue
            cand = {lo_s, hi_s}
            for index in slot.windows:
                window = self.axis[index]
                cand.add(int(window["L"]))
                cand.add(int(window["R"]) - q)
            for a, b, _oid in opp_near:
                cand.add(a)
                cand.add(b)
                cand.add(a - q)
                cand.add(b - q)
            for s in cand:
                if not (lo_s <= s <= hi_s) or s in seen:
                    continue
                seen.add(s)
                points.append(s)
        out: list[tuple[int, int]] = []
        for start in points:
            end = start + q
            out.append((start, end))
        out.sort(
            key=lambda se: (
                -_cross_lots(opp_near, layout.prices, se[0], se[1], slot.price),
                -se[1],
                se[0],
            )
        )
        return out[: self._k]

    def _dfs(
        self,
        index: int,
        seq: list[_Slot],
        assign: Mapping[str, int],
        layout: _Layout,
    ) -> bool:
        self._nodes_left -= 1
        if self._nodes_left <= 0 or self._expired():
            raise _Budget("budget")
        if index >= len(seq):
            return self._leaf_ok(layout)
        slot = seq[index]
        q = int(assign[slot.oid])
        for start, end in self._candidates(slot, q, layout):
            layout.place(slot, start, end)
            if self._touched_ok(slot, layout) and self._dfs(
                index + 1, seq, assign, layout
            ):
                return True
            layout.unplace(slot)
        return False

    def _sequence(self, assign: Mapping[str, int]) -> list[_Slot]:
        slots = [slot for slot in self.slots if int(assign.get(slot.oid, 0)) > 0]
        slots.sort(
            key=lambda slot: (
                slot.hi - slot.lo - int(assign[slot.oid]),
                -int(assign[slot.oid]),
                slot.price,
                slot.side,
                slot.oid,
            )
        )
        return slots

    def _attempt(
        self,
        assign: Mapping[str, int],
        *,
        k: int | None = None,
    ) -> dict[str, tuple[int, int]] | None:
        if self._budget_out():
            return None
        seq = self._sequence(assign)
        if not seq:
            return {}
        layout = _Layout()
        # K=1 是单路径（线性）放置，等价于「优先撮合」的联合贪心；
        # 回溯在几百张单上是指数爆炸，所以大簇只用 K=1。
        if k is None:
            k = self.candidate_k if len(seq) <= self.dfs_max_slots else 1
        self._k = max(1, int(k))
        try:
            ok = self._dfs(0, seq, assign, layout)
        except _Budget:
            return None
        return dict(layout.pos) if ok else None

    def _try_place(
        self, slot: _Slot, q: int, layout: _Layout
    ) -> tuple[int, int] | None:
        """尝试以手数 ``q`` 落位；成功返回 ``(start, end)``，失败返回 ``None``。"""
        if q <= 0:
            return None
        for start, end in self._candidates(slot, q, layout):
            layout.place(slot, start, end)
            if self._touched_ok(slot, layout, optimistic=False):
                return start, end
            layout.unplace(slot)
        return None

    def _greedy_fill(
        self,
        assign: Mapping[str, int],
        sacrifices: list[dict[str, Any]],
    ) -> dict[str, tuple[int, int]]:
        """兜底：按序尽量放——**不放松笔数/门槛约束**。

        - **主动先于被动**：与正式牺牲序一致，避免被动先占轴把主动挤掉；
        - 被动 / other：能缩就缩、缩不动才去除；
        - 主动：**只去不缩**（满放失败则整张丢弃）；
        - 预算耗尽或簇太大时用它收尾：宁可少归因一单，也不往窗里塞超 30 万的小单行。
        """
        layout = _Layout()
        self._k = 1
        seq = self._sequence(assign)
        # 主动优先满放，再处理被动/other（与 solve 牺牲序「先被动缩、后主动去」对齐：
        # 兜底路径没有回溯，只能靠放置顺序保护主动）。
        ordered = [s for s in seq if s.role == ROLE_ACTIVE] + [
            s for s in seq if s.role != ROLE_ACTIVE
        ]
        for slot in ordered:
            need = int(assign[slot.oid])
            if need <= 0:
                continue
            if self._try_place(slot, need, layout) is not None:
                continue
            # 主动：满放失败 → 整张去除，绝不缩量
            if slot.role == ROLE_ACTIVE:
                sacrifices.append(
                    {
                        "order_id": slot.oid,
                        "action": "drop",
                        "stage": "budget",
                        "from": need,
                        "to": 0,
                    }
                )
                continue
            # 被动 / other：二分缩量
            placed = 0
            q = need // 2
            while q >= 1:
                if self._try_place(slot, q, layout) is not None:
                    placed = q
                    break
                q //= 2
            sacrifices.append(
                {
                    "order_id": slot.oid,
                    "action": "shrink" if placed else "drop",
                    "stage": "budget",
                    "from": need,
                    "to": placed,
                }
            )
        return dict(layout.pos)

    # ------------------------------------------------------------------
    # 牺牲序列
    # ------------------------------------------------------------------

    def _passive_slots(self) -> list[_Slot]:
        """被动 + 未标注主被动的 other（与 axis 路径的 passive_like 一致）。"""
        pick = [s for s in self.slots if s.role != ROLE_ACTIVE]
        pick.sort(key=lambda s: (-s.need, str(s.src.get("time") or ""), s.oid))
        return pick

    def _active_slots(self) -> list[_Slot]:
        pick = [s for s in self.slots if s.role == ROLE_ACTIVE]
        pick.sort(key=lambda s: (s.need, str(s.src.get("time") or ""), s.oid))
        return pick

    def _shrink_or_drop(
        self,
        slot: _Slot,
        assign: dict[str, int],
        sacrifices: list[dict[str, Any]],
    ) -> dict[str, tuple[int, int]] | None:
        """先缩（二分最大可解手数），缩不了就整张去除。"""
        need = int(assign[slot.oid])
        lo, hi = 0, need  # hi 已知不可行
        picked: tuple[int, dict[str, tuple[int, int]]] | None = None
        while hi - lo > 1:
            if self._budget_out():
                break
            mid = (lo + hi) // 2
            trial = dict(assign)
            trial[slot.oid] = mid
            found = self._attempt(trial)
            if found is not None:
                picked = (mid, found)
                lo = mid
            else:
                hi = mid
        if picked is not None:
            assign[slot.oid] = picked[0]
            sacrifices.append(
                {
                    "order_id": slot.oid,
                    "action": "shrink",
                    "stage": slot.role,
                    "from": need,
                    "to": picked[0],
                }
            )
            return picked[1]
        assign[slot.oid] = 0
        sacrifices.append(
            {
                "order_id": slot.oid,
                "action": "drop",
                "stage": slot.role,
                "from": need,
                "to": 0,
            }
        )
        return self._attempt(assign)

    def _polish(
        self, blocks: dict[str, tuple[int, int]], assign: Mapping[str, int]
    ) -> dict[str, tuple[int, int]]:
        """在保持可行的前提下，把同价交叉手数做大（「簇内尽量撮合」）。"""
        if not blocks or len(self.slots) > self.polish_max_slots:
            return blocks
        layout = _Layout()
        for slot in sorted(self.slots, key=lambda s: s.oid):
            span = blocks.get(slot.oid)
            if span:
                layout.place(slot, span[0], span[1])
        for slot in sorted(self.slots, key=lambda s: -int(assign.get(s.oid, 0))):
            current = layout.pos.get(slot.oid)
            if current is None:
                continue
            q = current[1] - current[0]
            opp = layout.other(slot.side)
            base = _cross_lots(
                opp, layout.prices, current[0], current[1], slot.price
            )
            layout.unplace(slot)
            target = current
            best = base
            for start, end in self._candidates(slot, q, layout):
                layout.place(slot, start, end)
                ok = self._touched_ok(slot, layout, optimistic=False)
                crossed = _cross_lots(
                    layout.other(slot.side),
                    layout.prices,
                    start,
                    end,
                    slot.price,
                )
                layout.unplace(slot)
                if ok and crossed > best:
                    best = crossed
                    target = (start, end)
                    break
            layout.place(slot, target[0], target[1])
        return dict(layout.pos)

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------

    def solve(self) -> SolveResult:
        self._deadline = time.monotonic() + self.budget_ms / 1000.0
        self._nodes_left = self.budget_nodes
        assign: dict[str, int] = {slot.oid: slot.need for slot in self.slots}
        sacrifices: list[dict[str, Any]] = []
        level = 0
        reason = ""

        # 超大簇（几百张单串成一条影响链）全局搜索无意义：直接逐张贪心 + 必要时缩量。
        if len(self.slots) > self.greedy_max_slots:
            blocks = self._greedy_fill(assign, sacrifices)
            return SolveResult(
                ok=bool(blocks),
                level=0 if not sacrifices else 3,
                blocks=blocks,
                nodes=0,
                reason="" if not sacrifices else "greedy_fallback",
                sacrifices=sacrifices,
                unplaced=self._unplaced(assign, blocks, sacrifices),
            )

        # 1) 单路径（K=1）联合贪心：线性时间，绝大多数簇一次就成
        best = self._attempt(assign, k=1)
        # 2) 小簇才值得回溯找更优排列
        if best is None and len(self.slots) <= self.dfs_max_slots:
            best = self._attempt(assign)

        # 3) 牺牲序列：被动（大→小）先缩量、缩不动去除；再去主动（小→大）
        if best is None:
            level = 1
            for slot in self._passive_slots():
                if best is not None or self._budget_out():
                    break
                best = self._shrink_or_drop(slot, assign, sacrifices)

        if best is None:
            level = 2
            for slot in self._active_slots():
                if best is not None or self._budget_out():
                    break
                assign[slot.oid] = 0
                sacrifices.append(
                    {
                        "order_id": slot.oid,
                        "action": "drop",
                        "stage": "active",
                        "from": slot.need,
                        "to": 0,
                    }
                )
                best = self._attempt(assign)

        # 4) 预算耗尽仍无解 → 保持约束的兜底：放不下的整张去除
        if best is None:
            level = 3
            reason = "budget_fallback"
            assign = {slot.oid: slot.need for slot in self.slots}
            best = self._greedy_fill(assign, sacrifices)
        elif level:
            reason = "degraded"

        if best:
            best = self._polish(best, assign)

        result = SolveResult(
            ok=bool(best),
            level=level,
            blocks=best or {},
            nodes=max(0, self.budget_nodes - self._nodes_left),
            reason=reason,
            sacrifices=sacrifices,
        )
        result.unplaced = self._unplaced(assign, result.blocks, sacrifices)
        return result

    def _unplaced(
        self,
        assign: Mapping[str, int],
        blocks: Mapping[str, tuple[int, int]],
        sacrifices: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        reason_by_id = {str(s["order_id"]): s for s in sacrifices}
        out: list[dict[str, Any]] = []
        for slot in self.slots:
            got = 0
            span = blocks.get(slot.oid)
            if span:
                got = span[1] - span[0]
            if got >= slot.need:
                continue
            mark = reason_by_id.get(slot.oid) or {}
            action = str(mark.get("action") or "")
            stage = str(mark.get("stage") or "")
            if action == "drop":
                reason = f"dropped_{stage}_first" if stage else "dropped"
            elif action:
                reason = f"shrunk_{stage}_first" if stage else action
            else:
                reason = "no_feasible_slot"
            out.append(
                {
                    "order_id": slot.oid,
                    "time": slot.src.get("time"),
                    "missing": float(slot.need - got),
                    "reason": reason,
                    "side": slot.side,
                    "placed": float(got),
                    "role": slot.role,
                }
            )
        return out


def _deadline_index(
    axis_windows: list[dict[str, Any]], end: int, windows: Iterable[int]
) -> int:
    """右端 ``end`` 落在哪个截止窗（``L < end <= R``）。"""
    last = 0
    for index in windows:
        last = index
        window = axis_windows[index]
        if int(window["L"]) < end <= int(window["R"]):
            return index
    return last


def place_joint(
    axis_windows: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    *,
    threshold: float = DEFAULT_TRADE_THRESHOLD,
    min_lots: float = DEFAULT_MIN_LOTS,
    max_lookback: int = 0,
    budget_nodes: int = 20_000,
    budget_ms: int = 400,
    candidate_k: int = 8,
) -> tuple[
    Occupancy, Occupancy, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]
]:
    """把所有大单按「最小连续簇」逐簇一次性联合落位。

    返回 ``(buy_occ, sell_occ, placed, unplaced, report)``；
    ``placed`` 项与旧路径同构：``order/side/start/end/lots/deadline_index``。
    """
    report: dict[str, Any] = {
        "clusters": 0,
        "cluster_detail": [],
        "sacrifices": [],
        "infeasible_windows": [],
        "nodes": 0,
        "degraded_clusters": 0,
        "fallback_clusters": 0,
    }
    buy_occ = Occupancy()
    sell_occ = Occupancy()
    placed: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []

    if not axis_windows:
        for order in orders:
            unplaced.append(
                {
                    "order_id": str(order.get("order_id") or ""),
                    "time": order.get("time"),
                    "missing": float(_lots_int(order.get("lots"))),
                    "reason": "no_windows",
                }
            )
        return buy_occ, sell_occ, placed, unplaced, report

    clusters = build_influence_clusters(
        orders, axis_windows, max_lookback=max_lookback
    )
    clustered: set[str] = set()
    for cluster in clusters:
        solver = ClusterSolver(
            cluster,
            axis_windows,
            threshold=threshold,
            min_lots=min_lots,
            max_lookback=max_lookback,
            budget_nodes=budget_nodes,
            budget_ms=budget_ms,
            candidate_k=candidate_k,
        )
        if not solver.slots:
            continue
        result = solver.solve()
        report["nodes"] += result.nodes
        if result.level == 3:
            report["fallback_clusters"] += 1
        elif result.level:
            report["degraded_clusters"] += 1
        report["sacrifices"].extend(result.sacrifices)
        report["clusters"] += 1

        for slot in solver.slots:
            clustered.add(slot.oid)
            span = result.blocks.get(slot.oid)
            if not span:
                continue
            start, end = int(span[0]), int(span[1])
            occ = buy_occ if slot.side == "buy" else sell_occ
            occ.add(start, end, slot.oid)
            placed.append(
                {
                    "order": slot.src,
                    "side": slot.side,
                    "start": start,
                    "end": end,
                    "lots": float(end - start),
                    "deadline_index": _deadline_index(
                        axis_windows, end, slot.windows
                    ),
                    "role": slot.role,
                }
            )
        unplaced.extend(result.unplaced)

        detail = {
            "span": [int(cluster.span[0]), int(cluster.span[1])],
            "windows": [int(cluster.window_indices[0]), int(cluster.window_indices[-1])],
            "orders": len(cluster.orders),
            "level": result.level,
            "nodes": result.nodes,
            "reason": result.reason,
        }
        over: list[dict[str, Any]] = []
        price_map = {
            str(meta["order"].get("order_id")): _f(meta["order"].get("price"))
            for meta in placed
        }
        for index in cluster.window_indices:
            window = axis_windows[index]
            left, right = int(window["L"]), int(window["R"])
            cost = window_cost(
                window,
                buy_occ.clip_to_window(left, right),
                sell_occ.clip_to_window(left, right),
                threshold=threshold,
                min_lots=min_lots,
                prices=price_map,
            )
            if count_checked(window) and cost.rows_min > window_count(window):
                over.append(
                    {
                        "time": window["time"],
                        "need_rows": cost.rows_min,
                        "count": window_count(window),
                        "reason": "count_infeasible",
                    }
                )
        if over:
            detail["infeasible"] = over
            report["infeasible_windows"].extend(over)
        report["cluster_detail"].append(detail)

    for order in orders:
        oid = str(order.get("order_id") or "")
        if not oid or oid in clustered:
            continue
        unplaced.append(
            {
                "order_id": oid,
                "time": order.get("time"),
                "missing": float(_lots_int(order.get("lots"))),
                "reason": "no_deadline",
                "side": "buy" if str(order.get("side") or "buy") == "buy" else "sell",
            }
        )

    placed.sort(
        key=lambda meta: (
            0 if meta.get("role") == ROLE_ACTIVE else (1 if meta.get("role") == ROLE_PASSIVE else 2),
            -float(meta["lots"]),
            int(meta["start"]),
        )
    )
    return buy_occ, sell_occ, placed, unplaced, report


__all__ = [
    "ClusterSolver",
    "Occupancy",
    "SolveResult",
    "place_joint",
]
