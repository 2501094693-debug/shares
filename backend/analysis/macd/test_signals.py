"""MACD 金叉 / 即将金叉纯函数单测。"""

from __future__ import annotations

import unittest

from analysis.macd.signals import (
    SIGNAL_OVER_CROSS,
    SIGNAL_OVER_NEAR,
    SIGNAL_UNDER_CROSS,
    SIGNAL_UNDER_NEAR,
    classify_macd_cross,
    gap_velocity,
    relative_gap,
)


def _row(date: str, dif: float, dea: float) -> dict:
    return {"date": date, "dif": dif, "dea": dea, "macd": 2 * (dif - dea)}


class RelativeGapTests(unittest.TestCase):
    def test_basic(self) -> None:
        # (DEA-DIF)/|DEA| = ( -1 - (-1.05) ) / 1 = 0.05
        self.assertAlmostEqual(relative_gap(-1.05, -1.0), 0.05, places=6)


class GapVelocityTests(unittest.TestCase):
    def test_velocity(self) -> None:
        # 缺口 0.20 → 0.05，速度 0.15
        gap_t, gap_prev, velocity = gap_velocity(-1.05, -1.0, -1.20, -1.0)
        self.assertAlmostEqual(gap_t, 0.05, places=6)
        self.assertAlmostEqual(gap_prev, 0.20, places=6)
        self.assertAlmostEqual(velocity, 0.15, places=6)


class ClassifyMacdCrossTests(unittest.TestCase):
    def test_under_cross(self) -> None:
        items = [
            _row("2026-01-08", -1.2, -1.0),
            _row("2026-01-09", -0.9, -1.0),
        ]
        out = classify_macd_cross(items)
        self.assertTrue(out["matched"])
        self.assertEqual(out["primary"], SIGNAL_UNDER_CROSS)
        self.assertTrue(out["underwater"])

    def test_over_cross(self) -> None:
        items = [
            _row("2026-01-08", 0.8, 1.0),
            _row("2026-01-09", 1.1, 1.0),
        ]
        out = classify_macd_cross(items)
        self.assertTrue(out["matched"])
        self.assertEqual(out["primary"], SIGNAL_OVER_CROSS)
        self.assertFalse(out["underwater"])

    def test_under_near(self) -> None:
        # 缺口 0.20 → 0.05：速度外推和相对缺口两种路径都满足
        items = [
            _row("2026-01-08", -1.20, -1.0),
            _row("2026-01-09", -1.05, -1.0),
        ]
        out = classify_macd_cross(items, near_ratio=0.10)
        self.assertTrue(out["matched"])
        self.assertEqual(out["primary"], SIGNAL_UNDER_NEAR)
        self.assertTrue(out["gap_narrowing"])
        self.assertTrue(out["near_by_prediction"])
        self.assertTrue(out["near_by_relative_gap"])
        self.assertAlmostEqual(out["pred_next_gap"], -0.10, places=6)
        self.assertAlmostEqual(out["rel_gap"], 0.05, places=6)

    def test_over_near(self) -> None:
        # 水上同样两种任一命中
        items = [
            _row("2026-01-08", 0.80, 1.0),
            _row("2026-01-09", 0.95, 1.0),
        ]
        out = classify_macd_cross(items, near_ratio=0.10)
        self.assertTrue(out["matched"])
        self.assertEqual(out["primary"], SIGNAL_OVER_NEAR)
        self.assertTrue(out["near_by_prediction"])
        self.assertTrue(out["near_by_relative_gap"])

    def test_near_rejected_when_gap_wide(self) -> None:
        # 缺口 0.50 → 0.30：预测下日 0.10，相对缺口 0.30，两条都不满足
        items = [
            _row("2026-01-08", -1.50, -1.0),
            _row("2026-01-09", -1.30, -1.0),
        ]
        out = classify_macd_cross(items, near_ratio=0.10)
        self.assertFalse(out["matched"])
        self.assertFalse(out["near_by_prediction"])
        self.assertFalse(out["near_by_relative_gap"])

    def test_near_rejected_when_narrowing_too_slow(self) -> None:
        # 缺口 0.12 → 0.11：预测下日 0.10，相对缺口 0.11 > 0.10，两条都不满足
        items = [
            _row("2026-01-08", -1.12, -1.0),
            _row("2026-01-09", -1.11, -1.0),
        ]
        out = classify_macd_cross(items, near_ratio=0.10)
        self.assertFalse(out["matched"])
        self.assertAlmostEqual(out["rel_gap"], 0.11, places=6)
        self.assertAlmostEqual(out["pred_next_gap"], 0.10, places=6)
        self.assertFalse(out["near_by_prediction"])
        self.assertFalse(out["near_by_relative_gap"])

    def test_near_accepted_by_relative_gap_alone(self) -> None:
        # 缺口 0.11 → 0.10：速度不足以预测下日金叉，但相对缺口 0.10 达标
        items = [
            _row("2026-01-08", -1.11, -1.0),
            _row("2026-01-09", -1.10, -1.0),
        ]
        out = classify_macd_cross(items, near_ratio=0.10)
        self.assertTrue(out["matched"])
        self.assertEqual(out["primary"], SIGNAL_UNDER_NEAR)
        self.assertFalse(out["near_by_prediction"])
        self.assertTrue(out["near_by_relative_gap"])
        self.assertAlmostEqual(out["pred_next_gap"], 0.09, places=6)

    def test_near_accepted_when_prediction_crosses_despite_wide_rel_gap(self) -> None:
        # 相对缺口 0.20 > 0.10，但速度足够：0.50 → 0.20，预测下日 -0.10
        items = [
            _row("2026-01-08", -1.50, -1.0),
            _row("2026-01-09", -1.20, -1.0),
        ]
        out = classify_macd_cross(items, near_ratio=0.10)
        self.assertTrue(out["matched"])
        self.assertEqual(out["primary"], SIGNAL_UNDER_NEAR)
        self.assertGreater(out["rel_gap"], 0.10)
        self.assertTrue(out["near_by_prediction"])
        self.assertFalse(out["near_by_relative_gap"])

    def test_near_rejected_when_widening(self) -> None:
        # 相对缺口 0.20 ≤ 0.30，但缺口在扩大，仍不命中
        items = [
            _row("2026-01-08", -1.05, -1.0),
            _row("2026-01-09", -1.20, -1.0),
        ]
        out = classify_macd_cross(items, near_ratio=0.30)
        self.assertFalse(out["matched"])
        self.assertTrue(out["near_by_relative_gap"])
        self.assertFalse(out["gap_narrowing"])

    def test_need_two_bars(self) -> None:
        out = classify_macd_cross([_row("2026-01-09", -0.9, -1.0)])
        self.assertFalse(out["matched"])


if __name__ == "__main__":
    unittest.main()
