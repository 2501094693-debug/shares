"""聪明投机者纯函数单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.line.T.core import compute_trader


def _bar(date: str, high: float, low: float, volume_lots: float) -> dict:
    """volume 单位：手（与 fetcher 一致）。"""
    return {
        "time": date,
        "open": (high + low) / 2,
        "close": (high + low) / 2,
        "high": high,
        "low": low,
        "volume": volume_lots,
    }


class ComputeTraderTests(unittest.TestCase):
    def test_first_day_buy_only(self) -> None:
        # 1000 手 = 100_000 股；1% = 1000 股 @ 10
        bars = [_bar("2024-01-02", 11.0, 10.0, 1000)]
        out = compute_trader(bars, "2024-01-02")
        self.assertEqual(out["count"], 1)
        self.assertAlmostEqual(out["shares"], 1000.0)
        self.assertAlmostEqual(out["avg_price"], 10.0)
        self.assertAlmostEqual(out["bought"], 1000.0)
        self.assertAlmostEqual(out["sold"], 0.0)

    def test_sell_capped_by_holdings(self) -> None:
        # Day1: 买 1000 股 @10
        # Day2: 目标卖 5000，但持仓只有 1000 → 全卖 @12；再买 5000 @9
        bars = [
            _bar("2024-01-02", 11.0, 10.0, 1000),
            _bar("2024-01-03", 12.0, 9.0, 5000),
        ]
        out = compute_trader(bars, "2024-01-02", "2024-01-03")
        self.assertAlmostEqual(out["sold"], 1000.0)
        self.assertAlmostEqual(out["bought"], 1000.0 + 5000.0)
        self.assertAlmostEqual(out["shares"], 5000.0)
        self.assertAlmostEqual(out["avg_price"], 9.0)
        self.assertAlmostEqual(out["sell_proceeds"], 1000.0 * 12.0)

    def test_weighted_avg_after_partial_sell(self) -> None:
        # Day1: 买 1000 @10 → shares=1000 cost=10000
        # Day2: 卖 500 @12 → shares=500 cost=5000；买 500 @8
        #        → shares=1000 cost=5000+4000=9000 → avg=9
        # 净成本: 10000 - 500*12 + 500*8 = 8000 → net_avg=8
        # close=(12+8)/2=10 → 已实现 500*(12-10)=1000；浮盈 1000*(10-9)=1000
        bars = [
            _bar("2024-01-02", 11.0, 10.0, 1000),
            _bar("2024-01-03", 12.0, 8.0, 500),
        ]
        out = compute_trader(bars, "2024-01-02")
        self.assertAlmostEqual(out["shares"], 1000.0)
        self.assertAlmostEqual(out["avg_price"], 9.0)
        self.assertAlmostEqual(out["net_cost"], 8000.0)
        self.assertAlmostEqual(out["net_avg_price"], 8.0)
        self.assertAlmostEqual(out["sold"], 500.0)
        self.assertAlmostEqual(out["realized_pnl"], 1000.0)
        self.assertAlmostEqual(out["close"], 10.0)
        self.assertAlmostEqual(out["unrealized_pnl"], 1000.0)
        self.assertAlmostEqual(out["pnl"], 2000.0)

    def test_history_flag(self) -> None:
        bars = [
            _bar("2024-01-02", 11.0, 10.0, 1000),
            _bar("2024-01-03", 12.0, 9.0, 1000),
        ]
        out = compute_trader(bars, "2024-01-02", return_history=True)
        self.assertEqual(len(out["history"]), 2)
        self.assertEqual(out["history"][0]["sell"], 0.0)
        self.assertGreater(out["history"][1]["sell"], 0.0)

    def test_empty_range(self) -> None:
        bars = [_bar("2024-01-02", 11.0, 10.0, 1000)]
        with self.assertRaises(ValueError):
            compute_trader(bars, "2024-02-01", "2024-02-28")


if __name__ == "__main__":
    unittest.main()
