"""MACD 纯函数单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.line.MACD.core import _ema, compute_macd


def _bar(date: str, close: float, **extra: float) -> dict:
    row = {
        "time": date,
        "open": extra.get("open", close),
        "high": extra.get("high", close),
        "low": extra.get("low", close),
        "close": close,
    }
    return row


def _dates(n: int, start: str = "2024-01-02") -> list[str]:
    """生成连续日历日（单测不要求交易日）。"""
    from datetime import datetime, timedelta

    cur = datetime.strptime(start, "%Y-%m-%d")
    out: list[str] = []
    for _ in range(n):
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


class EmaTests(unittest.TestCase):
    def test_sma_seed_then_ema(self) -> None:
        # period=3: SMA([1,2,3])=2；下一根 4 → 2/4*4 + 2/4*2 = 3
        values = [1.0, 2.0, 3.0, 4.0]
        out = _ema(values, 3)
        self.assertIsNone(out[0])
        self.assertIsNone(out[1])
        self.assertAlmostEqual(out[2], 2.0)
        self.assertAlmostEqual(out[3], 3.0)

    def test_none_breaks_chain(self) -> None:
        values = [1.0, 2.0, None, 3.0, 4.0, 5.0]
        out = _ema(values, 3)
        self.assertIsNone(out[2])
        self.assertIsNone(out[3])
        self.assertIsNone(out[4])
        self.assertAlmostEqual(out[5], 4.0)


class ComputeMacdTests(unittest.TestCase):
    def test_constant_price_zero_macd(self) -> None:
        dates = _dates(40)
        bars = [_bar(d, 10.0) for d in dates]
        out = compute_macd(bars, dates[0], dates[-1], fast=3, slow=5, signal=3)
        latest = out["latest"]
        self.assertIsNotNone(latest["dif"])
        self.assertAlmostEqual(latest["dif"], 0.0, places=6)
        self.assertAlmostEqual(latest["dea"], 0.0, places=6)
        self.assertAlmostEqual(latest["macd"], 0.0, places=6)

    def test_range_slice_and_warmup(self) -> None:
        dates = _dates(30)
        # 前半段低、后半段高 → DIF 应为正
        bars = [
            _bar(d, 10.0 if i < 15 else 20.0) for i, d in enumerate(dates)
        ]
        beg = dates[20]
        end = dates[25]
        out = compute_macd(bars, beg, end, fast=3, slow=5, signal=3)
        self.assertEqual(out["beg"], beg)
        self.assertEqual(out["end"], end)
        self.assertEqual(out["count"], 6)
        self.assertTrue(all(row["dif"] is not None for row in out["items"]))
        self.assertGreater(out["latest"]["dif"], 0)

    def test_price_field_high(self) -> None:
        dates = _dates(25)
        bars = [
            _bar(d, close=10.0, high=10.0 + i * 0.5) for i, d in enumerate(dates)
        ]
        out_close = compute_macd(
            bars, dates[0], dates[-1], fast=3, slow=5, signal=3, price="close"
        )
        out_high = compute_macd(
            bars, dates[0], dates[-1], fast=3, slow=5, signal=3, price="high"
        )
        self.assertEqual(out_high["price"], "high")
        self.assertNotEqual(
            out_close["latest"]["price"], out_high["latest"]["price"]
        )

    def test_defaults_and_histogram_times_two(self) -> None:
        dates = _dates(60)
        bars = [_bar(d, 10.0 + (i % 7) * 0.3) for i, d in enumerate(dates)]
        out = compute_macd(bars, dates[30], dates[-1])
        self.assertEqual(out["fast"], 10)
        self.assertEqual(out["slow"], 20)
        self.assertEqual(out["signal"], 7)
        row = out["latest"]
        if row["dif"] is not None and row["dea"] is not None:
            self.assertAlmostEqual(
                row["macd"], 2.0 * (row["dif"] - row["dea"]), places=6
            )

    def test_invalid_params(self) -> None:
        bars = [_bar("2024-01-02", 10.0)]
        with self.assertRaises(ValueError):
            compute_macd(bars, "2024-01-02", fast=22, slow=10, signal=8)
        with self.assertRaises(ValueError):
            compute_macd(bars, "2024-01-02", price="mid")
        with self.assertRaises(ValueError):
            compute_macd([], "2024-01-02")

    def test_empty_range(self) -> None:
        bars = [_bar("2024-01-02", 10.0)]
        with self.assertRaises(ValueError):
            compute_macd(bars, "2024-02-01", "2024-02-28")


if __name__ == "__main__":
    unittest.main()
