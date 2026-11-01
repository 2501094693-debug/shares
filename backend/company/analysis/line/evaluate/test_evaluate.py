"""区间评估纯函数单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.line.evaluate.core import (
    find_max_range,
    lowest_day,
    score_low_point,
    summarize_sigma,
    window_within,
)
from company.analysis.line.undulate.service import compute_undulate
from company.analysis.line.undulate.volatility import compute_volatility


def _bar(
    date: str,
    close: float,
    *,
    open: float | None = None,
    high: float | None = None,
    low: float | None = None,
    volume: float = 100.0,
) -> dict:
    """四价默认全等于 close，便于只看收盘口径。"""
    return {
        "time": date,
        "open": close if open is None else open,
        "close": close,
        "high": close if high is None else high,
        "low": close if low is None else low,
        "volume": volume,
    }


class FindMaxRangeTests(unittest.TestCase):
    def test_extends_until_first_break(self) -> None:
        # 01-06 相对基准 9.0 跳涨 16.7%，把它纳入窗口即超出 ±9%
        bars = [
            _bar("2026-01-05", 9.0),
            _bar("2026-01-06", 10.5),
            _bar("2026-01-07", 10.6),
            _bar("2026-01-08", 10.4),
            _bar("2026-01-09", 10.5),
        ]
        out = find_max_range(bars, factor="close", band=0.09)
        self.assertTrue(out["found"])
        self.assertEqual(out["window"]["beg"], "2026-01-07")
        self.assertEqual(out["window"]["end"], "2026-01-09")
        self.assertEqual(out["window"]["count"], 3)
        self.assertFalse(out["reached_start"])
        self.assertEqual(out["first_fail"]["beg"], "2026-01-06")

    def test_reached_start_when_no_prior_base(self) -> None:
        # 全程在 ±9% 内，会一路推到数据头部，因首根无基准而停止
        bars = [
            _bar("2026-01-05", 10.0),
            _bar("2026-01-06", 10.2),
            _bar("2026-01-07", 10.1),
            _bar("2026-01-08", 10.3),
            _bar("2026-01-09", 10.2),
        ]
        out = find_max_range(bars, factor="close", band=0.09)
        self.assertTrue(out["found"])
        self.assertTrue(out["reached_start"])
        self.assertEqual(out["window"]["beg"], "2026-01-06")
        self.assertEqual(out["window"]["count"], 4)

    def test_latest_day_fails_returns_not_found(self) -> None:
        # 最新一日相对前收跳涨 20%，单日窗口即不满足
        bars = [
            _bar("2026-01-05", 10.0),
            _bar("2026-01-06", 12.0),
        ]
        out = find_max_range(bars, factor="close", band=0.09)
        self.assertFalse(out["found"])
        self.assertIsNone(out["window"])
        self.assertIsNotNone(out["first_fail"])

    def test_invalid_factor_raises(self) -> None:
        with self.assertRaises(ValueError):
            find_max_range([_bar("2026-01-05", 10.0), _bar("2026-01-06", 10.0)], factor="foo")

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            find_max_range([])


class WindowWithinTests(unittest.TestCase):
    def _pack(self, bars: list[dict]) -> dict:
        return compute_undulate(bars, "2026-01-06", "2026-01-07")

    def test_close_within_but_high_exceeds(self) -> None:
        bars = [
            _bar("2026-01-05", 10.0),
            _bar("2026-01-06", 10.0, high=11.0),  # 最高 +10%
            _bar("2026-01-07", 10.0),
        ]
        pack = self._pack(bars)
        self.assertTrue(window_within(pack, factor="close", band=0.09))
        self.assertFalse(window_within(pack, factor="all", band=0.09))

    def test_all_within(self) -> None:
        bars = [
            _bar("2026-01-05", 10.0),
            _bar("2026-01-06", 10.0, high=10.5, low=9.6),
            _bar("2026-01-07", 10.0),
        ]
        pack = self._pack(bars)
        self.assertTrue(window_within(pack, factor="all", band=0.09))


class LowestDayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bars = [
            _bar("2026-01-05", 10.0),
            _bar("2026-01-06", 10.1, open=10.2, high=10.3, low=9.8),
            _bar("2026-01-07", 9.9, open=10.0, high=10.1, low=9.5),
            _bar("2026-01-08", 10.2, open=10.1, high=10.4, low=9.9),
        ]
        self.window = compute_undulate(self.bars, "2026-01-06", "2026-01-08")

    def test_lowest_close(self) -> None:
        out = lowest_day(self.window, factor="close")
        self.assertEqual(out["date"], "2026-01-07")
        self.assertAlmostEqual(out["price"], 9.9)

    def test_lowest_low(self) -> None:
        out = lowest_day(self.window, factor="low")
        self.assertEqual(out["date"], "2026-01-07")
        self.assertAlmostEqual(out["price"], 9.5)

    def test_invalid_factor_raises(self) -> None:
        with self.assertRaises(ValueError):
            lowest_day(self.window, factor="volume")


class ScoreLowPointTests(unittest.TestCase):
    def test_match_trough(self) -> None:
        bars = [
            _bar("2026-01-06", 10.2),
            _bar("2026-01-07", 9.8),
            _bar("2026-01-08", 9.5),
            _bar("2026-01-09", 9.9),
            _bar("2026-01-10", 10.1),
        ]
        out = score_low_point(bars, "2026-01-08", series="close")
        self.assertEqual(out["series"], "close")
        self.assertIsNotNone(out["match"])
        self.assertEqual(out["match"]["date"], "2026-01-08")
        for key in ("score", "score_price", "score_days", "score_gap"):
            self.assertIn(key, out["match"])

    def test_invalid_series_falls_back_close(self) -> None:
        bars = [
            _bar("2026-01-06", 10.2),
            _bar("2026-01-07", 9.8),
            _bar("2026-01-08", 9.5),
        ]
        out = score_low_point(bars, "2026-01-07", series="foo")
        self.assertEqual(out["series"], "close")


class SummarizeSigmaTests(unittest.TestCase):
    def test_keys_and_values(self) -> None:
        bars = [
            _bar("2026-01-05", 10.0),
            _bar("2026-01-06", 10.5),
            _bar("2026-01-07", 9.8),
        ]
        vol = compute_volatility(bars, "2026-01-06", "2026-01-07")
        out = summarize_sigma(vol)
        self.assertEqual(out["beg"], "2026-01-06")
        self.assertEqual(out["end"], "2026-01-07")
        self.assertIn("close", out["stats"])
        row = out["stats"]["close"]
        for key in ("beg_pct", "beg_sigma", "beg_z", "end_pct", "end_sigma", "end_z", "mean", "std"):
            self.assertIn(key, row)


if __name__ == "__main__":
    unittest.main()
