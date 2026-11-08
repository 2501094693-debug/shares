"""窗内「最少成交行数」判据：原子划分 + 30 万门槛手数上限。

模型
----
同一个分时窗 ``[L, R)`` 里，按买卖两层的大单块端点切成原子段，每段
``(buy_oid, sell_oid)`` 恒定：

- **交叉原子**（两侧都是大单、同价）→ 一笔成交同时服务两张单 → **1 行**，
  手数不受门槛限制（双方都在资金动向里）；
- **单侧原子**（只有一侧是大单）→ 对手只能是匿名小单 → 该行手数必须
  ``<= cap`` → 至少 ``ceil(lots / cap)`` 行；
- **纯小单段** → 同理至少 ``ceil(small_lots / cap)`` 行。

``cap`` = 单笔 30 万门槛折算的整手上限。只要一行里有一侧是匿名小单，这一行
的成交额就必须低于门槛，否则它本身就该出现在资金动向里 —— 这条推论把
「小单不能超过 30 万」从展示层的美化规则，变成**落位阶段必须事先满足的
可行性判据**：

    rows_min(w) <= count_w

「尽可能撮合大单」也落在这里：交叉原子只算 1 行，所以簇内让同价买卖块尽量
重叠，等于直接给窗笔数预算腾空间。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from company.analysis.deal.constants import (
    DEFAULT_MIN_LOTS,
    PRICE_EPS,
    SHARES_PER_LOT,
)
from company.analysis.deal.util import _lots_int

# 价格未知 / 门槛未设时的「无上限」手数
CAP_UNLIMITED = 10**9


def _f(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _ceil_div(lots: int, cap: int) -> int:
    if lots <= 0:
        return 0
    if cap <= 0:
        return lots
    return -(-lots // cap)


def cap_lots(
    threshold: float,
    price: float,
    *,
    min_lots: float = DEFAULT_MIN_LOTS,
) -> int:
    """单笔金额门槛对应的最大整手数（≥ 1）。

    ``threshold`` 是资金动向的收录门槛（默认 30 万），一手 = 100 股，
    所以 ``cap = floor(threshold / (price * 100))``。
    """
    floor = 1
    try:
        if min_lots and float(min_lots) > 0:
            floor = max(1, int(round(float(min_lots))))
    except (TypeError, ValueError):
        floor = 1
    px = _f(price)
    th = _f(threshold)
    if px <= 0 or th <= 0:
        return CAP_UNLIMITED
    raw = th / (px * SHARES_PER_LOT)
    if not math.isfinite(raw) or raw <= 0:
        return CAP_UNLIMITED
    return max(floor, int(math.floor(raw + 1e-9)))


def window_atoms(
    left: int,
    right: int,
    buy_clips: list[tuple[int, int, str]],
    sell_clips: list[tuple[int, int, str]],
) -> list[dict[str, Any]]:
    """把窗 ``[left, right)`` 按买卖占用切成原子段（同 buy/sell 编号合并）。

    ``buy_clips`` / ``sell_clips`` 是已裁到窗内的 ``(start, end, order_id)``。
    """
    if right <= left:
        return []
    cuts = {left, right}
    for a, b, _oid in buy_clips:
        cuts.add(max(left, a))
        cuts.add(min(right, b))
    for a, b, _oid in sell_clips:
        cuts.add(max(left, a))
        cuts.add(min(right, b))
    points = sorted(cuts)

    def _at(clips: list[tuple[int, int, str]], pos: int) -> str:
        for a, b, oid in clips:
            if a <= pos < b:
                return oid
        return ""

    atoms: list[dict[str, Any]] = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        if a >= b:
            continue
        b_oid = _at(buy_clips, a)
        s_oid = _at(sell_clips, a)
        if atoms and atoms[-1]["buy_oid"] == b_oid and atoms[-1]["sell_oid"] == s_oid:
            atoms[-1]["end"] = b
            atoms[-1]["lots"] = atoms[-1]["end"] - atoms[-1]["start"]
        else:
            atoms.append(
                {
                    "start": a,
                    "end": b,
                    "lots": b - a,
                    "buy_oid": b_oid,
                    "sell_oid": s_oid,
                }
            )
    return atoms


@dataclass
class WindowCost:
    """一个窗在给定占用下的笔数代价。"""

    rows_min: int = 0
    crossed_rows: int = 0
    single_rows: int = 0
    mixed_rows: int = 0
    small_rows: int = 0
    crossed_lots: int = 0
    mixed_lots: int = 0
    order_lots: int = 0  # 大单在窗内「计一次」的手数（交叉段只算一次）
    small_lots: int = 0
    price_conflict: bool = False
    atoms: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows_min": self.rows_min,
            "crossed_rows": self.crossed_rows,
            "single_rows": self.single_rows,
            "mixed_rows": self.mixed_rows,
            "small_rows": self.small_rows,
            "crossed_lots": self.crossed_lots,
            "mixed_lots": self.mixed_lots,
            "order_lots": self.order_lots,
            "small_lots": self.small_lots,
            "price_conflict": self.price_conflict,
        }


def window_cost(
    window: Mapping[str, Any],
    buy_clips: list[tuple[int, int, str]],
    sell_clips: list[tuple[int, int, str]],
    *,
    threshold: float,
    min_lots: float = DEFAULT_MIN_LOTS,
    prices: Mapping[str, float] | None = None,
    optimistic: set[tuple[str, float]] | None = None,
) -> WindowCost:
    """窗内最少成交行数。

    ``prices`` 给大单价格（单侧原子的 cap 按订单自己的价算，避免用料外的
    窗均价把上限放宽）。

    **异价重叠**（买卖都是大单但价格不同）不算交叉：一笔成交只能有一个价，
    展开时只能保留一侧的编号，另一侧退化为匿名小单，所以这一段的对手方是匿名的
    → 同样要按 ``cap`` 拆行（取两侧里更严的 cap，宁多不少）。

    ``optimistic`` 是「本窗还存在同价对层大单」的 ``(side, price)`` 集合：落位
    搜索中途对层单可能还没放进来，若按单侧计数会误杀「买卖一起放才可行」的解，
    所以把这类单侧原子按 1 行计（下界）。同时**不计残段小单行数**——未放完的
    大单还会填掉空档；只在叶子 ``optimistic=None`` 时把小单行算进 ``rows_min``。
    """
    left = int(window.get("L") or 0)
    right = int(window.get("R") or 0)
    win_price = _f(window.get("price"))
    price_of = prices or {}
    atoms = window_atoms(left, right, buy_clips, sell_clips)

    cost = WindowCost(atoms=atoms)
    for atom in atoms:
        lots_i = int(atom["lots"])
        b_oid = str(atom["buy_oid"] or "")
        s_oid = str(atom["sell_oid"] or "")
        if b_oid and s_oid:
            pb = _f(price_of.get(b_oid))
            ps = _f(price_of.get(s_oid))
            if pb > 0 and ps > 0 and abs(pb - ps) > PRICE_EPS:
                cost.price_conflict = True
                cap = min(
                    cap_lots(threshold, pb, min_lots=min_lots),
                    cap_lots(threshold, ps, min_lots=min_lots),
                )
                cost.mixed_rows += max(1, _ceil_div(lots_i, cap))
                cost.mixed_lots += lots_i
                cost.order_lots += lots_i
                continue
            cost.crossed_rows += 1
            cost.crossed_lots += lots_i
            cost.order_lots += lots_i
            continue
        if b_oid or s_oid:
            oid = b_oid or s_oid
            px = _f(price_of.get(oid)) or win_price
            side = "buy" if b_oid else "sell"
            cost.order_lots += lots_i
            if optimistic and (side, round(px, 4)) in optimistic:
                cost.crossed_rows += 1
                continue
            cap = cap_lots(threshold, px, min_lots=min_lots)
            cost.single_rows += max(1, _ceil_div(lots_i, cap))
            continue
        cost.small_lots += lots_i

    if cost.small_lots > 0:
        small_cap = cap_lots(threshold, win_price, min_lots=min_lots)
        cost.small_rows = max(1, _ceil_div(cost.small_lots, small_cap))

    # 搜索乐观下界：残段仍可能被后续大单填满，小单行数留给叶子精确验收
    small_for_min = 0 if optimistic is not None else cost.small_rows
    cost.rows_min = (
        cost.crossed_rows + cost.single_rows + cost.mixed_rows + small_for_min
    )
    return cost


def window_count(window: Mapping[str, Any]) -> int:
    return max(0, int(window.get("count") or 0))


def count_checked(window: Mapping[str, Any]) -> bool:
    """集合竞价窗的笔数是撮合外壳，不参与「行数 <= 笔数」判定。"""
    return not bool(window.get("auction"))


def window_ok(window: Mapping[str, Any], cost: WindowCost) -> bool:
    if not count_checked(window):
        return True
    return cost.rows_min <= window_count(window)


def check_rows_cap(
    rows: list[Mapping[str, Any]],
    *,
    threshold: float,
    min_lots: float = DEFAULT_MIN_LOTS,
) -> list[dict[str, Any]]:
    """R12：任何一侧是匿名小单的成交行，手数必须 <= cap（30 万门槛）。

    买卖双方都是真实大单（``order_id`` 与 ``order_id_peer`` 都在）的行不受限。
    """
    bad: list[dict[str, Any]] = []
    for row in rows:
        if row.get("order_id") and row.get("order_id_peer"):
            continue
        px = _f(row.get("price"))
        lots_i = _lots_int(row.get("lots"))
        cap = cap_lots(threshold, px, min_lots=min_lots)
        if lots_i > cap:
            bad.append(
                {
                    "time": row.get("time"),
                    "window_time": row.get("window_time"),
                    "lots": lots_i,
                    "cap": cap,
                    "price": px,
                    "order_id": row.get("order_id") or "",
                    "kind": row.get("kind") or "",
                }
            )
    return bad


__all__ = [
    "CAP_UNLIMITED",
    "WindowCost",
    "cap_lots",
    "check_rows_cap",
    "count_checked",
    "window_atoms",
    "window_count",
    "window_cost",
    "window_ok",
]
