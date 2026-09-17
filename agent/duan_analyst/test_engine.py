"""段永平看业务规则引擎：长期毛利率、净现金、过滤器路由。"""

from __future__ import annotations

import unittest

from agent.duan_analyst.rules import engine as duan_engine


def _row(**overrides):
    base = {
        "PERIOD_LABEL": "2025年报",
        "TOTALOPERATEREVE": 100e8,
        "OPERATE_COST": 40e8,
        "XSMLL": 60.0,
        "XSJLL": 20.0,
        "PARENTNETPROFIT": 20e8,
        "ROEJQ": 25.0,
        "CONSTRUCT_LONG_ASSET": 1.1e8,
        "NETCASH_OPERATE": 22e8,
        "TOTAL_PARENT_EQUITY": 80e8,
        "TOTAL_ASSETS": 120e8,
        "LIABILITY": 40e8,
        "ZCFZL": 33.0,
    }
    base.update(overrides)
    return base


def _years(template_fn, n=5):
    rows = []
    for i in range(n):
        year = 2025 - i
        row = template_fn()
        row["PERIOD_LABEL"] = f"{year}年报"
        rows.append(row)
    return rows


class LongTermScreenTests(unittest.TestCase):
    def test_sees_like_company_is_good_hint(self):
        result = duan_engine.run_duan_screen(_years(lambda: _row()))
        self.assertEqual(result["numeric_hint"], duan_engine.HINT_GOOD)
        self.assertIn("毛利率", result["tables"]["long_term"])
        self.assertIn("60.00%", result["tables"]["long_term"])
        self.assertIn("计算公式", result["tables"]["long_term"])

    def test_airline_like_thin_margin_is_hard_hint(self):
        result = duan_engine.run_duan_screen(_years(lambda: _row(XSMLL=8.0, ZCFZL=80.0, LIABILITY=96e8)))
        self.assertEqual(result["numeric_hint"], duan_engine.HINT_HARD)
        self.assertTrue(any("毛利率" in f or "负债" in f for f in result["flags"]))

    def test_high_capex_good_cash_is_not_hard(self):
        """台积电式：重资本开支但毛利厚、现金好，不能据此判苦生意。"""
        result = duan_engine.run_duan_screen(
            _years(lambda: _row(CONSTRUCT_LONG_ASSET=25e8, NETCASH_OPERATE=40e8, XSMLL=50.0))
        )
        self.assertEqual(result["numeric_hint"], duan_engine.HINT_GOOD)
        self.assertFalse(any("辛苦" in f for f in result["flags"]))

    def test_insufficient_sample_is_thin(self):
        result = duan_engine.run_duan_screen([_row()])
        self.assertEqual(result["numeric_hint"], duan_engine.HINT_THIN)
        self.assertEqual(duan_engine.hint_to_fallback_verdict(result["numeric_hint"]), duan_engine.WEAK)


class FilterRoutingTests(unittest.TestCase):
    def test_parse_filter_verdict(self):
        text = "差异化不够。\n过滤器判决：离开\n本章小结：先走。"
        self.assertEqual(duan_engine.parse_filter_verdict(text), duan_engine.REJECT)

    def test_business_reject_stops(self):
        self.assertFalse(duan_engine.should_continue_after_business("离开"))
        self.assertFalse(duan_engine.should_continue_after_business("看不懂"))
        self.assertTrue(duan_engine.should_continue_after_business("通过"))
        self.assertTrue(duan_engine.should_continue_after_business("存疑"))

    def test_final_attitude_cannot_override_leave(self):
        self.assertEqual(
            duan_engine.resolve_final_attitude("离开", "通过", "便宜"),
            "离开",
        )
        self.assertEqual(
            duan_engine.resolve_final_attitude("看不懂", "通过", "便宜"),
            "看不懂",
        )
        self.assertEqual(
            duan_engine.resolve_final_attitude("通过", "通过", "贵"),
            "等待好价钱",
        )
        self.assertEqual(
            duan_engine.resolve_final_attitude("通过", "存疑", "还行"),
            "可以毛估估",
        )


if __name__ == "__main__":
    unittest.main()
