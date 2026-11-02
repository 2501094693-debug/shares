"""相对强弱分纯函数单测（无网络）。"""

from __future__ import annotations

import math
import unittest

from company.analysis.line.evaluate.strength import (
    score_strength,
    strength_from_pct,
)


class ScoreStrengthTests(unittest.TestCase):
    def test_positive_when_a_ahead(self) -> None:
        # 价差稳定为正 → A 强
        out = score_strength([0.02, 0.025, 0.03, 0.035])
        self.assertGreater(out["strength"], 0)
        self.assertEqual(out["count"], 4)
        self.assertAlmostEqual(out["end"], 0.035)

    def test_negative_when_b_ahead(self) -> None:
        out = score_strength([-0.02, -0.025, -0.03, -0.035])
        self.assertLess(out["strength"], 0)
        self.assertAlmostEqual(
            out["strength"], -score_strength([0.02, 0.025, 0.03, 0.035])["strength"]
        )

    def test_near_zero_when_flat(self) -> None:
        out = score_strength([0.0, 0.0, 0.0, 0.0])
        self.assertEqual(out["strength"], 0.0)
        self.assertEqual(out["z"], 0.0)

    def test_tanh_saturation(self) -> None:
        # 大幅领先且几乎不晃 → |z| 很大 → 接近 ±100
        out = score_strength([0.20, 0.21, 0.22, 0.23])
        self.assertGreater(out["strength"], 95)
        self.assertLessEqual(out["strength"], 100)

    def test_matches_formula(self) -> None:
        spreads = [0.01, 0.02, 0.03]
        out = score_strength(spreads)
        mean = sum(spreads) / 3
        var = sum((x - mean) ** 2 for x in spreads) / 2
        std = math.sqrt(var)
        raw = 0.6 * 0.03 + 0.4 * mean
        z = raw / max(std, 0.01)
        self.assertAlmostEqual(out["raw"], round(raw, 6))
        self.assertAlmostEqual(out["z"], round(z, 6))
        self.assertAlmostEqual(out["strength"], round(100 * math.tanh(z), 2))

    def test_too_few_raises(self) -> None:
        with self.assertRaises(ValueError):
            score_strength([0.01])
        with self.assertRaises(ValueError):
            score_strength([])

    def test_skips_none(self) -> None:
        out = score_strength([0.01, None, 0.02, float("nan"), 0.03])
        self.assertEqual(out["count"], 3)


class StrengthFromPctTests(unittest.TestCase):
    def test_positional_zip(self) -> None:
        out = strength_from_pct([0.05, 0.06, 0.07], [0.01, 0.02, 0.02])
        self.assertGreater(out["strength"], 0)
        self.assertIsNone(out["dates"])
        self.assertEqual(out["count"], 3)

    def test_date_intersection(self) -> None:
        out = strength_from_pct(
            [0.05, 0.08, 0.10],
            [0.01, 0.02],
            dates_a=["2026-01-01", "2026-01-02", "2026-01-03"],
            dates_b=["2026-01-01", "2026-01-03"],
        )
        # 仅 01-01、01-03：价差 0.04、0.08
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["dates"], ["2026-01-01", "2026-01-03"])
        self.assertAlmostEqual(out["end"], 0.08)

    def test_one_sided_dates_raises(self) -> None:
        with self.assertRaises(ValueError):
            strength_from_pct([0.1, 0.2], [0.0, 0.0], dates_a=["a", "b"])

    def test_date_length_mismatch_raises(self) -> None:
        with self.assertRaises(ValueError):
            strength_from_pct(
                [0.1, 0.2],
                [0.0, 0.0],
                dates_a=["2026-01-01"],
                dates_b=["2026-01-01", "2026-01-02"],
            )


if __name__ == "__main__":
    unittest.main()
