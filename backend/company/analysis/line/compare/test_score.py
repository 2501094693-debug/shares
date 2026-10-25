"""方向分类、波动标准化与指数码解析单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.line.compare.codes import normalize_index_code, resolve_indices
from company.analysis.line.compare.score import (
    classify_dir,
    pair_row,
    range_sigma,
    summarize_all,
    summarize_factor,
)
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

    def test_pair_row_raw(self) -> None:
        row = pair_row(0.02, 0.01)
        self.assertEqual(row["dir"], "同涨")
        self.assertAlmostEqual(row["dif"], 0.01)
        self.assertEqual(row["norm"], "raw")
        self.assertIsNone(row["zdif"])

    def test_pair_row_vol(self) -> None:
        # 股 σ=3%，指 σ=0.8%；同跌 1% → zs≈-0.333, zb≈-1.25, zdif>0 股相对强
        row = pair_row(-0.01, -0.01, sigma_s=0.03, sigma_b=0.008)
        self.assertEqual(row["norm"], "vol")
        self.assertEqual(row["dir"], "同跌")
        self.assertAlmostEqual(row["dif"], 0.0)
        self.assertGreater(row["zdif"], 0.5)


class SummarizeScoreTests(unittest.TestCase):
    def test_raw_signed_stronger(self) -> None:
        pack = summarize_factor([{"dif": 0.01, "dir": "同涨"}])
        self.assertEqual(pack["mode"], "raw")
        self.assertAlmostEqual(pack["score"], 1.0)
        self.assertAlmostEqual(pack["deviation"], 1.0)

    def test_raw_signed_weaker(self) -> None:
        pack = summarize_factor([{"dif": -0.01, "dir": "同跌"}])
        self.assertEqual(pack["mode"], "raw")
        self.assertAlmostEqual(pack["score"], -1.0)
        self.assertAlmostEqual(pack["deviation"], 1.0)

    def test_raw_reverse_weight(self) -> None:
        pack = summarize_factor([{"dif": 0.01, "dir": "股涨指跌"}])
        self.assertAlmostEqual(pack["score"], 1.5)

    def test_vol_same_pct_stock_stronger(self) -> None:
        # 10 日同跌 1%，zdif>0 → 偏强
        rows = [
            {
                "dif": 0.0,
                "zdif": 0.9,
                "dir": "同跌",
                "norm": "vol",
            }
            for _ in range(10)
        ]
        pack = summarize_factor(rows)
        self.assertEqual(pack["mode"], "vol")
        self.assertAlmostEqual(pack["score"], 0.9)
        self.assertEqual(
            summarize_all({"open": rows, "high": rows, "low": rows, "close": rows})[
                "total"
            ]["level"],
            "明显偏强",
        )

    def test_raw_total_level(self) -> None:
        daily = {
            "open": [{"dif": -0.02, "dir": "同跌"}],
            "high": [{"dif": -0.02, "dir": "同跌"}],
            "low": [{"dif": -0.02, "dir": "同跌"}],
            "close": [{"dif": -0.02, "dir": "同跌"}],
        }
        out = summarize_all(daily)
        self.assertEqual(out["mode"], "raw")
        self.assertEqual(out["total"]["level"], "极端偏弱")
        self.assertEqual(out["deviation"]["level"], "极端偏离")


class RangeSigmaTests(unittest.TestCase):
    def test_closed_range(self) -> None:
        fac = {
            "2026-01-01": {"close": 0.01},
            "2026-01-02": {"close": -0.01},
            "2026-01-03": {"close": 0.02},
            "2026-01-04": {"close": -0.02},
        }
        dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
        sig = range_sigma(fac, "close", dates)
        self.assertIsNotNone(sig)
        self.assertGreater(sig, 0)
        # 子集区间 σ 应不同（或至少可单独计算）
        sig2 = range_sigma(fac, "close", dates[:2])
        self.assertIsNotNone(sig2)

    def test_too_short(self) -> None:
        fac = {"2026-01-01": {"close": 0.01}}
        self.assertIsNone(range_sigma(fac, "close", ["2026-01-01"]))


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
