"""DCF 增速推导与金融中介口径单测（无网络）。"""

from __future__ import annotations

import unittest

from company.analysis.valuation.dcf import (
    REVENUE_GROWTH_YEARS,
    VALUATION_MODE_FINANCIAL,
    VALUATION_MODE_INDUSTRIAL,
    _earnings_cagr,
    _revenue_cagr,
    dcf_valuate,
    is_financial_intermediary,
)


def _rows(*revenues: float) -> list[dict]:
    """构造降序年度序列（最新在前）。"""
    return [{"TOTALOPERATEREVE": r} for r in revenues]


def _earn_rows(*nets: float) -> list[dict]:
    return [{"PARENTNETPROFIT": n} for n in nets]


class RevenueGrowthTests(unittest.TestCase):
    def test_two_periods_equals_yoy(self) -> None:
        # 最新 120、最早 100 → 唯一一期 YoY = 20%
        g = _revenue_cagr(_rows(120.0, 100.0))
        self.assertIsNotNone(g)
        self.assertAlmostEqual(g, 0.20, places=6)

    def test_recent_weighs_more_than_old(self) -> None:
        # 路径：100 → 110 (+10%) → 132 (+20%)；最新在前 [132, 110, 100]
        # 权重：近 20%×2 + 远 10%×1 → (0.4+0.1)/3 = 1/6 ≈ 16.67%
        g = _revenue_cagr(_rows(132.0, 110.0, 100.0))
        self.assertIsNotNone(g)
        self.assertAlmostEqual(g, (0.20 * 2 + 0.10 * 1) / 3, places=6)

    def test_not_point_to_point_cagr(self) -> None:
        # 先暴涨再停滞：100 → 200 (+100%) → 200 (0%)；最新在前 [200, 200, 100]
        # 首尾 CAGR = (200/100)^(1/2)-1 ≈ 41.4%
        # 加权 YoY = (0%×2 + 100%×1)/3 ≈ 33.3%，应明显低于首尾 CAGR
        g = _revenue_cagr(_rows(200.0, 200.0, 100.0))
        self.assertIsNotNone(g)
        point_cagr = (200.0 / 100.0) ** 0.5 - 1.0
        self.assertAlmostEqual(g, (0.0 * 2 + 1.0 * 1) / 3, places=6)
        self.assertLess(g, point_cagr)

    def test_window_ignores_years_beyond_display(self) -> None:
        # 窗口内：均匀 +10%；窗口外塞极端暴涨，不得影响 g
        inside = [100.0 * (1.10**i) for i in range(REVENUE_GROWTH_YEARS - 1, -1, -1)]
        # inside 最新在前：… 100*1.10^(n-1), …, 100
        older_spike = [1.0]  # 极早一期极小 → 若被计入会把早期 YoY 拉到天文数字
        g_window = _revenue_cagr(_rows(*inside))
        g_with_older = _revenue_cagr(_rows(*inside, *older_spike))
        self.assertIsNotNone(g_window)
        self.assertIsNotNone(g_with_older)
        self.assertAlmostEqual(g_window, 0.10, places=6)
        self.assertAlmostEqual(g_with_older, g_window, places=6)

    def test_insufficient_returns_none(self) -> None:
        self.assertIsNone(_revenue_cagr([]))
        self.assertIsNone(_revenue_cagr(_rows(100.0)))


class FinancialIntermediaryTests(unittest.TestCase):
    def test_detect_futures_by_l3(self) -> None:
        self.assertTrue(
            is_financial_intermediary({"l1_name": "非银金融", "l3_name": "期货"})
        )

    def test_detect_bank_by_l1(self) -> None:
        self.assertTrue(is_financial_intermediary({"l1_name": "银行"}))

    def test_industrial_not_flagged(self) -> None:
        self.assertFalse(
            is_financial_intermediary({"l1_name": "食品饮料", "l3_name": "白酒"})
        )

    def test_earnings_cagr_weights_recent(self) -> None:
        # 100 → 110 (+10%) → 132 (+20%)
        g = _earnings_cagr(_earn_rows(132.0, 110.0, 100.0))
        self.assertIsNotNone(g)
        self.assertAlmostEqual(g, (0.20 * 2 + 0.10 * 1) / 3, places=6)

    def test_financial_mode_uses_net_profit_and_zero_net_debt(self) -> None:
        """模拟南华：虚高 OCF + 巨额客户货币资金，金融口径应压回净利润量级。"""
        metrics = {
            "cash": {
                "ocf": 70e8,
                "fcf": 69.7e8,
                "fcf_source": "ocf_minus_capex",
                "capex": 0.3e8,
            },
            "assets": {"cash": 403e8},
            "liabilities": {"financial_liabilities": 0.0, "total_liabilities": 598e8},
            "profit": {"net_profit": 4.86e8},
        }
        profile = {"price": 11.47, "total_shares": 7.18e8}
        industry = {"l1_name": "非银金融", "l2_name": "多元金融", "l3_name": "期货"}
        annual = _earn_rows(4.86e8, 4.58e8, 4.02e8, 2.46e8, 2.44e8)

        fin = dcf_valuate(
            metrics,
            profile=profile,
            annual_series=annual,
            industry=industry,
        )
        ind = dcf_valuate(metrics, profile=profile, annual_series=_rows(14e8, 13e8))

        self.assertEqual(fin.valuation_mode, VALUATION_MODE_FINANCIAL)
        self.assertAlmostEqual(fin.fcf_base or 0.0, 4.86e8, places=0)
        self.assertIsNotNone(fin.net_debt)
        self.assertAlmostEqual(fin.net_debt, 0.0, places=6)
        self.assertIsNotNone(fin.intrinsic_value_per_share)
        # 工业口径会被客户资金抬飞；金融口径应显著更低
        self.assertEqual(ind.valuation_mode, VALUATION_MODE_INDUSTRIAL)
        self.assertGreater(ind.fcf_base or 0.0, 50e8)
        self.assertLess(fin.intrinsic_value_per_share or 0.0, 40.0)
        self.assertLess(
            fin.intrinsic_value_per_share or 0.0,
            (ind.intrinsic_value_per_share or 0.0) * 0.3,
        )


if __name__ == "__main__":
    unittest.main()
