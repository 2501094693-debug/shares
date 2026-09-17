"""巴菲特读表规则引擎：所有者盈余三列与生意分类。"""

from __future__ import annotations

import unittest

from agent.buffett_analyst.rules import engine as buffett_engine


def _row(**overrides):
    base = {
        "PERIOD_LABEL": "2025年报",
        "TOTALOPERATEREVE": 100e8,
        "OPERATE_COST": 40e8,
        "XSMLL": 60.0,
        "PARENTNETPROFIT": 20e8,
        "KCFJCXSYJLR": 19e8,
        "ROEJQ": 25.0,
        "FA_IR_DEPR": 1e8,
        "IA_AMORTIZE": 0.2e8,
        "LPE_AMORTIZE": 0.0,
        "CONSTRUCT_LONG_ASSET": 1.1e8,
        "NETCASH_OPERATE": 22e8,
        "TOTAL_PARENT_EQUITY": 80e8,
        "TOTAL_ASSETS": 120e8,
        "FIXED_ASSET": 8e8,
        "CIP": 0.0,
        "GOODWILL": 0.0,
        "INTANGIBLE_ASSET": 0.0,
        "ACCOUNTS_RECE": 4e8,
        "INVENTORY": 3e8,
        "PREPAYMENT": 0.0,
        "ACCOUNTS_PAYABLE": 5e8,
        "ADVANCE_RECEIVABLES": 2e8,
        "ASSIGN_CASH_DIVIDEND": 5e8,
        "SHARE_CAPITAL": 10e8,
        "ACCEPT_INVEST_CASH": 0.0,
    }
    base.update(overrides)
    return base


class OwnerEarningsTests(unittest.TestCase):
    def test_owner_earnings_band_for_sees_like_company(self):
        result = buffett_engine.run_buffett_analysis([_row()])
        latest = result["metrics"]["latest"]
        self.assertEqual(latest["a"], 20e8)
        self.assertAlmostEqual(latest["b"], 1.2e8)
        self.assertAlmostEqual(latest["oe_upper"], 20e8)
        self.assertAlmostEqual(latest["oe_lower"], 20e8 + 1.2e8 - 1.1e8)
        self.assertAlmostEqual(latest["fcf"], 22e8 - 1.1e8)
        self.assertAlmostEqual(latest["capex_da"], 1.1e8 / 1.2e8)
        self.assertEqual(result["business_type"], "伟大")
        table = result["tables"]["owner_earnings"]
        self.assertIn("所有者盈余上沿", table)
        self.assertIn("所有者盈余下沿", table)
        self.assertIn("OCF−资本开支", table)
        self.assertIn("计算公式", table)
        self.assertIn("20亿", table)

    def test_undisclosed_da_marks_lower_bound(self):
        row = _row()
        for key in ("FA_IR_DEPR", "IA_AMORTIZE", "LPE_AMORTIZE", "OILGAS_BIOLOGY_DEPR", "IR_DEPR"):
            row.pop(key, None)
        result = buffett_engine.run_buffett_analysis([row])
        latest = result["metrics"]["latest"]
        self.assertFalse(latest["da_disclosed"])
        self.assertIsNone(latest["oe_lower"])
        self.assertIn("未披露", result["tables"]["owner_earnings"])
        self.assertTrue(any("折旧摊销" in flag for flag in result["flags"]))

    def test_high_return_high_reinvestment_is_excellent(self):
        older = _row(
            PERIOD_LABEL="2024年报",
            PARENTNETPROFIT=12e8,
            TOTAL_PARENT_EQUITY=80e8,
            FIXED_ASSET=40e8,
            FA_IR_DEPR=5e8,
            IA_AMORTIZE=0.0,
            CONSTRUCT_LONG_ASSET=12e8,
            ROEJQ=20.0,
        )
        newer = _row(
            PERIOD_LABEL="2025年报",
            PARENTNETPROFIT=20e8,
            TOTAL_PARENT_EQUITY=100e8,
            FIXED_ASSET=60e8,
            FA_IR_DEPR=5e8,
            IA_AMORTIZE=0.0,
            CONSTRUCT_LONG_ASSET=12e8,
            ROEJQ=20.0,
        )
        result = buffett_engine.run_buffett_analysis([newer, older])
        self.assertEqual(result["business_type"], "优秀")
        incr = result["metrics"]["incremental"]["incremental_return"]
        self.assertIsNotNone(incr)
        self.assertGreater(incr, 15)

    def test_low_return_expansion_is_terrible(self):
        row = _row(
            PARENTNETPROFIT=3e8,
            ROEJQ=3.0,
            TOTAL_PARENT_EQUITY=100e8,
            FA_IR_DEPR=8e8,
            IA_AMORTIZE=0.0,
            CONSTRUCT_LONG_ASSET=20e8,
            FIXED_ASSET=50e8,
            TOTALOPERATEREVE=80e8,
            XSMLL=18.0,
        )
        result = buffett_engine.run_buffett_analysis([row])
        self.assertEqual(result["business_type"], "糟糕")
        self.assertTrue(any("糟糕" in flag for flag in result["flags"]))

    def test_tangible_roe_strips_goodwill(self):
        row = _row(
            PARENTNETPROFIT=10e8,
            TOTAL_PARENT_EQUITY=100e8,
            GOODWILL=40e8,
            INTANGIBLE_ASSET=10e8,
            ROEJQ=None,
        )
        result = buffett_engine.run_buffett_analysis([row])
        latest = result["metrics"]["latest"]
        self.assertAlmostEqual(latest["tangible_equity"], 50e8)
        self.assertAlmostEqual(latest["tangible_roe"], 20.0)

    def test_dollar_test_flags_share_dilution(self):
        older = _row(PERIOD_LABEL="2024年报", SHARE_CAPITAL=10e8, PARENTNETPROFIT=18e8, TOTAL_PARENT_EQUITY=70e8)
        newer = _row(PERIOD_LABEL="2025年报", SHARE_CAPITAL=13e8, PARENTNETPROFIT=20e8, TOTAL_PARENT_EQUITY=90e8)
        result = buffett_engine.run_buffett_analysis([newer, older])
        self.assertTrue(result["metrics"]["dollar"]["share_dilution"])
        self.assertTrue(any("股本" in flag for flag in result["flags"]))

    def test_public_rules_payload_is_json_serializable(self):
        import json

        from agent.buffett_rules_service import public_buffett_rules

        raw = buffett_engine.run_buffett_analysis([_row()])
        pack = public_buffett_rules(
            stock={"code": "600519", "name": "贵州茅台", "market": "sh"},
            engine=raw,
        )
        blob = json.dumps(pack, ensure_ascii=False)
        self.assertIn("伟大", pack["business_type"])
        self.assertIn("owner_earnings", pack["tables"])
        self.assertTrue(pack["data_available"])
        self.assertIn("600519", blob)

    def test_selects_latest_quarter_not_last_annual(self):
        q3_new = _row(PERIOD_LABEL="2025三季报", REPORT_DATE="2025-09-30", PARENTNETPROFIT=15e8)
        q3_old = _row(PERIOD_LABEL="2024三季报", REPORT_DATE="2024-09-30", PARENTNETPROFIT=12e8)
        annual = _row(PERIOD_LABEL="2024年报", REPORT_DATE="2024-12-31", PARENTNETPROFIT=20e8)
        rows = buffett_engine.select_periodic_rows(
            annual=[annual],
            recent=[q3_new, annual, q3_old],
            merged=[q3_new, annual, q3_old],
        )
        self.assertEqual([r["PERIOD_LABEL"] for r in rows], ["2025三季报", "2024三季报"])
        result = buffett_engine.run_buffett_analysis(
            [annual],
            [q3_new, annual, q3_old],
            merged=[q3_new, annual, q3_old],
        )
        self.assertEqual(result["metrics"]["latest_period"], "2025三季报")
        self.assertEqual(result["metrics"]["period_kind"], "三季报")
        self.assertTrue(result["metrics"]["ytd"])
        self.assertEqual(result["metrics"]["latest"]["a"], 15e8)
        self.assertTrue(any("三季报" in flag for flag in result["flags"]))
        self.assertIn("recent_all", result["tables"])
        self.assertGreaterEqual(result["metrics"]["merged_count"], 3)


class ProposedDividendTests(unittest.TestCase):
    def test_parses_assign_description_when_numeric_field_empty(self):
        row = _row()
        row.pop("ASSIGN_CASH_DIVIDEND", None)
        row["ASSIGNDSCRPT"] = "10派280.2423元(含税,扣税后252.2181元)"
        row["TOTAL_SHARE"] = 1250081601
        result = buffett_engine.run_buffett_analysis([row])
        expected = 1250081601 * (280.2423 / 10)
        self.assertAlmostEqual(result["metrics"]["latest"]["dividend"], expected, delta=1)
        self.assertIn("350.33亿", result["tables"]["allocation"])

    def test_no_distribution_is_zero_not_blank(self):
        row = _row()
        row.pop("ASSIGN_CASH_DIVIDEND", None)
        row["ASSIGNDSCRPT"] = "不分配不转增"
        result = buffett_engine.run_buffett_analysis([row])
        self.assertEqual(result["metrics"]["latest"]["dividend"], 0.0)
        self.assertIn("0", result["tables"]["allocation"])

    def test_numeric_field_wins_over_description(self):
        row = _row(ASSIGN_CASH_DIVIDEND=5e8, ASSIGNDSCRPT="10派280.2423元")
        result = buffett_engine.run_buffett_analysis([row])
        self.assertEqual(result["metrics"]["latest"]["dividend"], 5e8)

    def test_transfer_and_cash_scheme(self):
        row = _row()
        row.pop("ASSIGN_CASH_DIVIDEND", None)
        row["ASSIGNDSCRPT"] = "10转5派2元"
        row["TOTAL_SHARE"] = 1000
        self.assertAlmostEqual(buffett_engine._proposed_cash_dividend(row), 200.0)


if __name__ == "__main__":
    unittest.main()
