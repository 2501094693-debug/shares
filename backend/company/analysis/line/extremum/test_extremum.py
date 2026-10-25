"""四价前低回溯纯函数单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.line.extremum.service import compute_extremum


def _bar(date: str, o: float, c: float, h: float, low: float) -> dict:
    return {"time": date, "open": o, "close": c, "high": h, "low": low}


class ComputeExtremumTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bars = [
            _bar("2026-01-05", 10.0, 10.5, 11.0, 9.5),
            _bar("2026-01-06", 10.6, 10.2, 10.8, 10.1),
            _bar("2026-01-07", 10.3, 11.2, 11.5, 10.0),
            _bar("2026-01-08", 11.0, 10.8, 11.3, 10.4),
            _bar("2026-01-09", 10.9, 11.6, 12.0, 10.7),
        ]

    def test_target_date_basic(self) -> None:
        out = compute_extremum(self.bars, "2026-01-09")
        self.assertEqual(out["date"], "2026-01-09")
        ext = out["extremum"]
        # 开盘 10.9：往前最近更低于此价的是 01-07 的 10.3（01-08 的 11.0 不低）
        self.assertEqual(ext["open"]["date"], "2026-01-07")
        self.assertAlmostEqual(ext["open"]["found_price"], 10.3)
        self.assertEqual(ext["open"]["gap"], 1)
        # 收盘 11.6：往前最近收盘低于 11.6 的是 01-08 的 10.8
        self.assertEqual(ext["close"]["date"], "2026-01-08")
        self.assertEqual(ext["close"]["gap"], 0)
        # 最高 12.0：往前最近最高低于此价的是 01-08 的 11.3
        self.assertEqual(ext["high"]["date"], "2026-01-08")
        # 最低 10.7：往前最近最低低于此价的是 01-08 的 10.4（相邻日，间隔 0）
        self.assertEqual(ext["low"]["date"], "2026-01-08")
        self.assertEqual(ext["low"]["gap"], 0)

    def test_snap_non_trading_day(self) -> None:
        # 2026-01-10 非交易日，应取不晚于它的最近交易日 01-09
        out = compute_extremum(self.bars, "20260110")
        self.assertEqual(out["date"], "2026-01-09")
        self.assertTrue(out["snapped"])

    def test_no_prior_lower(self) -> None:
        bars = [
            _bar("2026-01-05", 10.0, 10.0, 10.0, 10.0),
            _bar("2026-01-06", 11.0, 11.0, 11.0, 11.0),
        ]
        out = compute_extremum(bars, "2026-01-06")
        # 01-06 四项全为 11，均高于 01-05 的 10，全部找到
        self.assertEqual(out["extremum"]["open"]["date"], "2026-01-05")

    def test_first_day_no_history(self) -> None:
        out = compute_extremum(self.bars, "2026-01-05")
        for f in ("open", "close", "high", "low"):
            self.assertIsNone(out["extremum"][f]["date"])

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_extremum([], "2026-01-09")


if __name__ == "__main__":
    unittest.main()
