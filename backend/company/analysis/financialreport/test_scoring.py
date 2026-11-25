"""财报连续打分单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.financialreport.scoring import (
    ASPECT_WEIGHTS,
    RISK_PER_HIT,
    blend,
    change_score,
    compute_scores,
    score_ocf_core_level,
    score_outlook_leg,
    sigmoid_score,
    weighted_total,
)


class SigmoidTests(unittest.TestCase):
    def test_midpoint_is_fifty(self) -> None:
        self.assertAlmostEqual(sigmoid_score(10, 10, 0.25), 50.0, places=6)

    def test_higher_and_lower_symmetric(self) -> None:
        hi = sigmoid_score(15, 10, 0.25, higher_is_better=True)
        lo = sigmoid_score(15, 10, 0.25, higher_is_better=False)
        self.assertAlmostEqual(hi + lo, 100.0, places=6)

    def test_change_flat_is_fifty(self) -> None:
        self.assertAlmostEqual(change_score(0.0, 0.5), 50.0, places=6)

    def test_lower_better_expense_drop_scores_above_fifty(self) -> None:
        # 费用率下降 delta=-2 → 低好变化分 > 50
        s = change_score(-2.0, 0.35, higher_is_better=False)
        self.assertIsNotNone(s)
        self.assertGreater(s, 50.0)


class BlendTests(unittest.TestCase):
    def test_blend_half(self) -> None:
        self.assertAlmostEqual(blend(80.0, 40.0), 60.0, places=6)

    def test_blend_missing_change_uses_level(self) -> None:
        self.assertAlmostEqual(blend(70.0, None), 70.0, places=6)

    def test_blend_missing_level_is_none(self) -> None:
        self.assertIsNone(blend(None, 70.0))


class OcfCoreQuadrantTests(unittest.TestCase):
    def test_positive_core_uses_ratio(self) -> None:
        score, ratio, note = score_ocf_core_level(110.0, 100.0)
        self.assertAlmostEqual(ratio, 110.0, places=6)
        self.assertEqual(note, "")
        self.assertIsNotNone(score)
        # 110 > x0=90 → 水平分 > 50
        self.assertGreater(score, 50.0)

    def test_negative_core_ocf_positive(self) -> None:
        score, ratio, note = score_ocf_core_level(50.0, -10.0)
        self.assertIsNone(ratio)
        self.assertAlmostEqual(score, 60.0, places=6)
        self.assertIn("60", note)

    def test_both_negative(self) -> None:
        score, ratio, note = score_ocf_core_level(-20.0, -10.0)
        self.assertIsNone(ratio)
        self.assertAlmostEqual(score, 25.0, places=6)
        self.assertIn("25", note)

    def test_missing(self) -> None:
        score, ratio, note = score_ocf_core_level(None, 10.0)
        self.assertIsNone(score)
        self.assertIsNone(ratio)
        self.assertEqual(note, "缺数据")


class OutlookLegTests(unittest.TestCase):
    def test_positive_prev_uses_yoy(self) -> None:
        score, rate, note = score_outlook_leg(110.0, 100.0)
        self.assertAlmostEqual(rate, 10.0, places=6)
        self.assertEqual(note, "")
        self.assertGreater(score, 50.0)

    def test_turnaround(self) -> None:
        score, rate, note = score_outlook_leg(1.0, -2.0)
        self.assertIsNone(rate)
        self.assertEqual(note, "扭亏")
        self.assertAlmostEqual(score, 75.0, places=6)

    def test_narrow_loss(self) -> None:
        score, rate, note = score_outlook_leg(-1.0, -5.0)
        self.assertEqual(note, "减亏")
        self.assertAlmostEqual(score, 65.0, places=6)

    def test_widen_loss(self) -> None:
        score, rate, note = score_outlook_leg(-8.0, -2.0)
        self.assertEqual(note, "扩亏")
        self.assertAlmostEqual(score, 25.0, places=6)

    def test_slip_to_loss(self) -> None:
        # 上期≤0 才走固定分；由零转亏
        score, rate, note = score_outlook_leg(-1.0, 0.0)
        self.assertEqual(note, "由零转亏")
        self.assertAlmostEqual(score, 20.0, places=6)

    def test_profit_to_loss_uses_yoy(self) -> None:
        # 上期>0 本期亏损：仍走普通同比（大幅为负 → 分低于 50）
        score, rate, note = score_outlook_leg(-1.0, 5.0)
        self.assertEqual(note, "")
        self.assertLess(rate, 0)
        self.assertLess(score, 50.0)


class WeightedTotalTests(unittest.TestCase):
    def test_full_weights(self) -> None:
        # 二~八 全 100 → 总分 100
        scores = [100.0] * 7
        self.assertEqual(weighted_total(scores), 100)

    def test_renormalize_when_missing(self) -> None:
        # 仅四看 20 权重有分 100，其余缺失 → 总分 100
        scores = [None, None, 100.0, None, None, None, None]
        self.assertEqual(weighted_total(scores), 100)

    def test_risk_deduction(self) -> None:
        # 3 项触发 → 100 - 37.5 = 62.5
        self.assertAlmostEqual(100.0 - RISK_PER_HIT * 3, 62.5, places=6)


def _row(
    *,
    rev: float = 1e9,
    cogs: float = 6e8,
    ocf: float = 1.5e8,
    roe: float = 12.0,
    total_assets: float = 2e9,
    total_liab: float = 8e8,
    equity: float = 1.2e9,
    core_extra: dict | None = None,
) -> dict:
    """构造足够跑通 compute_scores 的简化行（字段名对齐 metrics）。"""
    row = {
        "REPORT_DATE": "2024-12-31",
        "TOTAL_OPERATE_INCOME": rev,
        "OPERATE_COST": cogs,
        "OPERATE_TAX_ADD": 1e7,
        "SALE_EXPENSE": 3e7,
        "MANAGE_EXPENSE": 2e7,
        "RESEARCH_EXPENSE": 1e7,
        "FINANCE_EXPENSE": 5e6,
        "PARENT_NETPROFIT": 1e8,
        "DEDUCT_PARENT_NETPROFIT": 9e7,
        "NETCASH_OPERATE": ocf,
        "ROEJQ": roe,
        "TOTAL_ASSETS": total_assets,
        "TOTAL_LIABILITIES": total_liab,
        "TOTAL_EQUITY": equity,
        "MONETARYFUNDS": 2e8,
        "ACCOUNTS_RECE": 1e8,
        "INVENTORY": 1.5e8,
        "FIXED_ASSET": 5e8,
        "ACCOUNTS_PAYABLE": 1.2e8,
        "ADVANCE_RECEIVABLES": 5e7,
        "SHORT_LOAN": 3e7,
        "XSMLL": (rev - cogs) / rev * 100 if rev else None,
    }
    if core_extra:
        row.update(core_extra)
    return row


class ComputeScoresIntegrationTests(unittest.TestCase):
    def test_single_period_no_change_still_scores(self) -> None:
        from company.analysis.financialreport.metrics import compute_bundle

        series = [_row()]
        bundle = compute_bundle(series)
        out = compute_scores(series, bundle, risk_count=0)
        self.assertIsNotNone(out["score_total"])
        self.assertEqual(out["score_weights"], ASPECT_WEIGHTS)
        # 缺上期：变化缺失，仍有水平分 → 方面分存在
        value = next(a for a in out["aspects"] if a["key"] == "value")
        self.assertIsNotNone(value["score"])
        roe_m = value["metrics"][0]
        self.assertIsNotNone(roe_m["level_score"])
        self.assertIsNone(roe_m["change_score"])

    def test_two_periods_change_present(self) -> None:
        from company.analysis.financialreport.metrics import compute_bundle

        latest = _row(roe=15.0, rev=1.1e9, ocf=1.8e8)
        prev = _row(roe=10.0, rev=1.0e9, ocf=1.5e8)
        prev["REPORT_DATE"] = "2023-12-31"
        series = [latest, prev]
        bundle = compute_bundle(series)
        out = compute_scores(series, bundle, risk_count=0)
        value = next(a for a in out["aspects"] if a["key"] == "value")
        self.assertIsNotNone(value["metrics"][0]["change_score"])
        self.assertGreater(value["metrics"][0]["change_score"], 50.0)
        self.assertIsNotNone(value["level_score"])
        self.assertIsNotNone(value["change_score"])
        self.assertIsNotNone(out["score_level_total"])
        self.assertIsNotNone(out["score_change_total"])
        outlook = next(a for a in out["aspects"] if a["key"] == "outlook")
        self.assertIsNone(outlook["level_score"])
        self.assertIsNotNone(outlook["change_score"])
        risk = next(a for a in out["aspects"] if a["key"] == "risk")
        self.assertIsNotNone(risk["level_score"])
        self.assertIsNone(risk["change_score"])

    def test_risk_hits_deduct(self) -> None:
        from company.analysis.financialreport.metrics import compute_bundle

        series = [_row()]
        bundle = compute_bundle(series)
        out0 = compute_scores(series, bundle, risk_count=0)
        out3 = compute_scores(series, bundle, risk_count=3)
        risk0 = next(a for a in out0["aspects"] if a["key"] == "risk")
        risk3 = next(a for a in out3["aspects"] if a["key"] == "risk")
        self.assertAlmostEqual(risk0["score"], 100.0, places=6)
        self.assertAlmostEqual(risk3["score"], 100.0 - 3 * RISK_PER_HIT, places=6)

    def test_negative_core_ocf_quadrant_in_bundle(self) -> None:
        from company.analysis.financialreport.metrics import compute_bundle

        # 抬高费用使核心利润为负，同时 OCF 为正
        row = _row(rev=1e9, cogs=9e8, ocf=5e7)
        row["SALE_EXPENSE"] = 2e8
        row["MANAGE_EXPENSE"] = 1e8
        series = [row]
        bundle = compute_bundle(series)
        self.assertIsNotNone(bundle["profit"]["core_profit"])
        self.assertLess(bundle["profit"]["core_profit"], 0)
        out = compute_scores(series, bundle, risk_count=0)
        quality = next(a for a in out["aspects"] if a["key"] == "quality")
        ocf_m = next(m for m in quality["metrics"] if m["name"] == "OCF/核心利润")
        self.assertAlmostEqual(ocf_m["level_score"], 60.0, places=6)
        self.assertIsNone(ocf_m["value"])  # 无比率

    def test_build_summary_wires_score(self) -> None:
        from company.analysis.financialreport.metrics import compute_bundle
        from company.analysis.financialreport.views import build_summary

        latest = _row(roe=12.0)
        prev = _row(roe=10.0)
        prev["REPORT_DATE"] = "2023-12-31"
        series = [latest, prev]
        bundle = compute_bundle(series)
        summary = build_summary(series, bundle, coverage="同口径2期年报")
        self.assertIsNotNone(summary["score_total"])
        self.assertIsNotNone(summary["score_level_total"])
        self.assertIsNotNone(summary["score_change_total"])
        self.assertEqual(len(summary["dimensions"]), 8)
        self.assertEqual(len(summary["aspects"]), 8)
        # 评价列应为数字分（一看除外）
        self.assertTrue(str(summary["dimensions"][3][1]).isdigit() or summary["dimensions"][3][1] == "—")


if __name__ == "__main__":
    unittest.main()
