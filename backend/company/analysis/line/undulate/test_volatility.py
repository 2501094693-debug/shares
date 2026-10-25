"""四价涨跌幅统计量纯函数单测（无网络）。"""

from __future__ import annotations

import math
import unittest

from company.analysis.line.undulate.stats import compute_stats, summarize_factors
from company.analysis.line.undulate.volatility import (
    _norm_index_code,
    analyze_volatility,
    compute_volatility,
)


def _bar(date: str, o: float, c: float, h: float, low: float) -> dict:
    return {"time": date, "open": o, "close": c, "high": h, "low": low}


class ComputeStatsTests(unittest.TestCase):
    def test_basic(self) -> None:
        out = compute_stats([0.01, 0.02, 0.03])
        self.assertEqual(out["count"], 3)
        self.assertAlmostEqual(out["min"], 0.01)
        self.assertAlmostEqual(out["max"], 0.03)
        self.assertAlmostEqual(out["range"], 0.02)
        self.assertAlmostEqual(out["mean"], 0.02)
        # 样本标准差：sqrt(0.0002/2)
        self.assertAlmostEqual(out["std"], math.sqrt(0.0001))

    def test_single_sample(self) -> None:
        out = compute_stats([0.05])
        self.assertEqual(out["count"], 1)
        self.assertAlmostEqual(out["std"], 0.0)
        self.assertAlmostEqual(out["range"], 0.0)

    def test_skips_none_and_empty(self) -> None:
        self.assertIsNone(compute_stats([None, None])["mean"])
        out = compute_stats([None, -0.02, None, 0.04])
        self.assertEqual(out["count"], 2)
        self.assertAlmostEqual(out["mean"], 0.01)

    def test_summarize_factors(self) -> None:
        out = summarize_factors({"open": [0.01, -0.01], "close": [0.02]})
        self.assertAlmostEqual(out["open"]["min"], -0.01)
        self.assertAlmostEqual(out["close"]["std"], 0.0)


class ComputeVolatilityTests(unittest.TestCase):
    def setUp(self) -> None:
        # 基准 = 2026-01-05 收盘 10.0
        self.bars = [
            _bar("2026-01-05", 9.8, 10.0, 10.2, 9.7),
            _bar("2026-01-06", 10.2, 10.5, 10.6, 10.1),
            _bar("2026-01-07", 10.4, 9.8, 10.5, 9.6),
        ]

    def test_base_is_prior_trading_day_close(self) -> None:
        out = compute_volatility(self.bars, "2026-01-06")
        self.assertEqual(out["base"]["date"], "2026-01-05")
        self.assertAlmostEqual(out["base"]["close"], 10.0)
        self.assertEqual(out["count"], 2)

    def test_pct_series_per_factor(self) -> None:
        out = compute_volatility(self.bars, "2026-01-06")
        open_stats = out["stats"]["open"]
        self.assertEqual(open_stats["count"], 2)
        # 开盘：10.2/10-1 = +2%，10.4/10-1 = +4%
        self.assertAlmostEqual(open_stats["min"], 0.02)
        self.assertAlmostEqual(open_stats["max"], 0.04)
        self.assertAlmostEqual(open_stats["mean"], 0.03)
        self.assertAlmostEqual(open_stats["range"], 0.02)
        self.assertEqual(
            [pt["date"] for pt in out["series"]["open"]],
            ["2026-01-06", "2026-01-07"],
        )

    def test_close_negative_swing(self) -> None:
        out = compute_volatility(self.bars, "2026-01-06")
        close = out["stats"]["close"]
        # 收盘：10.5/10-1 = +5%，9.8/10-1 = -2%
        self.assertAlmostEqual(close["max"], 0.05)
        self.assertAlmostEqual(close["min"], -0.02)
        self.assertEqual(close["max_date"], "2026-01-06")
        self.assertEqual(close["min_date"], "2026-01-07")
        self.assertAlmostEqual(close["mean"], 0.015)

    def test_end_slices_range(self) -> None:
        out = compute_volatility(self.bars, "2026-01-06", "2026-01-06")
        self.assertEqual(out["count"], 1)
        self.assertAlmostEqual(out["stats"]["close"]["std"], 0.0)

    def test_end_z_position(self) -> None:
        # 区间 2026-01-06 ~ 2026-01-07，结束日 = 2026-01-07
        out = compute_volatility(self.bars, "2026-01-06")
        close = out["stats"]["close"]
        self.assertEqual(close["end_date"], "2026-01-07")
        # 收盘涨跌幅样本：+5% 与 -2%
        self.assertAlmostEqual(close["end_pct"], -0.02)
        # z 由已四舍五入的 mean / std 归一化得到
        expected_z = (close["end_pct"] - close["mean"]) / close["std"]
        self.assertAlmostEqual(close["end_z"], round(expected_z, 6))

    def test_end_z_single_sample_is_none(self) -> None:
        out = compute_volatility(self.bars, "2026-01-06", "2026-01-06")
        # 仅一个样本时 std=0，无法标准化，z 记为 None
        self.assertIsNone(out["stats"]["close"]["end_z"])
        self.assertAlmostEqual(out["stats"]["close"]["end_pct"], 0.05)

    def test_missing_base_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_volatility(self.bars, "2026-01-05")

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_volatility([], "2026-01-06")


class IndexKindHelpersTests(unittest.TestCase):
    def test_norm_index_code(self) -> None:
        self.assertEqual(_norm_index_code("000001"), "000001")
        self.assertEqual(_norm_index_code("1.000001"), "000001")
        self.assertEqual(_norm_index_code("sh000300"), "000300")

    def test_kind_must_be_stock_or_index(self) -> None:
        with self.assertRaises(ValueError):
            analyze_volatility("000001", "2026-01-06", kind="foo")


if __name__ == "__main__":
    unittest.main()
