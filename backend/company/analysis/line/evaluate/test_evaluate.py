"""区间评估纯函数单测（无网络）。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from company.analysis.line.evaluate.core import (
    find_max_range,
    lowest_day,
    score_low_point,
    summarize_sigma,
    window_within,
)
from company.analysis.line.evaluate.service import (
    EXTREMA_LOOKBACK_BARS,
    _divergence_factor,
    _extrema_bars,
    _path_labels,
    _pct_series,
    _safe_divergence,
    _safe_paths,
    _series_factor,
    analyze_evaluate,
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


class ExtremaBarsTests(unittest.TestCase):
    def test_takes_last_n_trading_days(self) -> None:
        from datetime import datetime, timedelta

        end = "2026-01-09"
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        bars = [
            _bar((end_dt - timedelta(days=1099 - i)).strftime("%Y-%m-%d"), 10.0 + i * 0.01)
            for i in range(1100)
        ]
        out = _extrema_bars(bars, end=end, lookback_bars=900)
        self.assertEqual(len(out), 900)
        self.assertEqual(out[-1]["time"], end)
        # 默认常量亦为 900 交易日
        self.assertEqual(EXTREMA_LOOKBACK_BARS, 900)
        out_default = _extrema_bars(bars, end=end)
        self.assertEqual(len(out_default), 900)


class FindMaxRangeTests(unittest.TestCase):
    def test_quiet_series_is_linear_time(self) -> None:
        """安静长序列应接近 O(n)，不再出现秒级耗时。"""
        import time
        from datetime import datetime, timedelta

        end = "2026-01-09"
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        bars = []
        price = 10.0
        for i in range(1200):
            d = (end_dt - timedelta(days=1199 - i)).strftime("%Y-%m-%d")
            price *= 1.00005
            bars.append(_bar(d, price))
        t0 = time.perf_counter()
        out = find_max_range(bars, end=end, factor="close", band=0.09)
        elapsed = time.perf_counter() - t0
        self.assertTrue(out["found"])
        self.assertLess(elapsed, 0.05, f"find_max_range too slow: {elapsed:.3f}s")

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
        out = score_low_point(bars, "2026-01-08", series="close", layers=1)
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

    def test_default_layers_is_three(self) -> None:
        bars = [
            _bar("2026-01-06", 10.2),
            _bar("2026-01-07", 9.8),
            _bar("2026-01-08", 9.5),
            _bar("2026-01-09", 9.9),
            _bar("2026-01-10", 10.1),
        ]
        out = score_low_point(bars, "2026-01-08", series="close")
        self.assertEqual(out["analysis"].get("layers"), 3)


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


class DivergenceWireTests(unittest.TestCase):
    def test_divergence_factor_all_falls_back_close(self) -> None:
        self.assertEqual(_divergence_factor("all"), "close")
        self.assertEqual(_divergence_factor("high"), "high")
        self.assertEqual(_series_factor("all"), "close")

    def test_safe_divergence_on_error(self) -> None:
        with patch(
            "company.analysis.line.evaluate.service.compare_divergence",
            side_effect=RuntimeError("boom"),
        ):
            out = _safe_divergence(
                "600519", "000001", beg="2026-01-01", end="2026-01-10", factor="close"
            )
        self.assertEqual(out["score"], None)
        self.assertIn("boom", out["error"])

    def test_analyze_evaluate_includes_divergence(self) -> None:
        bars = [
            _bar("2026-01-05", 10.0),
            _bar("2026-01-06", 10.2),
            _bar("2026-01-07", 10.1),
            _bar("2026-01-08", 10.3),
            _bar("2026-01-09", 10.2),
        ]
        hist = {"items": bars, "name": "测试", "source": "test"}
        fake_div = {
            "factor": "close",
            "score": 50.0,
            "count": 4,
            "reverse_count": 2,
            "dirs": {
                "same_up": 1,
                "same_down": 1,
                "stock_up_index_down": 1,
                "stock_down_index_up": 1,
            },
            "stock": {"code": "600519", "name": "测试"},
            "index": {"code": "000001", "name": "上证指数"},
        }
        fake_paths = {
            "beg": "2026-01-07",
            "end": "2026-01-09",
            "stock": {
                "code": "600519",
                "name": "测试",
                "paths": {
                    "open": "上行",
                    "high": "上行",
                    "low": "横盘",
                    "close": "上行",
                },
            },
            "index": {
                "code": "000001",
                "name": "上证指数",
                "paths": {
                    "open": "下行",
                    "high": "冲高回落",
                    "low": "探底回升",
                    "close": "横盘",
                },
            },
        }
        with (
            patch(
                "company.analysis.line.evaluate.service._fetch_day_range",
                return_value=hist,
            ),
            patch(
                "company.analysis.line.evaluate.service._fetch_index_day_range",
                return_value={
                    "code": "000001",
                    "name": "上证指数",
                    "source": "test",
                    "items": bars,
                },
            ) as fetch_idx,
            patch(
                "company.analysis.line.evaluate.service.compare_divergence",
                return_value=fake_div,
            ),
            patch(
                "company.analysis.line.evaluate.service._safe_paths",
                return_value=fake_paths,
            ),
            patch(
                "company.analysis.line.evaluate.service.score_low_point",
                return_value={"series": "close", "match": None, "analysis": {}},
            ),
        ):
            out = analyze_evaluate("600519", end="2026-01-09", lookback_days=60)
        self.assertTrue(out["found"])
        self.assertIn("divergence", out)
        self.assertIn("paths", out)
        self.assertNotIn("strength", out)
        self.assertNotIn("stock", out)  # 顶层不再挂个股 σ 块
        self.assertEqual(out["index"], "000001")
        self.assertEqual(out["divergence"]["score"], 50.0)
        self.assertEqual(out["paths"]["stock"]["paths"]["close"], "上行")
        self.assertNotIn("stats", out["divergence"])
        fetch_idx.assert_called_once()

    def test_analyze_evaluate_reuses_index_hist(self) -> None:
        bars = [
            _bar("2026-01-05", 10.0),
            _bar("2026-01-06", 10.2),
            _bar("2026-01-07", 10.1),
            _bar("2026-01-08", 10.3),
            _bar("2026-01-09", 10.2),
        ]
        hist = {"items": bars, "name": "测试", "source": "test"}
        index_hist = {
            "code": "000001",
            "name": "上证指数",
            "source": "prefetch",
            "items": [
                _bar("2026-01-05", 100.0),
                _bar("2026-01-06", 100.2),
                _bar("2026-01-07", 99.8),
                _bar("2026-01-08", 100.1),
                _bar("2026-01-09", 100.0),
            ],
        }
        with (
            patch(
                "company.analysis.line.evaluate.service._fetch_day_range",
                return_value=hist,
            ),
            patch(
                "company.analysis.line.evaluate.service._fetch_index_day_range",
            ) as fetch_idx,
            patch(
                "company.analysis.line.evaluate.service.score_low_point",
                return_value={"series": "close", "match": None, "analysis": {}},
            ),
        ):
            out = analyze_evaluate(
                "600519",
                end="2026-01-09",
                lookback_days=60,
                index_hist=index_hist,
            )
        self.assertTrue(out["found"])
        fetch_idx.assert_not_called()
        self.assertEqual(out["paths"]["index"]["source"], "prefetch")
        self.assertIsInstance(out["divergence"].get("score"), (int, float))

    def test_analyze_evaluate_miss_skips_extrema_refetch(self) -> None:
        # 最新日相对前收已超 ±9%，快筛未命中，不应再为极值补拉五年
        bars = [
            _bar("2026-01-05", 10.0),
            _bar("2026-01-06", 12.0),
        ]
        hist = {"items": bars, "name": "测试", "source": "test"}
        with patch(
            "company.analysis.line.evaluate.service._fetch_day_range",
            return_value=hist,
        ) as fetch_day:
            out = analyze_evaluate("600519", end="2026-01-06", lookback_days=60)
        self.assertFalse(out["found"])
        self.assertEqual(fetch_day.call_count, 1)
        fetch_day.assert_called_once()
        kwargs = fetch_day.call_args.kwargs
        self.assertEqual(kwargs.get("end_iso"), "2026-01-06")


class PathWireTests(unittest.TestCase):
    def test_pct_series_extracts_factor(self) -> None:
        window = {
            "days": [
                {"date": "2026-01-06", "pct": {"close": 0.01, "high": 0.02}},
                {"date": "2026-01-07", "pct": {"close": None, "high": 0.03}},
                {"date": "2026-01-08", "pct": {"close": 0.04}},
            ]
        }
        dates, pcts = _pct_series(window, factor="close")
        self.assertEqual(dates, ["2026-01-06", "2026-01-08"])
        self.assertEqual(pcts, [0.01, 0.04])

    def test_path_labels_from_volatility(self) -> None:
        bars = [
            _bar("2026-01-05", 10.0),
            _bar("2026-01-06", 10.5),
            _bar("2026-01-07", 10.8),
            _bar("2026-01-08", 11.0),
        ]
        vol = compute_volatility(bars, "2026-01-06", "2026-01-08", path_eps=0.0)
        labels = _path_labels(vol)
        for key in ("open", "high", "low", "close"):
            self.assertIn(key, labels)
            self.assertIn(
                labels[key],
                {"上行", "下行", "冲高回落", "探底回升", "横盘", "unknown"},
            )

    def test_safe_paths_includes_stock_and_index(self) -> None:
        bars = [
            _bar("2026-01-05", 10.0),
            _bar("2026-01-06", 10.5),
            _bar("2026-01-07", 10.8),
            _bar("2026-01-08", 11.0),
        ]
        index_bars = [
            _bar("2026-01-05", 100.0),
            _bar("2026-01-06", 100.2),
            _bar("2026-01-07", 100.1),
            _bar("2026-01-08", 100.3),
        ]
        with patch(
            "company.analysis.line.evaluate.service._fetch_index_day_range",
            return_value={
                "code": "000001",
                "name": "上证指数",
                "source": "test",
                "items": index_bars,
            },
        ):
            out = _safe_paths(
                bars,
                "000001",
                beg="2026-01-06",
                end="2026-01-08",
                stock_code="600519",
                stock_name="测试",
            )
        self.assertIsNone(out.get("error"))
        self.assertEqual(out["stock"]["code"], "600519")
        self.assertEqual(out["index"]["code"], "000001")
        self.assertEqual(out["stock"]["paths"]["close"] in {
            "上行", "下行", "冲高回落", "探底回升", "横盘", "unknown"
        }, True)

    def test_safe_paths_on_error(self) -> None:
        with patch(
            "company.analysis.line.evaluate.service.compute_volatility",
            side_effect=RuntimeError("boom"),
        ):
            out = _safe_paths(
                [_bar("2026-01-06", 10.0)],
                "000001",
                beg="2026-01-06",
                end="2026-01-08",
            )
        self.assertEqual(out["stock"]["paths"]["close"], "unknown")
        self.assertIn("boom", out["error"])


if __name__ == "__main__":
    unittest.main()
