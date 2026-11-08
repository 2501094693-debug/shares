"""约束口径回归：截止窗 / 守恒 / R8 / R12（默认联合落位管线）。"""

from __future__ import annotations

import unittest

from company.analysis.deal.pipeline import reconstruct_windows
from company.analysis.deal.util import _deadline_indices


PRICE = 17.5


def _tick(stamp: str, lots: float, count: int, side: str = "buy") -> dict:
    return {"time": stamp, "price": PRICE, "volume": lots, "count": count, "side": side}


def _deal(
    stamp: str,
    lots: float,
    side: str,
    *,
    aggressor: str = "active",
    price: float = PRICE,
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


class DeadlineConstraintTests(unittest.TestCase):
    def test_closed_endpoint_deadline(self) -> None:
        stamps = ["09:30:03", "09:30:06", "09:30:09"]
        self.assertEqual(_deadline_indices(stamps, "09:30:06"), [1, 2])

    def test_order_completes_in_deadline_window(self) -> None:
        pack = reconstruct_windows(
            [
                _tick("09:30:03", 100, 5),
                _tick("09:30:06", 100, 5),
                _tick("09:30:09", 100, 5),
            ],
            [_deal("09:30:07", 60, "sell")],
            view="all",
        )
        order_rows = [r for r in pack["rows"] if r.get("kind") == "order"]
        self.assertTrue(order_rows)
        self.assertTrue(
            any(r.get("window_time") in {"09:30:06", "09:30:09"} for r in order_rows)
        )


class ConservationTests(unittest.TestCase):
    def test_window_lots_and_count(self) -> None:
        pack = reconstruct_windows(
            [
                _tick("09:30:03", 200, 8),
                _tick("09:30:06", 150, 6),
            ],
            [
                _deal("09:30:03", 80, "buy"),
                _deal("09:30:06", 50, "sell", aggressor="passive"),
            ],
            view="all",
        )
        self.assertEqual(pack["reconcile"]["lot_mismatch_windows"], 0)
        self.assertEqual(pack["reconcile"]["count_mismatch_windows"], 0)
        self.assertTrue(pack["reconcile"]["constraints_ok"])


class PairAndCapTests(unittest.TestCase):
    def test_pair_one_print(self) -> None:
        pack = reconstruct_windows(
            [
                _tick("09:30:03", 200, 4),
                _tick("09:30:06", 200, 4),
            ],
            [
                _deal("09:30:06", 120, "buy", aggressor="passive"),
                _deal("09:30:06", 120, "sell", aggressor="active"),
            ],
            view="all",
        )
        pairs = [
            (r.get("buy_id"), r.get("sell_id"))
            for r in pack["rows"]
            if r.get("order_id") and r.get("order_id_peer")
        ]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_anonymous_rows_respect_cap(self) -> None:
        pack = reconstruct_windows(
            [_tick("09:30:03", 400, 4)],
            [_deal("09:30:02", 342, "sell")],
            view="all",
        )
        self.assertEqual(pack["reconcile"]["rows_cap_violation_count"], 0)


if __name__ == "__main__":
    unittest.main()
