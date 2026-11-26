"""MACDP 纯函数单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.line.MACDP.core import (
    _avg_price,
    _fixed_ema,
    _vol_ema,
    compute_macdp,
)


def _bar(
    date: str,
    close: float,
    *,
    volume: float = 1000.0,
    amount: float | None = None,
    **extra: float,
) -> dict:
    high = extra.get("high", close)
    low = extra.get("low", close)
    amt = amount if amount is not None else close * volume
    return {
        "time": date,
        "open": extra.get("open", close),
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "amount": amt,
    }


def _dates(n: int, start: str = "2024-01-02") -> list[str]:
    from datetime import datetime, timedelta

    cur = datetime.strptime(start, "%Y-%m-%d")
    out: list[str] = []
    for _ in range(n):
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


class AvgPriceTests(unittest.TestCase):
    def test_amount_over_volume(self) -> None:
        bar = _bar("2024-01-02", 10.0, volume=1000.0, amount=10_000.0)
        self.assertAlmostEqual(_avg_price(bar) or 0.0, 10.0)

    def test_hand_unit_fallback(self) -> None:
        # amount/volume 若把「手」当「股」会偏小；÷100 后落在高低价内
        bar = {
            "time": "2024-01-02",
            "open": 10.0,
            "high": 10.5,
            "low": 9.5,
            "close": 10.0,
            "volume": 100.0,  # 手
            "amount": 100_000.0,  # 元 → 均价 10（按股）
        }
        # amount/volume=1000 越界；amount/(volume*100)=10 合格
        self.assertAlmostEqual(_avg_price(bar) or 0.0, 10.0)

    def test_missing_amount_uses_typical(self) -> None:
        bar = {
            "time": "2024-01-02",
            "open": 10.0,
            "high": 12.0,
            "low": 9.0,
            "close": 11.0,
            "volume": 1000.0,
            "amount": None,
        }
        self.assertAlmostEqual(_avg_price(bar) or 0.0, (12.0 + 9.0 + 11.0) / 3.0)


class VolEmaTests(unittest.TestCase):
    def test_constant_volume_matches_one_over_n_plus_one(self) -> None:
        # period=3：种子 SMA([1,2,3])=2；下一根 α=1/4，EMA=0.25*4+0.75*2=2.5
        prices = [1.0, 2.0, 3.0, 4.0]
        volumes = [10.0, 10.0, 10.0, 10.0]
        out = _vol_ema(prices, volumes, 3)
        self.assertIsNone(out[0])
        self.assertIsNone(out[1])
        self.assertAlmostEqual(out[2] or 0.0, 2.0)
        self.assertAlmostEqual(out[3] or 0.0, 2.5)

    def test_higher_volume_pulls_harder(self) -> None:
        prices = [1.0, 1.0, 1.0, 10.0]
        vol_flat = [10.0, 10.0, 10.0, 10.0]
        vol_spike = [10.0, 10.0, 10.0, 1000.0]
        flat = _vol_ema(prices, vol_flat, 3)
        spike = _vol_ema(prices, vol_spike, 3)
        self.assertGreater(spike[3] or 0.0, flat[3] or 0.0)

    def test_none_breaks_chain(self) -> None:
        prices = [1.0, 2.0, None, 3.0, 4.0, 5.0]
        volumes = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
        out = _vol_ema(prices, volumes, 3)
        self.assertIsNone(out[2])
        self.assertIsNone(out[3])
        self.assertIsNone(out[4])
        self.assertAlmostEqual(out[5] or 0.0, 4.0)


class FixedEmaTests(unittest.TestCase):
    def test_alpha_one_over_n_plus_one(self) -> None:
        # period=3 → α=1/4；种子 SMA=2；下一根 0.25*4+0.75*2=2.5
        values = [1.0, 2.0, 3.0, 4.0]
        out = _fixed_ema(values, 3)
        self.assertAlmostEqual(out[2] or 0.0, 2.0)
        self.assertAlmostEqual(out[3] or 0.0, 2.5)


class ComputeMacdpTests(unittest.TestCase):
    def test_constant_price_zero_macd(self) -> None:
        dates = _dates(40)
        bars = [_bar(d, 10.0) for d in dates]
        out = compute_macdp(bars, dates[0], dates[-1], fast=3, slow=5, signal=3)
        latest = out["latest"]
        self.assertAlmostEqual(latest["dif"] or 0.0, 0.0, places=6)
        self.assertAlmostEqual(latest["dea"] or 0.0, 0.0, places=6)
        self.assertAlmostEqual(latest["macd"] or 0.0, 0.0, places=6)

    def test_range_slice_and_warmup(self) -> None:
        dates = _dates(30)
        bars = [
            _bar(d, 10.0 if i < 15 else 20.0) for i, d in enumerate(dates)
        ]
        beg = dates[20]
        end = dates[25]
        out = compute_macdp(bars, beg, end, fast=3, slow=5, signal=3)
        self.assertEqual(out["beg"], beg)
        self.assertEqual(out["end"], end)
        self.assertEqual(out["count"], 6)
        self.assertTrue(all(row["dif"] is not None for row in out["items"]))
        self.assertGreater(out["latest"]["dif"], 0)

    def test_defaults_and_histogram_times_two(self) -> None:
        dates = _dates(60)
        bars = [_bar(d, 10.0 + (i % 7) * 0.3) for i, d in enumerate(dates)]
        out = compute_macdp(bars, dates[30], dates[-1])
        self.assertEqual(out["fast"], 10)
        self.assertEqual(out["slow"], 20)
        self.assertEqual(out["signal"], 7)
        self.assertEqual(out["price"], "avg")
        self.assertEqual(out["dea_alpha"], "1/(signal+1)")
        row = out["latest"]
        if row["dif"] is not None and row["dea"] is not None:
            self.assertAlmostEqual(
                row["macd"], 2.0 * (row["dif"] - row["dea"]), places=6
            )

    def test_invalid_params(self) -> None:
        bars = [_bar("2024-01-02", 10.0)]
        with self.assertRaises(ValueError):
            compute_macdp(bars, "2024-01-02", fast=22, slow=10, signal=8)
        with self.assertRaises(ValueError):
            compute_macdp([], "2024-01-02")

    def test_empty_range(self) -> None:
        bars = [_bar("2024-01-02", 10.0)]
        with self.assertRaises(ValueError):
            compute_macdp(bars, "2024-02-01", "2024-02-28")


if __name__ == "__main__":
    unittest.main()
