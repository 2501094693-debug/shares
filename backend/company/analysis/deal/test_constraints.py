"""按需求逐条验证 3 秒窗口逐笔重建约束（无网络）。

需求清单
--------
R1 分时档 = 左闭右开 3 秒区间；大单按最后成交时间落入对应区间
R2 尽可能撮合大单，但窗内大单手数 <= 区间总手数
R3 区间若有剩余笔数，须为其预留可用手数
R4 大单最后成交时间不错（完成窗锚点）
R5 大单落位后填小单；填完后区间笔数、总手数、均价正确
R6 输出逐笔：成交时间 / 成交手数 / 卖单编号 / 买单编号
R7 手数为整手，允许 0，禁止小数
R8 任意一对买卖单只允许一笔成交（不可多笔）
R9 大单不得被拆开，须连续成交
"""

from __future__ import annotations

import json
import unittest
from collections import defaultdict
from pathlib import Path

from company.analysis.deal.window import (
    _deadline_index,
    emit_window,
    normalize_orders,
    place_orders,
    plan_window,
    reconstruct_windows,
)

PRICE = 17.5


def _w(lots: float, count: int, stamp: str, price: float = PRICE, **extra) -> dict:
    row = {
        "time": stamp,
        "lots": lots,
        "count": count,
        "amount": lots * price * 100,
        "price": price,
        "side": "buy",
    }
    row.update(extra)
    return row


def _o(oid: str, lots: float, stamp: str, side: str = "buy", price: float = PRICE) -> dict:
    return {
        "order_id": oid,
        "time": stamp,
        "price": price,
        "lots": lots,
        "amount": lots * price * 100,
        "side": side,
        "view": "active",
    }


def _assert_integer_lots(testcase: unittest.TestCase, rows: list[dict]) -> None:
    for row in rows:
        lots = row["lots"]
        testcase.assertEqual(lots, int(lots), msg=f"小数手: {row}")
        testcase.assertGreaterEqual(lots, 0)


def _assert_output_fields(testcase: unittest.TestCase, rows: list[dict]) -> None:
    for row in rows:
        for key in ("time", "lots", "sell_id", "buy_id"):
            testcase.assertIn(key, row)
        testcase.assertTrue(str(row["buy_id"]).startswith("B") or row["buy_id"] == "")
        testcase.assertTrue(str(row["sell_id"]).startswith("S") or row["sell_id"] == "")


def _pair_key(row: dict) -> tuple[str, str]:
    return (str(row.get("buy_id") or ""), str(row.get("sell_id") or ""))


def _window_vwap(rows: list[dict], window_time: str) -> float | None:
    subset = [r for r in rows if str(r.get("window_time") or r.get("time")) == window_time]
    lots = sum(float(r["lots"]) for r in subset)
    if lots <= 0:
        return None
    amount = sum(float(r["lots"]) * float(r["price"]) * 100 for r in subset)
    return amount / (lots * 100)


class DeadlineIndexTests(unittest.TestCase):
    """R1：左闭右开归属。"""

    def test_on_grid_goes_to_next_window(self) -> None:
        # 档 S 覆盖 [prev, S)；T==S 落在下一档 [S, S+3)
        stamps = ["09:30:03", "09:30:06", "09:30:09"]
        self.assertEqual(_deadline_index(stamps, "09:30:06"), 2)
        self.assertEqual(stamps[2], "09:30:09")

    def test_off_grid_goes_to_covering_window(self) -> None:
        stamps = ["09:30:03", "09:30:06", "09:30:09"]
        # 09:30:07 ∈ [09:30:06, 09:30:09) → 档 09:30:09
        self.assertEqual(_deadline_index(stamps, "09:30:07"), 2)

    def test_left_endpoint_belongs_to_window(self) -> None:
        stamps = ["09:30:03", "09:30:06", "09:30:09"]
        # 09:30:06 是下一档左端；按左闭右开，T=09:30:06 属 [09:30:06, 09:30:09)
        self.assertEqual(_deadline_index(stamps, "09:30:06"), 2)

    def test_auction_stays_on_own_stamp(self) -> None:
        stamps = ["09:25:00", "09:30:03"]
        self.assertEqual(_deadline_index(stamps, "09:25:00"), 0)


class PlaceConstraintTests(unittest.TestCase):
    """R2/R3/R4：容量、预留、完成时间。"""

    def test_big_lots_never_exceed_window(self) -> None:
        windows = [_w(10, 5, "09:30:03"), _w(10, 5, "09:30:06")]
        orders = [_o("BIG", 30, "09:30:06")]  # 超过全日总量
        allocation, unplaced = place_orders(windows, orders)
        for idx, items in allocation.items():
            side_lots = sum(it["lots"] for it in items)
            self.assertLessEqual(side_lots, windows[idx]["lots"] + 1e-9)
        self.assertTrue(unplaced)
        self.assertAlmostEqual(unplaced[0]["missing"], 10.0)

    def test_remaining_slots_reserved_when_min_lots(self) -> None:
        """R3：剩余笔数必须有手数可用（min_lots=1）。"""
        windows = [_w(10, 4, "09:30:03")]
        orders = [_o("BIG", 10, "09:30:03")]
        allocation, _ = place_orders(windows, orders, min_lots=1.0)
        big = sum(it["lots"] for items in allocation.values() for it in items)
        # 4 笔：大单占 1 槽，剩 3 槽各预留 1 → 大单最多 7
        self.assertEqual(big, 7.0)
        plan = plan_window(windows[0], allocation.get(0, []), min_lots=1.0)
        self.assertGreaterEqual(plan["small_lots"], plan["small_count"] * 1.0 - 1e-9)

    def test_default_min_lots_zero_allows_zero_lot_slots(self) -> None:
        """min_lots=0 时剩余笔数可用 0 手占位，大单可吃满。"""
        windows = [_w(10, 4, "09:30:03")]
        orders = [_o("BIG", 10, "09:30:03")]
        allocation, unplaced = place_orders(windows, orders, min_lots=0.0)
        self.assertFalse(unplaced)
        big = sum(it["lots"] for items in allocation.values() for it in items)
        self.assertEqual(big, 10.0)

    def test_completion_time_pinned(self) -> None:
        """R4：大单至少一笔落在截止窗。"""
        windows = [_w(5, 3, "09:30:03"), _w(5, 3, "09:30:06"), _w(5, 3, "09:30:09")]
        orders = [_o("O1", 12, "09:30:07")]  # off-grid → 截止窗 09:30:09
        allocation, unplaced = place_orders(windows, orders)
        self.assertFalse(unplaced)
        self.assertIn(2, allocation)
        pinned = sum(it["lots"] for it in allocation[2] if it["order"]["order_id"] == "O1")
        self.assertGreaterEqual(pinned, 1.0)


class EmitConstraintTests(unittest.TestCase):
    """R5–R9：展开后的守恒与形态约束。"""

    def test_output_schema_integer_lots(self) -> None:
        plan = plan_window(_w(10, 5, "09:30:03"), [])
        rows = emit_window(plan, [])
        _assert_output_fields(self, rows)
        _assert_integer_lots(self, rows)
        self.assertEqual(sum(r["lots"] for r in rows), 10)
        self.assertEqual(len(rows), 5)

    def test_count_lots_after_small_fill(self) -> None:
        """R5：填小单后笔数与总手数正确。"""
        window = _w(20, 8, "09:30:06")
        placed = [{"order": _o("O1", 7, "09:30:06"), "lots": 7.0}]
        plan = plan_window(window, placed)
        rows = emit_window(plan, placed)
        self.assertEqual(sum(r["lots"] for r in rows), 20)
        self.assertEqual(len(rows), 8)
        self.assertAlmostEqual(
            sum(r["lots"] for r in rows if r.get("order_id") == "O1"), 7.0, places=2
        )

    def test_exact_count_when_residual_forces_fold(self) -> None:
        """R5：count=1 但大单未吃满 → 残余并入该笔，笔数仍为 1，归因不变。"""
        window = _w(28, 1, "10:00:00")
        placed = [{"order": _o("O12", 13, "10:00:00"), "lots": 13.0}]
        plan = plan_window(window, placed)
        rows = emit_window(plan, placed)
        self.assertEqual(len(rows), 1)
        self.assertEqual(sum(r["lots"] for r in rows), 28)
        self.assertEqual(rows[0].get("attributed_lots"), 13.0)
        vwap = _window_vwap(rows, "10:00:00")
        self.assertAlmostEqual(vwap, PRICE, places=3)

    def test_vwap_when_order_price_equals_window(self) -> None:
        """R5：大单价 = 窗均价时，还原均价应对齐。"""
        window = _w(20, 8, "09:30:06", price=17.5)
        placed = [{"order": _o("O1", 7, "09:30:06", price=17.5), "lots": 7.0}]
        plan = plan_window(window, placed)
        rows = emit_window(plan, placed)
        vwap = _window_vwap(rows, "09:30:06")
        self.assertIsNotNone(vwap)
        self.assertAlmostEqual(vwap, 17.5, places=4)

    def test_vwap_aligned_when_order_price_differs(self) -> None:
        """R5：大单价 ≠ 窗均价时，填小单后窗内 VWAP 仍应等于分时均价。"""
        window = _w(20, 8, "09:30:06", price=17.50)
        placed = [{"order": _o("O1", 10, "09:30:06", price=17.80), "lots": 10.0}]
        plan = plan_window(window, placed)
        rows = emit_window(plan, placed)
        vwap = _window_vwap(rows, "09:30:06")
        self.assertIsNotNone(vwap)
        self.assertAlmostEqual(vwap, 17.50, places=3)
        # 大单本身仍保留资金动向价
        order_rows = [r for r in rows if r.get("order_id") == "O1"]
        self.assertTrue(order_rows)
        self.assertTrue(all(abs(float(r["price"]) - 17.80) < 1e-6 for r in order_rows))
        for row in rows:
            self.assertGreater(float(row["price"]), 0.0)

    def test_order_price_kept_when_small_cannot_absorb(self) -> None:
        """小单回校会非正时：放弃窗均价，大单仍保留资金动向价。"""
        window = _w(20, 8, "09:30:06", price=17.50)
        placed = [{"order": _o("O1", 19, "09:30:06", price=25.0), "lots": 19.0}]
        plan = plan_window(window, placed)
        rows = emit_window(plan, placed)
        order_rows = [r for r in rows if r.get("order_id") == "O1"]
        self.assertTrue(order_rows)
        self.assertTrue(all(abs(float(r["price"]) - 25.0) < 1e-6 for r in order_rows))
        for row in rows:
            self.assertGreater(float(row["price"]), 0.0)

    def test_order_price_kept_when_order_fills_whole_window(self) -> None:
        """大单吃满窗口：不把资金动向价改写成窗均价。"""
        window = _w(87, 12, "09:30:38", price=17.49)
        placed = [{"order": _o("O1", 87, "09:30:35", side="sell", price=17.48), "lots": 87.0}]
        plan = plan_window(window, placed)
        rows = emit_window(plan, placed)
        order_rows = [r for r in rows if r.get("order_id") == "O1"]
        self.assertTrue(order_rows)
        self.assertTrue(all(abs(float(r["price"]) - 17.48) < 1e-6 for r in order_rows))
        self.assertAlmostEqual(sum(r["lots"] for r in order_rows), 87.0, places=2)

    def test_one_pair_one_trade_only(self) -> None:
        """R8：任意 (buy_id, sell_id) 至多出现一次。"""
        window = _w(300, 40, "09:30:15")
        placed = [
            {"order": _o("OB", 100, "09:30:14", side="buy"), "lots": 100.0},
            {"order": _o("OS", 100, "09:30:14", side="sell"), "lots": 100.0},
        ]
        plan = plan_window(window, placed)
        rows = emit_window(plan, placed)
        pairs = [_pair_key(r) for r in rows if r.get("buy_id") and r.get("sell_id")]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_large_order_continuous_same_id(self) -> None:
        """R9：同一大单在时间序上其成交块连续（中间不夹其它真实大单编号切换再回来）。"""
        window = _w(50, 10, "09:30:06")
        placed = [{"order": _o("BIG", 30, "09:30:06", side="buy"), "lots": 30.0}]
        plan = plan_window(window, placed)
        rows = emit_window(plan, placed)
        order_rows = [r for r in rows if r.get("order_id") == "BIG"]
        self.assertTrue(order_rows)
        buy_ids = [r["buy_id"] for r in order_rows]
        self.assertEqual(len(set(buy_ids)), 1, "大单买单编号应唯一且贯穿")
        # 时间上应成块：按全序扫描，属于该 buy_id 的行应是一个连续区间
        all_sorted = sorted(rows, key=lambda r: (r["time"], 0 if r["kind"] == "order" else 1))
        flags = [r["buy_id"] == buy_ids[0] and r.get("kind") == "order" for r in all_sorted]
        if any(flags):
            first = flags.index(True)
            last = len(flags) - 1 - flags[::-1].index(True)
            self.assertTrue(all(flags[first : last + 1]))

    def test_cross_window_large_order_respects_window_capacity(self) -> None:
        """跨窗大单：各窗归因手数 ≤ 分时容量；按 time 汇总与分时档一致（四创 200 手）。"""
        ticks = [
            {"time": "09:30:35", "price": 17.48, "volume": 123, "count": 8, "side": "buy"},
            {"time": "09:30:38", "price": 17.49, "volume": 87, "count": 12, "side": "buy"},
        ]
        big = [
            {
                "time": "09:30:35",
                "price": 17.48,
                "volume": 20000,
                "volume_lots": 200,
                "amount": 349600,
                "side": "sell",
                "aggressor": "passive",
            },
        ]
        pack = reconstruct_windows(ticks, big, view="all")
        rows = pack["rows"]
        order_rows = [r for r in rows if r.get("order_id")]
        self.assertTrue(order_rows)
        sell_id = order_rows[0]["sell_id"]
        self.assertTrue(all(r["sell_id"] == sell_id for r in order_rows))
        self.assertAlmostEqual(sum(r["lots"] for r in order_rows), 200.0, places=2)
        # 全部门价均为资金动向价
        self.assertTrue(all(abs(float(r["price"]) - 17.48) < 1e-6 for r in order_rows))
        # 按 window_time（分时档）汇总 = 分时手数（不能把 200 叠进 87 手那一档）
        by_win: dict[str, float] = defaultdict(float)
        by_win_order: dict[str, float] = defaultdict(float)
        for r in rows:
            wt = str(r.get("window_time") or r["time"])
            by_win[wt] += float(r["lots"])
            if r.get("kind") == "order":
                by_win_order[wt] += float(r["lots"])
        self.assertAlmostEqual(by_win["09:30:35"], 123.0, places=2)
        self.assertAlmostEqual(by_win["09:30:38"], 87.0, places=2)
        self.assertLessEqual(by_win_order["09:30:35"], 123.0 + 1e-9)
        self.assertLessEqual(by_win_order["09:30:38"], 87.0 + 1e-9)
        self.assertAlmostEqual(
            by_win_order["09:30:35"] + by_win_order["09:30:38"], 200.0, places=2
        )
        # 完成时刻在 order_time
        self.assertTrue(all(r.get("order_time") == "09:30:35" for r in order_rows))
        # 跨窗大单在胶带上必须成块：中间不能夹小单（曾出现 113 + 10小 + 87）
        ordered = sorted(rows, key=lambda r: r.get("seq") or 0)
        flags = [
            r.get("kind") == "order" and r.get("sell_id") == sell_id for r in ordered
        ]
        first = flags.index(True)
        last = len(flags) - 1 - flags[::-1].index(True)
        self.assertTrue(all(flags[first : last + 1]), "跨窗大单被小单夹开")
        self.assertAlmostEqual(
            sum(float(ordered[i]["lots"]) for i in range(first, last + 1)), 200.0, places=2
        )

    def test_paired_orders_stay_continuous_across_windows(self) -> None:
        """R9：买卖大单跨窗时一对只出一笔；同侧编号在 order 行中连续。"""
        ticks = [
            {"time": "09:37:51", "price": 17.58, "volume": 100, "count": 5, "side": "buy"},
            {"time": "09:37:54", "price": 17.58, "volume": 200, "count": 10, "side": "buy"},
        ]
        big = [
            {
                "time": "09:37:51",
                "price": 17.58,
                "volume": 34400,
                "volume_lots": 344,
                "amount": 34400 * 17.58,
                "side": "buy",
                "aggressor": "active",
            },
            {
                "time": "09:37:51",
                "price": 17.58,
                "volume": 25400,
                "volume_lots": 254,
                "amount": 25400 * 17.58,
                "side": "sell",
                "aggressor": "passive",
            },
        ]
        pack = reconstruct_windows(ticks, big, view="all")
        rows = pack["rows"]
        paired = [
            r for r in rows
            if r.get("kind") == "order" and r.get("order_id") and r.get("order_id_peer")
        ]
        self.assertEqual(len(paired), 1, "一对买卖只应一笔")
        for side_key in ("buy_id", "sell_id"):
            positions: dict[str, list[int]] = defaultdict(list)
            ordered = sorted(rows, key=lambda x: (x["time"], x.get("seq") or 0))
            for i, r in enumerate(ordered):
                if r.get("kind") != "order":
                    continue
                sid = str(r.get(side_key) or "")
                if sid:
                    positions[sid].append(i)
            for sid, idxs in positions.items():
                if len(idxs) < 2:
                    continue
                span = ordered[min(idxs) : max(idxs) + 1]
                foreign = [
                    r for r in span
                    if r.get("kind") == "order" and r.get(side_key) and r.get(side_key) != sid
                ]
                self.assertEqual(foreign, [], msg=f"{side_key} {sid} 被拆开")


class ReconstructConstraintTests(unittest.TestCase):
    """端到端：多窗口 + 守恒 + 形态。"""

    def _pack(self) -> dict:
        ticks = [
            {"time": "09:30:03", "price": PRICE, "volume": 12, "count": 6, "side": "buy"},
            {"time": "09:30:06", "price": PRICE, "volume": 15, "count": 5, "side": "sell"},
            {"time": "09:30:09", "price": PRICE, "volume": 9, "count": 3, "side": "buy"},
        ]
        big = [
            {
                "time": "09:30:05",
                "price": PRICE,
                "volume": 500,
                "amount": 500 * PRICE * 100,
                "side": "buy",
                "aggressor": "active",
            },
            {
                "time": "09:30:09",
                "price": PRICE,
                "volume": 400,
                "amount": 400 * PRICE * 100,
                "side": "sell",
                "aggressor": "active",
            },
        ]
        return reconstruct_windows(ticks, big, code="TEST", view="aggressor")

    def test_end_to_end_conservation(self) -> None:
        pack = self._pack()
        rows = pack["rows"]
        _assert_output_fields(self, rows)
        _assert_integer_lots(self, rows)
        self.assertEqual(pack["reconcile"]["lot_mismatch_windows"], 0)
        self.assertEqual(pack["reconcile"]["count_mismatch_windows"], 0)
        # 按 window_time 对账
        by_win: dict[str, list] = defaultdict(list)
        for r in rows:
            by_win[str(r.get("window_time") or r["time"])].append(r)
        for bar in pack.get("window_bars") or []:
            got = by_win.get(bar["time"], [])
            self.assertAlmostEqual(sum(r["lots"] for r in got), bar["lots"], places=2)
            if not bar.get("auction"):
                self.assertGreaterEqual(len(got), bar["count"])

    def test_pair_uniqueness_across_day(self) -> None:
        pack = self._pack()
        pairs = [_pair_key(r) for r in pack["rows"] if r.get("buy_id") and r.get("sell_id")]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_completion_time_on_tape(self) -> None:
        """资金动向最后成交时间写在 order_time（time 跟分时档，不对齐完成秒）。"""
        pack = self._pack()
        for r in pack["rows"]:
            if r.get("kind") != "order" or not r.get("order_id"):
                continue
            self.assertTrue(r.get("order_time"), msg=f"{r.get('order_id')} 缺 order_time")


class RealCacheConstraintTests(unittest.TestCase):
    """用磁盘缓存 600990 做全量对账（有缓存才跑）。"""

    CODE = "600990"
    DAY = "2026-10-26"

    @classmethod
    def _load(cls) -> tuple[list, list] | None:
        root = Path(__file__).resolve().parents[3] / "cache"
        tick_path = root / "ticks" / f"{cls.CODE}_{cls.DAY}.json"
        flow_path = root / "fundflow" / f"{cls.CODE}_{cls.DAY}.json"
        if not tick_path.exists() or not flow_path.exists():
            return None
        ticks = json.loads(tick_path.read_text(encoding="utf-8"))
        flow = json.loads(flow_path.read_text(encoding="utf-8"))
        # ticks 缓存外壳：{data: {items: [...]}}；偶见扁平 {items: [...]}
        payload = ticks.get("data") if isinstance(ticks.get("data"), dict) else ticks
        tick_items = list(payload.get("items") or [])
        big_items = list(flow.get("items") or [])
        if not tick_items:
            return None
        return tick_items, big_items

    def _split_side_ids(self, rows: list[dict], side_key: str) -> list[str]:
        positions: dict[str, list[int]] = defaultdict(list)
        ordered = sorted(rows, key=lambda x: (x["time"], x.get("seq") or 0))
        for i, r in enumerate(ordered):
            if r.get("kind") != "order":
                continue
            sid = str(r.get(side_key) or "")
            if sid:
                positions[sid].append(i)
        split_ids: list[str] = []
        for sid, idxs in positions.items():
            if len(idxs) < 2:
                continue
            span = ordered[min(idxs) : max(idxs) + 1]
            foreign = [
                r
                for r in span
                if r.get("kind") == "order" and r.get(side_key) and r.get(side_key) != sid
            ]
            if foreign:
                split_ids.append(sid)
        return split_ids

    def test_real_day_hard_passes(self) -> None:
        """真实日：已满足的硬约束。"""
        loaded = self._load()
        if loaded is None:
            self.skipTest("无 600990 缓存")
        ticks, big = loaded
        pack = reconstruct_windows(ticks, big, code=self.CODE, day=self.DAY, view="all")
        rows = pack["rows"]
        self.assertGreater(len(rows), 0)
        _assert_output_fields(self, rows)
        _assert_integer_lots(self, rows)

        pairs = [_pair_key(r) for r in rows if r.get("buy_id") and r.get("sell_id")]
        self.assertEqual(len(pairs), len(set(pairs)))

        self.assertEqual(pack["reconcile"]["lot_mismatch_windows"], 0)
        self.assertEqual(pack["reconcile"]["count_mismatch_windows"], 0)  # 仅检查短缺
        self.assertEqual(pack["reconcile"]["unplaced_count"], 0)
        self.assertEqual(pack["reconcile"]["order_lot_mismatch_count"], 0)
        self.assertEqual(pack["reconcile"]["infeasible_windows"], 0)

        orders = normalize_orders(big, view="all")
        attr: dict[str, list[str]] = defaultdict(list)
        for r in rows:
            if r.get("kind") != "order":
                continue
            for key in (r.get("order_id"), r.get("order_id_peer")):
                if key:
                    attr[str(key)].append(str(r.get("order_time") or ""))
        for order in orders:
            times = attr.get(order["order_id"]) or []
            self.assertIn(order["time"], times, msg=f"{order['order_id']} 缺 order_time 完成时刻")

        # 按 window_time 汇总必须等于分时档手数
        by_win: dict[str, float] = defaultdict(float)
        for r in rows:
            by_win[str(r.get("window_time") or r.get("time") or "")] += float(r.get("lots") or 0)
        for bar in pack.get("window_bars") or []:
            self.assertAlmostEqual(
                by_win.get(bar["time"], 0.0),
                float(bar["lots"]),
                places=2,
                msg=f"{bar['time']} 分时手数与胶带汇总不一致",
            )

    def test_real_day_known_gaps(self) -> None:
        """真实日：均价 / 精确笔数 / 大单连续 必须全部满足。"""
        loaded = self._load()
        if loaded is None:
            self.skipTest("无 600990 缓存")
        ticks, big = loaded
        pack = reconstruct_windows(ticks, big, code=self.CODE, day=self.DAY, view="all")
        rows = pack["rows"]

        by_win: dict[str, list] = defaultdict(list)
        for r in rows:
            by_win[str(r.get("window_time") or r["time"])].append(r)

        # R5 精确笔数（reconcile 只查短缺，这里查相等）
        count_neq = [
            bar["time"]
            for bar in pack.get("window_bars") or []
            if not bar.get("auction")
            and len(by_win.get(bar["time"]) or []) != int(bar["count"])
        ]

        price_bad = []
        for bar in pack.get("window_bars") or []:
            got = by_win.get(bar["time"]) or []
            lots = sum(float(r["lots"]) for r in got)
            if lots <= 0:
                continue
            # 大单吃满窗时优先保资金动向价，窗均价可对不齐
            small_lots = sum(float(r["lots"]) for r in got if r.get("kind") != "order")
            if small_lots <= 0:
                continue
            vwap = sum(float(r["lots"]) * float(r["price"]) for r in got) / lots
            if abs(vwap - float(bar["price"])) > 0.005:
                price_bad.append(bar["time"])

        # 同一大单跨窗价格必须一致（资金动向价，不被某窗均价改写）
        order_px: dict[str, set[float]] = defaultdict(set)
        for r in rows:
            if r.get("kind") != "order":
                continue
            for key in (r.get("order_id"), r.get("order_id_peer")):
                if key:
                    order_px[str(key)].add(round(float(r.get("price") or 0), 4))
        order_price_split = [oid for oid, pxs in order_px.items() if len(pxs) > 1]

        split_buy = self._split_side_ids(rows, "buy_id")
        split_sell = self._split_side_ids(rows, "sell_id")

        gaps = {
            "count_exact_mismatch": count_neq,
            "vwap_mismatch": price_bad,
            "order_price_split": order_price_split,
            "split_buy_ids": split_buy,
            "split_sell_ids": split_sell,
        }
        unmet = {k: v for k, v in gaps.items() if v}
        self.assertFalse(
            unmet,
            msg=(
                "未满足需求："
                + "; ".join(f"{k}={len(v)} 例 {v[:5]}" for k, v in unmet.items())
            ),
        )


if __name__ == "__main__":
    unittest.main()
