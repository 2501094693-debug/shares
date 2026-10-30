"""日线局部极值点纯函数单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.line.local_extrema.score import score_extrema
from company.analysis.line.local_extrema.service import (
    compute_alternating_extrema,
    compute_local_extrema,
)


def _bar(date: str, close: float, *, volume: float = 100.0) -> dict:
    return {
        "time": date,
        "open": close,
        "close": close,
        "high": close,
        "low": close,
        "volume": volume,
    }


def _bars(closes: list[float]) -> list[dict]:
    return [_bar(f"2026-01-{5 + i:02d}", float(c)) for i, c in enumerate(closes)]


class ComputeLocalExtremaTests(unittest.TestCase):
    def test_basic_peaks_troughs(self) -> None:
        # 1, 3, 2, 4, 1 -> 峰@1、谷@2、峰@3
        out = compute_local_extrema(_bars([1, 3, 2, 4, 1]))
        self.assertEqual([e["index"] for e in out["extrema"]], [1, 2, 3])
        self.assertEqual([e["type"] for e in out["extrema"]], ["peak", "trough", "peak"])
        self.assertEqual(out["peak_count"], 2)
        self.assertEqual(out["trough_count"], 1)

    def test_output_two_sequences(self) -> None:
        out = compute_local_extrema(_bars([1, 3, 2, 4, 1]))
        self.assertIn("extrema", out)
        self.assertIn("peak_scores", out)
        self.assertIn("trough_scores", out)
        self.assertNotIn("peaks", out)
        self.assertNotIn("troughs", out)
        self.assertNotIn("bands", out)

    def test_left_right_span(self) -> None:
        # 1, 2, 5, 2, 1 -> 峰@2 值 5：左右各 2 天不更高
        out = compute_local_extrema(_bars([1, 2, 5, 2, 1]))
        peak = out["extrema"][0]
        self.assertEqual(peak["index"], 2)
        self.assertEqual(peak["left_span"], 2)
        self.assertEqual(peak["right_span"], 2)
        self.assertEqual(peak["span_days"], 5)

    def test_trough_span(self) -> None:
        # 5, 4, 1, 4, 5 -> 谷@2 值 1：左右各 2 天不更低
        out = compute_local_extrema(_bars([5, 4, 1, 4, 5]))
        trough = out["extrema"][0]
        self.assertEqual(trough["index"], 2)
        self.assertEqual(trough["left_span"], 2)
        self.assertEqual(trough["right_span"], 2)

    def test_span_includes_equal(self) -> None:
        # 允许相等：跨度遇到相等仍计入，直到严格更高/更低才停
        # 4,5,4,5,4 -> 峰@1、谷@2、峰@3
        out = compute_local_extrema(_bars([4, 5, 4, 5, 4]))
        peak1 = [e for e in out["extrema"] if e["type"] == "peak" and e["index"] == 1][0]
        self.assertEqual(peak1["right_span"], 3)
        peak3 = [e for e in out["extrema"] if e["type"] == "peak" and e["index"] == 3][0]
        self.assertEqual(peak3["left_span"], 3)

    def test_plateau_merged_single_peak(self) -> None:
        # 平台 1,2,2,2,1：相同值合并后只取一个点 -> 单个波峰@1
        out = compute_local_extrema(_bars([1, 2, 2, 2, 1]))
        self.assertEqual([e["index"] for e in out["extrema"]], [1])
        peak = out["extrema"][0]
        # 代表点取平台第一天；跨度覆盖整段平台
        self.assertEqual(peak["price"], 2.0)
        self.assertEqual(peak["left_span"], 1)
        self.assertEqual(peak["right_span"], 3)
        self.assertEqual(peak["span_days"], 5)

    def test_monotonic_no_extrema(self) -> None:
        out = compute_local_extrema(_bars([1, 2, 3, 4, 5]))
        self.assertEqual(out["extrema"], [])

    def test_endpoints_ignored(self) -> None:
        # 端点只有一个邻居，不作为极值（即便它是全局最高/最低）
        out = compute_local_extrema(_bars([9, 1, 2, 1]))
        peak_idx = [e["index"] for e in out["extrema"] if e["type"] == "peak"]
        trough_idx = [e["index"] for e in out["extrema"] if e["type"] == "trough"]
        self.assertNotIn(0, peak_idx + trough_idx)
        self.assertNotIn(3, peak_idx + trough_idx)
        self.assertEqual(peak_idx, [2])
        self.assertEqual(trough_idx, [1])

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_local_extrema([])

    def test_invalid_series_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_local_extrema(_bars([1, 2, 1]), series="foo")

    def test_smooth_runs(self) -> None:
        out = compute_local_extrema(_bars([1, 2, 1, 2, 1]), smooth_window=3)
        self.assertIsInstance(out["extrema"], list)
        self.assertIsInstance(out["extrema"], list)

    def test_flat_valley_merged_single_trough(self) -> None:
        # 3,5,3,3,5,3：平台谷 3,3 合并后只取一个点 -> 单个波谷@2
        out = compute_local_extrema(_bars([3, 5, 3, 3, 5, 3]))
        self.assertEqual([e["index"] for e in out["extrema"] if e["type"] == "peak"], [1, 4])
        self.assertEqual([e["index"] for e in out["extrema"] if e["type"] == "trough"], [2])

    def test_fields_present(self) -> None:
        out = compute_local_extrema(_bars([1, 3, 2]))
        point = out["extrema"][0]
        for key in ("date", "price", "index", "left_span", "right_span", "span_days"):
            self.assertIn(key, point)

    def test_monotonic_with_plateau_no_extrema(self) -> None:
        # 1,2,2,2,3：平台合并后为 1,2,3 单调递增 -> 无极值
        out = compute_local_extrema(_bars([1, 2, 2, 2, 3]))
        self.assertEqual(out["extrema"], [])


class ComputeAlternatingExtremaTests(unittest.TestCase):
    # P1 的极值：谷@4、峰@9、谷@14、峰@15
    P1 = [5, 4, 3, 2, 1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1, 2, 1]

    def test_no_filtering_keeps_all(self) -> None:
        # 不做过滤：所有极值保留
        out = compute_alternating_extrema(_bars(self.P1))
        self.assertEqual([e["index"] for e in out["extrema"]], [4, 9, 14, 15])

    def test_default_no_min_fields(self) -> None:
        out = compute_alternating_extrema(_bars(self.P1))
        self.assertNotIn("min_side", out)
        self.assertNotIn("min_span_days", out)

    def test_strict_alternation_invariant(self) -> None:
        prices = [3, 5, 3, 3, 5, 3, 8, 2, 8, 2, 1, 6, 1]
        out = compute_alternating_extrema(_bars(prices))
        types = [e["type"] for e in out["extrema"]]
        for a, b in zip(types, types[1:]):
            self.assertNotEqual(a, b)

    def test_merge_consecutive_same_type(self) -> None:
        # 连续出现的同类型极值合并：峰取最高、谷取最低
        # 构造：1,3,2,3,1 -> 峰@1、峰@3（连续无谷）合并为峰@3（更高? 3 vs3 平手保留后者?）
        prices = [1, 3, 2, 3, 1]
        out = compute_alternating_extrema(_bars(prices))
        # 基础 extrema: 峰@1, 谷@2, 峰@3 -> 已交替，无合并
        self.assertEqual([e["index"] for e in out["extrema"]], [1, 2, 3])

    def test_fields_present(self) -> None:
        out = compute_alternating_extrema(_bars(self.P1))
        point = out["extrema"][0]
        for key in ("type", "label", "date", "price", "index", "left_span", "right_span", "span_days"):
            self.assertIn(key, point)

    def test_score_sequences_present(self) -> None:
        out = compute_alternating_extrema(_bars(self.P1))
        self.assertEqual(len(out["peak_scores"]), out["peak_count"])
        self.assertEqual(len(out["trough_scores"]), out["trough_count"])
        for row in out["peak_scores"] + out["trough_scores"]:
            for key in (
                "score",
                "score_price",
                "score_days",
                "score_gap",
                "side_days",
                "gap_mean",
            ):
                self.assertIn(key, row)


class ScoreExtremaTests(unittest.TestCase):
    def test_split_and_score(self) -> None:
        # 峰@1=3, 谷@2=1, 峰@3=5, 谷@4=2, 峰@5=4
        # 谷：1 比 2 更低 → rank1 价格分 30 > rank2 价格分 15
        seq = [
            {"type": "peak", "label": "波峰", "date": "2026-01-06", "price": 3.0, "index": 1, "span_days": 3},
            {"type": "trough", "label": "波谷", "date": "2026-01-07", "price": 1.0, "index": 2, "span_days": 3},
            {"type": "peak", "label": "波峰", "date": "2026-01-08", "price": 5.0, "index": 3, "span_days": 3},
            {"type": "trough", "label": "波谷", "date": "2026-01-09", "price": 2.0, "index": 4, "span_days": 3},
            {"type": "peak", "label": "波峰", "date": "2026-01-10", "price": 4.0, "index": 5, "span_days": 3},
        ]
        out = score_extrema(seq)
        self.assertEqual(len(out["peak_scores"]), 3)
        self.assertEqual(len(out["trough_scores"]), 2)
        by_peak = {r["index"]: r for r in out["peak_scores"]}
        self.assertEqual(by_peak[3]["price_rank"], 1)
        self.assertAlmostEqual(by_peak[3]["score_price"], 30.0)
        by_idx = {r["index"]: r for r in out["trough_scores"]}
        self.assertEqual(by_idx[2]["price_rank"], 1)
        self.assertEqual(by_idx[4]["price_rank"], 2)
        self.assertAlmostEqual(by_idx[2]["score_price"], 30.0)
        self.assertAlmostEqual(by_idx[4]["score_price"], 15.0)

    def test_trough_gap_uses_both_peaks(self) -> None:
        import math

        seq = [
            {"type": "peak", "label": "波峰", "date": "2026-01-06", "price": 10.0, "index": 0, "span_days": 2},
            {"type": "trough", "label": "波谷", "date": "2026-01-08", "price": 5.0, "index": 2, "span_days": 3},
            {"type": "peak", "label": "波峰", "date": "2026-01-11", "price": 20.0, "index": 5, "span_days": 2},
        ]
        out = score_extrema(seq)
        t = out["trough_scores"][0]
        self.assertEqual(t["side_days"], 5)  # 5 - 0
        self.assertAlmostEqual(t["left_gap"], 0.5)  # (10-5)/10
        self.assertAlmostEqual(t["right_gap"], 0.75)  # (20-5)/20
        self.assertAlmostEqual(t["gap_max"], 0.75)
        # 单谷 rank1 → 30；天数 (1-e^-5)*30；差距 0.75*40=30
        expect = 30.0 + (1.0 - math.exp(-5)) * 30.0 + 0.75 * 40.0
        self.assertAlmostEqual(t["score"], round(expect, 2))


if __name__ == "__main__":
    unittest.main()
