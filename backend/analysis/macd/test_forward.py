"""事后最大涨幅纯函数单测。"""

from __future__ import annotations

import unittest

from analysis.macd.forward import max_forward_gains_from_bars


def _bar(date: str, *, o: float, h: float, l: float, c: float) -> dict:
    return {"time": date, "open": o, "high": h, "low": l, "close": c}


class MaxForwardGainsTests(unittest.TestCase):
    def test_basic(self) -> None:
        bars = [
            _bar("2026-01-08", o=10, h=10.5, l=9.8, c=10.0),
            _bar("2026-01-09", o=10.1, h=11.0, l=10.0, c=10.5),  # signal
            _bar("2026-01-10", o=10.6, h=12.0, l=10.4, c=11.5),
            _bar("2026-01-13", o=11.2, h=11.8, l=10.9, c=11.0),
        ]
        out = max_forward_gains_from_bars(bars, signal_date="2026-01-09")
        self.assertEqual(out["base_close"], 10.5)
        self.assertEqual(out["hold_days"], 3)
        # max close = 11.5 → 11.5/10.5 - 1
        self.assertAlmostEqual(out["max_close_gain"], 11.5 / 10.5 - 1.0, places=6)
        self.assertEqual(out["max_close_date"], "2026-01-10")
        # 区间内收盘最低相对基准：信号日自身 0（11.0、11.5 均高于基）
        self.assertAlmostEqual(out["max_close_drop"], 0.0, places=6)
        self.assertEqual(out["max_close_drop_date"], "2026-01-09")
        # max high = 12.0
        self.assertAlmostEqual(out["max_high_gain"], 12.0 / 10.5 - 1.0, places=6)
        self.assertEqual(out["max_high_date"], "2026-01-10")

    def test_max_close_drop(self) -> None:
        bars = [
            _bar("2026-01-09", o=10, h=10.5, l=9.5, c=10.0),  # signal
            _bar("2026-01-10", o=10, h=11.0, l=8.0, c=8.5),
            _bar("2026-01-13", o=8.5, h=12.0, l=8.4, c=11.5),
        ]
        out = max_forward_gains_from_bars(bars, signal_date="2026-01-09")
        self.assertAlmostEqual(out["max_close_gain"], 0.15, places=6)
        self.assertEqual(out["max_close_date"], "2026-01-13")
        self.assertAlmostEqual(out["max_close_drop"], -0.15, places=6)
        self.assertEqual(out["max_close_drop_date"], "2026-01-10")
        self.assertEqual(out["max_close_drop_price"], 8.5)

    def test_missing_signal_day(self) -> None:
        bars = [_bar("2026-01-10", o=10, h=11, l=9, c=10.5)]
        out = max_forward_gains_from_bars(bars, signal_date="2026-01-09")
        self.assertIsNone(out["max_close_gain"])
        self.assertIsNone(out["max_close_drop"])
        self.assertEqual(out["hold_days"], 0)

    def test_asof_clips(self) -> None:
        bars = [
            _bar("2026-01-09", o=10, h=10.2, l=9.9, c=10.0),
            _bar("2026-01-10", o=10, h=13.0, l=10, c=12.0),
            _bar("2026-01-13", o=12, h=15.0, l=12, c=14.0),
        ]
        out = max_forward_gains_from_bars(
            bars, signal_date="2026-01-09", asof="2026-01-10"
        )
        self.assertEqual(out["hold_days"], 2)
        self.assertAlmostEqual(out["max_close_gain"], 0.2, places=6)
        self.assertAlmostEqual(out["max_close_drop"], 0.0, places=6)
        self.assertAlmostEqual(out["max_high_gain"], 0.3, places=6)


if __name__ == "__main__":
    unittest.main()
