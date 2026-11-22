"""macd screen 精简行单元测试。"""

from __future__ import annotations

import unittest

from analysis.macd.screen import slim_row
from analysis.recent_low.screen import is_eligible_stock


class UniverseFilterTests(unittest.TestCase):
    def test_eligible_excludes_boards_st_delisted(self) -> None:
        self.assertTrue(is_eligible_stock({"code": "600519", "name": "贵州茅台"}))
        self.assertFalse(is_eligible_stock({"code": "300750", "name": "宁德时代"}))
        self.assertFalse(is_eligible_stock({"code": "688981", "name": "中芯国际"}))
        self.assertFalse(is_eligible_stock({"code": "600000", "name": "ST示例"}))
        self.assertFalse(is_eligible_stock({"code": "600001", "name": "退市示例"}))


class SlimRowTests(unittest.TestCase):
    def test_found_row(self) -> None:
        pack = {
            "found": True,
            "code": "600519",
            "name": "贵州茅台",
            "index": "000001",
            "range": {"beg": "2026-01-01", "end": "2026-01-09", "count": 7},
            "macd": {
                "cross": {
                    "primary": "水下金叉",
                    "signals": ["水下金叉"],
                    "date": "2026-01-09",
                    "dif": -0.9,
                    "dea": -1.0,
                    "underwater": True,
                },
                "latest": {"dif": -0.9, "dea": -1.0},
            },
            "score": {
                "score_close": 80.0,
                "score_low": 60.0,
                "score_prior": 70.0,
                "div_score": 20.0,
                "score_total": 55.0,
            },
            "divergence": {
                "reverse_count": 2,
                "score": 20.0,
                "index": {"name": "上证指数"},
            },
            "low_point_close": {"date": "2026-01-03", "price": 1600.0},
            "low_point_low": {"date": "2026-01-02", "price": 1580.0},
        }
        row = slim_row(pack)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["code"], "600519")
        self.assertEqual(row["macd_signal"], "水下金叉")
        self.assertEqual(row["score_total"], 55.0)
        self.assertEqual(row["reverse_count"], 2)
        self.assertEqual(row["count"], 7)

    def test_not_found(self) -> None:
        self.assertIsNone(slim_row({"found": False, "code": "600519"}))


if __name__ == "__main__":
    unittest.main()
