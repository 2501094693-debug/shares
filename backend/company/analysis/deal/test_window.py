"""摄入层单测：窗聚合 / 订单归一（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.deal.constants import (
    DEFAULT_MIN_LOTS,
    DEFAULT_TRADE_THRESHOLD,
    TRADE_MIN_LOTS,
)
from company.analysis.deal.ingest import build_windows, normalize_orders
from company.analysis.deal.pipeline import reconstruct_windows
from company.analysis.deal.util import _deadline_index, _deadline_indices, _stamp_key


class BuildWindowsTests(unittest.TestCase):
    def test_merge_same_stamp(self) -> None:
        windows, stats = build_windows(
            [
                {"time": "09:30:03", "price": 10.0, "volume": 5, "count": 2, "side": "buy"},
                {"time": "09:30:03", "price": 10.0, "volume": 7, "count": 3, "side": "sell"},
            ]
        )
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["lots"], 12)
        self.assertEqual(windows[0]["count"], 5)
        self.assertEqual(stats["windows"], 1)

    def test_drop_auction_virtual_snapshots(self) -> None:
        windows, stats = build_windows(
            [
                {
                    "time": "09:20:00",
                    "price": 10.0,
                    "volume": 100,
                    "count": 1,
                    "side": "4",
                },
                {"time": "09:30:03", "price": 10.0, "volume": 10, "count": 2, "side": "buy"},
            ]
        )
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["time"], "09:30:03")
        self.assertGreaterEqual(stats["auction_dropped"], 1)

    def test_stamp_normalization(self) -> None:
        windows, _ = build_windows(
            [
                {
                    "time": "20261009 09:30:03",
                    "price": 10.0,
                    "volume": 10,
                    "count": 1,
                    "side": "buy",
                }
            ]
        )
        self.assertEqual(windows[0]["time"], "09:30:03")


class NormalizeOrdersTests(unittest.TestCase):
    def test_view_all_keeps_both_sides(self) -> None:
        orders = normalize_orders(
            [
                {
                    "time": "09:30:03",
                    "price": 10.0,
                    "volume_lots": 20,
                    "amount": 20000,
                    "side": "buy",
                    "aggressor": "active",
                },
                {
                    "time": "09:30:03",
                    "price": 10.0,
                    "volume_lots": 15,
                    "amount": 15000,
                    "side": "sell",
                    "aggressor": "passive",
                },
            ],
            view="all",
        )
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0]["order_id"], "O00001")

    def test_view_aggressor_filters_passive(self) -> None:
        orders = normalize_orders(
            [
                {
                    "time": "09:30:03",
                    "price": 10.0,
                    "volume_lots": 20,
                    "amount": 20000,
                    "side": "buy",
                    "aggressor": "active",
                },
                {
                    "time": "09:30:03",
                    "price": 10.0,
                    "volume_lots": 15,
                    "amount": 15000,
                    "side": "sell",
                    "aggressor": "passive",
                },
            ],
            view="aggressor",
        )
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["side"], "buy")


class DeadlineTests(unittest.TestCase):
    def test_boundary_stamp_maps_to_two_windows(self) -> None:
        stamps = ["09:30:03", "09:30:06", "09:30:09"]
        self.assertEqual(_deadline_indices(stamps, "09:30:06"), [1, 2])
        self.assertEqual(_deadline_index(stamps, "09:30:06"), 2)
        self.assertEqual(_deadline_indices(stamps, "09:30:05"), [1])

    def test_call_auction_whole_second_aligns_to_real_bar(self) -> None:
        """资金动向 09:25:00 / 15:00:00 对齐到分时真实档 09:25:02 / 15:00:02。"""
        stamps = ["09:25:02", "09:30:03", "14:57:00", "15:00:02"]
        self.assertEqual(_deadline_indices(stamps, "09:25:00"), [0])
        self.assertEqual(_deadline_indices(stamps, "15:00:00"), [3])
        self.assertEqual(_deadline_indices(stamps, "09:25:02"), [0])

    def test_stamp_key_strips_date(self) -> None:
        self.assertEqual(_stamp_key("2026-10-09 09:30:03"), "09:30:03")


class ReconstructSmokeTests(unittest.TestCase):
    def test_end_to_end_lot_count(self) -> None:
        pack = reconstruct_windows(
            [
                {"time": "09:30:03", "price": 10.0, "volume": 100, "count": 5, "side": "buy"},
                {"time": "09:30:06", "price": 10.0, "volume": 50, "count": 3, "side": "sell"},
            ],
            [
                {
                    "time": "09:30:03",
                    "price": 10.0,
                    "volume_lots": 40,
                    "amount": 40000,
                    "side": "buy",
                    "aggressor": "active",
                    "event_id": "E1",
                }
            ],
            threshold=DEFAULT_TRADE_THRESHOLD,
            min_lots=DEFAULT_MIN_LOTS,
        )
        self.assertEqual(TRADE_MIN_LOTS, 0.0)
        self.assertEqual(pack["reconcile"]["lot_mismatch_windows"], 0)
        self.assertEqual(pack["reconcile"]["count_mismatch_windows"], 0)
        self.assertTrue(any(r.get("order_event_id") == "E1" for r in pack["rows"]))


if __name__ == "__main__":
    unittest.main()
