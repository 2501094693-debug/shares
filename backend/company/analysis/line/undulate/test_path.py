"""S0/U/S1 九格走势判定单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.line.undulate.path import (
    classify_path,
    path_from_stats,
)
from company.analysis.line.undulate.volatility import compute_volatility


def _bar(date: str, o: float, c: float, h: float, low: float) -> dict:
    return {"time": date, "open": o, "close": c, "high": h, "low": low}


class ClassifyPathTests(unittest.TestCase):
    def test_nine_cells_eps_zero(self) -> None:
        cases = [
            (-1.0, 0.0, 1.0, "上行"),       # < <
            (-1.0, 0.0, 0.0, "上行"),       # < =
            (-1.0, 1.0, 0.0, "冲高回落"),   # < >
            (0.0, 0.0, 1.0, "上行"),        # = <
            (0.0, 0.0, 0.0, "横盘"),        # = =
            (0.0, 0.0, -1.0, "下行"),       # = >
            (1.0, 0.0, 1.0, "探底回升"),    # > <
            (1.0, 0.0, 0.0, "下行"),        # > =
            (1.0, 0.0, -1.0, "下行"),       # > >
        ]
        for s0, u, s1, expect in cases:
            with self.subTest(s0=s0, u=u, s1=s1, expect=expect):
                out = classify_path(s0, u, s1, eps=0.0)
                self.assertEqual(out["label"], expect)

    def test_eps_collapses_to_sideways(self) -> None:
        # |差|<=0.1 视为相等 → 两等号横盘
        out = classify_path(0.05, 0.0, -0.05, eps=0.1)
        self.assertEqual(out["label"], "横盘")
        self.assertEqual(out["left"], "=")
        self.assertEqual(out["right"], "=")

    def test_eps_one_equality_follows_other(self) -> None:
        # S0≈U，U < S1 → 上行
        out = classify_path(0.05, 0.0, 1.0, eps=0.1)
        self.assertEqual(out["label"], "上行")
        self.assertEqual(out["left"], "=")
        self.assertEqual(out["right"], "<")

        # S0≈U，U > S1 → 下行
        out = classify_path(-0.05, 0.0, -1.0, eps=0.1)
        self.assertEqual(out["label"], "下行")
        self.assertEqual(out["right"], ">")

    def test_missing_is_unknown(self) -> None:
        out = classify_path(None, 0.0, 1.0, eps=0.1)
        self.assertEqual(out["label"], "unknown")

    def test_negative_eps_raises(self) -> None:
        with self.assertRaises(ValueError):
            classify_path(0.0, 0.0, 0.0, eps=-0.01)


class PathFromStatsTests(unittest.TestCase):
    def test_from_sigma_fields(self) -> None:
        row = {
            "mean": 0.02,
            "std": 0.01,
            "beg_sigma": -1.0,
            "end_sigma": 2.0,
        }
        # U = 0.02/0.01 = 2；S0=-1 < U=2 < S1=2 → 一等号上行
        out = path_from_stats(row, eps=0.0)
        self.assertEqual(out["label"], "上行")
        self.assertAlmostEqual(out["U"], 2.0)

    def test_std_zero_unknown(self) -> None:
        out = path_from_stats({"mean": 0.01, "std": 0.0, "beg_sigma": 1.0})
        self.assertEqual(out["label"], "unknown")


class ComputeVolatilityPathTests(unittest.TestCase):
    def test_path_attached(self) -> None:
        # 基准日 01-05 close=100；区间三天 close 抬升
        bars = [
            _bar("2026-01-05", 100, 100, 100, 100),
            _bar("2026-01-06", 101, 101, 102, 100),
            _bar("2026-01-07", 102, 103, 104, 101),
            _bar("2026-01-08", 104, 105, 106, 103),
        ]
        out = compute_volatility(bars, "2026-01-06", "2026-01-08", path_eps=0.0)
        close = out["stats"]["close"]
        self.assertIn("path", close)
        self.assertIn(close["path"]["label"], {
            "上行", "下行", "冲高回落", "探底回升", "横盘", "unknown",
        })
        self.assertIsNotNone(close["path"]["S0"])
        self.assertIsNotNone(close["path"]["U"])
        self.assertIsNotNone(close["path"]["S1"])


if __name__ == "__main__":
    unittest.main()
