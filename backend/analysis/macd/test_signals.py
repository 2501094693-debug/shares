"""MACD 金叉 / 即将金叉纯函数单测。"""

from __future__ import annotations

import unittest

from analysis.macd.signals import (
    SIGNAL_OVER_CROSS,
    SIGNAL_OVER_NEAR,
    SIGNAL_UNDER_CROSS,
    SIGNAL_UNDER_NEAR,
    classify_macd_cross,
    relative_gap,
)


def _row(date: str, dif: float, dea: float) -> dict:
    return {"date": date, "dif": dif, "dea": dea, "macd": 2 * (dif - dea)}


class RelativeGapTests(unittest.TestCase):
    def test_basic(self) -> None:
        # (DEA-DIF)/|DEA| = ( -1 - (-1.05) ) / 1 = 0.05
        self.assertAlmostEqual(relative_gap(-1.05, -1.0), 0.05, places=6)


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
        # 缺口收窄且相对缺口 0.05 ≤ 0.10
        items = [
            _row("2026-01-08", -1.20, -1.0),
            _row("2026-01-09", -1.05, -1.0),
        ]
        out = classify_macd_cross(items, near_ratio=0.10)
        self.assertTrue(out["matched"])
        self.assertEqual(out["primary"], SIGNAL_UNDER_NEAR)
        self.assertTrue(out["gap_narrowing"])
        self.assertAlmostEqual(out["rel_gap"], 0.05, places=6)

    def test_over_near(self) -> None:
        items = [
            _row("2026-01-08", 0.80, 1.0),
            _row("2026-01-09", 0.95, 1.0),
        ]
        out = classify_macd_cross(items, near_ratio=0.10)
        self.assertTrue(out["matched"])
        self.assertEqual(out["primary"], SIGNAL_OVER_NEAR)

    def test_near_rejected_when_gap_wide(self) -> None:
        # 相对缺口 0.30 > 0.10
        items = [
            _row("2026-01-08", -1.50, -1.0),
            _row("2026-01-09", -1.30, -1.0),
        ]
        out = classify_macd_cross(items, near_ratio=0.10)
        self.assertFalse(out["matched"])

    def test_near_rejected_when_widening(self) -> None:
        items = [
            _row("2026-01-08", -1.05, -1.0),
            _row("2026-01-09", -1.20, -1.0),
        ]
        out = classify_macd_cross(items, near_ratio=0.30)
        self.assertFalse(out["matched"])

    def test_need_two_bars(self) -> None:
        out = classify_macd_cross([_row("2026-01-09", -0.9, -1.0)])
        self.assertFalse(out["matched"])


if __name__ == "__main__":
    unittest.main()
