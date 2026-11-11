"""最新收盘 / 最低价「最近最低」回溯纯函数单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.line.local_extrema.recent_low import compute_recent_low


def _bar(date: str, close: float, low: float) -> dict:
    return {
        "time": date,
        "open": close,
        "close": close,
        "high": close,
        "low": low,
    }


class ComputeRecentLowTests(unittest.TestCase):
    def test_basic_days(self) -> None:
        # close: 10, 11, 12, 11.5 → 最新 11.5 是最近 2 日最低（11.5、12）
        # low:   9,  10, 11, 10.8 → 最新 10.8 是最近 2 日最低
        bars = [
            _bar("2026-01-05", 10.0, 9.0),
            _bar("2026-01-06", 11.0, 10.0),
            _bar("2026-01-07", 12.0, 11.0),
            _bar("2026-01-08", 11.5, 10.8),
        ]
        out = compute_recent_low(bars)
        self.assertEqual(out["date"], "2026-01-08")
        self.assertEqual(out["lookback"]["close"]["days"], 2)
        self.assertEqual(out["lookback"]["close"]["since"], "2026-01-07")
        self.assertEqual(out["lookback"]["close"]["prior_lower_date"], "2026-01-06")
        self.assertAlmostEqual(out["lookback"]["close"]["prior_lower_price"], 11.0)
        self.assertFalse(out["lookback"]["close"]["is_all_time_low"])

        self.assertEqual(out["lookback"]["low"]["days"], 2)
        self.assertEqual(out["lookback"]["low"]["since"], "2026-01-07")
        self.assertEqual(out["lookback"]["low"]["prior_lower_date"], "2026-01-06")

    def test_equal_prices_count(self) -> None:
        # 相等仍计入：10, 11, 10 → 最新收盘 10 是全部 3 日最低（无严格更低）
        bars = [
            _bar("2026-01-05", 10.0, 9.5),
            _bar("2026-01-06", 11.0, 10.0),
            _bar("2026-01-07", 10.0, 9.8),
        ]
        out = compute_recent_low(bars)
        self.assertEqual(out["lookback"]["close"]["days"], 3)
        self.assertTrue(out["lookback"]["close"]["is_all_time_low"])
        self.assertIsNone(out["lookback"]["close"]["prior_lower_date"])
        # low 9.8：往前 10.0、9.5 → 遇 9.5 停 → 最近 2 日
        self.assertEqual(out["lookback"]["low"]["days"], 2)
        self.assertEqual(out["lookback"]["low"]["prior_lower_date"], "2026-01-05")

    def test_all_time_low(self) -> None:
        bars = [
            _bar("2026-01-05", 12.0, 11.0),
            _bar("2026-01-06", 11.0, 10.5),
            _bar("2026-01-07", 10.0, 9.0),
        ]
        out = compute_recent_low(bars)
        self.assertEqual(out["lookback"]["close"]["days"], 3)
        self.assertTrue(out["lookback"]["close"]["is_all_time_low"])
        self.assertEqual(out["lookback"]["low"]["days"], 3)
        self.assertTrue(out["lookback"]["low"]["is_all_time_low"])

    def test_single_bar(self) -> None:
        out = compute_recent_low([_bar("2026-01-05", 10.0, 9.0)])
        self.assertEqual(out["lookback"]["close"]["days"], 1)
        self.assertEqual(out["lookback"]["low"]["days"], 1)
        self.assertTrue(out["lookback"]["close"]["is_all_time_low"])

    def test_yesterday_lower(self) -> None:
        # 昨日更低 → 最新只是 1 个交易日的最低
        bars = [
            _bar("2026-01-05", 10.0, 9.0),
            _bar("2026-01-06", 11.0, 10.0),
        ]
        out = compute_recent_low(bars)
        self.assertEqual(out["lookback"]["close"]["days"], 1)
        self.assertEqual(out["lookback"]["low"]["days"], 1)
        self.assertEqual(out["lookback"]["close"]["prior_lower_date"], "2026-01-05")

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_recent_low([])


if __name__ == "__main__":
    unittest.main()
