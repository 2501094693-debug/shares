"""方向分类与指数码解析单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.line.compare.codes import normalize_index_code, resolve_indices
from company.analysis.line.compare.score import (
    classify_dir,
    pair_row,
    score_divergence,
)
from company.analysis.line.compare.series import factors_of
from company.analysis.line.compare.service import compare_divergence, compare_from_bars


class ClassifyDirTests(unittest.TestCase):
    def test_same_up(self) -> None:
        self.assertEqual(classify_dir(0.01, 0.005), "同涨")

    def test_same_down(self) -> None:
        self.assertEqual(classify_dir(-0.01, -0.005), "同跌")

    def test_stock_up_index_down(self) -> None:
        self.assertEqual(classify_dir(0.01, -0.005), "股涨指跌")
        self.assertEqual(classify_dir(0.01, 0.0), "股涨指跌")

    def test_stock_down_index_up(self) -> None:
        self.assertEqual(classify_dir(-0.01, 0.005), "股跌指涨")
        self.assertEqual(classify_dir(-0.01, 0.0), "股跌指涨")

    def test_pair_row(self) -> None:
        row = pair_row(0.02, 0.01)
        self.assertEqual(row["dir"], "同涨")
        self.assertAlmostEqual(row["dif"], 0.01)
        self.assertNotIn("zdif", row)
        self.assertNotIn("sigma_s", row)


class CodesTests(unittest.TestCase):
    def test_normalize_name(self) -> None:
        self.assertEqual(normalize_index_code("沪深300"), "000300")
        self.assertEqual(normalize_index_code("SH000905"), "000905")
        self.assertEqual(normalize_index_code("1.000852"), "000852")

    def test_resolve_default(self) -> None:
        items = resolve_indices(None)
        self.assertEqual(len(items), 5)
        self.assertEqual(items[0]["code"], "000001")

    def test_resolve_subset(self) -> None:
        items = resolve_indices("沪深300,中证1000")
        self.assertEqual([i["code"] for i in items], ["000300", "000852"])


class FactorsTests(unittest.TestCase):
    def test_factors_of(self) -> None:
        bars = [
            {"time": "2026-01-01", "open": 10, "high": 11, "low": 9, "close": 10},
            {"time": "2026-01-02", "open": 10.5, "high": 11, "low": 9.5, "close": 10.2},
        ]
        fac = factors_of(bars)
        self.assertIn("2026-01-02", fac)
        row = fac["2026-01-02"]
        self.assertAlmostEqual(row["open"], 0.05)
        self.assertAlmostEqual(row["high"], 0.10)
        self.assertAlmostEqual(row["low"], -0.05)
        self.assertAlmostEqual(row["close"], 0.02)
        self.assertNotIn("2026-01-01", fac)


class ScoreDivergenceTests(unittest.TestCase):
    def test_all_same_is_zero(self) -> None:
        rows = [pair_row(0.01, 0.005), pair_row(-0.01, -0.002)]
        out = score_divergence(rows)
        self.assertEqual(out["score"], 0.0)
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["reverse_count"], 0)

    def test_all_reverse_is_hundred(self) -> None:
        rows = [pair_row(0.01, -0.005), pair_row(-0.01, 0.002)]
        out = score_divergence(rows)
        self.assertEqual(out["score"], 100.0)
        self.assertEqual(out["reverse_count"], 2)
        self.assertEqual(out["dirs"]["stock_up_index_down"], 1)
        self.assertEqual(out["dirs"]["stock_down_index_up"], 1)

    def test_mixed_ratio(self) -> None:
        rows = [
            pair_row(0.01, 0.005),   # 同涨
            pair_row(0.01, -0.005),  # 反向
            pair_row(-0.01, -0.002), # 同跌
            pair_row(-0.01, 0.002),  # 反向
        ]
        out = score_divergence(rows)
        self.assertEqual(out["count"], 4)
        self.assertEqual(out["reverse_count"], 2)
        self.assertEqual(out["score"], 50.0)

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            score_divergence([])


class CompareFromBarsTests(unittest.TestCase):
    def test_divergence_reuses_bars(self) -> None:
        stock_bars = [
            {"time": "2026-01-01", "open": 10, "high": 10, "low": 10, "close": 10},
            {"time": "2026-01-02", "open": 11, "high": 11, "low": 11, "close": 11},
            {"time": "2026-01-03", "open": 10, "high": 10, "low": 10, "close": 10},
        ]
        index_bars = [
            {"time": "2026-01-01", "open": 100, "high": 100, "low": 100, "close": 100},
            {"time": "2026-01-02", "open": 99, "high": 99, "low": 99, "close": 99},
            {"time": "2026-01-03", "open": 101, "high": 101, "low": 101, "close": 101},
        ]
        pack = compare_from_bars(
            "600519",
            "000001",
            beg="2026-01-02",
            end="2026-01-03",
            stock_bars=stock_bars,
            index_bars=index_bars,
            stock_name="测试",
            index_name="上证指数",
        )
        self.assertEqual(pack["dates"], ["2026-01-02", "2026-01-03"])
        out = compare_divergence(
            "600519",
            "000001",
            beg="2026-01-02",
            end="2026-01-03",
            factor="close",
            stock_bars=stock_bars,
            index_bars=index_bars,
            stock_name="测试",
            index_name="上证指数",
        )
        # 01-02 股涨指跌、01-03 股跌指涨 → 100
        self.assertEqual(out["score"], 100.0)
        self.assertEqual(out["reverse_count"], 2)


if __name__ == "__main__":
    unittest.main()
