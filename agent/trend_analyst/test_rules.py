"""趋势分析规则：只使用资金动向列表 + 分时成交列表。"""

from __future__ import annotations

import inspect
import unittest

from agent.tools import trend_data
from agent.trend_analyst import nodes
from agent.trend_analyst.rules import analyze_fund, analyze_ticks, build_verdict


def _deal(time: str, *, side: str, aggressor: str, amount: float) -> dict:
    return {
        "time": time,
        "side": side,
        "aggressor": aggressor,
        "amount": amount,
        "event_name": "测试",
        "price": 10.0,
        "volume_lots": amount / 1000,
    }


def _tick(time: str, *, side: str, volume: float, price: float = 10.0) -> dict:
    return {
        "time": time,
        "side_label": side,
        "volume": volume,
        "price": price,
        "amount": price * volume * 100,
    }


class TrendRulesTests(unittest.TestCase):
    def test_pack_builder_only_accepts_two_lists(self):
        params = inspect.signature(trend_data.build_trend_pack).parameters
        self.assertNotIn("fund_limit", params)
        self.assertNotIn("minute_klt", params)
        self.assertIn("min_deal_amount", params)

    def test_few_deals_are_watch(self):
        pack = {
            "big_deal": {
                "items": [
                    _deal("09:35:00", side="buy", aggressor="active", amount=400_000),
                    _deal("09:36:00", side="buy", aggressor="active", amount=400_000),
                ]
            }
        }
        fund = analyze_fund(pack)
        self.assertEqual(fund["label"], "观望")
        self.assertEqual(fund["big_deal_count"], 2)
        self.assertIsNone(fund.get("windows"))
        self.assertIsNone(fund.get("snapshot"))

    def test_balanced_active_is_wash(self):
        pack = {
            "big_deal": {
                "items": [
                    _deal("09:35:00", side="buy", aggressor="active", amount=1_000_000),
                    _deal("09:36:00", side="sell", aggressor="active", amount=950_000),
                    _deal("09:37:00", side="buy", aggressor="active", amount=1_000_000),
                    _deal("09:38:00", side="sell", aggressor="active", amount=980_000),
                    _deal("09:39:00", side="buy", aggressor="passive", amount=500_000),
                ]
            }
        }
        self.assertEqual(analyze_fund(pack)["label"], "对倒")

    def test_open_close_flip_is_divergence(self):
        pack = {
            "big_deal": {
                "items": [
                    _deal("09:35:00", side="buy", aggressor="active", amount=5_000_000),
                    _deal("09:40:00", side="buy", aggressor="active", amount=4_000_000),
                    _deal("14:40:00", side="sell", aggressor="active", amount=2_000_000),
                    _deal("14:50:00", side="sell", aggressor="active", amount=1_500_000),
                    _deal("10:30:00", side="buy", aggressor="passive", amount=300_000),
                ]
            }
        }
        self.assertEqual(analyze_fund(pack)["label"], "分歧")

    def test_net_active_buy_is_absorb(self):
        pack = {
            "big_deal": {
                "items": [
                    _deal("10:00:00", side="buy", aggressor="active", amount=3_000_000),
                    _deal("10:05:00", side="buy", aggressor="active", amount=2_000_000),
                    _deal("10:10:00", side="buy", aggressor="active", amount=2_000_000),
                    _deal("10:15:00", side="sell", aggressor="active", amount=500_000),
                    _deal("10:20:00", side="buy", aggressor="passive", amount=400_000),
                ]
            }
        }
        fund = analyze_fund(pack)
        self.assertEqual(fund["label"], "偏吸")
        self.assertGreater(fund["active_buy_share"], 0.7)

    def test_dump_plus_retail_buy_is_catching(self):
        pack = {
            "big_deal": {
                "items": [
                    _deal("10:00:00", side="sell", aggressor="active", amount=3_000_000),
                    _deal("10:05:00", side="sell", aggressor="active", amount=2_000_000),
                    _deal("10:10:00", side="sell", aggressor="active", amount=2_000_000),
                    _deal("10:15:00", side="buy", aggressor="active", amount=400_000),
                    _deal("10:20:00", side="sell", aggressor="passive", amount=400_000),
                ]
            },
            "ticks": {
                "pre_price": 10.0,
                "last_price": 9.9,
                "items": [
                    _tick("10:01:00", side="buy", volume=10) for _ in range(40)
                ]
                + [_tick("10:02:00", side="sell", volume=10) for _ in range(10)],
            },
        }
        fund = analyze_fund(pack)
        ticks = analyze_ticks(pack, fund)
        verdict = build_verdict(fund, ticks)
        self.assertEqual(fund["label"], "偏抛")
        self.assertEqual(ticks["stance"], "偏买")
        self.assertEqual(ticks["relation_to_main"], "接盘")
        self.assertEqual(verdict["lean"], "谨慎偏空")
        self.assertNotIn("主力净额", str(verdict))

    def test_stats_section_has_no_eastmoney_windows(self):
        pack = {
            "big_deal": {
                "items": [
                    _deal("10:00:00", side="buy", aggressor="active", amount=3_000_000),
                    _deal("10:05:00", side="buy", aggressor="active", amount=2_000_000),
                    _deal("10:10:00", side="buy", aggressor="active", amount=2_000_000),
                    _deal("10:15:00", side="sell", aggressor="active", amount=500_000),
                    _deal("10:20:00", side="buy", aggressor="passive", amount=400_000),
                ]
            },
            "ticks": {
                "pre_price": 10.0,
                "last_price": 10.2,
                "items": [_tick("10:01:00", side="buy", volume=20)],
            },
        }
        fund = analyze_fund(pack)
        ticks = analyze_ticks(pack, fund)
        text = nodes._stats_section({"main_force": fund, "retail": ticks})
        self.assertIn("四象限", text)
        self.assertIn("小单", text)
        self.assertNotIn("近5日", text)
        self.assertNotIn("当日快照", text)
        self.assertNotIn("分钟资金", text)
        self.assertNotIn("五档", text)


if __name__ == "__main__":
    unittest.main()
