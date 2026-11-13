"""recent_low screen 精简行 / 宇宙过滤单元测试。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from analysis.recent_low.screen import (
    _analyze_one,
    is_delisted,
    is_eligible_stock,
    slim_row,
)


class UniverseFilterTests(unittest.TestCase):
    def test_delisted_names(self) -> None:
        self.assertTrue(is_delisted("退市整理"))
        self.assertTrue(is_delisted("某某退"))
        self.assertFalse(is_delisted("贵州茅台"))

    def test_eligible(self) -> None:
        self.assertTrue(is_eligible_stock({"code": "600519", "name": "贵州茅台"}))
        self.assertTrue(is_eligible_stock({"code": "002415", "name": "海康威视"}))
        self.assertFalse(is_eligible_stock({"code": "300750", "name": "宁德时代"}))
        self.assertFalse(is_eligible_stock({"code": "688981", "name": "中芯国际"}))
        self.assertFalse(is_eligible_stock({"code": "600000", "name": "ST示例"}))
        self.assertFalse(is_eligible_stock({"code": "600001", "name": "退市示例"}))
        self.assertFalse(is_eligible_stock({"code": "", "name": "空码"}))


class SlimRowTests(unittest.TestCase):
    def test_basic(self) -> None:
        pack = {
            "code": "600519",
            "name": "贵州茅台",
            "date": "2026-11-11",
            "prices": {"close": 1600.0, "low": 1580.0},
            "lookback": {
                "close": {
                    "days": 12,
                    "since": "2026-10-20",
                    "is_all_time_low": False,
                },
                "low": {
                    "days": 8,
                    "since": "2026-10-28",
                    "is_all_time_low": False,
                },
            },
        }
        row = slim_row(pack)
        assert row is not None
        self.assertEqual(row["code"], "600519")
        self.assertEqual(row["close_days"], 12)
        self.assertEqual(row["low_days"], 8)
        self.assertEqual(row["gap"], 4)
        self.assertEqual(row["close_since"], "2026-10-20")
        self.assertFalse(row["close_all_time"])

    def test_empty_pack(self) -> None:
        self.assertIsNone(slim_row({}))


class AnalyzeOneWireTests(unittest.TestCase):
    def test_passes_adjust(self) -> None:
        with patch(
            "analysis.recent_low.screen.analyze_recent_low",
            return_value={
                "code": "600519",
                "name": "贵州茅台",
                "date": "2026-11-11",
                "prices": {"close": 1.0, "low": 0.9},
                "lookback": {
                    "close": {"days": 3, "since": "2026-11-09", "is_all_time_low": False},
                    "low": {"days": 2, "since": "2026-11-10", "is_all_time_low": False},
                },
            },
        ) as mocked:
            row, err = _analyze_one(
                {"code": "600519", "name": "贵州茅台"},
                adjust="qfq",
            )
        self.assertIsNone(err)
        assert row is not None
        self.assertEqual(row["gap"], 1)
        self.assertEqual(mocked.call_args.kwargs.get("adjust"), "qfq")


if __name__ == "__main__":
    unittest.main()
