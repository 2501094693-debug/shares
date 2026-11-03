"""日线局部极值点纯函数单测（无网络）。

口径说明（与 ``service.py`` 一致）：

- 相邻比较允许相等；
- 端点只有一个邻居，按「只检测一侧」参与判定，因此序列首尾也可能成为极值；
- ``compute_local_extrema`` 返回 raw 序列（不合并连续同类型）；
- ``compute_alternating_extrema`` 会合并连续同类型极值，输出严格交替序列。
"""

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
        # 1, 3, 2, 4, 1 -> 谷@0(端点)、峰@1、谷@2、峰@3、谷@4(端点)
        out = compute_local_extrema(_bars([1, 3, 2, 4, 1]))
        self.assertEqual([e["index"] for e in out["extrema"]], [0, 1, 2, 3, 4])
        self.assertEqual(
            [e["type"] for e in out["extrema"]],
            ["trough", "peak", "trough", "peak", "trough"],
        )
        self.assertEqual(out["peak_count"], 2)
        self.assertEqual(out["trough_count"], 3)

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
        peak = [e for e in out["extrema"] if e["type"] == "peak"][0]
        self.assertEqual(peak["index"], 2)
        self.assertEqual(peak["left_span"], 2)
        self.assertEqual(peak["right_span"], 2)
        self.assertEqual(peak["span_days"], 5)

    def test_trough_span(self) -> None:
        # 5, 4, 1, 4, 5 -> 谷@2 值 1：左右各 2 天不更低
        out = compute_local_extrema(_bars([5, 4, 1, 4, 5]))
        trough = [e for e in out["extrema"] if e["type"] == "trough"][0]
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
        # 1,2,2,2,1：raw 不合并，平台三点各自成峰；交替序列合并为单个峰@1
        raw = compute_local_extrema(_bars([1, 2, 2, 2, 1]))
        self.assertEqual(
            [e["index"] for e in raw["extrema"] if e["type"] == "peak"],
            [1, 2, 3],
        )

        out = compute_alternating_extrema(_bars([1, 2, 2, 2, 1]))
        peaks = [e for e in out["extrema"] if e["type"] == "peak"]
        self.assertEqual([e["index"] for e in peaks], [1])
        peak = peaks[0]
        # 代表点取平台第一天；跨度覆盖整段平台
        self.assertEqual(peak["price"], 2.0)
        self.assertEqual(peak["left_span"], 1)
        self.assertEqual(peak["right_span"], 3)
        self.assertEqual(peak["span_days"], 5)

    def test_monotonic_only_endpoints(self) -> None:
        # 1,2,3,4,5：单调递增，中段无任何极值；端点按「只检测一侧」各成一个
        out = compute_local_extrema(_bars([1, 2, 3, 4, 5]))
        self.assertEqual(
            [(e["index"], e["type"]) for e in out["extrema"]],
            [(0, "trough"), (4, "peak")],
        )

    def test_endpoints_one_sided(self) -> None:
        # 端点只有一个邻居，仍参与判定：9,1,2,1 -> 峰@0、谷@1、峰@2、谷@3
        out = compute_local_extrema(_bars([9, 1, 2, 1]))
        self.assertEqual(
            [(e["index"], e["type"]) for e in out["extrema"]],
            [(0, "peak"), (1, "trough"), (2, "peak"), (3, "trough")],
        )

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_local_extrema([])

    def test_invalid_series_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_local_extrema(_bars([1, 2, 1]), series="foo")

    def test_smooth_runs(self) -> None:
        out = compute_local_extrema(_bars([1, 2, 1, 2, 1]), smooth_window=3)
        self.assertIsInstance(out["extrema"], list)

    def test_flat_valley_merged_single_trough(self) -> None:
        # 3,5,3,3,5,3：raw 里平台谷 2、3 各自成谷；交替序列合并为单个谷@2
        raw = compute_local_extrema(_bars([3, 5, 3, 3, 5, 3]))
        self.assertEqual(
            [e["index"] for e in raw["extrema"] if e["type"] == "trough"],
            [0, 2, 3, 5],
        )

        out = compute_alternating_extrema(_bars([3, 5, 3, 3, 5, 3]))
        self.assertEqual(
            [e["index"] for e in out["extrema"] if e["type"] == "peak"],
            [1, 4],
        )
        self.assertEqual(
            [e["index"] for e in out["extrema"] if e["type"] == "trough"],
            [0, 2, 5],
        )

    def test_fields_present(self) -> None:
        out = compute_local_extrema(_bars([1, 3, 2]))
        point = out["extrema"][0]
        for key in ("date", "price", "index", "left_span", "right_span", "span_days"):
            self.assertIn(key, point)

    def test_monotonic_with_plateau_equal_points(self) -> None:
        # 1,2,2,2,3：允许相等时平台点都满足峰/谷定义（相等时峰优先），
        # 交替序列合并相邻峰后为 谷@0、峰@1、谷@3、峰@4。
        out = compute_alternating_extrema(_bars([1, 2, 2, 2, 3]))
        self.assertEqual(
            [(e["index"], e["type"]) for e in out["extrema"]],
            [(0, "trough"), (1, "peak"), (3, "trough"), (4, "peak")],
        )


class ComputeAlternatingExtremaTests(unittest.TestCase):
    # P1 的极值（含端点）：峰@0、谷@4、峰@9、谷@14、峰@15、谷@16
    P1 = [5, 4, 3, 2, 1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1, 2, 1]

    def test_no_filtering_keeps_all(self) -> None:
        # 不做过滤：所有极值（含两端点）保留
        out = compute_alternating_extrema(_bars(self.P1))
        self.assertEqual([e["index"] for e in out["extrema"]], [0, 4, 9, 14, 15, 16])

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
        # 1,3,2,3,1 -> 谷@0、峰@1、谷@2、峰@3、谷@4，本身已交替，无合并
        prices = [1, 3, 2, 3, 1]
        out = compute_alternating_extrema(_bars(prices))
        self.assertEqual([e["index"] for e in out["extrema"]], [0, 1, 2, 3, 4])

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
        # 谷价 1..2 线性：最低 30、最高 0；两谷 side_days=left+right 同为 4 → 天数均满分
        seq = [
            {
                "type": "peak",
                "label": "波峰",
                "date": "2026-01-06",
                "price": 3.0,
                "index": 1,
                "left_span": 1,
                "right_span": 1,
                "span_days": 3,
            },
            {
                "type": "trough",
                "label": "波谷",
                "date": "2026-01-07",
                "price": 1.0,
                "index": 2,
                "left_span": 2,
                "right_span": 2,
                "span_days": 5,
            },
            {
                "type": "peak",
                "label": "波峰",
                "date": "2026-01-08",
                "price": 5.0,
                "index": 3,
                "left_span": 3,
                "right_span": 2,
                "span_days": 6,
            },
            {
                "type": "trough",
                "label": "波谷",
                "date": "2026-01-09",
                "price": 2.0,
                "index": 4,
                "left_span": 2,
                "right_span": 2,
                "span_days": 5,
            },
            {
                "type": "peak",
                "label": "波峰",
                "date": "2026-01-10",
                "price": 4.0,
                "index": 5,
                "left_span": 1,
                "right_span": 0,
                "span_days": 2,
            },
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
        self.assertAlmostEqual(by_idx[4]["score_price"], 0.0)
        self.assertEqual(by_idx[2]["side_days"], 4)
        self.assertEqual(by_idx[4]["side_days"], 4)
        self.assertAlmostEqual(by_idx[2]["score_days"], 30.0)
        self.assertAlmostEqual(by_idx[4]["score_days"], 30.0)

    def test_trough_gap_uses_both_peaks(self) -> None:
        # 天数 = left_span + right_span（日线扫到更低价），不再用左右峰下标差
        seq = [
            {
                "type": "peak",
                "label": "波峰",
                "date": "2026-01-06",
                "price": 10.0,
                "index": 0,
                "left_span": 0,
                "right_span": 1,
                "span_days": 2,
            },
            {
                "type": "trough",
                "label": "波谷",
                "date": "2026-01-08",
                "price": 5.0,
                "index": 2,
                "left_span": 2,
                "right_span": 3,
                "span_days": 6,
            },
            {
                "type": "peak",
                "label": "波峰",
                "date": "2026-01-11",
                "price": 20.0,
                "index": 5,
                "left_span": 1,
                "right_span": 0,
                "span_days": 2,
            },
        ]
        out = score_extrema(seq)
        t = out["trough_scores"][0]
        self.assertEqual(t["side_days"], 5)  # 2 + 3
        self.assertAlmostEqual(t["left_gap"], 0.5)  # (10-5)/10
        self.assertAlmostEqual(t["right_gap"], 0.75)  # (20-5)/20
        self.assertAlmostEqual(t["gap_max"], 0.75)
        # 单谷：价格/天数组内归一均满分 30；差距 0.75*40=30
        expect = 30.0 + 30.0 + 0.75 * 40.0
        self.assertAlmostEqual(t["score"], round(expect, 2))
        self.assertAlmostEqual(t["score_days"], 30.0)
        self.assertAlmostEqual(t["score_price"], 30.0)

    def test_side_days_from_daily_spans(self) -> None:
        # 5,4,1,4,5 → 谷@2：左右各 2 天不更低 → side_days=4
        out = compute_alternating_extrema(_bars([5, 4, 1, 4, 5]))
        troughs = out["trough_scores"]
        self.assertEqual(len(troughs), 1)
        self.assertEqual(troughs[0]["side_days"], 4)
        self.assertEqual(troughs[0]["span_days"], 5)


if __name__ == "__main__":
    unittest.main()
