"""区间四价极值位置百分比 / 升序排名纯函数单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.line.extremum.position import compute_position


def _bar(date: str, o: float, c: float, h: float, low: float) -> dict:
    return {"time": date, "open": o, "close": c, "high": h, "low": low}


class ComputePositionTests(unittest.TestCase):
    def setUp(self) -> None:
        # close: 10.5, 10.2, 11.2, 10.8, 11.6 → min 10.2 @01-06, max 11.6 @01-09
        self.bars = [
            _bar("2026-01-05", 10.0, 10.5, 11.0, 9.5),
            _bar("2026-01-06", 10.6, 10.2, 10.8, 10.1),
            _bar("2026-01-07", 10.3, 11.2, 11.5, 10.0),
            _bar("2026-01-08", 11.0, 10.8, 11.3, 10.4),
            _bar("2026-01-09", 10.9, 11.6, 12.0, 10.7),
        ]

    def test_basic_close_at_high(self) -> None:
        out = compute_position(self.bars, "2026-01-05", "2026-01-09")
        self.assertEqual(out["beg"], "2026-01-05")
        self.assertEqual(out["end"], "2026-01-09")
        self.assertEqual(out["count"], 5)

        close = out["position"]["close"]
        self.assertAlmostEqual(close["min"], 10.2)
        self.assertEqual(close["min_date"], "2026-01-06")
        self.assertAlmostEqual(close["max"], 11.6)
        self.assertEqual(close["max_date"], "2026-01-09")
        self.assertAlmostEqual(close["end_price"], 11.6)
        # 结束日刚好是最高 → 100%；升序第 5/5
        self.assertAlmostEqual(close["pct"], 100.0)
        self.assertEqual(close["rank"], 5)
        self.assertEqual(close["n"], 5)

    def test_mid_range(self) -> None:
        # 截到 01-08：close 序列 10.5/10.2/11.2/10.8 → min 10.2 max 11.2
        # end=10.8 → (10.8-10.2)/(11.2-10.2)=60%
        # 升序：10.2, 10.5, 10.8, 11.2 → 第 3/4
        out = compute_position(self.bars, "2026-01-05", "2026-01-08")
        close = out["position"]["close"]
        self.assertAlmostEqual(close["min"], 10.2)
        self.assertAlmostEqual(close["max"], 11.2)
        self.assertAlmostEqual(close["end_price"], 10.8)
        self.assertAlmostEqual(close["pct"], 60.0)
        self.assertEqual(close["rank"], 3)
        self.assertEqual(close["n"], 4)

    def test_open_low_high(self) -> None:
        out = compute_position(self.bars, "2026-01-05", "2026-01-09")
        # open: 10.0/10.6/10.3/11.0/10.9 → min 10.0 @01-05, max 11.0 @01-08
        # end 10.9 → (10.9-10.0)/(11.0-10.0)=90%；升序第 4/5
        open_row = out["position"]["open"]
        self.assertAlmostEqual(open_row["min"], 10.0)
        self.assertAlmostEqual(open_row["max"], 11.0)
        self.assertAlmostEqual(open_row["pct"], 90.0)
        self.assertEqual(open_row["rank"], 4)
        self.assertEqual(open_row["n"], 5)

        # high: 11.0/10.8/11.5/11.3/12.0 → min 10.8 max 12.0，end=12.0 → 100%；第 5/5
        high = out["position"]["high"]
        self.assertAlmostEqual(high["min"], 10.8)
        self.assertAlmostEqual(high["max"], 12.0)
        self.assertAlmostEqual(high["pct"], 100.0)
        self.assertEqual(high["rank"], 5)
        self.assertEqual(high["n"], 5)

        # low: 9.5/10.1/10.0/10.4/10.7 → min 9.5 max 10.7，end=10.7 → 100%；第 5/5
        low = out["position"]["low"]
        self.assertAlmostEqual(low["min"], 9.5)
        self.assertAlmostEqual(low["max"], 10.7)
        self.assertAlmostEqual(low["pct"], 100.0)
        self.assertEqual(low["rank"], 5)
        self.assertEqual(low["n"], 5)

    def test_live_price_override(self) -> None:
        # 区间结束日 close=11.6，但最新实时 close=10.9
        out = compute_position(
            self.bars,
            "2026-01-05",
            "2026-01-09",
            live_prices={"close": 10.9},
            live_date="2026-10-26",
        )
        close = out["position"]["close"]
        self.assertEqual(close["price_source"], "live")
        self.assertEqual(close["end_date"], "2026-10-26")
        self.assertAlmostEqual(close["end_price"], 10.9)
        # (10.9-10.2)/(11.6-10.2)=50%；区间升序：10.2,10.5,10.8,10.9 → 第 4/5
        self.assertAlmostEqual(close["pct"], 50.0)
        self.assertEqual(close["rank"], 4)
        self.assertEqual(close["n"], 5)
        self.assertTrue(out["live"])
        self.assertEqual(out["quote_date"], "2026-10-26")

        # 未提供实时价的口径仍回退到区间结束日
        open_row = out["position"]["open"]
        self.assertEqual(open_row["price_source"], "bar")
        self.assertEqual(open_row["end_date"], "2026-01-09")
        self.assertAlmostEqual(open_row["end_price"], 10.9)

    def test_live_price_above_range(self) -> None:
        out = compute_position(
            self.bars,
            "2026-01-05",
            "2026-01-09",
            live_prices={"close": 12.0},
            live_date="2026-10-26",
        )
        close = out["position"]["close"]
        # 高于区间全部 5 个收盘价 → 1 + 5 = 第 6，样本数仍为 5
        self.assertEqual(close["rank"], 6)
        self.assertEqual(close["n"], 5)
        self.assertAlmostEqual(close["pct"], 128.5714)

    def test_rank_tie(self) -> None:
        # close: 10, 11, 10, 12 → end=12 第 4；若 end 截到第三根 close=10，并列最低 → 第 1
        bars = [
            _bar("2026-01-05", 10.0, 10.0, 11.0, 9.0),
            _bar("2026-01-06", 10.0, 11.0, 11.5, 9.5),
            _bar("2026-01-07", 10.0, 10.0, 10.5, 9.8),
            _bar("2026-01-08", 10.0, 12.0, 12.5, 10.0),
        ]
        tied = compute_position(bars, "2026-01-05", "2026-01-07")
        self.assertEqual(tied["position"]["close"]["rank"], 1)
        self.assertEqual(tied["position"]["close"]["n"], 3)

        top = compute_position(bars, "2026-01-05", "2026-01-08")
        self.assertEqual(top["position"]["close"]["rank"], 4)
        self.assertEqual(top["position"]["close"]["n"], 4)

    def test_snap_non_trading_end(self) -> None:
        out = compute_position(self.bars, "2026-01-05", "20260110")
        self.assertEqual(out["end"], "2026-01-09")
        self.assertTrue(out["snapped"])

    def test_zero_range(self) -> None:
        bars = [
            _bar("2026-01-05", 10.0, 10.0, 10.0, 10.0),
            _bar("2026-01-06", 10.0, 10.0, 10.0, 10.0),
        ]
        out = compute_position(bars, "2026-01-05", "2026-01-06")
        for f in ("open", "close", "high", "low"):
            self.assertIsNone(out["position"][f]["pct"])
            # 全部持平 → 并列最低，升序第 1/2
            self.assertEqual(out["position"][f]["rank"], 1)
            self.assertEqual(out["position"][f]["n"], 2)

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_position([], "2026-01-05")

    def test_no_bars_in_range(self) -> None:
        with self.assertRaises(ValueError):
            compute_position(self.bars, "2026-02-01", "2026-02-10")


if __name__ == "__main__":
    unittest.main()
