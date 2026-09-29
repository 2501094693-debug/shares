"""估值规则引擎：四路 × 三情景数字全部在此算出。"""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from agent.valuation_analyst.rules.engine import (
    PATH_LABELS,
    percentile,
    run_valuation,
)


def _day(offset: int) -> str:
    return (date(2026, 9, 1) - timedelta(days=offset)).isoformat()


def _history(*, years: int = 8, pe: float = 20.0, pb: float = 2.0, ps: float = 4.0) -> list[dict]:
    items = []
    # ~12 points/year so 10-year window has enough samples
    steps = years * 12
    for i in range(steps):
        items.append(
            {
                "time": _day(i * 30),
                "pe_ttm": pe + (i % 7) - 3,
                "pb": pb + (i % 5) * 0.1,
                "ps_ttm": ps + (i % 4) * 0.2,
            }
        )
    return items


def _stock(*, price=10.0, shares=1e9, pe=20.0, pb=2.0, ps=4.0) -> dict:
    mcap = price * shares
    return {
        "_price_raw": price,
        "_mcap_raw": mcap,
        "pe_ttm": pe,
        "pb": pb,
        "ps_ttm": ps,
        "total_share": shares,
    }


def _buffett(*, business="优秀", ni=5e8, deduct=4.8e8, fcf=3e8, revenue=4e9, oe_upper=5e8, oe_lower=3e8) -> dict:
    rows = []
    for i in range(5):
        rows.append(
            {
                "period": str(2024 - i),
                "a": ni * (1 - 0.03 * i),
                "deduct": deduct * (1 - 0.03 * i),
                "fcf": fcf,
                "revenue": revenue * (1 - 0.05 * i),
            }
        )
    return {
        "business_type": business,
        "metrics": {
            "business_type": business,
            "annual_periods": rows,
            "latest": {
                "oe_upper": oe_upper,
                "oe_lower": oe_lower,
                "da_disclosed": True,
                "fcf": fcf,
            },
        },
    }


class ValuationEngineTests(unittest.TestCase):
    def test_percentile_interpolates(self):
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2.5)
        self.assertEqual(percentile([10], 25), 10)

    def test_history_uses_p25_p50_p75(self):
        stock = _stock()
        out = run_valuation(stock, _history(), _buffett(), {})
        hist = {row["name"]: row for row in out["paths"]["history"]["scenarios"]}
        ni = stock["_mcap_raw"] / stock["pe_ttm"]
        self.assertAlmostEqual(hist["悲观"]["mcap"] / ni, out["stats"]["pe_ttm"]["p25"], places=4)
        self.assertAlmostEqual(hist["中性"]["mcap"] / ni, out["stats"]["pe_ttm"]["p50"], places=4)
        self.assertAlmostEqual(hist["乐观"]["mcap"] / ni, out["stats"]["pe_ttm"]["p75"], places=4)
        self.assertGreater(hist["乐观"]["mcap"], hist["悲观"]["mcap"])
        self.assertEqual(out["primary"], "PE_TTM")

    def test_financials_use_pb(self):
        out = run_valuation(_stock(), _history(), _buffett(), {"l2_name": "银行"})
        self.assertTrue(out["financial"])
        self.assertEqual(out["paths"]["history"]["primary"], "PB")
        self.assertEqual(out["paths"]["fundamentals"]["primary"], "PB")

    def test_poor_business_uses_ps(self):
        out = run_valuation(_stock(), _history(), _buffett(business="糟糕"), {})
        self.assertEqual(out["primary"], "PS_TTM")
        self.assertEqual(out["paths"]["history"]["primary"], "PS_TTM")

    def test_loss_switches_off_pe(self):
        stock = _stock(pe=-5.0)
        out = run_valuation(stock, _history(), _buffett(), {})
        self.assertFalse(out["pe_ok"])
        self.assertEqual(out["primary"], "PS_TTM")
        self.assertTrue(all(s.get("mcap") is not None for s in out["paths"]["history"]["scenarios"]))

    def test_formatted_profile_parses_yi(self):
        stock = {
            "price": "10.00",
            "total_market_cap": "100.00亿",
            "total_shares": "10.00亿",
            "pe_ttm": "20.00倍",
            "pb": "2.00",
            "ps_ttm": "4.00",
        }
        out = run_valuation(stock, _history(), _buffett(), {})
        self.assertAlmostEqual(out["snap"]["price"], 10.0)
        self.assertAlmostEqual(out["snap"]["mcap"], 1e10)
        self.assertAlmostEqual(out["snap"]["shares"], 1e9)
        self.assertAlmostEqual(out["snap"]["pe_ttm"], 20.0)

    def test_bare_market_cap_is_yi(self):
        stock = {
            "price": "10.00",
            "market_cap": "100.00",
            "total_shares": "10.00亿",
            "pe_ttm": "20.00",
            "pb": "2.00",
            "ps_ttm": "4.00",
        }
        out = run_valuation(stock, _history(), _buffett(), {})
        self.assertAlmostEqual(out["snap"]["mcap"], 1e10)
        self.assertAlmostEqual(out["snap"]["shares"], 1e9)

    def test_composite_anchor_is_market_median_not_buffett(self):
        out = run_valuation(_stock(), _history(), _buffett(oe_upper=1e11, oe_lower=8e10), {})
        mids = []
        for key in ("history", "fundamentals", "drivers"):
            for row in out["paths"][key]["scenarios"]:
                if row["name"] == "中性" and row.get("mcap"):
                    mids.append(row["mcap"])
        mids.sort()
        self.assertAlmostEqual(out["composite"]["anchor_mid_mcap"], mids[1], places=0)
        buffett_mid = next(s["mcap"] for s in out["paths"]["buffett"]["scenarios"] if s["name"] == "中性")
        self.assertNotAlmostEqual(out["composite"]["anchor_mid_mcap"], buffett_mid, places=0)
        self.assertEqual(out["composite"]["mos_floor_mcap"], buffett_mid)

    def test_not_understood_cannot_recommend_study(self):
        cheap = _stock(price=0.1)
        understood = run_valuation(cheap, _history(), _buffett(), {}, understood=True)
        blind = run_valuation(cheap, _history(), _buffett(), {}, understood=False)
        self.assertNotEqual(blind["composite"]["stance"], "值得进一步研究")
        self.assertIn(understood["composite"]["stance"], {"值得进一步研究", "观望", "回避"})

    def test_tables_cover_four_paths(self):
        out = run_valuation(_stock(), _history(), _buffett(), {})
        for key in PATH_LABELS:
            self.assertIn(key, out["tables"])
            self.assertIn("悲观", out["tables"][key])
        self.assertIn("综合锚", out["tables"]["overview"])
        self.assertIn("巴菲特安全边际下限", out["tables"]["overview"])

    def test_history_window_label_reflects_available_span(self):
        short = run_valuation(_stock(), _history(years=5), _buffett(), {})
        full = run_valuation(_stock(), _history(years=10), _buffett(), {})
        self.assertIn("源数据不足", short["history_window_label"])
        self.assertIn("源数据不足", short["text"])
        self.assertEqual(full["history_window_label"], "近10年")
        self.assertIn("#### 近10年分位", full["text"])


if __name__ == "__main__":
    unittest.main()
