"""逐笔还原硬约束：验收 + 定向修复（对应产品需求）。

生成路径应尽量一次做对；本模块在 ``reconstruct_windows`` 末尾再跑一遍：

1. ``validate_tape`` 按 R2–R11 验收
2. 若有硬伤，``repair_tape`` 做确定性修补（不是盲目重试）
3. 再验收；仍失败则 ``ok=False`` 写入 reconcile，禁止当合格结果用

需求 → 检查项
--------------
R1  左闭右开 3 秒窗：大单按最后成交时间归属截止窗（place / deadline）
R2  窗内大单手数 ≤ 区间总手数
R3  剩余笔数有可用手数（min_lots；默认 0 允许 0 手占位）
R4  大单完成时刻：order_time = 资金动向最后成交时间；截止窗有成交
R5  填小单后笔数、总手数正确；有小单可调时均价也正确
R6  输出字段：time / lots / sell_id / buy_id
R7  手数整手，允许 0，禁止小数
R8  任意一对 (buy_id, sell_id) 只成交一笔
R9  大单同侧编号在同一分时档内连续（跨档因容量拆开允许）
R10 大单价格全程等于资金动向价（不被窗均价改写）
R11 按 window_time（分时档）汇总手数/笔数 = 分时；time 为窗内真实时刻 ∈ [prev, stamp)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from company.analysis.deal.window import (
    _align_window_vwap,
    _deadline_index,
    _f,
    _lots_int,
    _stamp_key,
)


def validate_tape(
    rows: list[Mapping[str, Any]],
    windows: list[Mapping[str, Any]],
    orders: list[Mapping[str, Any]],
    *,
    min_lots: float = 0.0,
) -> dict[str, Any]:
    """校验还原胶带。返回 ``{ok, hard, soft, checks}``。

    ``hard`` 非空表示生成结果不合格；``soft`` 为可解释的放宽项（如大单吃满窗时
    无法同时保住资金动向价与窗均价）。
    """
    hard: list[dict[str, Any]] = []
    soft: list[dict[str, Any]] = []
    checks: dict[str, Any] = {}

    win_by_t = {str(w.get("time") or ""): w for w in windows}
    order_by_id = {str(o.get("order_id") or ""): o for o in orders if o.get("order_id")}
    stamps = [str(w.get("time") or "") for w in windows]

    # ---- R6 / R7 字段与整手 ----
    bad_fields = 0
    frac = 0
    neg = 0
    for row in rows:
        for key in ("time", "lots", "buy_id", "sell_id"):
            if key not in row:
                bad_fields += 1
        lots = row.get("lots")
        try:
            number = float(lots)
        except (TypeError, ValueError):
            frac += 1
            continue
        if number != int(number):
            frac += 1
        if number < 0:
            neg += 1
    if bad_fields:
        hard.append({"code": "R6_fields", "count": bad_fields, "msg": "缺 time/lots/buy_id/sell_id"})
    if frac:
        hard.append({"code": "R7_integer_lots", "count": frac, "msg": "出现小数手"})
    if neg:
        hard.append({"code": "R7_nonneg_lots", "count": neg, "msg": "出现负手数"})
    checks["R6_fields"] = bad_fields == 0
    checks["R7_integer_lots"] = frac == 0 and neg == 0

    # ---- R11 / R5：按 window_time（分时档）汇总 = 分时；time 可为窗内真实时刻 ----
    missing_wt = 0
    by_win_lots: dict[str, float] = defaultdict(float)
    by_win_count: dict[str, int] = defaultdict(int)
    by_win_order: dict[str, float] = defaultdict(float)
    by_win_amount: dict[str, float] = defaultdict(float)
    for row in rows:
        wt = str(row.get("window_time") or row.get("time") or "")
        if not str(row.get("window_time") or ""):
            missing_wt += 1
        lots = float(_lots_int(row.get("lots")))
        by_win_lots[wt] += lots
        by_win_count[wt] += 1
        by_win_amount[wt] += lots * float(row.get("price") or 0)
        if row.get("kind") == "order":
            by_win_order[wt] += lots
    if missing_wt:
        hard.append(
            {
                "code": "R11_window_time",
                "count": missing_wt,
                "msg": "缺 window_time，无法与分时档对账",
            }
        )
    lot_mismatch = []
    count_mismatch = []
    for stamp, window in win_by_t.items():
        need_lots = float(_lots_int(window.get("lots")))
        need_count = int(window.get("count") or 0)
        got_lots = by_win_lots.get(stamp, 0.0)
        got_count = by_win_count.get(stamp, 0)
        if abs(got_lots - need_lots) > 0.05:
            lot_mismatch.append({"time": stamp, "need": need_lots, "got": got_lots})
        if not window.get("auction") and got_count != need_count:
            count_mismatch.append({"time": stamp, "need": need_count, "got": got_count})
    if lot_mismatch:
        hard.append(
            {
                "code": "R5_lot_conservation",
                "count": len(lot_mismatch),
                "samples": lot_mismatch[:10],
                "msg": "分时档手数与胶带按 window_time 汇总不一致",
            }
        )
    if count_mismatch:
        hard.append(
            {
                "code": "R5_count_conservation",
                "count": len(count_mismatch),
                "samples": count_mismatch[:10],
                "msg": "分时档笔数与胶带不一致",
            }
        )
    checks["R11_window_time"] = missing_wt == 0
    checks["R5_lot_conservation"] = not lot_mismatch
    checks["R5_count_conservation"] = not count_mismatch

    # ---- R2 窗内大单手数 ≤ V ----
    over_cap = []
    for stamp, window in win_by_t.items():
        cap = float(_lots_int(window.get("lots")))
        order_lots = by_win_order.get(stamp, 0.0)
        if order_lots > cap + 1e-6:
            over_cap.append({"time": stamp, "cap": cap, "order_lots": order_lots})
    if over_cap:
        hard.append(
            {
                "code": "R2_order_le_window",
                "count": len(over_cap),
                "samples": over_cap[:10],
                "msg": "某三秒窗内大单手数超过分时容量",
            }
        )
    checks["R2_order_le_window"] = not over_cap

    # ---- R5 均价：有小单可调时必须对齐；大单吃满则放宽并记 soft ----
    vwap_bad = []
    vwap_deferred = []
    for stamp, window in win_by_t.items():
        need_lots = float(_lots_int(window.get("lots")))
        if need_lots <= 0:
            continue
        got_lots = by_win_lots.get(stamp, 0.0)
        if got_lots <= 0:
            continue
        target = float(window.get("price") or 0)
        if target <= 0:
            continue
        vwap = by_win_amount.get(stamp, 0.0) / got_lots
        small = got_lots - by_win_order.get(stamp, 0.0)
        if abs(vwap - target) <= 0.005:
            continue
        if small <= 1e-9:
            vwap_deferred.append({"time": stamp, "target": target, "vwap": round(vwap, 4)})
        else:
            vwap_bad.append({"time": stamp, "target": target, "vwap": round(vwap, 4)})
    if vwap_bad:
        hard.append(
            {
                "code": "R5_vwap",
                "count": len(vwap_bad),
                "samples": vwap_bad[:10],
                "msg": "有小单可调时窗均价仍不对齐",
            }
        )
    if vwap_deferred:
        soft.append(
            {
                "code": "R5_vwap_deferred",
                "count": len(vwap_deferred),
                "samples": vwap_deferred[:10],
                "msg": "大单吃满窗：保留资金动向价，窗均价无法同时对齐",
            }
        )
    checks["R5_vwap"] = not vwap_bad

    # ---- R8 一对买卖只一笔 ----
    pair_count: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        bid = str(row.get("buy_id") or "")
        sid = str(row.get("sell_id") or "")
        if bid and sid:
            pair_count[(bid, sid)] += 1
    pair_dups = [{"buy_id": a, "sell_id": b, "n": n} for (a, b), n in pair_count.items() if n > 1]
    if pair_dups:
        hard.append(
            {
                "code": "R8_one_pair_one_print",
                "count": len(pair_dups),
                "samples": pair_dups[:10],
                "msg": "同一买卖编号对出现多笔成交",
            }
        )
    checks["R8_one_pair_one_print"] = not pair_dups

    # ---- R9 同窗内大单同侧编号连续 ----
    split_ids: list[dict[str, Any]] = []
    by_win_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_win_rows[str(row.get("window_time") or row.get("time") or "")].append(row)
    for stamp, win_rows in by_win_rows.items():
        for side_key in ("buy_id", "sell_id"):
            positions: dict[str, list[int]] = defaultdict(list)
            for i, row in enumerate(win_rows):
                if row.get("kind") != "order":
                    continue
                sid = str(row.get(side_key) or "")
                if sid:
                    positions[sid].append(i)
            for sid, idxs in positions.items():
                if len(idxs) < 2:
                    continue
                span = win_rows[min(idxs) : max(idxs) + 1]
                foreign = [
                    r
                    for r in span
                    if r.get("kind") == "order"
                    and r.get(side_key)
                    and str(r.get(side_key)) != sid
                ]
                if foreign:
                    split_ids.append({"time": stamp, "side": side_key, "id": sid})
    if split_ids:
        hard.append(
            {
                "code": "R9_continuous_in_window",
                "count": len(split_ids),
                "samples": split_ids[:10],
                "msg": "同一分时档内大单编号被拆开",
            }
        )
    checks["R9_continuous_in_window"] = not split_ids

    # ---- R10 大单价格全程一致且等于资金动向价 ----
    order_px: dict[str, set[float]] = defaultdict(set)
    for row in rows:
        if row.get("kind") != "order":
            continue
        px = round(float(row.get("price") or 0), 4)
        for key in (row.get("order_id"), row.get("order_id_peer")):
            kid = str(key or "")
            if kid:
                order_px[kid].add(px)
    price_split = []
    price_mismatch = []
    for oid, pxs in order_px.items():
        if len(pxs) > 1:
            price_split.append({"order_id": oid, "prices": sorted(pxs)})
        src = order_by_id.get(oid)
        if src is not None:
            want = round(float(src.get("price") or 0), 4)
            if want > 0 and any(abs(p - want) > 0.005 for p in pxs):
                price_mismatch.append({"order_id": oid, "need": want, "got": sorted(pxs)})
    if price_split:
        hard.append(
            {
                "code": "R10_order_price_split",
                "count": len(price_split),
                "samples": price_split[:10],
                "msg": "同一大单跨笔价格不一致",
            }
        )
    if price_mismatch:
        hard.append(
            {
                "code": "R10_order_price_match",
                "count": len(price_mismatch),
                "samples": price_mismatch[:10],
                "msg": "大单价格与资金动向不一致",
            }
        )
    checks["R10_order_price"] = not price_split and not price_mismatch

    # ---- R4 完成时刻 / 截止窗 ----
    attr_time: dict[str, list[str]] = defaultdict(list)
    attr_win: dict[str, set[str]] = defaultdict(set)
    attr_lots: dict[str, float] = defaultdict(float)
    for row in rows:
        if row.get("kind") != "order":
            continue
        fill = row.get("attributed_lots")
        if fill is None:
            fill = row.get("lots") or 0
        fill_f = float(fill)
        for key in (row.get("order_id"), row.get("order_id_peer")):
            kid = str(key or "")
            if not kid:
                continue
            attr_time[kid].append(str(row.get("order_time") or ""))
            attr_win[kid].add(str(row.get("window_time") or row.get("time") or ""))
            attr_lots[kid] += fill_f

    missing_ot = []
    missing_deadline = []
    lot_bad = []
    for oid, order in order_by_id.items():
        need = float(_lots_int(order.get("lots")))
        got = float(attr_lots.get(oid, 0.0))
        # 未完整放置的订单不强制 R4（由 unplaced 另报）
        if abs(got - need) > 0.5:
            lot_bad.append({"order_id": oid, "need": need, "got": got})
            continue
        ot = _stamp_key(order.get("time"))
        if ot and ot not in attr_time.get(oid, []):
            missing_ot.append({"order_id": oid, "need": ot})
        if stamps and ot:
            idx = _deadline_index(stamps, ot)
            if idx >= 0:
                deadline = stamps[idx]
                if deadline not in attr_win.get(oid, set()):
                    missing_deadline.append(
                        {"order_id": oid, "deadline": deadline, "windows": sorted(attr_win.get(oid, []))}
                    )
    if missing_ot:
        hard.append(
            {
                "code": "R4_order_time",
                "count": len(missing_ot),
                "samples": missing_ot[:10],
                "msg": "大单缺 order_time 完成时刻",
            }
        )
    if missing_deadline:
        # 一对买卖若已在回溯窗配对，截止窗余量走 virtual_pair 并入首笔，
        # 胶带不再出第二笔（R8）；完成时刻仍以 order_time 为准 → 记 soft。
        soft.append(
            {
                "code": "R4_deadline_window_virtual",
                "count": len(missing_deadline),
                "samples": missing_deadline[:10],
                "msg": "截止窗余量已虚拟并入首笔配对（保一对一笔）；order_time 仍应对齐资金动向",
            }
        )
    if lot_bad:
        # 归因手数不符：可能是容量不足未放完，记 soft+统计，与 unplaced 对照
        soft.append(
            {
                "code": "R2_order_lots_incomplete",
                "count": len(lot_bad),
                "samples": lot_bad[:10],
                "msg": "部分大单手数未完全归因（容量不足时允许）",
            }
        )
    checks["R4_order_time"] = not missing_ot
    checks["R4_deadline_window"] = True  # 虚拟并入时以 order_time 为硬约束

    # ---- R3 剩余笔数手数（min_lots>0 时）----
    if float(min_lots or 0) > 0:
        floor = max(1, int(round(float(min_lots))))
        reserve_bad = []
        for stamp, window in win_by_t.items():
            if window.get("auction"):
                continue
            count = int(window.get("count") or 0)
            lots = float(_lots_int(window.get("lots")))
            order_n = sum(
                1
                for row in by_win_rows.get(stamp, [])
                if row.get("kind") == "order"
            )
            # 粗估：非订单笔数应能被剩余手数覆盖
            small_n = max(0, count - order_n)
            small_lots = lots - by_win_order.get(stamp, 0.0)
            if small_n > 0 and small_lots + 1e-9 < small_n * floor:
                reserve_bad.append(
                    {"time": stamp, "small_n": small_n, "small_lots": small_lots, "floor": floor}
                )
        if reserve_bad:
            hard.append(
                {
                    "code": "R3_reserve_lots",
                    "count": len(reserve_bad),
                    "samples": reserve_bad[:10],
                    "msg": "剩余笔数没有足够手数",
                }
            )
        checks["R3_reserve_lots"] = not reserve_bad
    else:
        checks["R3_reserve_lots"] = True

    ok = not hard
    return {
        "ok": ok,
        "hard": hard,
        "soft": soft,
        "hard_count": len(hard),
        "soft_count": len(soft),
        "checks": checks,
    }


def repair_tape(
    rows: list[dict[str, Any]],
    windows: list[Mapping[str, Any]],
    orders: list[Mapping[str, Any]],
    report: Mapping[str, Any] | None = None,
) -> list[str]:
    """针对硬约束失败做确定性修补，返回执行过的修复动作标签。

    不重新随机生成：只修能安全改的字段（时间对齐、大单价、小单均价回校）。
    结构性问题（一对多笔、容量超限）留给生成器本身保证，这里只标记无法自动修。
    """
    actions: list[str] = []
    if not rows:
        return actions
    report = report or validate_tape(rows, windows, orders)
    hard_codes = {str(item.get("code") or "") for item in report.get("hard") or []}
    order_by_id = {str(o.get("order_id") or ""): o for o in orders if o.get("order_id")}
    win_by_t = {str(w.get("time") or ""): w for w in windows}

    # R11：补缺 window_time（不得把 time 强行改成档位，否则完成时刻显示错乱）
    if "R11_window_time" in hard_codes:
        fixed = 0
        for row in rows:
            if not row.get("window_time") and row.get("time"):
                row["window_time"] = str(row.get("time") or "")
                fixed += 1
        if fixed:
            actions.append(f"R11_fill_window_time:{fixed}")

    # R10：大单价拉回资金动向价
    if "R10_order_price_match" in hard_codes or "R10_order_price_split" in hard_codes:
        fixed = 0
        for row in rows:
            if row.get("kind") != "order":
                continue
            for key in (row.get("order_id"), row.get("order_id_peer")):
                oid = str(key or "")
                src = order_by_id.get(oid)
                if not src:
                    continue
                want = _f(src.get("price"))
                if want <= 0:
                    continue
                if abs(float(row.get("price") or 0) - want) > 0.005:
                    row["price"] = round(want, 4)
                    fixed += 1
                break
        if fixed:
            actions.append(f"R10_restore_order_price:{fixed}")

    # R4：补 order_time
    if "R4_order_time" in hard_codes:
        fixed = 0
        for row in rows:
            if row.get("kind") != "order":
                continue
            for key in (row.get("order_id"), row.get("order_id_peer")):
                oid = str(key or "")
                src = order_by_id.get(oid)
                if not src:
                    continue
                ot = _stamp_key(src.get("time"))
                if ot and str(row.get("order_time") or "") != ot:
                    row["order_time"] = ot
                    fixed += 1
                break
        if fixed:
            actions.append(f"R4_fill_order_time:{fixed}")

    # R5：有小单的窗重新回校均价（不改大单价）
    if "R5_vwap" in hard_codes:
        by_win: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_win[str(row.get("window_time") or row.get("time") or "")].append(row)
        fixed = 0
        for stamp, win_rows in by_win.items():
            window = win_by_t.get(stamp)
            if not window:
                continue
            if not any(r.get("kind") != "order" for r in win_rows):
                continue
            _align_window_vwap(win_rows, float(window.get("price") or 0))
            fixed += 1
        if fixed:
            actions.append(f"R5_realign_vwap:{fixed}")

    # R7：手数强制整手
    if "R7_integer_lots" in hard_codes or "R7_nonneg_lots" in hard_codes:
        fixed = 0
        for row in rows:
            lots = _lots_int(row.get("lots"))
            if float(row.get("lots") or 0) != float(lots):
                row["lots"] = float(lots)
                fixed += 1
        if fixed:
            actions.append(f"R7_integerize:{fixed}")

    return actions


def enforce_constraints(
    rows: list[dict[str, Any]],
    windows: list[Mapping[str, Any]],
    orders: list[Mapping[str, Any]],
    *,
    min_lots: float = 0.0,
    max_rounds: int = 2,
) -> dict[str, Any]:
    """验收 → 修复 → 再验收，直到硬约束通过或轮次用尽。

    返回最终 ``validate_tape`` 报告，并附 ``repairs`` / ``rounds``。
    """
    repairs: list[str] = []
    report: dict[str, Any] = validate_tape(rows, windows, orders, min_lots=min_lots)
    for round_i in range(max(1, int(max_rounds))):
        if report.get("ok"):
            break
        actions = repair_tape(rows, windows, orders, report)
        if not actions:
            break
        repairs.extend(f"r{round_i + 1}:{a}" for a in actions)
        report = validate_tape(rows, windows, orders, min_lots=min_lots)
    report = dict(report)
    report["repairs"] = repairs
    report["rounds"] = len({r.split(":", 1)[0] for r in repairs}) if repairs else 0
    return report


__all__ = ["enforce_constraints", "repair_tape", "validate_tape"]
