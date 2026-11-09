"""簇内联合落位单测：30 万门槛行数判据 + 簇内撮合 + 牺牲降级 + 展开。

覆盖的口径
----------
1. 「小单 ≤ 30w」不只约束纯小单，也约束**单侧大单行的匿名对手** ——
   只要一行里有一侧是匿名小单，该行手数就必须 ≤ 30 万门槛折算的整手；
   只有买卖双方都是真实大单（交叉原子）的行可以超过。
2. 簇内**尽量撮合大单**：同价买卖块重叠只出 1 笔，交叉手数越多越省窗笔数，
   所以放置顺序与候选排序都优先撮合。
"""

from __future__ import annotations

import unittest

from company.analysis.deal.influence import (
    build_influence_clusters,
    order_influence_range,
    order_touched_windows,
)
from company.analysis.deal.prints import cap_lots, check_rows_cap, window_cost
from company.analysis.deal.window import reconstruct_windows

PRICE = 17.5  # 30 万 / (17.5 * 100) ≈ 171 手


def _tick(stamp: str, lots: float, count: int, price: float = PRICE) -> dict:
    return {
        "time": stamp,
        "price": price,
        "volume": lots,
        "count": count,
        "side": "buy",
    }


def _deal(
    stamp: str,
    lots: float,
    side: str,
    *,
    price: float = PRICE,
    aggressor: str = "active",
) -> dict:
    return {
        "time": stamp,
        "price": price,
        "volume": lots * 100,
        "volume_lots": lots,
        "amount": lots * price * 100,
        "side": side,
        "aggressor": aggressor,
    }


def _run(ticks: list[dict], deals: list[dict], **kwargs) -> dict:
    return reconstruct_windows(ticks, deals, code="TEST", view="all", **kwargs)


def _order_rows(pack: dict) -> list[dict]:
    return [row for row in pack["rows"] if row.get("kind") == "order"]


def _crossed_rows(pack: dict) -> list[dict]:
    return [
        row
        for row in pack["rows"]
        if row.get("order_id") and row.get("order_id_peer")
    ]


class CapLotsTests(unittest.TestCase):
    def test_threshold_to_lots(self) -> None:
        # 300000 / (17.5 * 100) = 171.4 → 171 手
        self.assertEqual(cap_lots(300_000.0, 17.5), 171)
        self.assertEqual(cap_lots(300_000.0, 3.8), 789)
        # 门槛/价格缺失时不做限制
        self.assertGreater(cap_lots(0.0, 17.5), 1000)
        self.assertGreater(cap_lots(300_000.0, 0.0), 1000)
        # 单笔下限抬帽
        self.assertEqual(cap_lots(300_000.0, 1000.0, min_lots=5), 5)


class WindowRowsTests(unittest.TestCase):
    """窗内「最少成交行数」：交叉 1 行，匿名侧按要求拆行。"""

    def _cost(self, buy_clips, sell_clips, *, lots, buy_price, sell_price, count=99):
        window = {
            "L": 0,
            "R": lots,
            "count": count,
            "price": PRICE,
        }
        prices = {
            "B": buy_price,
            "S": sell_price,
        }
        return window_cost(
            window, buy_clips, sell_clips, threshold=300_000.0, min_lots=0.0, prices=prices
        )

    def test_same_price_cross_is_one_row(self) -> None:
        cost = self._cost(
            [(0, 400, "B")], [(0, 400, "S")], lots=400, buy_price=PRICE, sell_price=PRICE
        )
        self.assertEqual(cost.crossed_rows, 1)
        self.assertEqual(cost.small_lots, 0)
        self.assertEqual(cost.rows_min, 1)
        self.assertGreater(cost.crossed_lots, cap_lots(300_000.0, PRICE))

    def test_different_price_overlap_is_not_cross(self) -> None:
        cost = self._cost(
            [(0, 400, "B")],
            [(0, 400, "S")],
            lots=400,
            buy_price=17.4,
            sell_price=17.6,
        )
        self.assertEqual(cost.crossed_rows, 0)
        # 一笔成交只有一个价 → 只能留一侧编号，另一侧退成匿名小单 → 必须拆行
        self.assertGreaterEqual(cost.mixed_rows, 3)
        self.assertEqual(cost.rows_min, cost.mixed_rows + cost.small_rows)

    def test_single_side_rows_follow_cap(self) -> None:
        cost = self._cost(
            [(0, 342, "B")], [], lots=400, buy_price=PRICE, sell_price=PRICE
        )
        self.assertEqual(cost.single_rows, 2)  # ceil(342/171)
        self.assertEqual(cost.small_rows, 1)  # 58 手
        self.assertEqual(cost.rows_min, 3)


class InfluenceWindowClusterTests(unittest.TestCase):
    def _axis(self):
        from company.analysis.deal.axis import build_lot_axis
        from company.analysis.deal.window import build_windows

        windows, _ = build_windows(
            [
                _tick("09:30:03", 100, 10),
                _tick("09:30:06", 100, 10),
                _tick("09:30:09", 100, 10),
            ]
        )
        return build_lot_axis(windows)[0]

    def test_influence_range_off_grid(self) -> None:
        axis = self._axis()
        # 09:30:07 落在 [09:30:06, 09:30:09] → 截止窗是 09:30:09 档 [200,300)
        order = {"order_id": "O1", "time": "09:30:07", "price": PRICE, "lots": 60, "side": "sell"}
        self.assertEqual(order_influence_range(order, axis), (141, 300))
        self.assertEqual(order_touched_windows(order, axis), [1, 2])

    def test_clusters_are_window_aligned(self) -> None:
        axis = self._axis()
        # 一张单截止在第 1 档、一张截止在第 2 档：影响区间都覆盖前两档 → 同簇
        orders = [
            {"order_id": "A", "time": "09:30:04", "price": PRICE, "lots": 30, "side": "sell"},
            {"order_id": "B", "time": "09:30:07", "price": PRICE, "lots": 30, "side": "buy"},
        ]
        clusters = build_influence_clusters(orders, axis)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].span, (0, 300))
        self.assertEqual(clusters[0].window_indices, [0, 1, 2])

    def test_clusters_contain_or_disjoint_and_cover_each_window_once(self) -> None:
        """簇跨度窗对齐：两两包含或不相交；每个分时窗最多属于一簇。"""
        axis = self._axis()
        orders = [
            {"order_id": "A", "time": "09:30:02", "price": PRICE, "lots": 10, "side": "buy"},
            {"order_id": "B", "time": "09:30:04", "price": PRICE, "lots": 20, "side": "sell"},
            {"order_id": "C", "time": "09:30:08", "price": PRICE, "lots": 15, "side": "buy"},
        ]
        clusters = build_influence_clusters(orders, axis)
        spans = sorted(c.span for c in clusters)
        for i in range(len(spans) - 1):
            a0, a1 = spans[i]
            b0, b1 = spans[i + 1]
            # 半开区间：端点相接允许；禁止部分重叠
            self.assertTrue(a1 <= b0 or (a0 <= b0 and a1 >= b1) or (b0 <= a0 and b1 >= a1))
        owned: dict[int, int] = {}
        for ci, cluster in enumerate(clusters):
            for wi in cluster.window_indices:
                self.assertNotIn(wi, owned)
                owned[wi] = ci


class SolverTests(unittest.TestCase):
    def test_crossing_is_preferred(self) -> None:
        """同价买卖块优先重叠：两单都满放，且只出 1 笔交叉行。"""
        pack = _run(
            [_tick("09:30:03", 400, 3)],
            [
                _deal("09:30:02", 200, "buy", aggressor="passive"),
                _deal("09:30:02", 200, "sell", aggressor="active"),
            ],
        )
        rec = pack["reconcile"]
        self.assertEqual(rec["unplaced_count"], 0)
        self.assertEqual(rec["sacrifice_count"], 0)
        crossed = _crossed_rows(pack)
        self.assertEqual(len(crossed), 1)
        self.assertEqual(float(crossed[0]["lots"]), 200.0)
        # 交叉原子只算 1 行，剩下的 200 手按 171 拆 2 行 → 共 3 笔
        self.assertEqual(len(pack["rows"]), 3)
        self.assertEqual(rec["count_mismatch_windows"], 0)

    def test_passive_shrinks_before_drop(self) -> None:
        """同侧放不下：先缩被动（大→小），缩不动才去除。"""
        pack = _run(
            [_tick("09:30:03", 100, 10)],
            [
                _deal("09:30:02", 60, "buy", aggressor="passive"),
                _deal("09:30:02", 50, "buy", aggressor="passive"),
                _deal("09:30:02", 10, "sell", aggressor="active"),
            ],
        )
        rec = pack["reconcile"]
        sacrifices = rec["sacrifices"]
        self.assertTrue(sacrifices)
        self.assertEqual(sacrifices[0]["action"], "shrink")
        self.assertEqual(sacrifices[0]["stage"], "passive")
        self.assertEqual(sacrifices[0]["from"], 60)
        self.assertLessEqual(sacrifices[0]["to"], 50)
        self.assertEqual(rec["degraded_clusters"], 1)

    def test_active_never_shrinks_smallest_dropped(self) -> None:
        """主动单整张去除、不缩量；先去除最小的。"""
        pack = _run(
            [_tick("09:30:03", 100, 10)],
            [
                _deal("09:30:02", 60, "sell", aggressor="active"),
                _deal("09:30:02", 50, "sell", aggressor="active"),
            ],
        )
        rec = pack["reconcile"]
        self.assertEqual(rec["unplaced_count"], 1)
        dropped = rec["unplaced_orders"][0]
        self.assertEqual(dropped["reason"], "dropped_active_first")
        self.assertEqual(dropped["missing"], 50.0)
        placed = _order_rows(pack)
        self.assertTrue(placed)
        self.assertTrue(all(float(row["lots"]) > 0 for row in placed))

    def test_budget_fallback_active_never_shrinks(self) -> None:
        """预算兜底路径：主动满放失败只记 drop，blocks 里绝不能出现缩量主动块。"""
        from company.analysis.deal.axis import build_lot_axis
        from company.analysis.deal.influence import build_influence_clusters
        from company.analysis.deal.joint import ClusterSolver
        from company.analysis.deal.window import build_windows, normalize_orders

        windows, _ = build_windows([_tick("09:30:03", 100, 10)])
        axis, _ = build_lot_axis(windows)
        orders = normalize_orders(
            [
                _deal("09:30:02", 60, "sell", aggressor="active"),
                _deal("09:30:02", 50, "sell", aggressor="active"),
            ]
        )
        clusters = build_influence_clusters(orders, axis)
        self.assertEqual(len(clusters), 1)
        # greedy_max_slots=1 强制走 _greedy_fill（两张主动同侧容量冲突）
        solver = ClusterSolver(
            clusters[0],
            axis,
            dfs_max_slots=1,
            greedy_max_slots=1,
            polish_max_slots=0,
        )
        result = solver.solve()
        by_id = {o["order_id"]: o for o in orders}
        for oid, span in result.blocks.items():
            got = span[1] - span[0]
            need = int(by_id[oid]["lots"])
            self.assertEqual(got, need, f"active {oid} shrunk {need}->{got}")
        for sac in result.sacrifices:
            if sac.get("stage") in {"budget", "active"}:
                self.assertEqual(sac["action"], "drop")
                self.assertEqual(sac["to"], 0)
        # 至少丢掉一张；留下的必须满手数
        self.assertEqual(sum(1 for s in result.sacrifices if s["action"] == "drop"), 1)
        self.assertEqual(len(result.blocks), 1)

    def test_budget_fallback_prefers_active_over_passive(self) -> None:
        """预算兜底：同轴挤兑时先保主动满放，再缩/丢被动。"""
        from company.analysis.deal.axis import build_lot_axis
        from company.analysis.deal.influence import build_influence_clusters
        from company.analysis.deal.joint import ClusterSolver
        from company.analysis.deal.util import ROLE_ACTIVE
        from company.analysis.deal.window import build_windows, normalize_orders

        windows, _ = build_windows([_tick("09:30:03", 100, 10)])
        axis, _ = build_lot_axis(windows)
        orders = normalize_orders(
            [
                _deal("09:30:02", 80, "sell", aggressor="passive"),
                _deal("09:30:02", 70, "sell", aggressor="active"),
            ]
        )
        active_id = next(o["order_id"] for o in orders if o.get("view") == "active")
        clusters = build_influence_clusters(orders, axis)
        self.assertEqual(len(clusters), 1)
        solver = ClusterSolver(
            clusters[0],
            axis,
            dfs_max_slots=1,
            greedy_max_slots=1,
            polish_max_slots=0,
        )
        result = solver.solve()
        self.assertIn(active_id, result.blocks)
        a0, a1 = result.blocks[active_id]
        self.assertEqual(a1 - a0, 70)
        # 被动被挤：缩量或整张去除均可，但不能反过来丢掉主动
        dropped = {s["order_id"] for s in result.sacrifices if s["action"] == "drop"}
        self.assertNotIn(active_id, dropped)
        self.assertEqual(solver.by_id[active_id].role, ROLE_ACTIVE)

    def test_active_dropped_when_single_rows_blow_count_budget(self) -> None:
        """342 手单侧 = 2 行 + 小单 1 行 > 2 笔 → 主动单整张去除。"""
        pack = _run(
            [_tick("09:30:03", 400, 2)],
            [_deal("09:30:02", 342, "sell", aggressor="active")],
        )
        rec = pack["reconcile"]
        self.assertEqual(rec["unplaced_count"], 1)
        self.assertEqual(rec["unplaced_orders"][0]["reason"], "dropped_active_first")
        self.assertEqual(_order_rows(pack), [])

    def test_single_side_rows_within_cap_when_feasible(self) -> None:
        """笔数够时单侧大单照样满放，但每行都必须 ≤ 30 万门槛手数。"""
        pack = _run(
            [_tick("09:30:03", 400, 4)],
            [_deal("09:30:02", 342, "sell", aggressor="active")],
        )
        self.assertEqual(pack["reconcile"]["unplaced_count"], 0)
        rows = _order_rows(pack)
        self.assertEqual(sum(float(row["lots"]) for row in rows), 342.0)
        self.assertTrue(all(float(row["lots"]) <= 171 for row in rows))
        self.assertEqual(pack["reconcile"]["rows_cap_violation_count"], 0)

    def test_same_window_crosses_sorted_by_fill_time(self) -> None:
        """同窗多笔交叉按完成时刻出场，不按手数轴左右倒序。"""
        pack = _run(
            [_tick("09:30:03", 723, 19, price=146.82)],
            [
                _deal("09:30:02", 362, "sell", aggressor="active", price=146.82),
                _deal("09:30:03", 713, "buy", aggressor="passive", price=146.82),
                _deal("09:30:03", 234, "sell", aggressor="active", price=146.82),
                _deal("09:30:03", 92, "sell", aggressor="active", price=146.82),
            ],
        )
        crossed = _crossed_rows(pack)
        self.assertEqual(len(crossed), 3)
        lots = [float(r["lots"]) for r in crossed]
        # 14:18:40 的 362 应排在两笔 14:18:41 之前
        self.assertEqual(lots[0], 362.0)
        self.assertEqual(sorted(lots[1:]), [92.0, 234.0])
        self.assertEqual(str(crossed[0].get("order_time_peer") or crossed[0].get("time")), "09:30:02")

    def test_large_cross_not_killed_by_residual_small_rows(self) -> None:
        """大窗少量笔数：先落单侧时残段小单行不能误杀「买卖一起放」的解。

        药明康德 14:18:41 一类场景：723 手 / 19 笔 + 被动买 713 + 三笔主动卖
        （同价）。搜索中途只放下一张卖单时，若仍把窗内空档按小单计行，会
        ``rows_min > count``，四大单全部被预算丢掉。
        """
        pack = _run(
            [_tick("09:30:03", 723, 19, price=146.82)],
            [
                _deal("09:30:02", 362, "sell", aggressor="active", price=146.82),
                _deal("09:30:03", 713, "buy", aggressor="passive", price=146.82),
                _deal("09:30:03", 234, "sell", aggressor="active", price=146.82),
                _deal("09:30:03", 92, "sell", aggressor="active", price=146.82),
            ],
        )
        rec = pack["reconcile"]
        self.assertEqual(rec["unplaced_count"], 0, msg=rec.get("unplaced_orders"))
        self.assertEqual(rec["sacrifice_count"], 0)
        crossed = _crossed_rows(pack)
        self.assertEqual(len(crossed), 3)
        self.assertEqual(sum(float(r["lots"]) for r in crossed), 688.0)
        self.assertEqual(rec["rows_cap_violation_count"], 0)

    def test_block_right_end_pinned_to_deadline_window(self) -> None:
        pack = _run(
            [
                _tick("09:30:03", 100, 10),
                _tick("09:30:06", 100, 10),
                _tick("09:30:09", 100, 10),
            ],
            [_deal("09:30:07", 60, "sell", aggressor="active")],
        )
        self.assertEqual(pack["reconcile"]["unplaced_count"], 0)
        rows = [row for row in _order_rows(pack) if row.get("order_id") == "O00001"]
        self.assertTrue(rows)
        # 完成时刻 09:30:07 → 必须有一笔落在 09:30:09 档
        self.assertIn("09:30:09", {str(row["window_time"]) for row in rows})
        # 块必须整段落在 I(o)=[141,300) 内
        order_row = rows[0]
        self.assertNotEqual(str(order_row["window_time"]), "09:30:03")

    def test_oversized_order_is_dropped_and_reported(self) -> None:
        """大单比当日总量还大（数据矛盾）→ 整张去除并留痕，手数守恒不变。"""
        pack = _run(
            [_tick("09:30:03", 100, 3)],
            [_deal("09:30:01", 400, "sell", aggressor="active")],
        )
        rec = pack["reconcile"]
        self.assertGreaterEqual(rec["unplaced_count"], 1)
        self.assertEqual(rec["unplaced_orders"][0]["reason"], "dropped_active_first")
        self.assertEqual(rec["lot_mismatch_windows"], 0)
        self.assertEqual(rec["rows_cap_violation_count"], 0)

    def test_infeasible_window_is_reported_without_breaking_tape(self) -> None:
        """分时档本身矛盾（300 手 / 1 笔 → 单行必超 30 万）→ 如实上报。"""
        pack = _run([_tick("09:30:03", 300, 1)], [])
        rec = pack["reconcile"]
        # 1 笔 300 手 ≈ 52.5 万 > 30 万，笔数与门槛不可兼得 → 记 R12 违反
        self.assertGreaterEqual(rec["rows_cap_violation_count"], 1)
        self.assertEqual(len(pack["rows"]), 1)
        self.assertEqual(sum(float(row["lots"]) for row in pack["rows"]), 300.0)


class EmitTests(unittest.TestCase):
    def test_anon_counterparty_and_smalls_share_uniform_size(self) -> None:
        """单侧大单的匿名对手与纯小单共用笔数预算，手数尽量接近。"""
        pack = _run(
            [_tick("09:30:03", 42, 33, price=146.75)],
            [_deal("09:30:03", 25, "buy", aggressor="passive", price=146.82)],
        )
        rows = pack["rows"]
        self.assertEqual(len(rows), 33)
        self.assertEqual(sum(float(r["lots"]) for r in rows), 42.0)
        order_rows = [r for r in rows if r.get("kind") == "order"]
        small_rows = [r for r in rows if r.get("kind") != "order"]
        self.assertTrue(order_rows)
        self.assertTrue(small_rows)
        order_lots = [float(r["lots"]) for r in order_rows]
        small_lots = [float(r["lots"]) for r in small_rows if float(r["lots"]) > 0]
        # 不再出现「大单对手 ~12、纯小单 ~1」的两极；正手数彼此差 ≤ 1
        positive = [x for x in order_lots + small_lots if x > 0]
        self.assertLessEqual(max(positive) - min(positive), 1.0)
        self.assertEqual(pack["reconcile"]["rows_cap_violation_count"], 0)
        self.assertEqual(pack["reconcile"]["count_mismatch_windows"], 0)

    def test_small_rows_uniform_and_conserved(self) -> None:
        pack = _run(
            [
                _tick("09:30:03", 300, 7),
                _tick("09:30:06", 250, 5),
            ],
            [],
        )
        rows = pack["rows"]
        by_win: dict[str, list[dict]] = {}
        for row in rows:
            by_win.setdefault(str(row["window_time"]), []).append(row)
        self.assertEqual(len(by_win["09:30:03"]), 7)
        self.assertEqual(len(by_win["09:30:06"]), 5)
        self.assertEqual(sum(float(r["lots"]) for r in rows), 550.0)
        for subset in by_win.values():
            lots = [float(r["lots"]) for r in subset]
            self.assertLessEqual(max(lots) - min(lots), 1.0)
        self.assertEqual(pack["reconcile"]["count_mismatch_windows"], 0)
        self.assertEqual(check_rows_cap(rows, threshold=300_000.0), [])

    def test_pair_can_print_across_windows(self) -> None:
        """同一对买卖大单可跨窗连续多笔（R8），各窗手数仍守恒。"""
        pack = _run(
            [
                _tick("09:30:03", 50, 3),
                _tick("09:30:06", 100, 3),
            ],
            [
                _deal("09:30:06", 120, "buy", aggressor="passive"),
                _deal("09:30:06", 120, "sell", aggressor="active"),
            ],
        )
        rec = pack["reconcile"]
        self.assertEqual(rec["lot_mismatch_windows"], 0)
        crossed = _crossed_rows(pack)
        self.assertGreaterEqual(len(crossed), 1)
        # 同一对可出现在多个分时档
        by_pair_wins: dict[tuple[str, str], set[str]] = {}
        for row in crossed:
            key = (str(row["buy_id"]), str(row["sell_id"]))
            by_pair_wins.setdefault(key, set()).add(str(row["window_time"]))
        # 每窗手数与分时档一致
        by_win: dict[str, float] = {}
        for row in pack["rows"]:
            key = str(row["window_time"])
            by_win[key] = by_win.get(key, 0.0) + float(row["lots"])
        self.assertAlmostEqual(by_win["09:30:03"], 50.0, places=2)
        self.assertAlmostEqual(by_win["09:30:06"], 100.0, places=2)
        checks = (rec.get("constraints") or {}).get("checks") or {}
        self.assertTrue(checks.get("R8_pair_contiguous_in_window", True))

    def test_mixed_price_atom_keeps_passive_side(self) -> None:
        """异价重叠：成交价等于被动方挂单价 → 保留被动侧编号与价格。"""
        pack = _run(
            [_tick("09:30:03", 100, 10, price=17.45)],
            [
                _deal("09:30:02", 40, "buy", price=17.40, aggressor="passive"),
                _deal("09:30:02", 40, "sell", price=17.50, aggressor="active"),
            ],
        )
        rows = _order_rows(pack)
        self.assertTrue(rows)
        kept = [row for row in rows if row.get("order_id")]
        buy_row = next(row for row in kept if row["side"] == "buy")
        self.assertEqual(buy_row["order_id"], "O00001")
        self.assertAlmostEqual(float(buy_row["price"]), 17.40, places=2)

    def test_end_to_end_constraints(self) -> None:
        """一整天小样本：硬约束（含 R12）全过。"""
        pack = _run(
            [
                _tick("09:30:03", 220, 6),
                _tick("09:30:06", 180, 5),
                _tick("09:30:09", 140, 4),
            ],
            [
                _deal("09:30:02", 150, "buy", aggressor="passive"),
                _deal("09:30:05", 150, "sell", aggressor="active"),
                _deal("09:30:08", 90, "buy", aggressor="active"),
            ],
        )
        rec = pack["reconcile"]
        self.assertEqual(rec["lot_mismatch_windows"], 0)
        self.assertEqual(rec["count_mismatch_windows"], 0)
        self.assertEqual(rec["unplaced_count"], 0)
        self.assertEqual(rec["rows_cap_violation_count"], 0)
        self.assertEqual(check_rows_cap(pack["rows"], threshold=300_000.0), [])
        hard = [item["code"] for item in rec["constraints"].get("hard") or []]
        self.assertEqual(hard, [])
        self.assertGreater(len(_crossed_rows(pack)), 0)


if __name__ == "__main__":
    unittest.main()
