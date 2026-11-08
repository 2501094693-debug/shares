"""双手数轴 / 影响区间 / 默认管线 单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.deal.axis import build_lot_axis
from company.analysis.deal.constants import DEFAULT_MIN_LOTS
from company.analysis.deal.influence import (
    build_influence_clusters,
    order_influence_range,
    order_touched_windows,
)
from company.analysis.deal.ingest import build_windows, normalize_orders
from company.analysis.deal.pipeline import reconstruct, reconstruct_windows
from company.analysis.deal.solver import Occupancy

PRICE = 1000.0


def _tick(stamp: str, lots: float, count: int, side: str = "buy") -> dict:
    return {"time": stamp, "price": PRICE, "volume": lots, "count": count, "side": side}


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


class OccupancyTests(unittest.TestCase):
    def test_add_and_clip(self) -> None:
        occ = Occupancy()
        occ.add(0, 10, "A")
        occ.add(20, 30, "B")
        self.assertEqual(occ.clip_to_window(5, 25), [(5, 10, "A"), (20, 25, "B")])
        self.assertEqual(occ.get("A"), (0, 10))


class BuildLotAxisTests(unittest.TestCase):
    def test_cumulative_intervals(self) -> None:
        windows, _ = build_windows(
            [
                _tick("09:30:03", 100, 10),
                _tick("09:30:06", 50, 5),
                _tick("09:30:09", 80, 8),
            ]
        )
        axis, total = build_lot_axis(windows)
        self.assertEqual(total, 230)
        self.assertEqual(axis[0]["L"], 0)
        self.assertEqual(axis[0]["R"], 100)
        self.assertEqual(axis[1]["L"], 100)
        self.assertEqual(axis[1]["R"], 150)
        self.assertEqual(axis[2]["L"], 150)
        self.assertEqual(axis[2]["R"], 230)
        self.assertEqual(axis[1]["prev_time"], "09:30:03")


class InfluenceTests(unittest.TestCase):
    def test_influence_and_clusters(self) -> None:
        windows, _ = build_windows(
            [
                _tick("09:30:03", 100, 10),
                _tick("09:30:06", 100, 10),
                _tick("09:30:09", 100, 10),
            ]
        )
        axis, _ = build_lot_axis(windows)
        orders = normalize_orders(
            [
                _deal("09:30:06", 60, "sell"),
                _deal("09:30:09", 40, "buy", aggressor="passive"),
            ]
        )
        lo, hi = order_influence_range(orders[0], axis)
        self.assertLess(lo, hi)
        touched = order_touched_windows(orders[0], axis)
        self.assertTrue(touched)
        clusters = build_influence_clusters(orders, axis)
        self.assertGreaterEqual(len(clusters), 1)
        covered = set()
        for cluster in clusters:
            for index in cluster.window_indices:
                self.assertNotIn(index, covered)
                covered.add(index)


class ReconstructTests(unittest.TestCase):
    def test_default_pipeline_conserves(self) -> None:
        pack = reconstruct(
            [
                _tick("09:30:03", 100, 5),
                _tick("09:30:06", 80, 4),
            ],
            [
                _deal("09:30:03", 40, "buy"),
                _deal("09:30:06", 30, "sell", aggressor="passive"),
            ],
            code="TEST",
            view="all",
            min_lots=DEFAULT_MIN_LOTS,
        )
        self.assertEqual(pack["granularity"], "axis")
        self.assertEqual(pack["params"]["solver"], "joint")
        self.assertEqual(pack["reconcile"]["lot_mismatch_windows"], 0)
        self.assertEqual(pack["reconcile"]["count_mismatch_windows"], 0)
        self.assertAlmostEqual(pack["summary"]["lots"], 180.0)

    def test_reconstruct_windows_alias_ignores_legacy_flags(self) -> None:
        pack = reconstruct_windows(
            [_tick("09:30:03", 50, 5)],
            [_deal("09:30:03", 20, "buy")],
            algorithm="window",
            solver="greedy",
        )
        self.assertEqual(pack["granularity"], "axis")
        self.assertEqual(pack["params"]["solver"], "joint")


if __name__ == "__main__":
    unittest.main()
