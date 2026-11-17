"""筹码 V2 双池引擎单测（无网络）。"""

from __future__ import annotations

import unittest

import numpy as np

from company.analysis.line.chip.v2_core import (
    intraday_volume_hist,
    make_grid_range,
    normalize_decay_mode,
    run_chip_v2,
    split_volume,
    take_from_known,
)
from company.analysis.line.chip.v2_service import to_payload_v2


def _minute(price: float, lots: float) -> dict:
    return {"price": price, "volume": lots, "volume_lots": lots}


def _day(date: str, close: float, low: float | None = None, high: float | None = None) -> dict:
    lo = low if low is not None else close - 1.0
    hi = high if high is not None else close + 1.0
    return {
        "date": date,
        "open": close,
        "high": hi,
        "low": lo,
        "close": close,
        "volume": 1e6,
        "turnover": 1.0,
    }


class NormalizeModeTests(unittest.TestCase):
    def test_aliases(self) -> None:
        self.assertEqual(normalize_decay_mode("获利优先"), "profit")
        self.assertEqual(normalize_decay_mode("割肉"), "cut")
        self.assertEqual(normalize_decay_mode("even"), "uniform")


class SplitVolumeTests(unittest.TestCase):
    def test_k_zero_all_from_u(self) -> None:
        v_u, v_k = split_volume(100.0, unknown=1000.0, known=0.0)
        self.assertAlmostEqual(v_u, 100.0)
        self.assertAlmostEqual(v_k, 0.0)

    def test_proportional(self) -> None:
        v_u, v_k = split_volume(100.0, unknown=750.0, known=250.0)
        self.assertAlmostEqual(v_u, 75.0)
        self.assertAlmostEqual(v_k, 25.0)

    def test_clamp_to_pool(self) -> None:
        v_u, v_k = split_volume(9999.0, unknown=80.0, known=20.0)
        self.assertAlmostEqual(v_u + v_k, 100.0)


class HistAndTakeTests(unittest.TestCase):
    def test_intraday_hist(self) -> None:
        edges, _ = make_grid_range(9.0, 11.0, bins=20)
        hist = intraday_volume_hist(
            [_minute(10.0, 10), _minute(10.0, 5)],
            edges,
        )
        self.assertAlmostEqual(float(hist.sum()), 15 * 100)

    def test_hist_empty_raises(self) -> None:
        edges, _ = make_grid_range(9.0, 11.0, bins=20)
        with self.assertRaises(ValueError):
            intraday_volume_hist([], edges)

    def test_take_profit_prefers_below_close(self) -> None:
        centers = np.array([8.0, 9.0, 10.0, 11.0, 12.0])
        chips = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
        out = take_from_known(chips, centers, close=10.0, volume=150.0, mode="profit")
        # 获利侧 8、9（及可能中性 10）优先被扣；11、12 应尽量保留
        self.assertLess(float(out[0] + out[1]), 200.0)
        self.assertAlmostEqual(float(out.sum()), 350.0, places=5)
        self.assertGreaterEqual(float(out[3] + out[4]), 199.0)

    def test_take_cut_prefers_above_close(self) -> None:
        centers = np.array([8.0, 9.0, 10.0, 11.0, 12.0])
        chips = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
        out = take_from_known(chips, centers, close=10.0, volume=150.0, mode="cut")
        self.assertAlmostEqual(float(out.sum()), 350.0, places=5)
        self.assertGreaterEqual(float(out[0] + out[1]), 199.0)

    def test_take_uniform(self) -> None:
        centers = np.array([8.0, 9.0, 10.0])
        chips = np.array([100.0, 100.0, 100.0])
        out = take_from_known(chips, centers, close=9.0, volume=30.0, mode="uniform")
        self.assertTrue(np.allclose(out, np.array([90.0, 90.0, 90.0])))


class RunChipV2Tests(unittest.TestCase):
    def test_day1_all_from_unknown_conserves(self) -> None:
        rows = [_day("2024-01-02", 10.0)]
        trends = {
            "2024-01-02": [_minute(10.0, 100)],  # 100 手 = 10000 股
        }
        float_n = 1_000_000.0
        out = run_chip_v2(
            rows,
            trends,
            float_shares=float_n,
            bins=40,
            decay_mode="uniform",
        )
        self.assertAlmostEqual(out["unknown_shares"] + out["known_shares"], float_n, places=3)
        self.assertAlmostEqual(out["known_shares"], 10_000.0, places=3)
        self.assertAlmostEqual(out["unknown_shares"], float_n - 10_000.0, places=3)
        self.assertEqual(len(out["history"]), 1)
        self.assertAlmostEqual(out["history"][0]["volume_from_unknown"], 10_000.0, places=3)
        self.assertAlmostEqual(out["history"][0]["volume_from_known"], 0.0, places=3)

    def test_day2_proportional_split(self) -> None:
        rows = [
            _day("2024-01-02", 10.0),
            _day("2024-01-03", 11.0, low=9.0, high=12.0),
        ]
        # 日1: 10000 股；日2: 20000 股
        trends = {
            "2024-01-02": [_minute(10.0, 100)],
            "2024-01-03": [_minute(11.0, 200)],
        }
        float_n = 1_000_000.0
        out = run_chip_v2(rows, trends, float_shares=float_n, bins=50, decay_mode="uniform")
        # 日2 前：U=990000, K=10000 → V_u=19800, V_k=200
        h2 = out["history"][1]
        self.assertAlmostEqual(h2["volume"], 20_000.0, places=3)
        self.assertAlmostEqual(h2["volume_from_unknown"], 19_800.0, places=1)
        self.assertAlmostEqual(h2["volume_from_known"], 200.0, places=1)
        self.assertAlmostEqual(out["unknown_shares"] + out["known_shares"], float_n, places=2)

    def test_missing_intraday_raises(self) -> None:
        rows = [_day("2024-01-02", 10.0)]
        with self.assertRaises(ValueError) as ctx:
            run_chip_v2(rows, {}, float_shares=1e6, bins=40)
        self.assertIn("2024-01-02", str(ctx.exception))

    def test_payload_only_known(self) -> None:
        rows = [_day("2024-01-02", 10.0)]
        trends = {"2024-01-02": [_minute(10.0, 50)]}
        out = run_chip_v2(rows, trends, float_shares=500_000.0, bins=30)
        out.update(symbol="600519", name="测试", beg="2024-01-02", end="2024-01-02")
        payload = to_payload_v2(out)
        self.assertIn("unknown_shares", payload)
        self.assertIn("chips_shares", payload)
        self.assertAlmostEqual(sum(payload["chips"]), 1.0, places=6)
        self.assertEqual(payload["meta"]["pool"], "dual")
        self.assertEqual(payload["meta"]["inject"], "intraday")


if __name__ == "__main__":
    unittest.main()
