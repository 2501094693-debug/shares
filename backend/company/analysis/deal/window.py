"""3 秒窗口级逐笔成交重建：分时成交 × 资金动向 → 逐笔明细。

分时成交每一档代表**之前 3 秒**内完成的笔数与总手数。例如
``09:30:24  17.53  93手/33笔  买`` 表示区间 ``[09:30:21, 09:30:24)``
以均价 17.53 成交了 33 笔、共 93 手。资金动向每一行是一张大单的
**最后成交时间**、手数与价格。

算法
----
1. 把分时档当成互不重叠的左闭右开 3 秒窗口；按大单最后成交时间落入截止窗。
2. 尽可能撮合大单，但窗内大单手数 ≤ 区间总手数；剩余笔数按 min_lots 预留。
3. 大单落位后填小单，使笔数、总手数对齐；有小单时再回校均价（大单价不改）。
4. 输出逐笔 ``time / lots / sell_id / buy_id``：
   ``window_time`` = 分时档右端点（对账用）；``time`` ∈ 左闭右开区间内的真实成交时刻
   （完成落在本窗则用资金动向完成时刻，不再显示成右端点如 09:30:38）。
5. 生成后由 ``validate.validate_tape`` 做硬约束验收，结果写入 ``reconcile.constraints``。

硬约束（验收清单，详见 ``validate.py``）
----------------------------------------
R2 窗内大单 ≤ 分时容量　R4 完成时刻/截止窗　R5 笔数·手数·(可调时)均价
R6 输出字段　R7 整手可 0　R8 一对买卖一笔　R9 同档大单连续
R10 大单价=资金动向价　R11 按 window_time 汇总=分时手数

集合竞价真实成交只在撮合点：开盘 ``09:25``、收盘 ``15:00``。
"""

from __future__ import annotations

import bisect
import math
from typing import Any, Iterable, Mapping

# 一手 = 100 股（仅用于金额 ↔ 手数换算；成交手数本身一律整手）
SHARES_PER_LOT = 100.0
# 资金动向收录门槛：单笔成交额 >= 该值即为「大单」
DEFAULT_TRADE_THRESHOLD = 300_000.0
# 分时快照缺笔数时，按笔均手数反推
DEFAULT_AVG_LOTS_PER_TICK = 3.0
# 单笔最小规模：默认 0 手。禁止小数手，只允许 0 / 1 / 2 … 整手。
DEFAULT_MIN_LOTS = 0.0
TRADE_MIN_LOTS = 0.0

_EPS = 1e-9
_BUY_SIDES = {"1", "b", "buy", "买", "买盘", "b1", "2"}
_AUCTION_SIDES = {"4", "auction"}
# 集合竞价虚拟撮合快照时段（应剔除，避免累计量重复计入）
_AUCTION_WINDOWS = (("09:15:00", "09:25:00"), ("14:57:00", "15:00:00"))
# 集合竞价**真实成交**落点：开盘撮合在 09:25（个别源会散落在随后几秒），收盘在 15:00
_CALL_AUCTION_MATCH = (("09:25:00", "09:26:00"), ("15:00:00", "15:01:00"))
# 开盘撮合之后、连续竞价之前：不应有新成交
_PRE_CONTINUOUS_GAP = (("09:26:00", "09:30:00"),)


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _f(value: Any) -> float:
    """宽松转正 float，非法 / 非正 / NaN 一律返回 0.0。"""
    if value is None or value == "":
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number) or number <= 0:
        return 0.0
    return number


def _is_buy(row: Mapping[str, Any]) -> bool:
    side = row.get("side")
    if side is not None and str(side).strip().lower() in _BUY_SIDES:
        return True
    label = str(row.get("side_label") or "").strip().lower()
    return label in _BUY_SIDES


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
    """单笔手数下限（整手，可为 0）。锚点仍至少钉 1 手，见 ``_anchor_lots``。"""
    if min_lots is None:
        min_lots = DEFAULT_MIN_LOTS
    try:
        number = float(min_lots)
    except (TypeError, ValueError):
        number = float(DEFAULT_MIN_LOTS)
    if not math.isfinite(number) or number <= 0:
        return 0
    return int(round(number))


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


def _is_auction_snapshot(row: Mapping[str, Any]) -> bool:
    """集合竞价窗口内的 auction 行（累计虚拟撮合快照）。"""
    side = "" if row.get("side") is None else str(row.get("side")).strip().lower()
    label = str(row.get("side_label") or "").strip().lower()
    if side not in _AUCTION_SIDES and label not in _AUCTION_SIDES:
        return False
    stamp = _stamp_key(row.get("time"))
    return any(start <= stamp < end for start, end in _AUCTION_WINDOWS)


def _is_call_auction_match(stamp: Any) -> bool:
    """是否为集合竞价真实成交时刻（开盘 09:25 起约一分钟内 / 收盘 15:00）。"""
    key = _stamp_key(stamp)
    if not key:
        return False
    return any(start <= key < end for start, end in _CALL_AUCTION_MATCH)


def _is_pre_continuous_gap(stamp: Any) -> bool:
    """开盘撮合后、09:30 连续竞价前的空窗（不应有新成交）。"""
    key = _stamp_key(stamp)
    if not key:
        return False
    return any(start <= key < end for start, end in _PRE_CONTINUOUS_GAP)


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


def _flag(n: int) -> float:
    return math.lgamma(n + 1) / math.log(10.0)


def _log10_compositions(total: float, parts: int) -> float:
    """把 total（整手）拆成 parts 个正整数解的个数，取 log10。"""
    if parts <= 1:
        return 0.0
    units = int(round(total)) - parts
    if units <= 0:
        return 0.0
    return _flag(units + parts - 1) - _flag(units) - _flag(parts - 1)


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


# ---------------------------------------------------------------------------
# 3. 逐窗口可行性判定
# ---------------------------------------------------------------------------

def _order_side(order: Mapping[str, Any]) -> str:
    return "buy" if (order.get("side") or "buy") == "buy" else "sell"


def plan_window(
    window: Mapping[str, Any],
    placed: list[dict[str, Any]],
    *,
    threshold: float = DEFAULT_TRADE_THRESHOLD,
    min_lots: float = DEFAULT_MIN_LOTS,
) -> dict[str, Any]:
    """给出该窗口的可行 ``m`` 区间与实际取值，并判定是否可解。

    ``placed`` 是落在本窗口的订单分配 ``[{"order": 订单, "lots": 分配到的手数}]``，
    这里只用到 ``lots``（**分配到本窗口**的手数，不是订单总量）。

    - ``count`` 是区间笔数。超门槛时一条可拆成多笔，成交笔数 ``>= count``。
    - 30 万门槛约束的是**每笔**；超门槛时拆成 ``ceil(lots / cap_lots)`` 笔。
    - 手数一律整手（``min_lots`` 默认 0）。``min_lots>0`` 时笔数不能多于 ``lots/min_lots``。
    """
    lots = float(_lots_int(window.get("lots")))
    count = int(window.get("count") or 0)
    price = _f(window.get("price"))
    is_auction = bool(window.get("auction")) or _is_call_auction_match(window.get("time"))
    buy_lots = float(sum(_lots_int(item.get("lots")) for item in placed if _order_side(item.get("order") or {}) == "buy"))
    sell_lots = float(sum(_lots_int(item.get("lots")) for item in placed if _order_side(item.get("order") or {}) == "sell"))
    # 双边各自 <= V；窗内「归因手数」按成交口径取 max(买, 卖)（一笔成交同时服务买卖）
    buy_lots = min(buy_lots, lots)
    sell_lots = min(sell_lots, lots)
    order_lots = float(max(buy_lots, sell_lots))
    buy_n = sum(1 for item in placed if _order_side(item.get("order") or {}) == "buy")
    sell_n = sum(1 for item in placed if _order_side(item.get("order") or {}) == "sell")
    needed = max(buy_n, sell_n)
    rest_lots = float(int(lots) - int(order_lots))
    floor_i = _min_lots_floor(min_lots)
    floor = float(floor_i)
    cap_lots = _cap_lots_int(threshold, price, min_lots=max(1.0, floor))

    # min_lots>0 时每笔至少 floor 手 → 笔数有上限；min_lots=0 时笔数可大于手数（0 手占位）
    if floor_i > 0 and lots > 0:
        max_records = int(math.floor(lots / floor_i + 1e-9))
    elif lots > 0:
        max_records = max(count, needed, 1)
    else:
        max_records = 0
    trades_min = count
    if math.isfinite(cap_lots) and cap_lots > 0:
        trades_min = max(count, int(math.ceil(lots / cap_lots - 1e-9)))

    side_ok = buy_lots <= lots + 1e-6 and sell_lots <= lots + 1e-6
    if is_auction:
        count_ok = floor_i <= 0 or count <= max_records or count == 0
        feasible = lots <= 0 or (side_ok and count_ok)
    else:
        count_ok = floor_i <= 0 or count <= max_records
        # 连续竞价：买卖两侧各自槽位 <= 笔数
        slot_ok = buy_n <= count and sell_n <= count
        feasible = lots <= 0 or (side_ok and slot_ok and count_ok)

    if is_auction:
        # 记录只是聚合外壳；买卖大单互相配对，不按「一单一条」占坑
        fills = min(count, max(needed, 0)) if count else 0
        if needed > count:
            fills = count
        if rest_lots > _EPS and fills >= count and count > 0:
            fills = max(0, count - 1) if needed < count else count
        small_count = 0 if order_lots >= lots - 1e-6 else max(0, count - fills)
    elif feasible:
        target = int(round(count * (order_lots / lots))) if lots > 0 else 0
        fills = max(needed, min(count, target))
        if rest_lots > _EPS and count - fills <= 0:
            fills = max(needed, count - 1)
        fills = max(0, min(fills, count))
        small_count = max(0, count - fills)
    else:
        fills = max(0, min(needed, count))
        small_count = max(0, count - fills)

    lo, hi = (0, count) if is_auction else (needed, count)
    return {
        "time": window.get("time"),
        "lots": lots,
        "count": count,
        "price": price,
        "side": window.get("side") or "buy",
        "auction": is_auction,
        "order_lots": order_lots,
        "order_count": needed,
        "small_lots": rest_lots,
        "small_count": small_count,
        "cap_lots": cap_lots,
        "min_lots": min_lots,
        "threshold": threshold,
        "trades_min": trades_min,
        "multi_trade": trades_min > count,
        "fills": fills,
        "fills_lo": lo,
        "fills_hi": hi,
        "feasible": feasible,
    }


def plan_windows(
    windows: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    *,
    threshold: float = DEFAULT_TRADE_THRESHOLD,
    min_lots: float = DEFAULT_MIN_LOTS,
    max_lookback: int = 0,
) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]], list[dict[str, Any]]]:
    """按订单成交时刻把它们落到窗口里，再逐窗口判定。

    返回 ``(plans, allocation, unplaced)``。
    """
    allocation, unplaced = place_orders(
        windows, orders, max_lookback=max_lookback, min_lots=min_lots
    )
    plans = []
    for index, window in enumerate(windows):
        plan = plan_window(
            window, allocation.get(index, []), threshold=threshold, min_lots=min_lots
        )
        plan["index"] = index
        plans.append(plan)
    return plans, allocation, unplaced


# ---------------------------------------------------------------------------
# 4. 回溯放置订单（保证 B <= W，且都早于自己的成交时刻）
# ---------------------------------------------------------------------------

def _deadline_index(stamps: list[str], stamp: str) -> int:
    """资金动向完全成交时刻 → 分时窗口下标。

    分时档 ``S`` 是**左闭右开** ``[prev, S)``：档 ``S`` 覆盖 ``S`` 之前 3 秒的
    成交，**不含 ``S`` 这一刻**（``S`` 本身是下一档的左端）。资金动向的 ``time``
    是该笔成交的**收尾时刻**：可能恰好等于某档右端点 ``S``（成交其实发生在
    ``[prev, S)`` 内、严格早于 ``S``），也可能是档间秒（如 ``14:36:14``）。
    因此完成时刻 ``T`` 归属**第一个 ``time > T``** 的档（``T`` 落在档间时，也即首个
    ``time >= T`` 的档）：

    - ``T`` 恰等于某档（如 ``09:37:51``）→ 下一档 ``09:37:54`` ``[09:37:51, 09:37:54)``
      （该笔正好落在下一档的左端；上一档 ``[09:37:48, 09:37:51)`` 不含 ``09:37:51``）
    - ``T`` 落在两档之间（如 ``14:36:14``，档为 ``14:36:12`` / ``14:36:15``）
      → 下一档 ``14:36:15``（``[14:36:12, 14:36:15)`` 恰好含 ``14:36:14``）

    集合竞价撮合档（``09:25`` / ``15:00``）本身就是该时刻的一次撮合，成交落本档；
    完成时刻恰为最后一档（右开无后继档）时回落到最后一档，避免整单丢弃。
    """
    if not stamps or not stamp:
        return -1
    if _is_call_auction_match(stamp):
        idx = bisect.bisect_left(stamps, stamp)
        if idx < len(stamps) and stamps[idx] == stamp:
            return idx
    index = bisect.bisect_right(stamps, stamp)
    if index >= len(stamps):
        last = len(stamps) - 1
        return last if stamps[last] == stamp else -1
    return index


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


def _order_fill_stamp(
    window_stamp: str,
    order: Mapping[str, Any] | None,
    *,
    prev_stamp: str = "",
) -> str:
    """大单胶带 ``time``：落在分时档左闭右开区间 ``[prev, stamp)`` 内的真实时刻。

    - 资金动向完成时刻若 ∈ ``[prev, stamp)``（截止窗）→ 用完成时刻
      （例：完成 09:30:35、档 09:30:38 → 显示 09:30:35，不是 09:30:38）
    - 否则为回溯窗 → 用区间左端 ``prev``（严格早于完成时刻）
    - ``window_time`` 仍为档位右端点，按窗汇总与分时对账
    """
    win = _stamp_key(window_stamp)
    order_t = _stamp_key((order or {}).get("time"))
    left = _stamp_key(prev_stamp) if prev_stamp else (_shift_stamp(win, -3) if win else "")
    if not win:
        return order_t or str(window_stamp or "")
    if order_t and (not left or left <= order_t < win):
        return order_t
    if left and left < win:
        return left
    return _shift_stamp(win, -1) if win else win


def _anchor_lots(need: float, available: float, *, min_lots: float = DEFAULT_MIN_LOTS) -> float:
    """完成窗上钉死的最小整手：至少 1 手（保证最后成交时间），不超过剩余量。"""
    need_i = _lots_int(need)
    avail_i = _lots_int(available)
    if need_i <= 0 or avail_i <= 0:
        return 0.0
    # 锚点必须占用真实成交，即使 min_lots=0 也至少钉 1 手
    floor = max(1, _min_lots_floor(min_lots))
    pin = min(need_i, avail_i, floor)
    return float(pin) if pin > 0 else 0.0


def _cap_lots_int(threshold: float, price: float, *, min_lots: float = DEFAULT_MIN_LOTS) -> float:
    """单笔金额门槛对应的最大整手；不足 1 手时退回 1 手。"""
    floor = float(max(1, _min_lots_floor(min_lots)))
    if price <= 0 or threshold <= 0:
        return float("inf")
    raw = threshold / price / SHARES_PER_LOT
    if not math.isfinite(raw) or raw <= 0:
        return float("inf")
    return max(floor, float(int(math.floor(raw + 1e-9))))


def place_orders(
    windows: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    *,
    max_lookback: int = 0,
    min_lots: float = DEFAULT_MIN_LOTS,
) -> tuple[dict[int, list[dict[str, Any]]], list[dict[str, Any]]]:
    """把订单填入截止窗及更早窗口，并保证完全成交时刻对齐。

    资金动向的 ``time`` 是订单**完全成交**时刻，因此重建必须满足：

    - 截止窗 = 第一个 ``time >= T`` 的分时档（见 ``_deadline_index``）
    - **至少有一笔**落在截止窗（先钉锚点，再回溯填残余量）
    - 买 / 卖两侧**各自**占用窗口手数容量（每侧 ``<= V``），互不挤占

    两阶段：

    1. **锚点**：按完成时刻升序（同时刻大单优先）在截止窗占最小一手；
       锚点失败的订单不再回溯填量（避免最后成交时间错位）。
    2. **填量**：残余量按大单优先，从截止窗剩余容量起向前回溯。

    连续竞价：买 / 卖各自最多占 ``count`` 个槽位；集合竞价不限槽。
    ``max_lookback`` 为 0 不限制回溯。填量时按 ``min_lots`` 为剩余空槽预留手数。
    """
    stamps = [window["time"] for window in windows]
    cap_buy = [_lots_int(window["lots"]) for window in windows]
    cap_sell = list(cap_buy)
    slots_buy = [
        10**9 if (window.get("auction") or _is_call_auction_match(window.get("time")))
        else int(window["count"])
        for window in windows
    ]
    slots_sell = list(slots_buy)
    auction_flags = [
        bool(window.get("auction") or _is_call_auction_match(window.get("time")))
        for window in windows
    ]
    filled: dict[int, dict[str, int]] = {}
    order_by_id: dict[str, dict[str, Any]] = {}
    need_of: dict[str, int] = {}
    deadline_of: dict[str, int] = {}
    unanchored: list[dict[str, Any]] = []
    floor_lots = _min_lots_floor(min_lots)

    for order in orders:
        oid = str(order.get("order_id") or "")
        if not oid:
            continue
        order_by_id[oid] = order
        need_of[oid] = _lots_int(order["lots"])
        deadline_of[oid] = _deadline_index(stamps, order["time"])

    def _caps_slots(side: str) -> tuple[list[int], list[int]]:
        if side == "sell":
            return cap_sell, slots_sell
        return cap_buy, slots_buy

    def _credit(index: int, order: Mapping[str, Any], take: float) -> None:
        take_i = _lots_int(take)
        if take_i <= 0:
            return
        oid = str(order["order_id"])
        side = _order_side(order)
        caps, slots = _caps_slots(side)
        bucket = filled.setdefault(index, {})
        first = oid not in bucket
        bucket[oid] = bucket.get(oid, 0) + take_i
        caps[index] -= take_i
        need_of[oid] -= take_i
        if first and not auction_flags[index]:
            slots[index] -= 1

    # ---- Phase 1: 完成窗锚点（完全成交时间钉死）----
    anchor_order = sorted(
        orders,
        key=lambda order: (order["time"], -float(order["lots"]), str(order.get("order_id") or "")),
    )
    for order in anchor_order:
        oid = str(order.get("order_id") or "")
        if not oid or need_of.get(oid, 0) <= 0:
            continue
        index = deadline_of[oid]
        if index < 0:
            unanchored.append(
                {"order_id": oid, "time": order["time"], "missing": float(need_of[oid]),
                 "reason": "no_window_ge_deadline"}
            )
            continue
        side = _order_side(order)
        caps, slots = _caps_slots(side)
        if caps[index] <= 0 or slots[index] <= 0:
            unanchored.append(
                {"order_id": oid, "time": order["time"], "missing": float(need_of[oid]),
                 "reason": "deadline_full"}
            )
            continue
        pin = _anchor_lots(need_of[oid], caps[index], min_lots=floor_lots)
        if pin <= 0:
            unanchored.append(
                {"order_id": oid, "time": order["time"], "missing": float(need_of[oid]),
                 "reason": "deadline_full"}
            )
            continue
        _credit(index, order, pin)

    unanchored_ids = {str(item["order_id"]) for item in unanchored}

    # ---- Phase 2: 残余量，大单优先；锚点失败的不再填 ----
    fill_order = sorted(
        orders,
        key=lambda order: (-float(order["lots"]), order["time"], str(order.get("order_id") or "")),
    )
    for order in fill_order:
        oid = str(order.get("order_id") or "")
        if not oid or need_of.get(oid, 0) <= 0 or oid in unanchored_ids:
            continue
        index = deadline_of[oid]
        if index < 0:
            continue
        side = _order_side(order)
        caps, slots = _caps_slots(side)
        # 截止窗优先填满，再向前回溯。若 on-grid 时把主量都压到上一档、截止窗只留
        # 锚点 1 手，买卖大单会在前窗部分配对，截止窗锚点又因 pair_done 无法再配对，
        # 残留只能找匿名对手 → 同一大单编号被拆开。截止窗本身是 [T, T+3)（含完成时刻），
        # 主量落在此窗合法，也能让一对买卖大单在同一窗整笔撮合。
        floor_index = max(0, index - max_lookback) if max_lookback > 0 else 0
        cursor = index
        while need_of[oid] > 0 and cursor >= floor_index:
            already = oid in filled.get(cursor, {})
            can_add = caps[cursor] > 0 and (already or slots[cursor] > 0)
            if not can_add:
                cursor -= 1
                continue
            slot_cost = 0 if already else 1
            remaining_slots = max(0, slots[cursor] - slot_cost)
            reserved = remaining_slots * floor_lots
            avail = caps[cursor] - reserved
            if avail <= 0:
                cursor -= 1
                continue
            take = float(min(need_of[oid], avail))
            _credit(cursor, order, take)
            left_slots = slots[cursor]
            if caps[cursor] - left_slots * floor_lots <= 0:
                cursor -= 1

    allocation: dict[int, list[dict[str, Any]]] = {}
    for index, bucket in filled.items():
        allocation[index] = [
            {"order": order_by_id[oid], "lots": float(lots)}
            for oid, lots in bucket.items()
            if lots > 0
        ]

    unplaced: list[dict[str, Any]] = []
    seen_unplaced: set[str] = set()
    for item in unanchored:
        oid = str(item["order_id"])
        if oid in seen_unplaced:
            continue
        unplaced.append(
            {
                "order_id": oid,
                "time": item["time"],
                "missing": float(max(need_of.get(oid, 0), _lots_int(order_by_id[oid]["lots"]))),
                "reason": item.get("reason"),
            }
        )
        seen_unplaced.add(oid)
    for oid, left in need_of.items():
        if left <= 0 or oid in seen_unplaced:
            continue
        order = order_by_id[oid]
        unplaced.append(
            {"order_id": oid, "time": order["time"], "missing": float(left), "reason": "capacity"}
        )
    return allocation, unplaced


# ---------------------------------------------------------------------------
# 5. 逐窗口展开成成交
# ---------------------------------------------------------------------------

def _record_trades(lots: float, cap_lots: float) -> int:
    """一条逐笔记录内部至少含多少笔，才能让每笔都低于门槛。

    记录是聚合出来的：终端里 ``6手 / 6笔`` 就是一条记录含 6 笔。
    所以记录手数超过门槛并不违规，只是它内部笔数更多而已。
    """
    if not math.isfinite(cap_lots) or cap_lots <= 0:
        return 1
    return max(1, int(math.ceil(lots / cap_lots - 1e-9)))


def _fold_residual_lots(rows: list[dict[str, Any]], residual: int) -> None:
    """残余手数并入最后一行，不新增笔数。

    订单行先冻结 ``attributed_lots``（归因仍按资金动向），胶带 ``lots`` 可被抬高
    以保住窗口量守恒与笔数守恒。
    """
    left = int(residual)
    if left <= 0 or not rows:
        return
    for row in rows:
        if row.get("kind") == "order" and row.get("attributed_lots") is None:
            row["attributed_lots"] = float(_lots_int(row.get("lots")))
    rows[-1]["lots"] = float(_lots_int(rows[-1].get("lots")) + left)


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


def _append_matches(
    rows: list[dict[str, Any]],
    ids: _OrderIds,
    *,
    stamp: str,
    price: float,
    lots: float,
    trades: int,
    aggressor: str,
    aggressor_id: str | None = None,
    order_id: str = "",
    order_event_id: str = "",
    order_time: str = "",
    window_time: str = "",
    kind: str = "small",
    real: bool = False,
    allow_zero: bool = False,
) -> None:
    """把一条记录拆成真正的逐笔：每笔 = 时间 / 价格 / 手数 / 买单号 / 卖单号。

    主动方订单号在拆笔间保持不变（对应「一笔大单扫掉多个对手盘」）；
    被动方每笔新开一个编号。``allow_zero=True`` 时保留 0 手占位以满足笔数。
    ``window_time`` 保留分时档时刻，供窗口量守恒对账；``time`` 对大单用资金动向时刻。
    """
    pieces = _split(lots, max(1, int(trades or 1)))
    if not allow_zero:
        pieces = [p for p in pieces if p > 0]
    if not pieces and allow_zero:
        pieces = [0.0]
    side = "buy" if aggressor == "buy" else "sell"
    win = window_time or stamp
    if side == "buy":
        buy_id = aggressor_id or ids.next_buy()
        for piece in pieces:
            rows.append(
                {
                    "time": stamp,
                    "window_time": win,
                    "order_time": order_time or "",
                    "price": round(price, 2),
                    "lots": 0.0 if piece <= 0 else float(_lots_int(piece)),
                    "buy_id": buy_id,
                    "sell_id": ids.next_sell(),
                    "side": side,
                    "order_id": order_id,
                    "order_event_id": order_event_id,
                    "order_peer_event_id": "",
                    "kind": kind,
                    "real": real,
                }
            )
    else:
        sell_id = aggressor_id or ids.next_sell()
        for piece in pieces:
            rows.append(
                {
                    "time": stamp,
                    "window_time": win,
                    "order_time": order_time or "",
                    "price": round(price, 2),
                    "lots": 0.0 if piece <= 0 else float(_lots_int(piece)),
                    "buy_id": ids.next_buy(),
                    "sell_id": sell_id,
                    "side": side,
                    "order_id": order_id,
                    "order_event_id": order_event_id,
                    "order_peer_event_id": "",
                    "kind": kind,
                    "real": real,
                }
            )


def _emit_auction_window(
    plan: Mapping[str, Any],
    placed: list[dict[str, Any]],
    ids: _OrderIds,
) -> list[dict[str, Any]]:
    """集合竞价窗口：买卖大单多对多配对，不要求一单一条记录。"""
    stamp = plan["time"]
    price = _f(plan.get("price")) or 0.0
    window_lots = _lots_int(plan.get("lots"))
    threshold = _f(plan.get("threshold")) or DEFAULT_TRADE_THRESHOLD
    min_lots = _f(plan.get("min_lots")) or DEFAULT_MIN_LOTS
    cap_lots = _cap_lots_int(threshold, price, min_lots=min_lots)
    rows: list[dict[str, Any]] = []

    raw_lots = [_lots_int(item["lots"]) for item in placed]

    def _scale_side(indices: list[int]) -> None:
        """单侧手数之和不得超过窗口 V；买卖互不挤占。"""
        if not indices or window_lots <= 0:
            return
        total = sum(raw_lots[i] for i in indices)
        if total <= window_lots:
            return
        scaled = [window_lots * raw_lots[i] / total for i in indices]
        bases = [int(math.floor(x)) for x in scaled]
        left = window_lots - sum(bases)
        ranked = sorted(range(len(bases)), key=lambda j: -(scaled[j] - bases[j]))
        for j in ranked:
            if left <= 0:
                break
            bases[j] += 1
            left -= 1
        for j, idx in enumerate(indices):
            raw_lots[idx] = bases[j]

    buy_idx = [
        i for i, item in enumerate(placed)
        if _order_side(item.get("order") or {}) == "buy"
    ]
    sell_idx = [
        i for i, item in enumerate(placed)
        if _order_side(item.get("order") or {}) == "sell"
    ]
    _scale_side(buy_idx)
    _scale_side(sell_idx)

    # slot: [lots, display_id, order_id, order_price, order_time, event_id]
    buys: list[list[Any]] = []
    sells: list[list[Any]] = []
    for item, lots in zip(placed, raw_lots):
        if lots <= 0:
            continue
        order = item["order"]
        display = ids.bind(order)
        order_px = _f(order.get("price")) or price
        order_t = _stamp_key(order.get("time"))
        slot = [
            lots,
            display,
            str(order.get("order_id") or ""),
            order_px,
            order_t,
            str(order.get("event_id") or ""),
        ]
        if (order.get("side") or "buy") == "buy":
            buys.append(slot)
        else:
            sells.append(slot)
    buys.sort(key=lambda item: -item[0])
    sells.sort(key=lambda item: -item[0])

    # 完成时刻锚点改为事后补（见 _ensure_completion_marks）：事前给每单无脑扣 1 手
    # 会在对手大单的连续色块中间塞一笔新编号，把 2089 手这种大单劈成两块。

    def _append_row(
        lots: float,
        buy_id: str,
        sell_id: str,
        *,
        order_id: str = "",
        order_id_peer: str = "",
        order_event_id: str = "",
        order_peer_event_id: str = "",
        kind: str = "order",
        real: bool = True,
        row_price: float | None = None,
        side: str = "buy",
        row_time: str | None = None,
        order_time: str = "",
    ) -> None:
        rows.append(
            {
                "time": row_time or stamp,
                "window_time": stamp,
                "order_time": order_time or "",
                "price": round(row_price if row_price is not None else price, 2),
                "lots": float(_lots_int(lots)),
                "buy_id": buy_id,
                "sell_id": sell_id,
                "side": side,
                "order_id": order_id,
                "order_id_peer": order_id_peer,
                "order_event_id": order_event_id,
                "order_peer_event_id": order_peer_event_id,
                "kind": kind,
                "real": real,
            }
        )

    def _flush_pair(
        lots: float,
        buy_id: str,
        sell_id: str,
        *,
        order_id: str = "",
        order_id_peer: str = "",
        order_event_id: str = "",
        order_peer_event_id: str = "",
        kind: str = "order",
        real: bool = True,
        refresh_buy: bool = False,
        refresh_sell: bool = False,
        row_price: float | None = None,
        side: str = "buy",
        piece_cap: float | None = None,
        row_time: str | None = None,
        order_time: str = "",
        piece_count: int | None = None,
    ) -> float:
        """按门槛拆笔。双边都是真实大单时编号不变；单边残留则每笔刷新对手编号。

        ``piece_count`` 直接指定拆几笔（如残余小单要补足分时档笔数）；
        缺省时按单笔金额门槛推出最少笔数。
        """
        lots_i = _lots_int(lots)
        use_cap = piece_cap if piece_cap is not None else cap_lots
        n_pieces = int(piece_count) if piece_count and piece_count > 0 else _record_trades(lots_i, use_cap)
        if lots_i <= 0 and not (kind == "small" and n_pieces > 0):
            return 0.0
        total = 0.0
        pieces = _split(lots_i, n_pieces) if n_pieces > 0 else []
        if not pieces and kind == "small" and n_pieces > 0:
            pieces = [0.0] * n_pieces
        for piece in pieces:
            if piece <= 0 and kind != "small":
                continue
            bid = ids.next_buy() if refresh_buy else buy_id
            sid = ids.next_sell() if refresh_sell else sell_id
            if not bid:
                bid = ids.next_buy()
            if not sid:
                sid = ids.next_sell()
            _append_row(
                piece,
                bid,
                sid,
                order_id=order_id,
                order_id_peer=order_id_peer,
                order_event_id=order_event_id,
                order_peer_event_id=order_peer_event_id,
                kind=kind,
                real=real,
                row_price=row_price,
                side=side,
                row_time=row_time,
                order_time=order_time,
            )
            total += piece
        return total

    def _slot_px(slot: list[Any]) -> float:
        px = round(_f(slot[3]) if len(slot) > 3 else 0.0, 2)
        return px if px > 0 else round(price, 2)

    def _slot_t(slot: list[Any]) -> str:
        return str(slot[4]) if len(slot) > 4 and slot[4] else ""

    def _slot_evt(slot: list[Any]) -> str:
        return str(slot[5]) if len(slot) > 5 and slot[5] else ""

    matched = 0.0
    # 买卖大单只撮合「同价（同一 tick）」的对手盘：一笔成交的买卖双方必然同价。
    # 旧实现按手数大小盲目配对，会把一侧大单的价格改写成对手价（如资金动向
    # 09:30:16 主卖 427 手 @17.57 被记成 @17.58），导致逐笔与资金动向对不上。
    # 找不到同价对手时，这一侧大单改为与匿名小单成交（下面 leftover 循环），
    # 价格 / 时间保持它自己的资金动向值。
    for buy_slot in buys:
        if buy_slot[0] <= 0:
            continue
        bpx = _slot_px(buy_slot)
        for sell_slot in sells:
            if buy_slot[0] <= 0:
                break
            if sell_slot[0] <= 0:
                continue
            if abs(_slot_px(sell_slot) - bpx) > 0.005:
                continue
            buy_oid, sell_oid = str(buy_slot[2]), str(sell_slot[2])
            take = min(buy_slot[0], sell_slot[0])
            # 同一对已在此前窗口成交：本窗只做虚拟撮合（并入原行归因），
            # 胶带手数由小单补足，避免「一对两笔」或买卖双边重复占量。
            # 截止窗的量经 virtual 归入首笔；R4 以 order_time 为准（见 validate）。
            if ids.pair_done(buy_oid, sell_oid):
                virtual = ids.virtual_pair(buy_oid, sell_oid, take)
                if virtual > 0:
                    buy_slot[0] -= virtual
                    sell_slot[0] -= virtual
                continue
            buy_t, sell_t = _slot_t(buy_slot), _slot_t(sell_slot)
            # 完成时刻因果：资金动向 time 是「最后成交（完全成交）时间」。
            # 一笔撮合若把某一侧大单一次吃完，则该侧最后成交就在此刻，不能晚于
            # 对手的完成时间，否则会出现「09:30:00 已卖完的卖单吃掉 09:30:02 才
            # 买完的买单」这种因果倒挂。晚完成的一侧必须留到与小单/更晚对手成交。
            if buy_t and sell_t and buy_t != sell_t:
                fully_buy = take >= buy_slot[0] - 1e-9
                fully_sell = take >= sell_slot[0] - 1e-9
                if (fully_buy and buy_t > sell_t) or (fully_sell and sell_t > buy_t):
                    continue
            # 胶带 time ∈ [prev, stamp)；完成时刻落在本窗则显示完成时刻。
            candidates = [t for t in (buy_t, sell_t) if t]
            order_t = min(candidates) if candidates else ""
            row_t = _order_fill_stamp(
                stamp,
                {"time": order_t} if order_t else None,
                prev_stamp=str(plan.get("prev_time") or ""),
            )
            before = len(rows)
            matched += _flush_pair(
                take,
                buy_slot[1],
                sell_slot[1],
                order_id=buy_oid,
                order_id_peer=sell_oid,
                order_event_id=_slot_evt(buy_slot),
                order_peer_event_id=_slot_evt(sell_slot),
                row_price=bpx,
                side="buy",
                piece_cap=_cap_lots_int(threshold, bpx, min_lots=min_lots),
                row_time=row_t,
                order_time=order_t or row_t,
                # 一对真实买卖大单只能在同一笔成交：同一买/卖编号不能拆成多笔
                piece_count=1,
            )
            buy_slot[0] -= take
            sell_slot[0] -= take
            pair_row = rows[before] if len(rows) > before else None
            ids.mark_pair(buy_oid, sell_oid, pair_row)

    # 统一决定「补大单的小单」的目标单笔手数：尽量贴近本档笔均
    # window_lots / count，让同档各笔手数接近；若大单量过大导致按笔均拆会
    # 超出本档笔数，则放大到刚好装进剩余笔数（仍受金额门槛约束，保证匿名
    # 对手不会变成大额买单）。这样避免一档里同时出现 2 手和 144 手。
    count_target = max(1, int(plan.get("count") or 0))
    avg_lots = window_lots / count_target
    if not math.isfinite(avg_lots) or avg_lots <= 0:
        avg_lots = 1.0
    leftover_lots = sum(float(s[0]) for s in buys if s[0] > 0) + sum(
        float(s[0]) for s in sells if s[0] > 0
    )
    order_lots_now = matched + leftover_lots
    genuine_small = max(0.0, window_lots - order_lots_now)
    small_rows_reserve = int(math.ceil(genuine_small / avg_lots - 1e-9)) if genuine_small > 0 else 0
    pair_rows = len(rows)
    leftover_budget = max(1, count_target - pair_rows - small_rows_reserve)
    leftover_piece_cap = (
        max(avg_lots, leftover_lots / leftover_budget) if leftover_lots > 0 else avg_lots
    )

    def _flush_leftover(slot: list[Any], *, side: str) -> float:
        lots = slot[0]
        if lots <= 0:
            return 0.0
        display, order_id, order_px = slot[1], slot[2], slot[3]
        order_t = str(slot[4]) if len(slot) > 4 else ""
        order_evt = _slot_evt(slot)
        row_t = _order_fill_stamp(
            stamp,
            {"time": order_t} if order_t else None,
            prev_stamp=str(plan.get("prev_time") or ""),
        )
        # 大单残留拆成多笔、与匿名小单成交。拆笔目标由窗口统一算出的
        # leftover_piece_cap 决定（≈ 本档笔均手数），使同档各笔手数接近；
        # 同时不超过金额门槛（匿名对手仍需低于 30 万，避免凭空冒出大额买单）。
        # 真实大单侧只占一个编号，多笔残片共享它，前端仍合并成一个整块。
        cap_by_threshold = _cap_lots_int(threshold, order_px or price, min_lots=min_lots)
        piece_cap = min(cap_by_threshold, max(1.0, float(leftover_piece_cap)))
        if side == "buy":
            took = _flush_pair(
                lots, display, "",
                order_id=order_id, order_event_id=order_evt, refresh_sell=True,
                row_price=order_px or price, side="buy",
                row_time=row_t, order_time=order_t or row_t, piece_cap=piece_cap,
            )
        else:
            took = _flush_pair(
                lots, "", display,
                order_id=order_id, order_event_id=order_evt, refresh_buy=True,
                row_price=order_px or price, side="sell",
                row_time=row_t, order_time=order_t or row_t, piece_cap=piece_cap,
            )
        slot[0] = 0
        return took

    # 每对真实买卖撮合后，立刻冲掉该对两侧残留，保证同一大单编号连续；
    # 从未配对的大单最后再发。
    buy_by_oid = {str(slot[2]): slot for slot in buys if slot[2]}
    sell_by_oid = {str(slot[2]): slot for slot in sells if slot[2]}
    for row in list(rows):
        if row.get("kind") != "order" or not row.get("order_id_peer"):
            continue
        b_oid = str(row.get("order_id") or "")
        s_oid = str(row.get("order_id_peer") or "")
        if b_oid in buy_by_oid:
            matched += _flush_leftover(buy_by_oid[b_oid], side="buy")
        if s_oid in sell_by_oid:
            matched += _flush_leftover(sell_by_oid[s_oid], side="sell")
    for slot in buys:
        matched += _flush_leftover(slot, side="buy")
    for slot in sells:
        matched += _flush_leftover(slot, side="sell")

    # 完成时刻只写入 order_time，绝不改贴 time（time 必须等于分时档，否则
    # 按秒汇总会把跨窗大单叠到完成秒上，和该秒分时容量对不上）。
    def _ensure_completion_mark(order: Mapping[str, Any]) -> None:
        order_id = str(order.get("order_id") or "")
        order_t = _stamp_key(order.get("time"))
        if not order_id or not order_t or stamp < order_t:
            return
        idxs = [
            i for i, row in enumerate(rows)
            if row.get("kind") == "order"
            and (row.get("order_id") == order_id or row.get("order_id_peer") == order_id)
        ]
        if not idxs or any(str(rows[i].get("order_time") or "") == order_t for i in idxs):
            return
        own = [
            i for i in idxs
            if (rows[i].get("order_id") == order_id and not rows[i].get("order_id_peer"))
            or (rows[i].get("order_id_peer") == order_id and not rows[i].get("order_id"))
        ]
        pool = own or idxs
        src = max(pool, key=lambda i: (str(rows[i].get("time") or ""), float(rows[i].get("lots") or 0)))
        rows[src]["order_time"] = order_t

    for item in placed:
        _ensure_completion_mark(item.get("order") or {})

    small_lots = max(0, window_lots - int(matched))
    if small_lots > 0:
        # 残余小单按剩余笔数拆；若已无剩余笔数，并入已有行（不增笔）。
        order_rows = sum(1 for row in rows if row.get("kind") == "order")
        residual_count = max(0, int(plan.get("count") or 0) - order_rows)
        if residual_count > 0:
            # 笔数硬约束：小单笔数 = 剩余笔数（门槛拆笔让位于笔数守恒）
            _flush_pair(
                small_lots,
                "",
                "",
                kind="small",
                real=False,
                refresh_buy=True,
                refresh_sell=True,
                row_time=stamp,
                piece_count=residual_count,
            )
        elif rows:
            _fold_residual_lots(rows, small_lots)
        else:
            _flush_pair(
                small_lots,
                "",
                "",
                kind="small",
                real=False,
                refresh_buy=True,
                refresh_sell=True,
                row_time=stamp,
                piece_count=1,
            )
    _align_window_vwap(rows, price)
    return rows


def emit_window(
    plan: Mapping[str, Any],
    placed: list[dict[str, Any]],
    ids: _OrderIds | None = None,
) -> list[dict[str, Any]]:
    """把一个窗口展开成逐笔成交（订单成交在前，无归属小单在后）。

    每条输出：``time / price / lots / buy_id / sell_id``。
    集合竞价走多对多配对；连续竞价仍按「一单至少一条记录」。
    量守恒（C1）优先：窗口本身无解时，残余手数会摊回订单成交。
    """
    book = ids or _OrderIds()
    has_buy = any(_order_side(item.get("order") or {}) == "buy" for item in placed)
    has_sell = any(_order_side(item.get("order") or {}) == "sell" for item in placed)
    # 集合竞价，或连续竞价同时有买卖大单：多对多配对（一笔成交服务两侧）
    if plan.get("auction") or _is_call_auction_match(plan.get("time")) or (has_buy and has_sell):
        return _emit_auction_window(plan, placed, book)

    stamp = plan["time"]
    prev_stamp = str(plan.get("prev_time") or "")
    price = _f(plan.get("price")) or 0.0
    window_lots = _lots_int(plan.get("lots"))
    window_count = int(plan.get("count") or 0)
    floor_i = _min_lots_floor(plan.get("min_lots"))
    min_lots = float(floor_i)
    threshold = _f(plan.get("threshold")) or DEFAULT_TRADE_THRESHOLD
    rows: list[dict[str, Any]] = []

    # 笔数 > 手数时保留笔数，用 0 手占位（不再压缩）
    if floor_i > 0 and window_count > window_lots > 0:
        window_count = window_lots

    fills = int(plan.get("fills") or 0)
    order_lots = [_lots_int(item["lots"]) for item in placed]
    # 单边大单：放置阶段已保证 <= V，禁止再裁切/摊派，否则手数对不上资金动向
    order_lots_total = sum(order_lots)
    if order_lots_total > window_lots > 0 and placed:
        # 安全网：按比例压回窗口，但绝不把手数抬高到超过放置量
        scaled = [window_lots * w / order_lots_total for w in order_lots]
        bases = [int(math.floor(x)) for x in scaled]
        left = window_lots - sum(bases)
        ranked = sorted(range(len(bases)), key=lambda i: -(scaled[i] - bases[i]))
        for i in ranked:
            if left <= 0:
                break
            bases[i] += 1
            left -= 1
        order_lots = [min(bases[i], order_lots[i]) for i in range(len(order_lots))]
        order_lots_total = sum(order_lots)
    reserve = 1 if window_lots - order_lots_total > 0 else 0
    if placed:
        if reserve == 0:
            fills = window_count
        else:
            fills = min(max(fills, len(placed)), max(len(placed), window_count - 1))

        count = len(placed)
        weights = [float(w) for w in order_lots]
        unit = max(1, floor_i)
        caps = [max(1, int(math.floor(weight / unit + 1e-6))) for weight in weights]
        if fills <= sum(caps):
            shares = [1] * count
            left = max(0, fills - count)
            ranked = sorted(range(count), key=lambda i: -weights[i])
            while left > 0:
                moved = False
                for i in ranked:
                    if left <= 0:
                        break
                    if shares[i] < caps[i]:
                        shares[i] += 1
                        left -= 1
                        moved = True
                if not moved:
                    break
        else:
            base = fills // count
            rest = fills - base * count
            shares = [base + (1 if i < rest else 0) for i in range(count)]
    else:
        shares = [0] * len(placed)

    order_rows_total = sum(share for share in shares if share > 0) if placed else 0
    small_count = max(0, window_count - order_rows_total)
    small_lots = max(0, window_lots - order_lots_total)
    # 有残余手数但没小单槽位：并入已有行（不增笔）；归因用 attributed_lots 保资金动向手数

    for item, share, lots_i in zip(placed, shares, order_lots):
        if lots_i <= 0:
            continue
        order = item["order"]
        k = max(1, share)
        # 大单用资金动向价格，便于与左侧列表对照
        order_price = _f(order.get("price")) or price
        # 笔数硬约束：单边大单不按金额门槛再拆笔（否则会撑破窗口笔数）
        aggressor_id = book.bind(order)
        aggressor = order.get("side") or "buy"
        fill_stamp = _order_fill_stamp(stamp, order, prev_stamp=prev_stamp)
        for lots in _split(lots_i, k):
            if lots <= 0:
                continue
            _append_matches(
                rows,
                book,
                stamp=fill_stamp,
                window_time=stamp,
                price=order_price,
                lots=lots,
                trades=1,
                aggressor=aggressor,
                aggressor_id=aggressor_id,
                order_id=str(order.get("order_id") or ""),
                order_event_id=str(order.get("event_id") or ""),
                order_time=_stamp_key(order.get("time")),
                kind="order",
                real=True,
            )

    # 小单 time 用窗左端（与同窗回溯大单一致），避免按 time 排序时
    # 出现「大单113 @左端 → 小单10 @右端 → 大单87 @完成秒」夹心。
    small_stamp = (
        _stamp_key(prev_stamp)
        if prev_stamp and _stamp_key(prev_stamp) < stamp
        else (_shift_stamp(stamp, -3) if stamp else stamp)
    )
    if not small_stamp:
        small_stamp = stamp

    if small_count > 0:
        if floor_i > 0:
            small_count = min(small_count, max(small_lots, 0) // floor_i if small_lots else 0)
        if small_count > 0:
            sizes = _split(small_lots, small_count)
            side = plan.get("side") or "buy"
            for lots in sizes:
                _append_matches(
                    rows,
                    book,
                    stamp=small_stamp,
                    window_time=stamp,
                    price=price,
                    lots=lots,
                    trades=1,
                    aggressor=side,
                    kind="small",
                    real=False,
                    allow_zero=True,
                )
    elif small_lots > 0:
        if rows:
            _fold_residual_lots(rows, small_lots)
        else:
            _append_matches(
                rows,
                book,
                stamp=small_stamp,
                window_time=stamp,
                price=price,
                lots=small_lots,
                trades=1,
                aggressor=plan.get("side") or "buy",
                kind="small",
                real=False,
                allow_zero=True,
            )
    _align_window_vwap(rows, price)
    return rows


# ---------------------------------------------------------------------------
# 6. 全天编排
# ---------------------------------------------------------------------------

def reconstruct_windows(
    ticks: Iterable[Mapping[str, Any]] | None,
    big_deals: Iterable[Mapping[str, Any]] | None = None,
    *,
    code: str = "",
    day: str = "",
    threshold: float = DEFAULT_TRADE_THRESHOLD,
    min_lots: float = DEFAULT_MIN_LOTS,
    avg_lots_per_tick: float = DEFAULT_AVG_LOTS_PER_TICK,
    max_lookback: int = 0,
    view: str = "all",
    with_rows: bool = True,
    with_windows: bool = True,
) -> dict[str, Any]:
    """分时成交 × 资金动向 → 一个满足全部约束的逐笔成交序列。

    ``rows`` 每条为：``time / price / lots / buy_id / sell_id``
    （另附 ``seq/side/kind/order_id/real`` 便于归因统计）。

    ``min_lots`` 是单笔下限，默认 0 手。输出手数一律为整手（0 / 1 / 2 …），
    禁止小数手；``笔数 > 手数`` 时用 0 手占位，仍保持笔数守恒。
    ``view`` 默认 ``all``：主/被买卖大单全部纳入。
    """
    windows, source_stats = build_windows(ticks, avg_lots_per_tick=avg_lots_per_tick)
    orders = normalize_orders(big_deals, threshold=threshold, view=view)

    pack: dict[str, Any] = {
        "code": code,
        "day": day,
        "granularity": "window",
        "threshold": threshold,
        "params": {
            "max_lookback": int(max_lookback or 0),
            "view": view,
            "min_lots": min_lots,
        },
        "windows": source_stats["windows"],
        "orders": len(orders),
        "notes": [],
        "rows": [],
        "count": 0,
    }
    if not windows:
        pack["notes"].append("分时成交为空，无法还原")
        pack["summary"] = _empty_summary()
        pack["reconcile"] = {"lot_mismatch_windows": 0, "count_mismatch_windows": 0, "infeasible": []}
        return pack

    plans, allocation, unplaced = plan_windows(
        windows, orders, threshold=threshold, min_lots=min_lots, max_lookback=max_lookback
    )

    rows: list[dict[str, Any]] = []
    if with_rows:
        book = _OrderIds()
        for index, plan in enumerate(plans):
            plan = dict(plan)
            plan["prev_time"] = str(windows[index - 1]["time"]) if index > 0 else ""
            rows.extend(emit_window(plan, allocation.get(plan["index"], []), ids=book))
        # 排序目标：跨窗大单整块连续（禁止 113 + 小单10 + 87 夹心），
        # 同时按分时档 window_time 对账。
        # 规则：跨多窗大单以首窗为锚；同锚下先排「早于该大单首窗的小单」，
        # 再排大单各窗切片（按 window_time），该窗残余小单挪到整块大单之后。
        for emit_i, row in enumerate(rows):
            row["_emit"] = emit_i
        oid_wins: dict[str, set[str]] = {}
        for row in rows:
            if row.get("kind") != "order":
                continue
            wt = str(row.get("window_time") or row.get("time") or "")
            for key in (row.get("order_id"), row.get("order_id_peer")):
                oid = str(key or "")
                if not oid:
                    continue
                oid_wins.setdefault(oid, set()).add(wt)
        multi_oids = {oid for oid, wins in oid_wins.items() if len(wins) > 1}
        # 每个分时档：若有跨窗大单占用以该档为锚，则本档小单改挂到「大单块之后」
        span_anchor_by_win: dict[str, str] = {}
        for oid in multi_oids:
            anchor = min(oid_wins[oid])
            for wt in oid_wins[oid]:
                prev = span_anchor_by_win.get(wt)
                if prev is None or anchor < prev:
                    span_anchor_by_win[wt] = anchor

        # 同一分时档内，把「同一张真实大单」的多笔成交排到一起（R9）。
        # 一张大卖单可能连续吃掉多张被动买单（839 = 501 + 172 + 166），
        # 若按逐笔撮合顺序出胶带，这些切片会被别的订单隔开，前端就只能
        # 各显示各的手数。这里用并查集把同一笔成交的 buy_id / sell_id 连成
        # 一族，同族订单行在档内按族聚拢，前端相邻同编号即可合并成整块。
        parent: dict[str, str] = {}

        def _find(key: str) -> str:
            parent.setdefault(key, key)
            root = key
            while parent[root] != root:
                root = parent[root]
            while parent[key] != root:
                parent[key], key = root, parent[key]
            return root

        def _union(a: str, b: str) -> None:
            ra, rb = _find(a), _find(b)
            if ra == rb:
                return
            # 取字典序小的做根，保证输出稳定可复现
            if ra <= rb:
                parent[rb] = ra
            else:
                parent[ra] = rb

        for row in rows:
            if row.get("kind") != "order":
                continue
            bid = str(row.get("buy_id") or "")
            sid = str(row.get("sell_id") or "")
            if bid and sid:
                _union(bid, sid)
            elif bid:
                _find(bid)
            elif sid:
                _find(sid)
        for row in rows:
            if row.get("kind") != "order":
                continue
            bid = str(row.get("buy_id") or "")
            sid = str(row.get("sell_id") or "")
            anchor_id = bid or sid
            row["_grp"] = _find(anchor_id) if anchor_id else ""

        def _tape_sort_key(row: dict[str, Any]) -> tuple:
            wt = str(row.get("window_time") or row.get("time") or "")
            emit = int(row.get("_emit") or 0)
            if row.get("kind") != "order":
                anchor = span_anchor_by_win.get(wt)
                if anchor is not None:
                    # 本窗有跨窗大单：小单排在该大单整块之前（同锚、相位 0），
                    # 避免夹在两段大单中间。
                    return (anchor, 0, wt, "", emit)
                return (wt, 0, wt, "", emit)
            oids = [
                str(key)
                for key in (row.get("order_id"), row.get("order_id_peer"))
                if key
            ]
            grp = str(row.get("_grp") or "")
            spanning = [oid for oid in oids if oid in multi_oids]
            if spanning:
                anchor = min(oid_wins[spanning[0]])
                return (anchor, 1, wt, grp, emit)
            return (wt, 1, wt, grp, emit)

        rows.sort(key=_tape_sort_key)
        for seq, row in enumerate(rows, start=1):
            row["seq"] = seq
            row.pop("_emit", None)
            row.pop("_grp", None)

    infeasible = [
        {
            "time": plan["time"],
            "lots": plan["lots"],
            "count": plan["count"],
            "order_lots": plan["order_lots"],
            "small_lots": plan["small_lots"],
            "fills_range": [plan["fills_lo"], plan["fills_hi"]],
        }
        for plan in plans
        if not plan["feasible"]
    ]
    lot_mismatch = count_mismatch = 0
    if rows:
        # 用 window_time（分时档）对账量守恒；time 可能已被改成资金动向时刻
        seen: dict[str, list[float]] = {}
        for row in rows:
            win = str(row.get("window_time") or row.get("time") or "")
            slot = seen.setdefault(win, [0.0, 0])
            slot[0] += row["lots"]
            slot[1] += 1
        for plan in plans:
            got = seen.get(plan["time"], [0.0, 0])
            if abs(got[0] - plan["lots"]) > 0.05:
                lot_mismatch += 1
            if plan.get("auction"):
                continue
            # 连续竞价：笔数必须精确相等（允许 0 手占位）
            if got[1] != plan["count"]:
                count_mismatch += 1

    # 逐订单归因：order_id + order_id_peer 合计应等于资金动向手数。
    # 笔数不够时残余并入胶带 lots，归因改读 attributed_lots（若有）。
    # 配对行两侧共用同一 lots；折叠抬高后两侧仍只计 attributed_lots。
    attributed: dict[str, float] = {str(order.get("order_id") or ""): 0.0 for order in orders}
    for row in rows:
        if row.get("kind") != "order":
            continue
        fill = row.get("attributed_lots")
        if fill is None:
            fill = row.get("lots") or 0
        fill_f = float(fill)
        for key in (row.get("order_id"), row.get("order_id_peer")):
            kid = str(key or "")
            if kid in attributed:
                attributed[kid] += fill_f
    order_lot_mismatch = []
    matched_order_lots = 0.0
    for order in orders:
        oid = str(order.get("order_id") or "")
        need = float(order.get("lots") or 0)
        got = float(attributed.get(oid) or 0)
        matched_order_lots += min(need, got)
        if abs(got - need) > 0.5:
            order_lot_mismatch.append(
                {
                    "order_id": oid,
                    "time": order.get("time"),
                    "side": order.get("side"),
                    "need": need,
                    "got": got,
                }
            )

    source_order_lots = round(sum(order["lots"] for order in orders), 3)
    total_lots = round(sum(window["lots"] for window in windows), 3)
    total_count = sum(window["count"] for window in windows)
    # 胶带上 kind=order 的成交量（买卖配对后每笔只计一次，<= 当日总量）
    filled_order_lots = round(
        sum(float(row.get("lots") or 0) for row in rows if row.get("kind") == "order"),
        3,
    )
    filled_small_lots = round(total_lots - filled_order_lots, 3)

    pack["summary"] = {
        "lots": total_lots,
        "count": total_count,
        "order_lots": round(matched_order_lots, 3),
        "order_tape_lots": filled_order_lots,
        "order_source_lots": source_order_lots,
        "order_count": len(orders),
        "small_lots": filled_small_lots,
        "small_count": max(0, total_count - len(orders)),
        "order_ratio": round(100.0 * filled_order_lots / total_lots, 2) if total_lots else 0.0,
        "windows": len(windows),
    }
    # 生成后按需求清单验收；硬伤则定向修复再验（不是盲目重掷）
    from company.analysis.deal.validate import enforce_constraints

    constraints = (
        enforce_constraints(rows, windows, orders, min_lots=min_lots)
        if rows
        else {"ok": True, "hard": [], "soft": [], "hard_count": 0, "soft_count": 0, "checks": {}, "repairs": []}
    )
    pack["reconcile"] = {
        "lot_mismatch_windows": lot_mismatch,
        "count_mismatch_windows": count_mismatch,
        "infeasible_windows": len(infeasible),
        "infeasible": infeasible[:20],
        "unplaced_orders": unplaced[:20],
        "unplaced_count": len(unplaced),
        "order_lot_mismatch": order_lot_mismatch[:20],
        "order_lot_mismatch_count": len(order_lot_mismatch),
        "constraints_ok": bool(constraints.get("ok")),
        "constraints_hard_count": int(constraints.get("hard_count") or 0),
        "constraints_soft_count": int(constraints.get("soft_count") or 0),
        "constraints_repairs": list(constraints.get("repairs") or []),
        "constraints": constraints,
    }
    pack["fills"] = _fill_stats(rows, orders)
    pack["ambiguity"] = _ambiguity(plans)

    if source_stats["auction_dropped"]:
        pack["notes"].append(
            f"已剔除 {source_stats['auction_dropped']} 条集合竞价累计虚拟撮合快照"
        )
    if source_stats["estimated_windows"]:
        pack["notes"].append(
            f"{source_stats['estimated_windows']} 个窗口缺笔数，按笔均 "
            f"{avg_lots_per_tick} 手估算"
        )
    if infeasible:
        pack["notes"].append(
            f"{len(infeasible)} 个窗口在约束下无解（订单量 / 笔数与总量矛盾），已按下界强行展开"
        )
    if unplaced:
        pack["notes"].append(f"{len(unplaced)} 个订单超出可用成交量，未完整放置")
    if order_lot_mismatch:
        pack["notes"].append(
            f"{len(order_lot_mismatch)} 个大单手数与资金动向不一致"
        )
    if lot_mismatch or count_mismatch:
        pack["notes"].append(
            f"对账：手数不符窗口 {lot_mismatch}，笔数不符窗口 {count_mismatch}"
        )
    if constraints.get("repairs"):
        pack["notes"].append(
            f"约束修复 {len(constraints['repairs'])} 步：{', '.join(constraints['repairs'][:5])}"
        )
    if not constraints.get("ok"):
        hard = constraints.get("hard") or []
        codes = ", ".join(str(item.get("code") or "?") for item in hard[:5])
        pack["notes"].append(
            f"硬约束未通过 {constraints.get('hard_count') or 0} 项（{codes}）"
        )
    elif constraints.get("soft_count"):
        pack["notes"].append(
            f"软约束提示 {constraints.get('soft_count')} 项"
            f"（如大单吃满窗时均价与资金动向价不可兼得）"
        )

    if with_windows:
        pack["window_bars"] = [
            {
                "time": plan["time"],
                "lots": plan["lots"],
                "count": plan["count"],
                "price": round(plan["price"], 3),
                "side": plan["side"],
                "auction": bool(plan.get("auction")),
                "order_lots": plan["order_lots"],
                "order_count": plan["order_count"],
                "small_lots": plan["small_lots"],
                "small_count": plan["small_count"],
                "fills_range": [plan["fills_lo"], plan["fills_hi"]],
                "feasible": plan["feasible"],
            }
            for plan in plans
        ]
    if with_rows:
        pack["rows"] = rows
        pack["count"] = len(rows)
    return pack


def _empty_summary() -> dict[str, Any]:
    return {
        "lots": 0.0,
        "count": 0,
        "order_lots": 0.0,
        "order_count": 0,
        "small_lots": 0.0,
        "small_count": 0,
        "order_ratio": 0.0,
        "windows": 0,
    }


def _fill_stats(rows: list[dict[str, Any]], orders: list[dict[str, Any]]) -> dict[str, Any]:
    """每个订单被拆成几笔成交。"""
    if not rows or not orders:
        return {"mean": 0.0, "median": 0, "max": 0, "histogram": {}}
    known = {str(order.get("order_id") or "") for order in orders}
    counter: dict[str, int] = {key: 0 for key in known if key}
    for row in rows:
        if row.get("kind") != "order":
            continue
        for key in (row.get("order_id"), row.get("order_id_peer")):
            kid = str(key or "")
            if kid and kid in counter:
                counter[kid] += 1
    values = sorted(counter.values()) or [0]
    histogram: dict[str, int] = {}
    for value in values:
        key = str(value) if value < 10 else "10+"
        histogram[key] = histogram.get(key, 0) + 1
    return {
        "mean": round(sum(values) / len(values), 2),
        "median": values[len(values) // 2],
        "max": values[-1],
        "histogram": dict(sorted(histogram.items(), key=lambda kv: (len(kv[0]), kv[0]))),
    }


def _ambiguity(plans: list[dict[str, Any]]) -> dict[str, Any]:
    """量化解空间：小单手数分配方式的组合规模 + 需猜测的窗口数。"""
    log10_total = 0.0
    guess_windows = 0
    for plan in plans:
        small_count = int(plan.get("small_count") or 0)
        if small_count < 1:
            continue
        if small_count > 1:
            guess_windows += 1
        log10_total += _log10_compositions(_f(plan.get("small_lots")), small_count)
    return {
        "undetermined_windows": guess_windows,
        "solutions_log10": round(log10_total, 1),
        "unique": log10_total < 1e-6,
    }


__all__ = [
    "DEFAULT_AVG_LOTS_PER_TICK",
    "DEFAULT_MIN_LOTS",
    "DEFAULT_TRADE_THRESHOLD",
    "TRADE_MIN_LOTS",
    "build_windows",
    "emit_window",
    "normalize_orders",
    "place_orders",
    "plan_window",
    "plan_windows",
    "reconstruct_windows",
]
