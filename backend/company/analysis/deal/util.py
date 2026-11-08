"""deal 子包的通用工具函数。

收纳窗口重建 / 逐笔撮合模块共用的纯函数与轻量类：数值归一、手数拆分、
时间戳归整、截止窗定位、成交时刻推算、窗内 VWAP 回校、订单编号分配，
以及买卖角色判断。数值阈值与集合竞价时段统一从 :mod:`constants` 读取。
"""

from __future__ import annotations

import bisect
import math
from typing import Any, Mapping

from company.analysis.deal.constants import (
    CALL_AUCTION_MATCH,
    DEFAULT_MIN_LOTS,
    ROLE_ACTIVE,
    ROLE_OTHER,
    ROLE_PASSIVE,
    SHARES_PER_LOT,
)


# ---------------------------------------------------------------------------
# 数值归一
# ---------------------------------------------------------------------------

def _f(value: Any) -> float:
    """严格转正 float：非法 / 非正 / NaN 一律返回 ``0.0``。

    这是 ``validate`` 依赖的**严格**版本：任何 ``<= 0`` 的输入都折叠成 0，
    便于在约束校验里把「缺失 / 零 / 负价」统一当成无效值处理。
    """
    if value is None or value == "":
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number) or number <= 0:
        return 0.0
    return number


def _lots_int(lots: float) -> int:
    """手数 → 非负整手（四舍五入；禁止小数手）。"""
    if lots is None:
        return 0
    try:
        number = float(lots)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number) or number <= 0:
        return 0
    return int(round(number))


def _split(lots: float, count: int) -> list[float]:
    """把手数拆成 count 份整手，Σ 与 ``round(lots)`` 完全一致。

    每份都是非负整数手（0 / 1 / 2 …）。``count > lots`` 时用 0 手占位，
    以保证笔数守恒。
    """
    if count <= 0:
        return []
    total = _lots_int(lots)
    if total <= 0:
        return [0.0] * count
    base = total // count
    spare = total - base * count
    parts = [base] * count
    for index in range(spare):
        parts[index] += 1
    return [float(part) for part in parts]


def _min_lots_floor(min_lots: float | None = None) -> int:
    """单笔手数下限（整手，可为 0）。锚点仍至少钉 1 手，见 ``place_orders``。"""
    if min_lots is None:
        min_lots = DEFAULT_MIN_LOTS
    try:
        number = float(min_lots)
    except (TypeError, ValueError):
        number = float(DEFAULT_MIN_LOTS)
    if not math.isfinite(number) or number <= 0:
        return 0
    return int(round(number))


def _cap_lots_int(threshold: float, price: float, *, min_lots: float = DEFAULT_MIN_LOTS) -> float:
    """单笔金额门槛对应的最大整手（legacy float 版本）；不足 1 手时退回 1 手。"""
    floor = float(max(1, _min_lots_floor(min_lots)))
    if price <= 0 or threshold <= 0:
        return float("inf")
    raw = threshold / price / SHARES_PER_LOT
    if not math.isfinite(raw) or raw <= 0:
        return float("inf")
    return max(floor, float(int(math.floor(raw + 1e-9))))


# ---------------------------------------------------------------------------
# 时间戳归一与集合竞价时刻判断
# ---------------------------------------------------------------------------

def _stamp_key(value: Any) -> str:
    """把各种来源的时间戳归一成 ``HH:MM:SS``。

    东财逐笔给 ``09:30:03``，同花顺给 ``20261009 09:30:03``，资金动向给
    ``09:25:00``。不归一的话 ``bisect`` 会把同花顺的窗口全部排到订单之前，
    订单一律落到第一个窗口，看起来像「无解」——其实是格式没对齐。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if " " in text:
        text = text.rsplit(" ", 1)[-1]
    if "T" in text:
        text = text.rsplit("T", 1)[-1]
    parts = text.split(":")
    if len(parts) >= 2:
        try:
            hh, mm = int(parts[0]), int(parts[1])
            ss = int(float(parts[2])) if len(parts) > 2 else 0
            return f"{hh:02d}:{mm:02d}:{ss:02d}"
        except (TypeError, ValueError):
            return text
    return text


def _is_call_auction_match(stamp: Any) -> bool:
    """是否为集合竞价真实成交时刻（开盘 09:25 起约一分钟内 / 收盘 15:00）。"""
    key = _stamp_key(stamp)
    if not key:
        return False
    return any(start <= key < end for start, end in CALL_AUCTION_MATCH)


def _shift_stamp(stamp: str, seconds: int) -> str:
    """``HH:MM:SS`` 加减秒，失败则原样返回。"""
    key = _stamp_key(stamp)
    if not key:
        return str(stamp or "")
    try:
        hh, mm, ss = (int(p) for p in key.split(":"))
        total = hh * 3600 + mm * 60 + ss + int(seconds)
        if total < 0:
            total = 0
        return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"
    except (TypeError, ValueError):
        return key


# ---------------------------------------------------------------------------
# 截止窗定位
# ---------------------------------------------------------------------------

def _deadline_indices(stamps: list[str], stamp: str) -> list[int]:
    """资金动向完全成交时刻 → 可归属的分时窗口下标（升序，1 或 2 个）。

    分时档按**两端闭区间**衔接，例如::

        [14:18:38, 14:18:41] 与 [14:18:41, 14:18:44]

    - 档间时刻（如 ``14:18:40``）只落在唯一覆盖档；
    - 恰落在档点 ``S``（如 ``14:18:41``）时，前后两档都可「完全成交」，
      返回 ``[本档, 下一档]`` 两个下标。

    集合竞价撮合点（``09:25`` / ``15:00``）只落本档；资金动向常给整点
    ``09:25:00`` / ``15:00:00``，而分时档可能是 ``09:25:02`` / ``15:00:02``，
    此时对齐到同一撮合分钟内最近的真实档（优先 ≥ 完成时刻的第一档）。
    """
    if not stamps or not stamp:
        return []
    key = _stamp_key(stamp)
    if not key:
        return []
    if _is_call_auction_match(key):
        idx = bisect.bisect_left(stamps, key)
        if idx < len(stamps) and stamps[idx] == key:
            return [idx]
        # 整点对齐：在同一撮合窗口 [09:25,09:26) / [15:00,15:01) 内找真实档
        for start, end in CALL_AUCTION_MATCH:
            if not (start <= key < end):
                continue
            in_match = [
                i for i, s in enumerate(stamps) if start <= str(s) < end
            ]
            if not in_match:
                return []
            after = [i for i in in_match if str(stamps[i]) >= key]
            if after:
                return [after[0]]
            return [in_match[-1]]
        return []
    on = bisect.bisect_left(stamps, key)
    if on < len(stamps) and stamps[on] == key:
        # 档点：本档 [prev, S] 与下一档 [S, next] 均可
        out = [on]
        if on + 1 < len(stamps):
            out.append(on + 1)
        return out
    # 档间：右端点为第一个 > T 的档
    nxt = bisect.bisect_right(stamps, key)
    if nxt >= len(stamps):
        return []
    return [nxt]


def _deadline_index(stamps: list[str], stamp: str) -> int:
    """兼容单下标：返回候选截止窗中靠后的一档；无候选为 -1。"""
    idxs = _deadline_indices(stamps, stamp)
    return idxs[-1] if idxs else -1


def _order_fill_stamp(
    window_stamp: str,
    order: Mapping[str, Any] | None,
    *,
    prev_stamp: str = "",
) -> str:
    """大单胶带 ``time``：落在分时档闭区间 ``[prev, stamp]`` 内的真实时刻。

    - 资金动向完成时刻若 ∈ ``[prev, stamp]``（截止窗）→ 用完成时刻
      （例：完成 09:30:35、档 09:30:38 → 显示 09:30:35；完成恰为档点也保留）
    - 否则为回溯窗 → 用区间左端 ``prev``（不晚于完成时刻）
    - ``window_time`` 仍为档位右端点，按窗汇总与分时对账
    """
    win = _stamp_key(window_stamp)
    order_t = _stamp_key((order or {}).get("time"))
    left = _stamp_key(prev_stamp) if prev_stamp else (_shift_stamp(win, -3) if win else "")
    if not win:
        return order_t or str(window_stamp or "")
    if order_t and (not left or left <= order_t <= win):
        return order_t
    if left and left <= win:
        return left
    return _shift_stamp(win, -1) if win else win


# ---------------------------------------------------------------------------
# 窗内 VWAP 回校
# ---------------------------------------------------------------------------

def _align_window_vwap(rows: list[dict[str, Any]], target_price: float) -> None:
    """回校窗内成交价，使 ``Σ(lots·price)/Σ lots = 分时均价``。

    **只改小单价格**；大单始终保留资金动向价（跨窗同一大单不能一段 17.48、
    一段被改成窗均价 17.49）。

    若无小单可调，或回校后小单价会变成 ``<=0``，则放弃本窗均价对齐——
    大单价优先于窗均价。
    """
    if not rows:
        return
    target = _f(target_price)
    if target <= 0:
        return
    total_lots = sum(_lots_int(row.get("lots")) for row in rows)
    if total_lots <= 0:
        return
    target_amount = target * total_lots
    order_rows = [row for row in rows if row.get("kind") == "order"]
    small_rows = [row for row in rows if row.get("kind") != "order"]
    small_lots = sum(_lots_int(row.get("lots")) for row in small_rows)
    # 大单吃满窗口：无法在不改大单价的前提下对齐均价 → 保持资金动向价
    if small_lots <= 0:
        return

    order_amount = sum(
        float(_lots_int(row.get("lots"))) * float(row.get("price") or 0)
        for row in order_rows
    )
    need = target_amount - order_amount
    px = need / small_lots
    # 小单价必须为正；否则放弃对齐，绝不改写大单
    if not math.isfinite(px) or px <= 0:
        return

    positive = [row for row in small_rows if _lots_int(row.get("lots")) > 0]
    for row in small_rows:
        if _lots_int(row.get("lots")) <= 0:
            row["price"] = round(target, 4)
        else:
            row["price"] = round(px, 4)
    # 最后一笔小单吃掉四舍五入误差，保证窗内 VWAP 严格对齐
    if positive:
        fixed = sum(
            float(_lots_int(row.get("lots"))) * float(row.get("price") or 0)
            for row in rows
            if row is not positive[-1]
        )
        last_lots = _lots_int(positive[-1].get("lots"))
        if last_lots > 0:
            last_px = (target_amount - fixed) / last_lots
            if not math.isfinite(last_px) or last_px <= 0:
                # 回滚小单改价，保持大单不动
                for row in small_rows:
                    row["price"] = round(target, 4)
                return
            positive[-1]["price"] = round(last_px, 4)


# ---------------------------------------------------------------------------
# 订单编号分配
# ---------------------------------------------------------------------------

class _OrderIds:
    """全天递增的买单 / 卖单编号。大单跨窗口复用同一编号。"""

    def __init__(self) -> None:
        self._buy = 0
        self._sell = 0
        self._bound: dict[str, str] = {}
        # 已成交过的「买大单, 卖大单」配对：一对真实买卖大单只能有一笔成交。
        # 跨窗残留通过 virtual_pair 并入原配对行的 attributed_lots，不再出第二笔。
        self._paired: set[tuple[str, str]] = set()
        self._pair_row: dict[tuple[str, str], dict[str, Any]] = {}

    def pair_done(self, buy_oid: str, sell_oid: str) -> bool:
        return bool(buy_oid) and bool(sell_oid) and (buy_oid, sell_oid) in self._paired

    def mark_pair(
        self,
        buy_oid: str,
        sell_oid: str,
        row: dict[str, Any] | None = None,
    ) -> None:
        if not buy_oid or not sell_oid:
            return
        key = (buy_oid, sell_oid)
        self._paired.add(key)
        if row is not None:
            self._pair_row[key] = row

    def virtual_pair(self, buy_oid: str, sell_oid: str, lots: float) -> float:
        """跨窗已配对过的买卖：本窗不再出第二笔，只把量并入原配对行归因。"""
        take = _lots_int(lots)
        if take <= 0 or not buy_oid or not sell_oid:
            return 0.0
        row = self._pair_row.get((buy_oid, sell_oid))
        if row is None:
            return 0.0
        if row.get("attributed_lots") is None:
            row["attributed_lots"] = float(_lots_int(row.get("lots")))
        row["attributed_lots"] = float(row["attributed_lots"]) + float(take)
        return float(take)

    def bind(self, order: Mapping[str, Any]) -> str:
        key = str(order.get("order_id") or "")
        if key and key in self._bound:
            return self._bound[key]
        display = self.next_buy() if (order.get("side") or "buy") == "buy" else self.next_sell()
        if key:
            self._bound[key] = display
        return display

    def next_buy(self) -> str:
        self._buy += 1
        return f"B{self._buy:05d}"

    def next_sell(self) -> str:
        self._sell += 1
        return f"S{self._sell:05d}"


# ---------------------------------------------------------------------------
# 订单角色判断
# ---------------------------------------------------------------------------

def role_of(order: Mapping[str, Any]) -> str:
    """主动 / 被动 / 其它。``view`` 是过滤模式时回落到 ``aggressor``。"""
    for key in ("aggressor", "view"):
        text = str(order.get(key) or "").strip().lower()
        if text in {"active", "aggressor", "1", "主动", "主买", "主卖"}:
            return ROLE_ACTIVE
        if text in {"passive", "2", "被动", "被买", "被卖"}:
            return ROLE_PASSIVE
    return ROLE_OTHER


def is_active_order(order: Mapping[str, Any]) -> bool:
    return role_of(order) == ROLE_ACTIVE


def is_passive_order(order: Mapping[str, Any]) -> bool:
    return role_of(order) == ROLE_PASSIVE



def _same_price(a: float, b: float) -> bool:
    """判断两个价格是否同价（容差 ``PRICE_EPS``）。"""
    from company.analysis.deal.constants import PRICE_EPS

    return a > 0 and b > 0 and abs(a - b) <= PRICE_EPS


def _keep_sell_side(
    buy_order: Mapping[str, Any], sell_order: Mapping[str, Any]
) -> bool:
    """异价重叠的原子只能留一侧编号。

    优先留**被动方**（成交价就是被动方挂单价），其次留完成更早的一方，
    再退回买方。被丢掉的那侧手数仍算在窗内，只是这一笔的对手变成匿名小单。
    """
    role_b, role_s = role_of(buy_order), role_of(sell_order)
    if role_s == ROLE_PASSIVE and role_b != ROLE_PASSIVE:
        return True
    if role_b == ROLE_PASSIVE and role_s != ROLE_PASSIVE:
        return False
    buy_t = _stamp_key(buy_order.get("time"))
    sell_t = _stamp_key(sell_order.get("time"))
    if buy_t and sell_t and buy_t != sell_t:
        return sell_t < buy_t
    return False

__all__ = [
    "_OrderIds",
    "_align_window_vwap",
    "_cap_lots_int",
    "_deadline_index",
    "_deadline_indices",
    "_f",
    "_is_call_auction_match",
    "_lots_int",
    "_min_lots_floor",
    "_order_fill_stamp",
    "_shift_stamp",
    "_split",
    "_stamp_key",
    "is_active_order",
    "is_passive_order",
    "role_of",
    "_same_price",
    "_keep_sell_side",
]
