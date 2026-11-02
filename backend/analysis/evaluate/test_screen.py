"""evaluate screen 精简行 / 宇宙过滤单元测试。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from analysis.evaluate.screen import (
    _analyze_one,
    is_chinext,
    is_eligible_stock,
    is_st,
    is_star,
    slim_row,
)


class UniverseFilterTests(unittest.TestCase):
    def test_chinext_codes(self) -> None:
        self.assertTrue(is_chinext("300750"))
        self.assertTrue(is_chinext("301234"))
        self.assertTrue(is_chinext("sz.300001"))
        self.assertFalse(is_chinext("600519"))
        self.assertFalse(is_chinext("000001"))
        self.assertFalse(is_chinext("002415"))

    def test_star_codes(self) -> None:
        self.assertTrue(is_star("688981"))
        self.assertTrue(is_star("689009"))
        self.assertTrue(is_star("sh.688111"))
        self.assertFalse(is_star("600519"))
        self.assertFalse(is_star("300750"))

    def test_st_names(self) -> None:
        self.assertTrue(is_st("ST明科"))
        self.assertTrue(is_st("*ST海航"))
        self.assertTrue(is_st("S*ST生物"))
        self.assertFalse(is_st("贵州茅台"))

    def test_eligible(self) -> None:
        self.assertTrue(is_eligible_stock({"code": "600519", "name": "贵州茅台"}))
        self.assertTrue(is_eligible_stock({"code": "002415", "name": "海康威视"}))
        self.assertFalse(is_eligible_stock({"code": "300750", "name": "宁德时代"}))
        self.assertFalse(is_eligible_stock({"code": "688981", "name": "中芯国际"}))
        self.assertFalse(is_eligible_stock({"code": "600000", "name": "ST示例"}))
        self.assertFalse(is_eligible_stock({"code": "", "name": "空码"}))


class SlimRowTests(unittest.TestCase):
    def test_found_row(self) -> None:
        pack = {
            "found": True,
            "code": "600519",
            "name": "贵州茅台",
            "range": {"beg": "2026-01-01", "end": "2026-01-09", "count": 7},
            "paths": {
                "stock": {
                    "code": "600519",
                    "name": "贵州茅台",
                    "paths": {
                        "open": "上行",
                        "high": "冲高回落",
                        "low": "探底回升",
                        "close": "上行",
                    },
                },
                "index": {
                    "code": "000001",
                    "name": "上证指数",
                    "paths": {
                        "open": "横盘",
                        "high": "上行",
                        "low": "下行",
                        "close": "横盘",
                    },
                },
            },
            "divergence": {"score": 50.0},
            "score": {"target": {"score": 88.0, "date": "2026-01-03"}},
            "low_point": {"date": "2026-01-03", "price": 1600.0},
        }
        row = slim_row(pack)
        assert row is not None
        self.assertEqual(row["code"], "600519")
        self.assertEqual(row["stock_path"]["close"], "上行")
        self.assertEqual(row["index_path"]["close"], "横盘")
        self.assertEqual(row["stock_path_close"], "上行")
        self.assertEqual(row["divergence"], 50.0)
        self.assertEqual(row["low_score"], 88.0)
        self.assertEqual(row["low_date"], "2026-01-03")
        self.assertEqual(row["index_name"], "上证指数")
        self.assertNotIn("days", row)
        self.assertNotIn("strength", row)

    def test_not_found(self) -> None:
        self.assertIsNone(slim_row({"found": False, "code": "600519"}))


class AnalyzeOneWireTests(unittest.TestCase):
    def test_passes_index_hist(self) -> None:
        index_hist = {"code": "000001", "items": [], "name": "上证指数"}
        with patch(
            "analysis.evaluate.screen.analyze_evaluate",
            return_value={"found": False},
        ) as mocked:
            row, err = _analyze_one(
                {"code": "600519", "name": "贵州茅台"},
                band=0.09,
                index="000001",
                factor="close",
                lookback_days=900,
                index_hist=index_hist,
            )
        self.assertIsNone(row)
        self.assertIsNone(err)
        self.assertIs(mocked.call_args.kwargs.get("index_hist"), index_hist)


if __name__ == "__main__":
    unittest.main()
