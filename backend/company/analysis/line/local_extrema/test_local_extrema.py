"""日线局部极值点纯函数单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.line.local_extrema.service import compute_local_extrema


def _bar(date: str, close: float, *, volume: float = 100.0) -> dict:
    return {
        "time": date,
        "open": close,
        "close": close,
        "high": close,
        "low": close,
        "volume": volume,
    }


class ComputeLocalExtremaTests(unittest.TestCase):
    def test_basic_peaks_troughs(self) -> None:
        bars = [
            _bar("2026-01-05", 1.0),
            _bar("2026-01-06", 3.0),
            _bar("2026-01-07", 2.0),
            _bar("2026-01-08", 4.0),
            _bar("2026-01-09", 1.0),
        ]
        out = compute_local_extrema(bars, w=1, min_distance=1, include_endpoints=False)
        types = [e["type"] for e in out["extrema"]]
        self.assertEqual(types, ["peak", "trough", "peak"])

    def test_plateau_single_peak(self) -> None:
        bars = [
            _bar("2026-01-05", 1.0),
            _bar("2026-01-06", 2.0),
            _bar("2026-01-07", 2.0),
            _bar("2026-01-08", 2.0),
            _bar("2026-01-09", 1.0),
        ]
        out = compute_local_extrema(bars, w=1, min_distance=1, include_endpoints=False)
        peaks = [e for e in out["extrema"] if e["type"] == "peak"]
        self.assertEqual(len(peaks), 1)

    def test_monotonic_no_internal_extrema(self) -> None:
        bars = [_bar(f"2026-01-{5+i:02d}", float(i + 1)) for i in range(5)]
        out = compute_local_extrema(bars, w=1, min_distance=1, include_endpoints=False)
        self.assertEqual(out["extrema"], [])

    def test_prominence_filter(self) -> None:
        bars = [
            _bar("2026-01-05", 10.0),
            _bar("2026-01-06", 10.2),  # 微小波峰
            _bar("2026-01-07", 10.0),
            _bar("2026-01-08", 12.0),  # 显著波峰
            _bar("2026-01-09", 10.0),
        ]
        out = compute_local_extrema(
            bars, w=1, min_distance=1, prominence=1.0, include_endpoints=False
        )
        peaks = [e for e in out["extrema"] if e["type"] == "peak"]
        self.assertEqual(len(peaks), 1)
        self.assertEqual(peaks[0]["date"], "2026-01-08")

    def test_alternation(self) -> None:
        bars = [
            _bar("2026-01-05", 1.0),
            _bar("2026-01-06", 3.0),
            _bar("2026-01-07", 2.0),
            _bar("2026-01-08", 2.5),
            _bar("2026-01-09", 1.5),
        ]
        out = compute_local_extrema(bars, w=1, min_distance=1, include_endpoints=False)
        types = [e["type"] for e in out["extrema"]]
        for a, b in zip(types, types[1:]):
            self.assertNotEqual(a, b)

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_local_extrema([], w=1)

    def test_invalid_series_raises(self) -> None:
        bars = [_bar("2026-01-05", 1.0)]
        with self.assertRaises(ValueError):
            compute_local_extrema(bars, series="foo")

    def test_bands_output(self) -> None:
        bars = [
            _bar("2026-01-05", 1.0),
            _bar("2026-01-06", 3.0),
            _bar("2026-01-07", 1.0),
        ]
        out = compute_local_extrema(bars, w=1, min_distance=1, include_endpoints=True)
        self.assertTrue(len(out["bands"]) >= 1)
        self.assertIn("amplitude", out["bands"][0])

    def test_endpoints_included(self) -> None:
        bars = [
            _bar("2026-01-05", 1.0),
            _bar("2026-01-06", 3.0),
            _bar("2026-01-07", 2.0),
        ]
        out = compute_local_extrema(bars, w=1, min_distance=1, include_endpoints=True)
        self.assertTrue(any(e["endpoint"] for e in out["extrema"]))

    def test_smooth_runs(self) -> None:
        bars = [_bar(f"2026-01-{5+i:02d}", float(v)) for i, v in enumerate([1, 2, 1, 2, 1])]
        out = compute_local_extrema(bars, w=1, min_distance=1, smooth_window=3, include_endpoints=False)
        self.assertIsInstance(out["extrema"], list)

    def test_prominence_pct_filter(self) -> None:
        bars = [
            _bar("2026-01-05", 10.0),
            _bar("2026-01-06", 10.1),
            _bar("2026-01-07", 10.0),
            _bar("2026-01-08", 12.0),
            _bar("2026-01-09", 10.0),
        ]
        out = compute_local_extrema(
            bars, w=1, min_distance=1, prominence_pct=5.0, include_endpoints=False
        )
        peaks = [e for e in out["extrema"] if e["type"] == "peak"]
        self.assertEqual(len(peaks), 1)


if __name__ == "__main__":
    unittest.main()
