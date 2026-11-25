"""gene 纯函数单测（无网络）。"""

from __future__ import annotations

import unittest

from analysis.macd.signals import (
    SIGNAL_OVER_CROSS,
    SIGNAL_UNDER_CROSS,
    SIGNAL_UNDER_NEAR,
)
from company.analysis.line.gene.core import (
    analyze_gene_from_macd,
    find_dif_above_span,
    interval_close_extremes,
    nearest_prior_extrema,
    resolve_preset,
)


def _row(date: str, dif: float, dea: float, close: float) -> dict:
    return {
        "date": date,
        "dif": dif,
        "dea": dea,
        "macd": 2 * (dif - dea),
        "close": close,
        "price": close,
    }


class ResolvePresetTests(unittest.TestCase):
    def test_default_and_classic(self) -> None:
        key, f, s, sig = resolve_preset("10,20,7")
        self.assertEqual(key, "10,20,7")
        self.assertEqual((f, s, sig), (10, 20, 7))
        key2, f2, s2, sig2 = resolve_preset("12,26,9")
        self.assertEqual(key2, "12,26,9")
        self.assertEqual((f2, s2, sig2), (12, 26, 9))

    def test_invalid(self) -> None:
        with self.assertRaises(ValueError):
            resolve_preset("5,10,3")


class DifAboveSpanTests(unittest.TestCase):
    def test_from_cross_day(self) -> None:
        items = [
            _row("2026-01-08", -1.2, -1.0, 10.0),
            _row("2026-01-09", -0.9, -1.0, 10.5),  # 金叉
            _row("2026-01-10", -0.8, -0.95, 11.0),
            _row("2026-01-11", -1.1, -1.0, 10.2),  # 跌破
            _row("2026-01-12", -0.7, -0.9, 10.8),
        ]
        span = find_dif_above_span(items, 1, from_next=False)
        self.assertTrue(span["found"])
        self.assertEqual(span["beg"], "2026-01-09")
        self.assertEqual(span["end"], "2026-01-10")
        self.assertEqual(span["count"], 2)
        self.assertFalse(span["open_ended"])
        self.assertEqual(span["break_date"], "2026-01-11")
        self.assertEqual(span["observe_end_idx"], span["break_idx"])

    def test_from_near_improves_then_cross(self) -> None:
        # 信号日 spread=-0.05；次日 -0.02（仍<0 但更大）→ 继续；再下日翻正
        items = [
            _row("2026-01-08", -1.20, -1.0, 10.0),
            _row("2026-01-09", -1.05, -1.0, 10.0),  # 即将
            _row("2026-01-10", -1.02, -1.0, 10.2),  # 改善，继续
            _row("2026-01-11", -0.90, -1.0, 10.5),  # 翻正
            _row("2026-01-12", -0.85, -0.95, 11.0),
            _row("2026-01-13", -1.10, -1.0, 10.4),  # 跌破
        ]
        span = find_dif_above_span(items, 1, from_next=True)
        self.assertTrue(span["found"])
        self.assertTrue(span["near_ok"])
        self.assertEqual(span["beg"], "2026-01-09")  # 从即将日算起
        self.assertEqual(span["cross_date"], "2026-01-11")
        self.assertEqual(span["end"], "2026-01-12")
        self.assertFalse(span["open_ended"])
        self.assertEqual(span["break_date"], "2026-01-13")

    def test_from_near_fails_when_macd_worsens(self) -> None:
        # 信号日 spread=-0.05；次日 -0.08 → 走弱失败
        items = [
            _row("2026-01-08", -1.20, -1.0, 10.0),
            _row("2026-01-09", -1.05, -1.0, 10.1),  # 即将 spread=-0.05
            _row("2026-01-10", -1.08, -1.0, 10.0),  # spread=-0.08 < 基准
            _row("2026-01-11", -0.90, -1.0, 10.8),
        ]
        span = find_dif_above_span(items, 1, from_next=True)
        self.assertFalse(span["found"])
        self.assertIs(span["near_ok"], False)
        self.assertEqual(span["decide_date"], "2026-01-10")


class IntervalExtremesTests(unittest.TestCase):
    def test_gain_and_drop(self) -> None:
        items = [
            _row("2026-01-09", 0.1, 0.0, 10.0),
            _row("2026-01-10", 0.2, 0.0, 11.0),
            _row("2026-01-11", 0.15, 0.0, 9.5),
        ]
        out = interval_close_extremes(items, 0, 2, base_close=10.0)
        self.assertAlmostEqual(out["max_close_gain"], 0.1, places=6)
        self.assertEqual(out["max_close_date"], "2026-01-10")
        self.assertAlmostEqual(out["max_close_drop"], -0.05, places=6)
        self.assertEqual(out["max_close_drop_date"], "2026-01-11")


class AnalyzeGeneFromMacdTests(unittest.TestCase):
    def test_under_cross_event(self) -> None:
        items = [
            _row("2026-01-08", -1.2, -1.0, 10.0),
            _row("2026-01-09", -0.9, -1.0, 10.0),  # 水下金叉
            _row("2026-01-10", -0.8, -0.95, 11.0),
            _row("2026-01-11", -1.1, -1.0, 9.5),
        ]
        pack = analyze_gene_from_macd(items, "2026-01-08", "2026-01-11")
        self.assertEqual(pack["event_count"], 1)
        ev = pack["events"][0]
        self.assertEqual(ev["date"], "2026-01-09")
        self.assertEqual(ev["signal"], SIGNAL_UNDER_CROSS)
        self.assertEqual(ev["dif_above_beg"], "2026-01-09")
        self.assertEqual(ev["dif_above_end"], "2026-01-10")
        self.assertEqual(ev["break_date"], "2026-01-11")
        self.assertEqual(ev["break_close"], 9.5)
        self.assertAlmostEqual(ev["break_close_chg"], -0.05, places=6)
        self.assertAlmostEqual(ev["max_close_gain"], 0.1, places=6)
        # 观察终点含跌破日 9.5 → 最大跌 -5%
        self.assertAlmostEqual(ev["max_close_drop"], -0.05, places=6)
        self.assertEqual(ev["max_close_drop_date"], "2026-01-11")

    def test_under_near_then_cross(self) -> None:
        items = [
            _row("2026-01-08", -1.20, -1.0, 10.0),
            _row("2026-01-09", -1.05, -1.0, 10.0),  # 即将水下金叉
            _row("2026-01-10", -0.90, -1.0, 10.5),  # 翻正
            _row("2026-01-11", -0.80, -0.95, 11.0),
        ]
        pack = analyze_gene_from_macd(items, "2026-01-08", "2026-01-11")
        signals = [e["signal"] for e in pack["events"]]
        self.assertIn(SIGNAL_UNDER_NEAR, signals)
        self.assertIn(SIGNAL_UNDER_CROSS, signals)
        near = next(e for e in pack["events"] if e["signal"] == SIGNAL_UNDER_NEAR)
        self.assertTrue(near["near_ok"])
        self.assertFalse(near["judgment_failed"])
        self.assertEqual(near["dif_above_beg"], "2026-01-09")
        self.assertEqual(near["cross_date"], "2026-01-10")
        self.assertEqual(near["dif_above_end"], "2026-01-11")
        self.assertTrue(near["dif_above_open_ended"])
        self.assertIsNone(near["break_date"])
        self.assertIsNone(near["break_close_chg"])
        self.assertAlmostEqual(near["max_close_gain"], 0.1, places=6)

    def test_under_near_judgment_failed(self) -> None:
        items = [
            _row("2026-01-08", -1.20, -1.0, 10.0),
            _row("2026-01-09", -1.05, -1.0, 10.0),  # 即将 spread=-0.05
            _row("2026-01-10", -1.10, -1.0, 9.8),  # spread=-0.10 走弱 → 失败
            _row("2026-01-11", -0.90, -1.0, 11.0),
        ]
        pack = analyze_gene_from_macd(items, "2026-01-08", "2026-01-11")
        near = next(e for e in pack["events"] if e["signal"] == SIGNAL_UNDER_NEAR)
        self.assertTrue(near["judgment_failed"])
        self.assertIs(near["near_ok"], False)
        self.assertFalse(near["dif_above_found"])
        self.assertIsNone(near["max_close_gain"])
        self.assertEqual(near["decide_date"], "2026-01-10")

    def test_over_cross(self) -> None:
        items = [
            _row("2026-01-08", 0.8, 1.0, 20.0),
            _row("2026-01-09", 1.1, 1.0, 20.0),
            _row("2026-01-10", 1.2, 1.05, 21.0),
        ]
        pack = analyze_gene_from_macd(items, "2026-01-08", "2026-01-10")
        self.assertEqual(pack["events"][0]["signal"], SIGNAL_OVER_CROSS)
        self.assertTrue(pack["events"][0]["dif_above_open_ended"])

    def test_prior_extrema_attached(self) -> None:
        items = [
            _row("2026-01-08", -1.2, -1.0, 10.0),
            _row("2026-01-09", -0.9, -1.0, 10.5),  # 水下金叉
            _row("2026-01-10", -0.8, -0.95, 11.0),
            _row("2026-01-11", -1.1, -1.0, 9.5),
        ]
        extrema = [
            {"type": "trough", "date": "2026-01-05", "price": 9.0},
            {"type": "peak", "date": "2026-01-07", "price": 12.0},
            {"type": "trough", "date": "2026-01-10", "price": 8.0},  # 金叉后，应忽略
        ]
        pack = analyze_gene_from_macd(
            items, "2026-01-08", "2026-01-11", extrema=extrema, extrema_layers=3
        )
        ev = pack["events"][0]
        pe = ev["prior_extrema"]
        self.assertEqual(pe["peak_date"], "2026-01-07")
        self.assertEqual(pe["trough_date"], "2026-01-05")
        # |10.5-12|=1.5，|10.5-9|=1.5 → 相等，峰日期更近 → 近峰
        self.assertEqual(pe["closer"], "peak")
        self.assertAlmostEqual(pe["gap"], 10.5 - 12.0, places=6)
        self.assertEqual(pack["summary"]["prior_extrema"]["closer_peak_count"], 1)


class NearestPriorExtremaTests(unittest.TestCase):
    def test_closer_to_trough(self) -> None:
        extrema = [
            {"type": "peak", "date": "2026-01-01", "price": 20.0},
            {"type": "trough", "date": "2026-01-05", "price": 10.0},
            {"type": "peak", "date": "2026-01-08", "price": 15.0},
        ]
        out = nearest_prior_extrema(10.5, "2026-01-10", extrema)
        self.assertEqual(out["peak_date"], "2026-01-08")
        self.assertEqual(out["trough_date"], "2026-01-05")
        self.assertEqual(out["closer"], "trough")
        self.assertEqual(out["closer_label"], "波谷")
        self.assertAlmostEqual(out["gap"], 0.5, places=6)
        self.assertAlmostEqual(out["gap_pct"], 0.05, places=6)

    def test_ignores_same_day_and_later(self) -> None:
        extrema = [
            {"type": "trough", "date": "2026-01-09", "price": 9.0},
            {"type": "peak", "date": "2026-01-10", "price": 12.0},
            {"type": "trough", "date": "2026-01-11", "price": 8.0},
        ]
        out = nearest_prior_extrema(10.0, "2026-01-10", extrema)
        self.assertEqual(out["trough_date"], "2026-01-09")
        self.assertIsNone(out["peak_date"])
        self.assertEqual(out["closer"], "trough")

    def test_empty_when_no_prior(self) -> None:
        extrema = [{"type": "peak", "date": "2026-01-12", "price": 12.0}]
        out = nearest_prior_extrema(10.0, "2026-01-10", extrema)
        self.assertIsNone(out["closer"])
        self.assertIsNone(out["gap"])


if __name__ == "__main__":
    unittest.main()
