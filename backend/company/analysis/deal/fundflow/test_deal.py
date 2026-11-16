"""大单统计引擎单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.deal.fundflow.core import (
    AMOUNT_STEP,
    LOTS_STEP,
    aggregate_big_deals,
    build_step_edges,
    classify_event,
    normalize_bin_by,
)


def _row(amount: float, lots: float, side: str = "buy", aggressor: str = "active") -> dict:
    return {
        "time": "10:00:00",
        "side": side,
        "aggressor": aggressor,
        "amount": amount,
        "volume_lots": lots,
        "volume": lots * 100,
    }


def _deals() -> list[dict]:
    return [
        _row(100_000, 10),
        _row(200_000, 20),
        _row(1_300_000, 130),
        _row(4_500_000, 450),
        _row(600_000, 60, side="sell", aggressor="passive"),
    ]


class ClassifyTests(unittest.TestCase):
    def test_side_and_aggressor(self) -> None:
        self.assertEqual(classify_event({"side": "buy", "aggressor": "active"}), "active_buy")
        self.assertEqual(classify_event({"side": "sell", "aggressor": "active"}), "active_sell")
        self.assertEqual(classify_event({"side": "buy", "aggressor": "passive"}), "passive_buy")
        self.assertEqual(classify_event({"side": "sell", "aggressor": "passive"}), "passive_sell")

    def test_label_and_name_fallback(self) -> None:
        self.assertEqual(classify_event({"side": "buy", "aggressor_label": "主"}), "active_buy")
        self.assertEqual(classify_event({"side": "sell", "aggressor_label": "被"}), "passive_sell")
        self.assertEqual(classify_event({"event_name": "特大主动卖"}), "active_sell")

    def test_unknown(self) -> None:
        self.assertIsNone(classify_event({}))
        self.assertIsNone(classify_event({"side": "buy"}))


class BinByTests(unittest.TestCase):
    def test_default_and_aliases(self) -> None:
        self.assertEqual(normalize_bin_by(""), "amount")
        self.assertEqual(normalize_bin_by("amount"), "amount")
        self.assertEqual(normalize_bin_by("volume_lots"), "lots")
        self.assertEqual(normalize_bin_by("BOTH"), "both")

    def test_invalid(self) -> None:
        with self.assertRaises(ValueError):
            normalize_bin_by("price")


class EdgeTests(unittest.TestCase):
    def test_no_sample(self) -> None:
        self.assertEqual(build_step_edges(0, AMOUNT_STEP), [])

    def test_covers_max(self) -> None:
        edges = build_step_edges(4_500_000, AMOUNT_STEP)
        self.assertEqual(len(edges), 5)
        self.assertEqual(edges[0], (0, 1_000_000))
        self.assertEqual(edges[-1], (4_000_000, 5_000_000))
        self.assertGreater(edges[-1][1], 4_500_000)

    def test_exact_multiple_gets_own_bin(self) -> None:
        edges = build_step_edges(2_000_000, AMOUNT_STEP)
        self.assertEqual(len(edges), 3)
        self.assertEqual(edges[-1], (2_000_000, 3_000_000))

    def test_lots_step(self) -> None:
        edges = build_step_edges(450, LOTS_STEP)
        self.assertEqual(len(edges), 5)
        self.assertEqual(edges[0], (0, 100))

class AggregateTests(unittest.TestCase):
    def test_quadrants_and_nets(self) -> None:
        out = aggregate_big_deals(_deals(), min_amount=0, bin_by="both")
        self.assertEqual(out["total_count"], 5)
        self.assertEqual(out["active_buy"]["count"], 4)
        self.assertEqual(out["active_buy"]["amount"], 6_100_000)
        self.assertEqual(out["active_buy"]["volume_lots"], 610)
        self.assertEqual(out["passive_sell"]["count"], 1)
        self.assertEqual(out["active_sell"]["count"], 0)
        self.assertEqual(out["buy"]["count"], 4)
        self.assertEqual(out["sell"]["count"], 1)
        self.assertEqual(out["net_amount"], 5_500_000)
        self.assertEqual(out["active_net_amount"], 6_100_000)

    def test_bins_cover_zero_and_keep_empty(self) -> None:
        out = aggregate_big_deals(_deals(), min_amount=0, bin_by="both")
        bins = out["active_buy"]["amount_bins"]
        self.assertEqual(len(bins), 5)
        self.assertEqual(bins[0]["lo"], 0)
        self.assertEqual(bins[0]["hi"], 1_000_000)
        self.assertEqual(bins[2]["count"], 0)
        self.assertEqual(bins[2]["amount"], 0)
        self.assertEqual(bins[-1]["count"], 1)
        self.assertEqual(bins[-1]["amount"], 4_500_000)

    def test_bins_sum_to_quadrant_totals(self) -> None:
        out = aggregate_big_deals(_deals(), min_amount=0, bin_by="both")
        for key in ("active_buy", "active_sell", "passive_buy", "passive_sell"):
            item = out[key]
            for field in ("amount_bins", "lots_bins"):
                self.assertEqual(sum(c["count"] for c in item[field]), item["count"])
                self.assertEqual(sum(c["amount"] for c in item[field]), item["amount"])
                self.assertEqual(
                    sum(c["volume_lots"] for c in item[field]), item["volume_lots"]
                )

    def test_quadrant_count_sums_to_total(self) -> None:
        out = aggregate_big_deals(_deals(), min_amount=0, bin_by="amount")
        total = sum(out[key]["count"] for key in ("active_buy", "active_sell", "passive_buy", "passive_sell"))
        self.assertEqual(total, out["total_count"])

    def test_bin_by_switches_fields(self) -> None:
        amount_only = aggregate_big_deals(_deals(), min_amount=0, bin_by="amount")
        self.assertIn("amount_bins", amount_only["active_buy"])
        self.assertNotIn("lots_bins", amount_only["active_buy"])

        lots_only = aggregate_big_deals(_deals(), min_amount=0, bin_by="lots")
        self.assertNotIn("amount_bins", lots_only["active_buy"])
        self.assertIn("lots_bins", lots_only["active_buy"])

    def test_min_amount_filters_samples(self) -> None:
        out = aggregate_big_deals(_deals(), min_amount=2_000_000, bin_by="amount")
        self.assertEqual(out["total_count"], 1)
        self.assertEqual(out["active_buy"]["count"], 1)
        self.assertEqual(out["sell"]["count"], 0)
        self.assertEqual(len(out["active_buy"]["amount_bins"]), 5)

    def test_unclassified_rows_are_ignored(self) -> None:
        rows = _deals() + [{"amount": 9_000_000, "volume_lots": 900}]
        out = aggregate_big_deals(rows, min_amount=0, bin_by="amount")
        self.assertEqual(out["total_count"], 5)

    def test_lots_fallback_from_volume(self) -> None:
        rows = [{"side": "buy", "aggressor": "active", "amount": 1_000_000, "volume": 5_000}]
        out = aggregate_big_deals(rows, min_amount=0, bin_by="lots")
        self.assertEqual(out["active_buy"]["volume_lots"], 50)
        self.assertEqual(len(out["active_buy"]["lots_bins"]), 1)

    def test_no_samples_gives_empty_bins(self) -> None:
        out = aggregate_big_deals([], min_amount=0, bin_by="both")
        self.assertEqual(out["total_count"], 0)
        self.assertEqual(out["active_buy"]["amount_bins"], [])
        self.assertEqual(out["active_buy"]["lots_bins"], [])
        self.assertEqual(out["net_amount"], 0)


if __name__ == "__main__":
    unittest.main()