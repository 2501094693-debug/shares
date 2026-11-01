"""方向分类与指数码解析单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.line.compare.codes import normalize_index_code, resolve_indices
from company.analysis.line.compare.score import classify_dir, pair_row
from company.analysis.line.compare.series import factors_of


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


if __name__ == "__main__":
    unittest.main()
