"""日线段划分纯函数单测（无网络）。"""

from __future__ import annotations

import datetime as dt
import unittest

from company.analysis.line.section.core import (
    DIR_DOWN,
    DIR_FLAT,
    DIR_UP,
    build_minimal_segments,
    compute_sections,
)


def _bars(closes: list[float]) -> list[dict]:
    base = dt.date(2024, 1, 2)
    out = []
    for i, c in enumerate(closes):
        d = (base + dt.timedelta(days=i)).strftime("%Y-%m-%d")
        out.append({"time": d, "open": c, "high": c, "low": c, "close": c})
    return out


class MinimalSegmentTests(unittest.TestCase):
    def test_chain_shares_endpoint(self) -> None:
        segs = build_minimal_segments(_bars([10, 11, 12, 11]))
        self.assertEqual(len(segs), 3)
        for a, b in zip(segs, segs[1:]):
            self.assertEqual(a["end_idx"], b["begin_idx"])
            self.assertEqual(a["end"], b["begin"])  # 闭区间共享端点

    def test_directions(self) -> None:
        segs = build_minimal_segments(_bars([10, 11, 10, 10]))
        self.assertEqual([s["direction"] for s in segs], [DIR_UP, DIR_DOWN, DIR_FLAT])

    def test_change_values(self) -> None:
        seg = build_minimal_segments(_bars([10, 11]))[0]
        self.assertAlmostEqual(seg["change_price"], 1.0)
        self.assertAlmostEqual(seg["change_pct"], 10.0)

    def test_too_few_bars(self) -> None:
        with self.assertRaises(ValueError):
            build_minimal_segments(_bars([10]))


class ComputeSectionsTests(unittest.TestCase):
    def test_merge_same_direction(self) -> None:
        out = compute_sections(_bars([10, 11, 12, 11, 9]), band_pct=0.05)
        self.assertEqual(out["run_count"], 2)
        self.assertEqual(
            [s["direction"] for s in out["segments"]], [DIR_UP, DIR_DOWN]
        )
        up, down = out["segments"]
        self.assertAlmostEqual(up["change_pct"], 20.0)
        self.assertAlmostEqual(down["change_pct"], -25.0)
        # 最终段 children 为 level 1 同向段
        self.assertEqual(up["children"][0]["level"], 1)

    def test_alternating_becomes_sideways(self) -> None:
        out = compute_sections(
            _bars([10.0, 10.2, 10.05, 10.15, 10.0, 10.3]), band_pct=0.05
        )
        self.assertEqual(out["segment_count"], 1)
        seg = out["segments"][0]
        self.assertEqual(seg["direction"], DIR_FLAT)
        self.assertEqual(seg["flag"], "横盘")
        self.assertAlmostEqual(seg["amplitude_pct"], 3.0)
        self.assertEqual(len(seg["children"]), 5)  # 5 个交替段作为子段

    def test_breakout_not_sideways(self) -> None:
        # 交替后向上突破带宽，应保留为趋势段而非横盘
        out = compute_sections(_bars([10.0, 10.2, 10.1, 11.0]), band_pct=0.05)
        self.assertTrue(all(s["direction"] != DIR_FLAT for s in out["segments"]))

    def test_empty(self) -> None:
        with self.assertRaises(ValueError):
            compute_sections([])


if __name__ == "__main__":
    unittest.main()
