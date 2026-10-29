"""筹码分布引擎 / 同花顺日线解析单测（无网络）。"""

from __future__ import annotations

import unittest

import numpy as np

from company.analysis.line.chip.calibrate import fit_rows, normalize_targets
from company.analysis.line.chip.core import (
    DEFAULT_PEAK,
    PEAK_MODES,
    make_grid,
    normalize_peak,
    peak_price,
    run_chip,
    summarize_chips,
    triangle_weights,
)
from company.analysis.line.chip.service import to_payload
from company.analysis.line.chip.ths import _jsonp, _parse_row, _rows_of

_JSONP = (
    'quotebridge_v6_line_hs_600519_01_2024({"data":'
    '"20240102,1580.59,1583.78,1543.69,1550.60,3215644,5440082500.00,0.256,,,0;'
    '20241231,1445.75,1465.35,1442.36,1444.35,3935445,6033540400.00,0.313,,,0"})'
)


def _row(date: str, price: float, turnover: float | None, volume: float = 1e6) -> dict:
    return {
        "date": date,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": volume,
        "turnover": turnover,
    }


class ThsParseTests(unittest.TestCase):
    def test_jsonp_and_rows(self) -> None:
        payload = _jsonp(_JSONP)
        rows = _rows_of(payload)
        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first["date"], "2024-01-02")
        self.assertAlmostEqual(first["open"], 1580.59)
        self.assertAlmostEqual(first["high"], 1583.78)
        self.assertAlmostEqual(first["low"], 1543.69)
        self.assertAlmostEqual(first["close"], 1550.60)
        self.assertAlmostEqual(first["volume"], 3215644.0)
        self.assertAlmostEqual(first["turnover"], 0.256)

    def test_parse_row_short(self) -> None:
        self.assertIsNone(_parse_row("20240102,1,2,3"))
        self.assertIsNone(_parse_row("bad,1,2,3,4,5,6,7"))

    def test_parse_row_uses_turnover_field(self) -> None:
        row = _parse_row("20250102,34.01,35.28,33.75,34.26,791137,54109629.00,13.759,,,0")
        assert row is not None
        self.assertAlmostEqual(row["turnover"], 13.759)
        self.assertAlmostEqual(row["volume"], 791137.0)


class CoreTests(unittest.TestCase):
    def test_triangle_weights_normalized(self) -> None:
        rows = [{
            "date": "2024-01-02",
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 1e6,
            "turnover": 5.0,
        }]
        _, centers = make_grid(rows, bins=50)
        weights = triangle_weights(rows[0], centers)
        self.assertAlmostEqual(float(weights.sum()), 1.0, places=9)
        self.assertEqual(float(weights[centers < 9.0].sum()), 0.0)
        self.assertEqual(float(weights[centers > 11.0].sum()), 0.0)

    def test_first_day_seed(self) -> None:
        out = run_chip([_row("2024-01-02", 10.0, 0.0)], bins=40)
        self.assertAlmostEqual(float(out["chips"].sum()), 1.0, places=9)
        self.assertAlmostEqual(out["stats"]["avg_cost"], 10.0, places=2)
        self.assertAlmostEqual(out["stats"]["profit_ratio"], 1.0, places=6)
        self.assertEqual(len(out["history"]), 1)

    def test_full_turnover_moves_cost(self) -> None:
        rows = [_row(f"2024-01-{day:02d}", 10.0, 0.0) for day in range(2, 12)]
        rows.append(_row("2024-01-12", 20.0, 100.0))
        out = run_chip(rows, bins=80)
        self.assertAlmostEqual(out["stats"]["avg_cost"], 20.0, delta=0.1)
        self.assertAlmostEqual(out["stats"]["profit_ratio"], 1.0, places=6)

    def test_low_turnover_keeps_old_chips(self) -> None:
        rows = [_row("2024-01-02", 10.0, 0.0), _row("2024-01-03", 20.0, 10.0)]
        out = run_chip(rows, bins=100)
        # 仅 10% 换手：平均成本明显仍靠近 10
        self.assertLess(out["stats"]["avg_cost"], 12.0)
        self.assertGreater(out["stats"]["avg_cost"], 10.0)
        self.assertAlmostEqual(out["stats"]["profit_ratio"], 1.0, places=6)

    def test_history_fields(self) -> None:
        rows = [
            _row("2024-01-02", 10.0, 5.0),
            _row("2024-01-03", 11.0, 5.0),
            _row("2024-01-04", 12.0, 5.0),
        ]
        out = run_chip(rows, bins=60)
        self.assertEqual(len(out["history"]), 3)
        for item in out["history"]:
            for key in ("date", "close", "profit_ratio", "avg_cost", "median",
                        "cost70_low", "cost70_high", "cost90_low", "cost90_high",
                        "concentration70", "concentration90", "peak"):
                self.assertIn(key, item)
        self.assertTrue(0.0 <= out["stats"]["profit_ratio"] <= 1.0)
        self.assertTrue(out["stats"]["cost90_low"] <= out["stats"]["cost90_high"])
        self.assertTrue(out["peaks"])

    def test_summarize_requires_chips(self) -> None:
        with self.assertRaises(ValueError):
            summarize_chips(np.zeros(5), np.arange(5, dtype=float), 1.0)

    def test_bad_decay(self) -> None:
        with self.assertRaises(ValueError):
            run_chip([_row("2024-01-02", 10.0, 1.0)], decay=0)

    def test_payload_shape(self) -> None:
        rows = [_row(f"2024-02-{day:02d}", 10.0 + day * 0.1, 3.0) for day in range(1, 6)]
        out = run_chip(rows, bins=30)
        out.update(symbol="600519", name="贵州茅台", source="tonghuashun", adjust="none",
                   end="2024-02-05", start="2024-02-01", decay=1.0)
        payload = to_payload(out, end="2024-02-05", series_limit=10)
        self.assertEqual(len(payload["grid"]), len(payload["chips"]))
        self.assertEqual(len(payload["series"]), 5)
        self.assertEqual(payload["date"], "2024-02-05")
        self.assertIn("stats", payload)
        self.assertIn("peaks", payload)
        self.assertEqual(payload["meta"]["bins"], 30)


class PeakModeTests(unittest.TestCase):
    def _row(self, **kw) -> dict:
        row = {
            "date": "2024-01-02",
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 1e6,
            "amount": None,
            "turnover": 5.0,
        }
        row.update(kw)
        return row

    def test_peak_price_modes(self) -> None:
        row = self._row(amount=1.0e7)  # 成交均价 10.0
        self.assertAlmostEqual(peak_price(row, "avg"), 10.0)
        self.assertAlmostEqual(peak_price(row, "ohlc4"), (10.0 + 11.0 + 9.0 + 10.5) / 4)
        self.assertAlmostEqual(peak_price(row, "typical"), (11.0 + 9.0 + 10.5) / 3)
        self.assertAlmostEqual(peak_price(row, "close"), 10.5)

    def test_avg_falls_back_without_amount(self) -> None:
        row = self._row(amount=None)
        self.assertAlmostEqual(peak_price(row, "avg"), peak_price(row, "ohlc4"))

    def test_avg_rejects_unit_mismatch(self) -> None:
        # 成交额误按「手」计算会放大 100 倍，均价 1000 元明显越界
        row = self._row(amount=1.0e9)
        self.assertAlmostEqual(peak_price(row, "avg"), peak_price(row, "ohlc4"))

    def test_peak_clamped_into_range(self) -> None:
        row = self._row(amount=5.0e7)  # 均价 50，超出 [9, 11]
        self.assertLessEqual(peak_price(row, "avg"), 11.0)
        self.assertGreaterEqual(peak_price(row, "avg"), 9.0)

    def test_triangle_apex_follows_mode(self) -> None:
        _, centers = make_grid([self._row()], bins=200)
        w_avg = triangle_weights(self._row(amount=1.0e7), centers, peak="avg")
        w_close = triangle_weights(self._row(), centers, peak="close")
        self.assertAlmostEqual(float(centers[int(np.argmax(w_avg))]), 10.0, delta=0.02)
        self.assertAlmostEqual(float(centers[int(np.argmax(w_close))]), 10.5, delta=0.02)

    def test_normalize_peak_aliases(self) -> None:
        self.assertEqual(normalize_peak("VWAP"), "avg")
        self.assertEqual(normalize_peak("HLC3"), "typical")
        self.assertEqual(normalize_peak(""), DEFAULT_PEAK)
        self.assertEqual(normalize_peak("bogus"), DEFAULT_PEAK)
        for mode in PEAK_MODES:
            self.assertEqual(normalize_peak(mode), mode)


class RunChipPeakTests(unittest.TestCase):
    def test_reports_peak_mode(self) -> None:
        out = run_chip([_row("2024-01-02", 10.0, 0.0)], bins=40, peak="ohlc4")
        self.assertEqual(out["peak"], "ohlc4")
        self.assertEqual(len(out["history"]), 1)

    def test_without_history(self) -> None:
        rows = [_row("2024-01-02", 10.0, 5.0), _row("2024-01-03", 11.0, 5.0)]
        out = run_chip(rows, bins=40, with_history=False)
        self.assertEqual(out["history"], [])
        self.assertAlmostEqual(float(out["chips"].sum()), 1.0, places=9)
        self.assertTrue(out["stats"]["avg_cost"] > 0)


class CalibrateTests(unittest.TestCase):
    @staticmethod
    def _rows() -> list[dict]:
        rows = []
        price = 10.0
        for i in range(60):
            price += 0.1 * ((i % 7) - 3)
            rows.append({
                "date": f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
                "open": price * 0.99,
                "high": price * 1.02,
                "low": price * 0.98,
                "close": price,
                "volume": 1e6,
                "amount": price * 1e6,  # 成交均价恰为 close
                "turnover": 3.0 + (i % 5),
            })
        return rows

    def test_recovers_known_combo(self) -> None:
        rows = self._rows()
        truth = run_chip(rows, bins=120, decay=1.5, peak="ohlc4", with_history=False)["stats"]
        result = fit_rows(
            rows,
            targets={"avg_cost": truth["avg_cost"], "peak": truth["peak"]},
            decays=[0.8, 1.0, 1.5, 2.0],
            peaks=["avg", "ohlc4"],
            bins=120,
            top=4,
        )
        self.assertEqual(result["best"]["peak"], "ohlc4")
        self.assertAlmostEqual(result["best"]["decay"], 1.5)
        self.assertAlmostEqual(result["best"]["score"], 0.0, places=4)

    def test_ratio_targets_accept_percent(self) -> None:
        self.assertAlmostEqual(normalize_targets({"profit_ratio": "62"})["profit_ratio"], 0.62)
        self.assertAlmostEqual(normalize_targets({"profit_ratio": 0.62})["profit_ratio"], 0.62)
        self.assertEqual(normalize_targets({"unknown": 1}), {})

    def test_requires_targets(self) -> None:
        with self.assertRaises(ValueError):
            fit_rows(self._rows(), targets={})


if __name__ == "__main__":
    unittest.main()
