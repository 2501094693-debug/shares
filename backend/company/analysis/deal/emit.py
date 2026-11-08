"""窗内展开：轴占用 → 逐笔成交带。

- 同价交叉原子 → 1 行（双方编号）
- 异价重叠 → 只留一侧（优先被动）
- 单侧大单的匿名对手 + 纯小单 → **共用剩余笔数预算，整窗均分**（≤30 万）
- R8：跨窗同一对买卖只出一笔，余量 virtual_pair
"""

from __future__ import annotations

from typing import Any, Mapping

from company.analysis.deal.constants import DEFAULT_MIN_LOTS, DEFAULT_TRADE_THRESHOLD
from company.analysis.deal.cost import cap_lots, window_atoms, window_count
from company.analysis.deal.solver import Occupancy
from company.analysis.deal.util import (
    _OrderIds,
    _align_window_vwap,
    _f,
    _keep_sell_side,
    _lots_int,
    _order_fill_stamp,
    _same_price,
    _split,
    _stamp_key,
)


def _allocate_row_counts(weights: list[int], total_rows: int) -> list[int]:
    """按手数比例把 ``total_rows`` 分给各桶（最大余数法）；0 手桶也可分到占位行。"""
    n = len(weights)
    if n == 0 or total_rows <= 0:
        return [0] * n
    mass = sum(max(0, int(w)) for w in weights)
    if mass <= 0:
        # 全 0：尽量均分占位行
        base = total_rows // n
        spare = total_rows - base * n
        return [base + (1 if i < spare else 0) for i in range(n)]
    raw = [total_rows * max(0, int(w)) / mass for w in weights]
    floors = [int(x) for x in raw]
    # 手数 > 0 的桶至少 1 行（后面还要再被 cap 约束抬升时由调用方处理）
    for i, w in enumerate(weights):
        if int(w) > 0 and floors[i] == 0 and total_rows >= sum(
            1 for x in weights if int(x) > 0
        ):
            floors[i] = 1
    assigned = sum(floors)
    # 若至少 1 行把总额撑破，改回纯四舍五入余数
    if assigned > total_rows:
        floors = [int(x) for x in raw]
        assigned = sum(floors)
    rem = total_rows - assigned
    order = sorted(
        range(n),
        key=lambda i: (raw[i] - floors[i], weights[i], -i),
        reverse=True,
    )
    for i in order:
        if rem <= 0:
            break
        floors[i] += 1
        rem -= 1
    return floors


def emit_window(
    window: Mapping[str, Any],
    buy_occ: Occupancy,
    sell_occ: Occupancy,
    orders_by_id: Mapping[str, Mapping[str, Any]],
    ids: _OrderIds,
    *,
    threshold: float = DEFAULT_TRADE_THRESHOLD,
    min_lots: float = DEFAULT_MIN_LOTS,
    stats: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """把轴上 ``[L, R)`` 展开成逐笔行。

    - **交叉原子**（买卖两侧都是大单、同价）→ 1 行，双方编号都在；
    - **单侧原子 + 纯小单** → 共享剩余笔数，按手数比例分摊行数后整窗均分，
      每行 ≤ 30 万门槛；避免「大单对手 ~12 手、纯小单 ~2 手」两极分化。

    跨窗同一对买卖只允许一笔成交（R8）：后续窗里同一对的交叉段不再出行，
    手数改由本窗小单补足，保持每窗手数守恒。
    """
    left = int(window.get("L") or 0)
    right = int(window.get("R") or 0)
    window_lots = right - left
    stamp = str(window.get("time") or "")
    prev_stamp = str(window.get("prev_time") or "")
    price = _f(window.get("price"))
    if window_lots <= 0:
        return []

    count = window_count(window)
    exact = count > 0
    buy_clips = buy_occ.clip_to_window(left, right)
    sell_clips = sell_occ.clip_to_window(left, right)
    atoms = window_atoms(left, right, buy_clips, sell_clips)

    rows: list[dict[str, Any]] = []
    pair_skipped = 0
    singles: list[dict[str, Any]] = []
    residual_small = 0

    def _order_of(oid: str) -> Mapping[str, Any]:
        return orders_by_id.get(oid) or {}

    def _price_of(oid: str) -> float:
        return _f(_order_of(oid).get("price")) or price

    def _row_time(oid: str) -> str:
        return _order_fill_stamp(stamp, _order_of(oid) or None, prev_stamp=prev_stamp)

    def _push(
        *,
        lots: float,
        buy_id: str,
        sell_id: str,
        row_price: float,
        kind: str,
        side: str,
        order_id: str = "",
        order_id_peer: str = "",
        order_time: str = "",
        row_time: str | None = None,
        real: bool = True,
    ) -> None:
        rows.append(
            {
                "time": row_time or _small_stamp(),
                "window_time": stamp,
                "prev_time": prev_stamp,
                "order_time": order_time,
                "price": round(row_price, 2),
                "lots": float(_lots_int(lots)),
                "buy_id": buy_id,
                "sell_id": sell_id,
                "side": side,
                "order_id": order_id,
                "order_id_peer": order_id_peer,
                "order_event_id": str(_order_of(order_id).get("event_id") or "")
                if order_id
                else "",
                "order_peer_event_id": str(_order_of(order_id_peer).get("event_id") or "")
                if order_id_peer
                else "",
                "kind": kind,
                "real": real,
            }
        )

    small_stamp_cache: list[str] = []

    def _small_stamp() -> str:
        if not small_stamp_cache:
            if prev_stamp and prev_stamp < stamp:
                small_stamp_cache.append(prev_stamp)
            else:
                small_stamp_cache.append(stamp)
        return small_stamp_cache[0]

    def _queue_single(oid: str, side: str, lots: int) -> None:
        if lots <= 0:
            return
        singles.append({"oid": oid, "side": side, "lots": int(lots)})

    for atom in atoms:
        lots_i = int(atom["lots"])
        if lots_i <= 0:
            continue
        b_oid = str(atom["buy_oid"] or "")
        s_oid = str(atom["sell_oid"] or "")
        if b_oid and s_oid:
            b_order, s_order = _order_of(b_oid), _order_of(s_oid)
            bpx, spx = _price_of(b_oid), _price_of(s_oid)
            if not _same_price(bpx, spx):
                # 异价重叠：只留一侧编号，另一侧并入匿名池均分
                keep_sell = _keep_sell_side(b_order, s_order)
                if stats is not None:
                    stats["price_split"] = int(stats.get("price_split") or 0) + 1
                _queue_single(
                    s_oid if keep_sell else b_oid,
                    "sell" if keep_sell else "buy",
                    lots_i,
                )
                continue
            if ids.pair_done(b_oid, s_oid):
                # 跨窗同一对只允许一笔（R8）：量进匿名池
                ids.virtual_pair(b_oid, s_oid, float(lots_i))
                pair_skipped += 1
                residual_small += lots_i
                continue
            order_time = min(
                [
                    t
                    for t in (
                        _stamp_key(b_order.get("time")),
                        _stamp_key(s_order.get("time")),
                    )
                    if t
                ]
                or [""]
            )
            row = {
                "time": _order_fill_stamp(
                    stamp,
                    {"time": order_time} if order_time else None,
                    prev_stamp=prev_stamp,
                ),
                "window_time": stamp,
                "prev_time": prev_stamp,
                "order_time": _stamp_key(b_order.get("time")) or order_time,
                "order_time_peer": _stamp_key(s_order.get("time")) or order_time,
                "price": round(bpx, 2),
                "lots": float(lots_i),
                "buy_id": ids.bind(b_order),
                "sell_id": ids.bind(s_order),
                "side": "buy",
                "order_id": b_oid,
                "order_id_peer": s_oid,
                "order_event_id": str(b_order.get("event_id") or ""),
                "order_peer_event_id": str(s_order.get("event_id") or ""),
                "kind": "order",
                "real": True,
            }
            rows.append(row)
            ids.mark_pair(b_oid, s_oid, row)
            continue
        if b_oid or s_oid:
            _queue_single(b_oid or s_oid, "buy" if b_oid else "sell", lots_i)
            continue
        residual_small += lots_i

    anon_lots = sum(int(item["lots"]) for item in singles) + int(residual_small)
    cap_w = cap_lots(threshold, price, min_lots=min_lots)

    if exact:
        need_rows = count - len(rows)
    else:
        need_rows = max(1, -(-anon_lots // cap_w)) if anon_lots > 0 else 0

    if need_rows < 0:
        if stats is not None:
            stats["count_over"] = int(stats.get("count_over") or 0) + 1
        need_rows = 0

    if need_rows > 0 and anon_lots >= 0:
        weights = [int(item["lots"]) for item in singles] + [int(residual_small)]
        # 各桶至少 ceil(lots/cap) 行，避免均分后单笔超 30 万；剩余笔数再按比例分
        mins: list[int] = []
        for item in singles:
            lots_i = int(item["lots"])
            px = _price_of(str(item["oid"]))
            order_cap = cap_lots(threshold, px, min_lots=min_lots)
            mins.append(max(1, -(-lots_i // order_cap)) if lots_i > 0 else 0)
        mins.append(
            max(1, -(-int(residual_small) // cap_w)) if residual_small > 0 else 0
        )
        min_total = sum(mins)
        if min_total > need_rows:
            # 笔数本身不够（矛盾窗）：退回纯比例，可能触发 R12
            counts = _allocate_row_counts(weights, need_rows)
        else:
            extra = need_rows - min_total
            extras = _allocate_row_counts(weights, extra) if extra else [0] * len(weights)
            counts = [m + e for m, e in zip(mins, extras)]
        single_counts = counts[:-1]
        small_count = counts[-1] if counts else 0

        for item, n_rows in zip(singles, single_counts):
            oid = str(item["oid"])
            side = str(item["side"])
            lots_i = int(item["lots"])
            n_rows = int(n_rows)
            if lots_i > 0:
                n_rows = max(1, n_rows)
            if n_rows <= 0:
                continue
            order = _order_of(oid)
            display = ids.bind(order)
            row_time = _row_time(oid)
            order_time = _stamp_key(order.get("time"))
            px = _price_of(oid)
            for piece in _split(lots_i, n_rows):
                if piece < 0:
                    continue
                if side == "buy":
                    _push(
                        lots=piece,
                        buy_id=display,
                        sell_id=ids.next_sell(),
                        row_price=px,
                        kind="order",
                        side="buy",
                        order_id=oid,
                        order_time=order_time,
                        row_time=row_time,
                    )
                else:
                    _push(
                        lots=piece,
                        buy_id=ids.next_buy(),
                        sell_id=display,
                        row_price=px,
                        kind="order",
                        side="sell",
                        order_id=oid,
                        order_time=order_time,
                        row_time=row_time,
                    )

        if small_count > 0:
            sizes = _split(residual_small, small_count)
            w_side = str(window.get("side") or "buy")
            for piece in sizes:
                _push(
                    lots=piece,
                    buy_id=ids.next_buy(),
                    sell_id=ids.next_sell(),
                    row_price=price,
                    kind="small",
                    side=w_side,
                    row_time=_small_stamp(),
                    real=False,
                )
    elif anon_lots > 0 and rows:
        if stats is not None:
            stats["small_folded"] = int(stats.get("small_folded") or 0) + 1
        rows[-1]["lots"] = float(_lots_int(rows[-1].get("lots")) + anon_lots)
    elif anon_lots > 0:
        _push(
            lots=anon_lots,
            buy_id=ids.next_buy(),
            sell_id=ids.next_sell(),
            row_price=price,
            kind="small",
            side=str(window.get("side") or "buy"),
            row_time=_small_stamp(),
            real=False,
        )

    # 笔数被单侧 cap 再拆抬高后，若超过 count，把多出来的空行没有意义——
    # 这里不删行；对账会记 count 不符。正常可行窗不会走到。
    if exact and len(rows) < count:
        # 比例分配后因 rounding 偶发少行：补 0 手小单
        w_side = str(window.get("side") or "buy")
        for _ in range(count - len(rows)):
            _push(
                lots=0,
                buy_id=ids.next_buy(),
                sell_id=ids.next_sell(),
                row_price=price,
                kind="small",
                side=w_side,
                row_time=_small_stamp(),
                real=False,
            )

    _align_small_prices(
        rows, price, threshold=threshold, min_lots=min_lots, stats=stats
    )
    if pair_skipped and stats is not None:
        stats["pair_virtual"] = int(stats.get("pair_virtual") or 0) + pair_skipped
    return rows


def _align_small_prices(
    rows: list[dict[str, Any]],
    target_price: float,
    *,
    threshold: float,
    min_lots: float,
    stats: dict[str, Any] | None = None,
) -> bool:
    """把小单价回校到窗均价；若回校后小单行会超过 30 万门槛则放弃对齐。

    大单永远保留资金动向价（R10），所以均价只能靠小单调。
    """
    small_rows = [row for row in rows if row.get("kind") != "order"]
    if not small_rows:
        return True
    saved = [(row, row.get("price")) for row in small_rows]
    _align_window_vwap(rows, target_price)
    bad = [
        row
        for row in small_rows
        if _lots_int(row.get("lots"))
        > cap_lots(threshold, _f(row.get("price")), min_lots=min_lots)
    ]
    if bad:
        for row, px in saved:
            row["price"] = px
        if stats is not None:
            stats["small_cap_conflict"] = int(stats.get("small_cap_conflict") or 0) + 1
        return False
    return True


__all__ = ["emit_window"]
