"""八看规则引擎：毛利率入表、二次加工公式。"""

from __future__ import annotations

import unittest

from agent.bazhang_analyst.rules import engine as zhang_engine


def _row(**overrides):
    base = {
        "PERIOD_LABEL": "2025年报",
        "TOTALOPERATEREVE": 100e8,
        "OPERATE_COST": 60e8,
        "OPERATE_TAX_ADD": 2e8,
        "SALE_EXPENSE": 3e8,
        "MANAGE_EXPENSE": 5e8,
        "RESEARCH_EXPENSE": 2e8,
        "FINANCE_EXPENSE": 1e8,
        "PARENTNETPROFIT": 20e8,
        "KCFJCXSYJLR": 18e8,
        "XSMLL": 40.0,
        "XSJLL": 20.0,
        "ROEJQ": 15.0,
        "ROIC": 12.0,
        "ACCOUNTS_RECE": 10e8,
        "INVENTORY": 12e8,
        "PREPAYMENT": 2e8,
        "ACCOUNTS_PAYABLE": 8e8,
        "ADVANCE_RECEIVABLES": 4e8,
        "FIXED_ASSET": 25e8,
        "TOTAL_ASSETS": 200e8,
        "TOTAL_EQUITY": 120e8,
        "LIABILITY": 80e8,
        "MONETARYFUNDS": 30e8,
        "SHORT_LOAN": 5e8,
    }
    base.update(overrides)
    return base


class EngineTableTests(unittest.TestCase):
    def test_core_profit_table_includes_disclosed_gross_margin(self):
        table = zhang_engine._core_profit_table([_row()])
        self.assertIn("毛利率", table.splitlines()[0])
        self.assertIn("40.00%", table)
        self.assertIn("计算公式", table)
        self.assertIn("核心利润", table)

    def test_core_profit_table_computes_gross_margin_when_undisclosed(self):
        table = zhang_engine._core_profit_table([_row(XSMLL=None)])
        self.assertIn("毛利率", table.splitlines()[0])
        self.assertIn("40.00%", table)

    def test_competitiveness_table_shows_two_ends_formula(self):
        table = zhang_engine._competitiveness_table([_row()])
        self.assertIn("两头吃指数", table)
        self.assertIn("计算公式", table)
        self.assertIn("(应付账款 + 预收款项/合同负债) ÷ (应收账款 + 预付款项)", table)
        self.assertIn("365 × 存货 ÷ 营业成本", table)
        self.assertIn("1.00x", table)

    def test_summary_mentions_gross_margin_and_two_ends_formula(self):
        result = zhang_engine.run_zhang_analysis([_row()])
        self.assertIn("毛利率 40.00%", result["text"])
        self.assertIn("＝(应付+预收)÷(应收+预付)", result["text"])
        self.assertIn("毛利率", result["tables"]["core_profit"])
        self.assertIn("计算公式", result["tables"]["competitiveness"])

    def test_uses_latest_interim_not_only_annual(self):
        semi_new = _row(
            PERIOD_LABEL="2026半年报",
            REPORT_DATE="2026-06-30",
            PARENTNETPROFIT=12e8,
            TOTALOPERATEREVE=60e8,
        )
        annual = _row(
            PERIOD_LABEL="2025年报",
            REPORT_DATE="2025-12-31",
            PARENTNETPROFIT=20e8,
        )
        semi_old = _row(
            PERIOD_LABEL="2025半年报",
            REPORT_DATE="2025-06-30",
            PARENTNETPROFIT=10e8,
            TOTALOPERATEREVE=50e8,
        )
        merged = [semi_new, annual, semi_old]
        selected = zhang_engine.select_periodic_rows(
            annual=[annual],
            recent=merged,
            merged=merged,
        )
        self.assertEqual([r["PERIOD_LABEL"] for r in selected], ["2026半年报", "2025半年报"])
        result = zhang_engine.run_zhang_analysis([annual], merged, merged=merged)
        self.assertEqual(result["metrics"]["latest_period"], "2026半年报")
        self.assertEqual(result["metrics"]["period_kind"], "半年报")
        self.assertTrue(result["metrics"]["ytd"])
        self.assertIn("2026半年报", result["tables"]["core_profit"])
        self.assertNotIn("2025年报", result["tables"]["core_profit"])
        self.assertIn("2025年报", result["tables"]["recent_all"])
        self.assertIn("2025半年报", result["tables"]["core_profit"])
        self.assertIn("annual_core", result["tables"])
        self.assertIn("2026半年报", result["text"])
        self.assertIn("核心利润（2026半年报）", result["text"])
        self.assertIn("不可与年报直接横比", result["text"])
        self.assertGreaterEqual(result["metrics"]["merged_count"], 3)


if __name__ == "__main__":
    unittest.main()
