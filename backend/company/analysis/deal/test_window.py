"""3 秒窗口级逐笔重建的单测（无网络）。

覆盖：

- 窗口聚合与集合竞价过滤
- 可行区间 ``[lo, hi]`` 的判定（含无解窗口）
- 订单时序与成交量/笔数槽位约束
- 量守恒 / 笔数守恒（硬约束）
- 订单归属（每个订单的成交合计 = 订单手数）
"""

from __future__ import annotations

import unittest

from company.analysis.deal.window import (
    DEFAULT_MIN_LOTS,
    DEFAULT_TRADE_THRESHOLD,
    TRADE_MIN_LOTS,
    build_windows,
    emit_window,
    normalize_orders,
    place_orders,
    plan_window,
    reconstruct_windows,
)

# 价格 1000 元 => 单笔上限 = 300000 / 1000 / 100 = 3 手
PRICE = 1000.0
CAP_LOTS = DEFAULT_TRADE_THRESHOLD / PRICE / 100.0


def _window(lots: float, count: int, stamp: str = "09:30:03", side: str = "buy") -> dict:
    return {
        "time": stamp,
        "lots": lots,
        "count": count,
        "amount": lots * PRICE * 100,
        "price": PRICE,
        "side": side,
    }


def _order(order_id: str, lots: float, stamp: str = "09:30:03", side: str = "buy") -> dict:
    return {
        "order_id": order_id,
        "time": stamp,
        "price": PRICE,
        "lots": lots,
        "amount": lots * PRICE * 100,
        "side": side,
        "view": "active",
    }


class BuildWindowsTests(unittest.TestCase):
    def test_aggregates_same_stamp(self) -> None:
        ticks = [
            {"time": "09:30:03", "price": 10.0, "volume": 4, "count": 2, "side": "buy"},
            {"time": "09:30:03", "price": 12.0, "volume": 6, "count": 3, "side": "sell"},
            {"time": "09:30:06", "price": 11.0, "volume": 5, "count": 1, "side": "buy"},
        ]
        windows, stats = build_windows(ticks)
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0]["lots"], 10.0)
        self.assertEqual(windows[0]["count"], 5)
        # 成交额加权：(4*10 + 6*12) / 10 = 11.2
        self.assertAlmostEqual(windows[0]["price"], 11.2, places=3)
        self.assertEqual(windows[0]["side"], "sell")
        self.assertEqual(stats["lots"], 15.0)

    def test_missing_count_estimated(self) -> None:
        windows, stats = build_windows(
            [{"time": "09:30:03", "price": 10.0, "volume": 9, "count": 0, "side": "buy"}],
            avg_lots_per_tick=3.0,
        )
        self.assertEqual(windows[0]["count"], 3)
        self.assertTrue(windows[0]["estimated"])
        self.assertEqual(stats["estimated_windows"], 1)

    def test_empty(self) -> None:
        windows, stats = build_windows([])
        self.assertEqual(windows, [])
        self.assertEqual(stats["windows"], 0)

    def test_opening_match_kept_gap_dropped(self) -> None:
        """09:25 开盘撮合保留；09:26–09:30 空窗剔除；09:30 起连续竞价保留。"""
        ticks = [
            {"time": "09:25:00", "price": 10.0, "volume": 5, "count": 1, "side": "buy"},
            {"time": "09:25:02", "price": 10.0, "volume": 2, "count": 1, "side": "buy"},
            {"time": "09:27:00", "price": 10.0, "volume": 9, "count": 1, "side": "buy"},
            {"time": "09:30:00", "price": 10.1, "volume": 3, "count": 1, "side": "sell"},
        ]
        windows, stats = build_windows(ticks)
        stamps = [w["time"] for w in windows]
        self.assertIn("09:25:00", stamps)
        self.assertIn("09:25:02", stamps)
        self.assertNotIn("09:27:00", stamps)
        self.assertIn("09:30:00", stamps)
        self.assertTrue(windows[0]["auction"])
        self.assertFalse(windows[-1]["auction"])
        self.assertGreaterEqual(stats["auction_dropped"], 1)

    def test_timestamp_formats_align(self) -> None:
        """同花顺给 ``20261009 09:30:03``，东财 / 资金动向给 ``09:30:03``。

        不归一的话订单会被 ``bisect`` 全部排到窗口之前，误报成「无解」。
        """
        ths = [{"time": "20261009 09:30:03", "price": 10.0, "volume": 4, "count": 2, "side": "buy"}]
        em = [{"time": "09:30:03", "price": 10.0, "volume": 4, "count": 2, "side": "buy"}]
        w_ths, _ = build_windows(ths)
        w_em, _ = build_windows(em)
        self.assertEqual(w_ths[0]["time"], w_em[0]["time"])
        self.assertEqual(w_ths[0]["time"], "09:30:03")

    def test_order_time_normalized(self) -> None:
        rows = [{"time": "20261009 09:30:03", "price": PRICE, "volume": 300,
                 "amount": 300000, "side": "buy", "aggressor": "active"}]
        orders = normalize_orders(rows, view="aggressor")
        self.assertEqual(orders[0]["time"], "09:30:03")


class NormalizeOrdersTests(unittest.TestCase):
    def _rows(self) -> list[dict]:
        return [
            {"time": "09:30:03", "price": PRICE, "volume": 300, "amount": 300000, "side": "buy", "aggressor": "active"},
            {"time": "09:30:03", "price": PRICE, "volume": 300, "amount": 300000, "side": "sell", "aggressor": "passive"},
        ]

    def test_aggressor_view_keeps_one_side(self) -> None:
        orders = normalize_orders(self._rows(), view="aggressor")
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["side"], "buy")
        self.assertEqual(orders[0]["lots"], 3.0)

    def test_all_view_keeps_active_and_passive(self) -> None:
        orders = normalize_orders(self._rows(), view="all")
        self.assertEqual(len(orders), 2)
        self.assertEqual({o["side"] for o in orders}, {"buy", "sell"})

    def test_both_aliases_all(self) -> None:
        orders = normalize_orders(self._rows(), view="both")
        self.assertEqual(len(orders), 2)

    def test_order_ids_sequential(self) -> None:
        orders = normalize_orders(self._rows(), view="all")
        self.assertEqual([order["order_id"] for order in orders], ["O00001", "O00002"])


class PlanWindowTests(unittest.TestCase):
    def test_feasible_range(self) -> None:
        plan = plan_window(_window(10.0, 5), [{"order": _order("O1", 3.0), "lots": 3.0}])
        self.assertTrue(plan["feasible"])
        self.assertEqual(plan["order_lots"], 3.0)
        self.assertAlmostEqual(plan["small_lots"], 7.0, places=3)
        self.assertLessEqual(plan["fills_lo"], plan["fills_hi"])

    def test_dense_window_needs_multi_trade_records(self) -> None:
        """10 手 / 3 条记录 = 每条 3.33 手 > 门槛 3 手。不是无解，是记录内含多笔。"""
        plan = plan_window(_window(10.0, 3), [])
        self.assertTrue(plan["feasible"])
        self.assertTrue(plan["multi_trade"])
        self.assertGreater(plan["trades_min"], plan["count"])
        rows = emit_window(plan, [])
        self.assertGreaterEqual(len(rows), plan["trades_min"])
        self.assertAlmostEqual(sum(row["lots"] for row in rows), 10.0, places=2)
        for row in rows:
            self.assertLess(row["lots"], CAP_LOTS + 1e-6)
            self.assertTrue(row["buy_id"].startswith("B"))
            self.assertTrue(row["sell_id"].startswith("S"))

    def test_real_sweep_window(self) -> None:
        """真实逐笔 14:05:17：东财 8 手 / 3 条记录；超门槛时拆成真正逐笔。"""
        window = {"time": "14:05:17", "lots": 8.0, "count": 3, "price": 1341.76, "side": "buy"}
        plan = plan_window(window, [], threshold=300_000.0)
        self.assertTrue(plan["feasible"])
        rows = emit_window(plan, [])
        self.assertGreaterEqual(len(rows), 3)
        self.assertAlmostEqual(sum(row["lots"] for row in rows), 8.0, places=2)
        for row in rows:
            self.assertLessEqual(row["lots"], plan["cap_lots"] + 1e-6)
            self.assertEqual(set(row) & {"time", "price", "lots", "buy_id", "sell_id"},
                             {"time", "price", "lots", "buy_id", "sell_id"})

    def test_infeasible_when_orders_exceed_records(self) -> None:
        """连续竞价：落到窗口里的订单数比记录数还多 → 无解。"""
        window = {"time": "09:30:03", "lots": 5.0, "count": 1, "price": 20.0, "side": "buy"}
        placed = [
            {"order": {"order_id": "A", "price": 20.0, "side": "buy"}, "lots": 2.0},
            {"order": {"order_id": "B", "price": 20.0, "side": "buy"}, "lots": 3.0},
        ]
        plan = plan_window(window, placed)
        self.assertFalse(plan["feasible"])

    def test_auction_allows_many_orders_one_record(self) -> None:
        """集合竞价多对多：1 条记录里可以同时有买单大单 + 卖单大单。"""
        window = {
            "time": "09:25:00",
            "lots": 5.0,
            "count": 1,
            "price": 20.0,
            "side": "buy",
            "auction": True,
        }
        placed = [
            {"order": {"order_id": "A", "price": 20.0, "side": "buy"}, "lots": 2.0},
            {"order": {"order_id": "B", "price": 20.0, "side": "sell"}, "lots": 3.0},
        ]
        plan = plan_window(window, placed)
        self.assertTrue(plan["feasible"])
        self.assertTrue(plan["auction"])
        rows = emit_window(plan, placed)
        self.assertAlmostEqual(sum(row["lots"] for row in rows), 5.0, places=2)
        # 2 手买 vs 3 手卖：先配对 2 手（真实买卖编号），剩 1 手卖单找合成对手
        paired = [row for row in rows if row.get("order_id_peer")]
        self.assertTrue(paired)
        self.assertAlmostEqual(sum(row["lots"] for row in paired), 2.0, places=2)

    def test_no_orders(self) -> None:
        plan = plan_window(_window(6.0, 3), [])
        self.assertTrue(plan["feasible"])
        self.assertEqual(plan["fills"], 0)
        self.assertEqual(plan["small_count"], 3)

    def test_all_order_window(self) -> None:
        plan = plan_window(_window(4.0, 4), [{"order": _order("O1", 4.0), "lots": 4.0}])
        self.assertTrue(plan["feasible"])
        self.assertEqual(plan["fills"], 4)


class PlaceOrdersTests(unittest.TestCase):
    def test_auction_no_slot_limit(self) -> None:
        """集合竞价窗口不按记录数占坑：1 条记录可同时放下买+卖两张大单。"""
        windows = [{
            "time": "09:25:00",
            "lots": 5.0,
            "count": 1,
            "price": PRICE,
            "side": "buy",
            "auction": True,
        }]
        orders = [
            _order("BUY", 2.0, "09:25:00", side="buy"),
            _order("SELL", 3.0, "09:25:00", side="sell"),
        ]
        allocation, unplaced = place_orders(windows, orders)
        self.assertFalse(unplaced)
        placed_ids = {it["order"]["order_id"] for it in allocation[0]}
        self.assertEqual(placed_ids, {"BUY", "SELL"})

    def test_respects_deadline(self) -> None:
        # 订单时刻恰等于档位 → 落入该档
        windows = [_window(10.0, 5, "09:30:03"), _window(10.0, 5, "09:30:06")]
        orders = [_order("O1", 4.0, "09:30:06")]
        allocation, unplaced = place_orders(windows, orders)
        self.assertFalse(unplaced)
        self.assertEqual(list(allocation), [1])

    def test_spills_backward_when_capacity_short(self) -> None:
        windows = [_window(2.0, 3, "09:30:03"), _window(2.0, 3, "09:30:06")]
        orders = [_order("O1", 4.0, "09:30:06")]
        allocation, unplaced = place_orders(windows, orders)
        self.assertFalse(unplaced)
        self.assertIn(0, allocation)
        self.assertIn(1, allocation)

    def test_unplaced_when_no_room(self) -> None:
        windows = [_window(1.0, 3, "09:30:03")]
        orders = [_order("O1", 5.0, "09:30:03")]
        _, unplaced = place_orders(windows, orders)
        self.assertEqual(len(unplaced), 1)
        self.assertGreater(unplaced[0]["missing"], 0)

    def test_buy_sell_capacity_independent(self) -> None:
        """买卖大单各自占用窗口手数，互不挤占。"""
        windows = [_window(5.0, 5, "09:30:03")]
        orders = [
            _order("BUY", 5.0, "09:30:03", side="buy"),
            _order("SELL", 5.0, "09:30:03", side="sell"),
        ]
        allocation, unplaced = place_orders(windows, orders)
        self.assertFalse(unplaced)
        by_id = {it["order"]["order_id"]: it["lots"] for it in allocation[0]}
        self.assertEqual(by_id["BUY"], 5.0)
        self.assertEqual(by_id["SELL"], 5.0)

    def test_big_order_priority_on_residual(self) -> None:
        """同完成窗：先各自钉锚点，残余容量归大单。"""
        windows = [_window(5.0, 3, "09:30:03")]
        orders = [
            _order("SMALL", 2.0, "09:30:03"),
            _order("BIG", 4.0, "09:30:03"),
        ]
        allocation, unplaced = place_orders(windows, orders)
        by_id = {
            it["order"]["order_id"]: it["lots"]
            for items in allocation.values()
            for it in items
        }
        self.assertEqual(by_id["BIG"], 4.0)
        self.assertEqual(by_id["SMALL"], 1.0)  # 仅锚点 1 手
        self.assertEqual([u["order_id"] for u in unplaced], ["SMALL"])
        self.assertAlmostEqual(unplaced[0]["missing"], 1.0)

    def test_reserve_lots_for_remaining_slots(self) -> None:
        """min_lots=1 时为大单填量预留剩余笔数的手数。"""
        windows = [_window(5.0, 3, "09:30:03")]
        orders = [_order("BIG", 5.0, "09:30:03")]
        allocation, unplaced = place_orders(windows, orders, min_lots=1.0)
        by_id = {
            it["order"]["order_id"]: it["lots"]
            for items in allocation.values()
            for it in items
        }
        # 3 笔窗口：大单占 1 槽后还剩 2 槽，各预留 1 手 → 大单最多吃 3 手
        self.assertEqual(by_id["BIG"], 3.0)
        self.assertEqual(len(unplaced), 1)
        self.assertAlmostEqual(unplaced[0]["missing"], 2.0)

    def test_deadline_uses_first_window_ge_stamp(self) -> None:
        """资金动向时刻落在两档之间时，截止窗取第一个 time >= stamp（下一档）。"""
        windows = [_window(10.0, 5, "09:30:03"), _window(10.0, 5, "09:30:09")]
        orders = [_order("O1", 4.0, "09:30:06")]
        allocation, unplaced = place_orders(windows, orders)
        self.assertFalse(unplaced)
        self.assertEqual(list(allocation), [1])
        self.assertEqual(allocation[1][0]["lots"], 4.0)
        self.assertEqual(windows[1]["time"], "09:30:09")

    def test_complete_time_not_stolen_by_later_large_order(self) -> None:
        """更晚的大单回溯时，不能把先完成订单的最后一笔挤出完成窗。

        左闭右开下，完成时刻恰为 ``09:30:06`` 的 EARLY 属于下一档
        ``[09:30:06, 09:30:09)``＝``09:30:09``：最后一笔锚在该完成窗（index 2），
        其余成交回溯到 ``09:30:06``（index 1）。
        """
        windows = [
            _window(10.0, 5, "09:30:03"),
            _window(10.0, 5, "09:30:06"),
            _window(10.0, 5, "09:30:09"),
        ]
        orders = [
            _order("EARLY", 2.0, "09:30:06"),
            _order("LATE_BIG", 25.0, "09:30:09"),
        ]
        allocation, _ = place_orders(windows, orders)
        early_idx = [
            index
            for index, items in allocation.items()
            for it in items
            if it["order"]["order_id"] == "EARLY"
        ]
        # 完成窗 = 09:30:09（index 2），被更晚大单抢占也会保住锚点
        self.assertIn(2, early_idx)
        self.assertEqual(max(early_idx), 2)
        self.assertEqual(windows[max(early_idx)]["time"], "09:30:09")


class EmitWindowTests(unittest.TestCase):
    def test_attribution(self) -> None:
        plan = plan_window(_window(10.0, 5), [{"order": _order("O1", 3.0), "lots": 3.0}])
        rows = emit_window(plan, [{"order": _order("O1", 3.0), "lots": 3.0}])
        order_rows = [row for row in rows if row["kind"] == "order"]
        small_rows = [row for row in rows if row["kind"] == "small"]
        self.assertTrue(order_rows)
        self.assertTrue(small_rows)
        self.assertTrue(all(row["order_id"] == "O1" for row in order_rows))
        # 主动买单：同一买单编号扫多个卖单
        buy_ids = {row["buy_id"] for row in order_rows}
        self.assertEqual(len(buy_ids), 1)
        self.assertTrue(buy_ids.pop().startswith("B"))
        self.assertEqual(len({row["sell_id"] for row in order_rows}), len(order_rows))
        self.assertAlmostEqual(sum(row["lots"] for row in order_rows), 3.0, places=2)
        self.assertAlmostEqual(sum(row["lots"] for row in rows), 10.0, places=2)
        self.assertGreaterEqual(len(rows), 5)

    def test_no_fold_inflate_order_lots(self) -> None:
        """单边大单占不满窗口时，残余归小单，不得撑破资金动向手数。"""
        window = _window(28.0, 1, "10:00:00")
        placed = [{"order": _order("O12", 13.0, "10:00:00"), "lots": 13.0}]
        plan = plan_window(window, placed)
        rows = emit_window(plan, placed)
        order_lots = sum(r["lots"] for r in rows if r.get("order_id") == "O12")
        self.assertAlmostEqual(order_lots, 13.0, places=2)
        self.assertAlmostEqual(sum(r["lots"] for r in rows), 28.0, places=2)

    def test_deadline_fill_uses_fund_flow_time(self) -> None:
        """截止窗内大单逐笔时间 = 资金动向最后成交时间，不是分时档位。"""
        window = _window(547.0, 74, "09:30:15")
        placed = [
            {"order": _order("O1", 258.0, "09:30:14", side="buy"), "lots": 258.0},
            {"order": _order("O2", 232.0, "09:30:14", side="sell"), "lots": 232.0},
        ]
        plan = plan_window(window, placed)
        rows = emit_window(plan, placed)
        order_rows = [r for r in rows if r.get("kind") == "order"]
        self.assertTrue(order_rows)
        self.assertTrue(all(r["time"] == "09:30:14" for r in order_rows))
        self.assertTrue(all(r.get("window_time") == "09:30:15" for r in order_rows))
        buy = sum(r["lots"] for r in order_rows if r.get("order_id") == "O1" or r.get("order_id_peer") == "O1")
        sell = sum(r["lots"] for r in order_rows if r.get("order_id") == "O2" or r.get("order_id_peer") == "O2")
        self.assertAlmostEqual(buy, 258.0, places=2)
        self.assertAlmostEqual(sell, 232.0, places=2)

    def test_one_buy_sell_pair_single_print(self) -> None:
        """一对真实买卖大单必须在一笔里成交，哪怕手数超门槛也不能拆成多笔。"""
        window = _window(300.0, 40, "09:30:15")
        placed = [
            {"order": _order("OB", 254.0, "09:30:14", side="buy"), "lots": 254.0},
            {"order": _order("OS", 254.0, "09:30:14", side="sell"), "lots": 254.0},
        ]
        plan = plan_window(window, placed)
        rows = emit_window(plan, placed)
        paired = [
            r for r in rows
            if {r.get("order_id"), r.get("order_id_peer")} == {"OB", "OS"}
        ]
        # 同一买/卖编号配对只应出现一次（一笔成交）
        self.assertEqual(len(paired), 1)
        self.assertAlmostEqual(paired[0]["lots"], 254.0, places=2)
        # 其余笔数由小单补足到窗口笔数
        self.assertGreaterEqual(len(rows), plan["count"])

    def test_small_trades_below_cap(self) -> None:
        plan = plan_window(_window(10.0, 5), [])
        rows = emit_window(plan, [])
        self.assertGreaterEqual(len(rows), 5)
        for row in rows:
            self.assertLess(row["lots"], CAP_LOTS + 1e-6)
            self.assertGreaterEqual(row["lots"], DEFAULT_MIN_LOTS - 1e-9)
            self.assertEqual(row["lots"], int(row["lots"]))
            self.assertTrue(row["buy_id"] and row["sell_id"])

    def test_zero_lot_placeholders_when_count_exceeds_lots(self) -> None:
        """笔数 > 手数：可行，用 0 手占位，笔数与总量同时守恒。"""
        window = {
            "time": "14:54:44",
            "lots": 58.0,
            "count": 72,
            "price": 1348.0,
            "side": "buy",
        }
        plan = plan_window(window, [], threshold=300_000.0)
        self.assertTrue(plan["feasible"])
        rows = emit_window(plan, [])
        self.assertEqual(len(rows), 72)
        self.assertEqual(sum(row["lots"] for row in rows), 58)
        self.assertTrue(any(row["lots"] == 0 for row in rows))
        for row in rows:
            self.assertEqual(row["lots"], int(row["lots"]))
            self.assertGreaterEqual(row["lots"], TRADE_MIN_LOTS)

    def test_min_lots_one_still_rejects_dense_window(self) -> None:
        """min_lots=1 时笔数 > 手数 → 无解，展开时压缩笔数。"""
        window = {
            "time": "14:54:44",
            "lots": 58.0,
            "count": 72,
            "price": 1348.0,
            "side": "buy",
        }
        plan = plan_window(window, [], threshold=300_000.0, min_lots=1.0)
        self.assertFalse(plan["feasible"])
        rows = emit_window(plan, [])
        self.assertEqual(len(rows), 58)
        self.assertEqual(sum(row["lots"] for row in rows), 58)


class ReconstructWindowsTests(unittest.TestCase):
    def _ticks(self) -> list[dict]:
        return [
            {"time": "09:30:03", "price": PRICE, "volume": 10, "count": 5, "side": "buy"},
            {"time": "09:30:06", "price": PRICE, "volume": 8, "count": 4, "side": "sell"},
            {"time": "09:30:09", "price": PRICE, "volume": 6, "count": 3, "side": "buy"},
        ]

    def _big(self) -> list[dict]:
        return [
            {"time": "09:30:03", "price": PRICE, "volume": 300, "amount": 300000, "side": "buy", "aggressor": "active"},
            {"time": "09:30:09", "price": PRICE, "volume": 200, "amount": 200000, "side": "sell", "aggressor": "active"},
        ]

    def test_conservation(self) -> None:
        pack = reconstruct_windows(self._ticks(), self._big(), code="600519", day="2026-10-26")
        summary = pack["summary"]
        rows = pack["rows"]
        self.assertAlmostEqual(sum(row["lots"] for row in rows), summary["lots"], places=1)
        self.assertGreaterEqual(len(rows), summary["count"])
        self.assertEqual(pack["reconcile"]["lot_mismatch_windows"], 0)
        self.assertEqual(pack["reconcile"]["count_mismatch_windows"], 0)
        for row in rows:
            self.assertTrue(row["buy_id"].startswith("B"))
            self.assertTrue(row["sell_id"].startswith("S"))
            self.assertEqual(row["lots"], int(row["lots"]))
            self.assertGreaterEqual(row["lots"], 0)

    def test_auction_opening_print(self) -> None:
        """开盘集合竞价：1 条记录 + 买卖各一张大单，应有解且买卖编号都能对上。"""
        ticks = [{"time": "09:25:00", "price": PRICE, "volume": 5, "count": 1, "side": "buy"}]
        big = [
            {"time": "09:25:00", "price": PRICE, "volume": 200, "amount": 200000,
             "side": "buy", "aggressor": "active"},
            {"time": "09:25:00", "price": PRICE, "volume": 300, "amount": 300000,
             "side": "sell", "aggressor": "active"},
        ]
        pack = reconstruct_windows(ticks, big, code="600519", view="both")
        self.assertEqual(pack["reconcile"]["infeasible_windows"], 0)
        self.assertEqual(pack["reconcile"]["unplaced_count"], 0)
        self.assertEqual(pack["reconcile"]["lot_mismatch_windows"], 0)
        self.assertAlmostEqual(sum(row["lots"] for row in pack["rows"]), 5.0, places=2)
        self.assertTrue(any(row.get("order_id_peer") for row in pack["rows"]))

    def test_order_lots_preserved(self) -> None:
        pack = reconstruct_windows(self._ticks(), self._big(), code="600519", view="aggressor")
        totals: dict[str, float] = {}
        for row in pack["rows"]:
            if row["kind"] == "order":
                oid = row.get("order_id") or row.get("order_id_peer")
                if not oid:
                    continue
                totals[oid] = totals.get(oid, 0.0) + row["lots"]
        # aggressor 两张单 3+2；逐笔按成交计一次
        self.assertGreaterEqual(sum(totals.values()), 5.0 - 1e-6)
        self.assertEqual(pack["summary"]["order_count"], 2)

    def test_rows_are_ordered_by_time(self) -> None:
        pack = reconstruct_windows(self._ticks(), self._big())
        times = [row["time"] for row in pack["rows"]]
        self.assertEqual(times, sorted(times))

    def test_no_ticks(self) -> None:
        pack = reconstruct_windows([], self._big())
        self.assertEqual(pack["count"], 0)
        self.assertTrue(pack["notes"])

    def test_orders_beyond_records_reported(self) -> None:
        ticks = [{"time": "09:30:03", "price": PRICE, "volume": 10, "count": 3, "side": "buy"}]
        pack = reconstruct_windows(ticks, [], threshold=DEFAULT_TRADE_THRESHOLD)
        self.assertEqual(pack["reconcile"]["infeasible_windows"], 0)

    def test_without_rows(self) -> None:
        pack = reconstruct_windows(self._ticks(), self._big(), with_rows=False, with_windows=False)
        self.assertEqual(pack["count"], 0)
        self.assertNotIn("window_bars", pack)
        self.assertEqual(pack["reconcile"]["lot_mismatch_windows"], 0)


if __name__ == "__main__":
    unittest.main()
