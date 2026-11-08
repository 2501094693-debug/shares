"""全天编排：分时 × 资金动向 → 双手数轴 → 簇内联合落位 → 成交带。"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from company.analysis.deal.axis import build_lot_axis
from company.analysis.deal.constants import (
    DEFAULT_AVG_LOTS_PER_TICK,
    DEFAULT_MIN_LOTS,
    DEFAULT_TRADE_THRESHOLD,
)
from company.analysis.deal.cost import check_rows_cap
from company.analysis.deal.emit import emit_window
from company.analysis.deal.ingest import build_windows, normalize_orders
from company.analysis.deal.solver import place_joint
from company.analysis.deal.util import (
    _OrderIds,
    is_active_order,
    is_passive_order,
)
from company.analysis.deal.validate import enforce_constraints


def _order_map(placed: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for meta in placed:
        order = meta.get("order") or {}
        oid = str(order.get("order_id") or "")
        if oid:
            out[oid] = dict(order)
    return out


def _sort_tape_for_continuity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """跨窗大单整块连续；同窗内同编号聚拢（对应旧路径 R9 排序）。"""
    if not rows:
        return rows
    for emit_i, row in enumerate(rows):
        row["_emit"] = emit_i
    oid_wins: dict[str, set[str]] = {}
    for row in rows:
        if row.get("kind") != "order":
            continue
        wt = str(row.get("window_time") or row.get("time") or "")
        for key in (row.get("order_id"), row.get("order_id_peer")):
            oid = str(key or "")
            if oid:
                oid_wins.setdefault(oid, set()).add(wt)
    multi_oids = {oid for oid, wins in oid_wins.items() if len(wins) > 1}

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
        # 同窗内按成交时刻（time / order_time）排，而不是手数轴左右顺序；
        # 轴上靠右偏好会把更早完成的大单放到几何右侧，直接按 emit 会倒序。
        wt = str(row.get("window_time") or row.get("time") or "")
        emit = int(row.get("_emit") or 0)
        row_time = str(row.get("time") or "")
        order_time = str(row.get("order_time") or "")
        peer_time = str(row.get("order_time_peer") or "")
        # 交叉行取两侧完成时刻的较早者，保证多笔同价撮合按时间出场
        fill_time = min(t for t in (row_time, order_time, peer_time) if t) if (
            row_time or order_time or peer_time
        ) else ""
        # 小单绝不借用跨窗 anchor：否则后窗小单会被整块拽到前窗大单之前，
        # 前端会出现「14:18:41–44 的 0 手小单」夹在「14:18:38–41 小单与大单」中间。
        if row.get("kind") != "order":
            return (wt, 0, fill_time, "", emit)
        oids = [str(key) for key in (row.get("order_id"), row.get("order_id_peer")) if key]
        grp = str(row.get("_grp") or "")
        spanning = [oid for oid in oids if oid in multi_oids]
        if spanning:
            # 跨窗大单以最早触及窗为锚，同编号块连在一起；仍按 wt/fill_time 细分
            anchor = min(oid_wins[spanning[0]])
            return (anchor, 1, wt, fill_time, grp, emit)
        return (wt, 1, fill_time, grp, emit)

    rows.sort(key=_tape_sort_key)
    for row in rows:
        row.pop("_emit", None)
        row.pop("_grp", None)
    return rows


def reconstruct(
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
    **_ignored: Any,
) -> dict[str, Any]:
    """双序列路径：分时 × 资金动向 → 逐笔成交（簇内联合落位）。"""
    windows, source_stats = build_windows(ticks, avg_lots_per_tick=avg_lots_per_tick)
    orders = normalize_orders(big_deals, threshold=threshold, view=view)
    axis_windows, total_v = build_lot_axis(windows)

    pack: dict[str, Any] = {
        "code": code,
        "day": day,
        "granularity": "axis",
        "threshold": threshold,
        "params": {
            "max_lookback": int(max_lookback or 0),
            "view": view,
            "min_lots": min_lots,
            "algorithm": "axis",
            "solver": "joint",
        },
        "windows": source_stats["windows"],
        "orders": len(orders),
        "notes": [],
        "rows": [],
        "count": 0,
    }
    if not windows:
        pack["notes"].append("分时成交为空，无法还原")
        pack["summary"] = {
            "lots": 0.0,
            "count": 0,
            "order_lots": 0.0,
            "order_tape_lots": 0.0,
            "order_source_lots": 0.0,
            "order_count": 0,
            "small_lots": 0.0,
            "small_count": 0,
            "order_ratio": 0.0,
            "windows": 0,
        }
        pack["reconcile"] = {
            "lot_mismatch_windows": 0,
            "count_mismatch_windows": 0,
            "windows_ok": True,
            "active_orders_ok": True,
            "passive_orders_ok": True,
            "active_lot_mismatch_count": 0,
            "passive_lot_mismatch_count": 0,
            "infeasible_windows": 0,
            "infeasible": [],
            "unplaced_orders": [],
            "unplaced_count": 0,
            "order_lot_mismatch": [],
            "order_lot_mismatch_count": 0,
            "constraints_ok": True,
            "constraints_hard_count": 0,
            "constraints_soft_count": 0,
            "constraints_repairs": [],
            "constraints": {
                "ok": True,
                "hard": [],
                "soft": [],
                "hard_count": 0,
                "soft_count": 0,
            },
        }
        return pack

    buy_occ, sell_occ, placed, unplaced, joint_report = place_joint(
        axis_windows,
        orders,
        threshold=threshold,
        min_lots=min_lots,
        max_lookback=max_lookback,
    )

    rows: list[dict[str, Any]] = []
    emit_stats: dict[str, Any] = {}
    if with_rows:
        book = _OrderIds()
        orders_by_id = _order_map(placed)
        for order in orders:
            orders_by_id.setdefault(str(order.get("order_id")), order)
        for window in axis_windows:
            rows.extend(
                emit_window(
                    window,
                    buy_occ,
                    sell_occ,
                    orders_by_id,
                    book,
                    threshold=threshold,
                    min_lots=min_lots,
                    stats=emit_stats,
                )
            )
        rows = _sort_tape_for_continuity(rows)
        for seq, row in enumerate(rows, start=1):
            row["seq"] = seq

    lot_mismatch = count_mismatch = 0
    if rows:
        seen: dict[str, list[float]] = {}
        for row in rows:
            win = str(row.get("window_time") or row.get("time") or "")
            slot = seen.setdefault(win, [0.0, 0])
            slot[0] += float(row.get("lots") or 0)
            slot[1] += 1
        for window in axis_windows:
            got = seen.get(str(window["time"]), [0.0, 0])
            if abs(got[0] - float(window["lots"])) > 0.05:
                lot_mismatch += 1
            if window.get("auction"):
                continue
            if int(got[1]) != int(window["count"]):
                count_mismatch += 1

    attributed: dict[str, float] = {
        str(o.get("order_id") or ""): 0.0 for o in orders
    }
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
    for occ in (buy_occ, sell_occ):
        for start, end, oid in occ.intervals:
            attributed[oid] = float(end - start)

    order_lot_mismatch = []
    active_lot_mismatch = []
    passive_lot_mismatch = []
    matched_order_lots = 0.0
    for order in orders:
        oid = str(order.get("order_id") or "")
        need = float(order.get("lots") or 0)
        got = float(attributed.get(oid) or 0)
        matched_order_lots += min(need, got)
        if abs(got - need) > 0.5:
            row = {
                "order_id": oid,
                "time": order.get("time"),
                "side": order.get("side"),
                "view": order.get("view"),
                "need": need,
                "got": got,
            }
            order_lot_mismatch.append(row)
            if is_active_order(order):
                active_lot_mismatch.append(row)
            elif is_passive_order(order):
                passive_lot_mismatch.append(row)

    source_order_lots = round(sum(float(o["lots"]) for o in orders), 3)
    total_lots = round(float(total_v), 3)
    total_count = sum(int(w["count"]) for w in windows)
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
        "order_ratio": round(100.0 * filled_order_lots / total_lots, 2)
        if total_lots
        else 0.0,
        "windows": len(windows),
    }

    constraints = (
        enforce_constraints(rows, windows, orders, min_lots=min_lots)
        if rows
        else {
            "ok": True,
            "hard": [],
            "soft": [],
            "hard_count": 0,
            "soft_count": 0,
            "checks": {},
            "repairs": [],
        }
    )
    windows_ok = lot_mismatch == 0 and count_mismatch == 0
    rows_cap_bad = check_rows_cap(rows, threshold=threshold, min_lots=min_lots)
    infeasible = list(joint_report.get("infeasible_windows") or [])
    pack["reconcile"] = {
        "solver": "joint",
        "lot_mismatch_windows": lot_mismatch,
        "count_mismatch_windows": count_mismatch,
        "windows_ok": windows_ok,
        "active_orders_ok": len(active_lot_mismatch) == 0,
        "passive_orders_ok": len(passive_lot_mismatch) == 0,
        "active_lot_mismatch_count": len(active_lot_mismatch),
        "passive_lot_mismatch_count": len(passive_lot_mismatch),
        "infeasible_windows": len(infeasible),
        "infeasible": infeasible[:20],
        "clusters": int(joint_report.get("clusters") or 0),
        "degraded_clusters": int(joint_report.get("degraded_clusters") or 0),
        "fallback_clusters": int(joint_report.get("fallback_clusters") or 0),
        "sacrifices": list(joint_report.get("sacrifices") or [])[:20],
        "sacrifice_count": len(joint_report.get("sacrifices") or []),
        "search_nodes": int(joint_report.get("nodes") or 0),
        "rows_cap_violations": rows_cap_bad[:20],
        "rows_cap_violation_count": len(rows_cap_bad),
        "emit": dict(emit_stats),
        "unplaced_orders": unplaced[:20],
        "unplaced_count": len(unplaced),
        "order_lot_mismatch": order_lot_mismatch[:20],
        "order_lot_mismatch_count": len(order_lot_mismatch),
        "constraints_ok": bool(constraints.get("ok")),
        "constraints_hard_count": int(constraints.get("hard_count") or 0),
        "constraints_soft_count": int(constraints.get("soft_count") or 0),
        "constraints_repairs": list(constraints.get("repairs") or []),
        "constraints": constraints,
        "tune_moves": 0,
    }
    pack["fills"] = {"mean": 0.0, "median": 0, "max": 0, "histogram": {}}
    pack["ambiguity"] = {
        "undetermined_windows": 0,
        "solutions_log10": 0.0,
        "unique": True,
    }
    if with_windows:
        pack["axis_windows"] = len(axis_windows)
        pack["axis_V"] = total_v
        pack["window_bars"] = [
            {
                "time": w["time"],
                "prev_time": str(w.get("prev_time") or ""),
                "lots": float(w["lots"]),
                "count": int(w["count"]),
                "price": w.get("price"),
                "L": int(w["L"]),
                "R": int(w["R"]),
                "auction": bool(w.get("auction")),
            }
            for w in axis_windows
        ]

    if source_stats["auction_dropped"]:
        pack["notes"].append(
            f"已剔除 {source_stats['auction_dropped']} 条集合竞价累计虚拟撮合快照"
        )
    if source_stats["estimated_windows"]:
        pack["notes"].append(
            f"{source_stats['estimated_windows']} 个窗口缺笔数，按笔均 "
            f"{avg_lots_per_tick} 手估算"
        )
    if unplaced:
        pack["notes"].append(f"{len(unplaced)} 个订单无法在轴上完整放置")
    if order_lot_mismatch:
        pack["notes"].append(
            f"{len(order_lot_mismatch)} 个大单手数与资金动向不一致"
        )
    if lot_mismatch or count_mismatch:
        pack["notes"].append(
            f"对账：手数不符窗口 {lot_mismatch}，笔数不符窗口 {count_mismatch}"
        )
    if not constraints.get("ok"):
        hard = constraints.get("hard") or []
        codes = ", ".join(str(item.get("code") or "?") for item in hard[:5])
        pack["notes"].append(
            f"硬约束未通过 {constraints.get('hard_count') or 0} 项（{codes}）"
        )

    pack["rows"] = rows if with_rows else []
    pack["count"] = len(rows) if with_rows else 0
    if not with_rows:
        pack.pop("rows", None)
    return pack


def reconstruct_axis(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """兼容旧名。"""
    kwargs.pop("solver", None)
    kwargs.pop("algorithm", None)
    return reconstruct(*args, **kwargs)


def reconstruct_windows(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """兼容旧入口（忽略 algorithm/solver，永远走联合落位）。"""
    kwargs.pop("algorithm", None)
    kwargs.pop("solver", None)
    return reconstruct(*args, **kwargs)


__all__ = ["reconstruct", "reconstruct_axis", "reconstruct_windows"]
