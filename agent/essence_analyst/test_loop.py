"""起草-质疑循环的纯函数测试，不调用大模型。"""

from __future__ import annotations

import unittest

from agent.essence_analyst.critic import apply_hard_rules, parse_critic
from agent.essence_analyst.layout import assemble_markdown
from agent.essence_analyst.stages import next_stage, route_after_advance, route_after_critique


class ParseCriticTest(unittest.TestCase):
    def test_json_fence(self):
        raw = """好的。\n```json\n{"verdict": "confirm", "issues": [], "required_fix": "", "search_query": "", "search_scope": "web"}\n```"""
        parsed = parse_critic(raw)
        self.assertEqual(parsed["verdict"], "confirm")

    def test_chinese_verdict(self):
        parsed = parse_critic('{"verdict": "不通过", "issues": ["没来源"]}')
        self.assertEqual(parsed["verdict"], "revise")
        self.assertEqual(parsed["issues"], ["没来源"])

    def test_need_evidence(self):
        parsed = parse_critic(
            '{"verdict": "need_evidence", "issues": ["缺使用场景"], "search_query": "客户 例子", "search_scope": "web"}'
        )
        self.assertEqual(parsed["verdict"], "need_evidence")
        self.assertEqual(parsed["search_query"], "客户 例子")

    def test_garbage_defaults_to_revise(self):
        parsed = parse_critic("我没法判断")
        self.assertEqual(parsed["verdict"], "revise")


class HardRulesTest(unittest.TestCase):
    def test_missing_source_blocks_confirm(self):
        parsed = apply_hard_rules(
            stage="explain",
            draft="这是卖酒的。",
            parsed={"verdict": "confirm", "issues": []},
        )
        self.assertEqual(parsed["verdict"], "revise")
        self.assertTrue(any("来源" in item for item in parsed["issues"]))

    def test_unofficial_on_businesses(self):
        parsed = apply_hard_rules(
            stage="businesses",
            draft="据雪球说公司做芯片。〔来源：雪球〕",
            parsed={"verdict": "confirm", "issues": []},
        )
        self.assertEqual(parsed["verdict"], "revise")

    def test_buffett_language_blocked(self):
        parsed = apply_hard_rules(
            stage="factors",
            draft="所有者盈余很高。〔来源：年报〕",
            parsed={"verdict": "confirm", "issues": []},
        )
        self.assertEqual(parsed["verdict"], "revise")
        self.assertTrue(any("巴菲特" in item for item in parsed["issues"]))

    def test_need_evidence_without_query_becomes_revise(self):
        parsed = apply_hard_rules(
            stage="explain",
            draft="卖酒。〔来源：年报〕",
            parsed={"verdict": "need_evidence", "issues": ["缺例子"], "search_query": ""},
        )
        self.assertEqual(parsed["verdict"], "revise")


class RouteTest(unittest.TestCase):
    def test_revise_goes_back_to_write(self):
        self.assertEqual(route_after_critique({"critique_verdict": "revise", "round": 1}), "write")

    def test_confirm_advances(self):
        self.assertEqual(route_after_critique({"critique_verdict": "confirm", "round": 1}), "advance")

    def test_need_evidence_searches(self):
        self.assertEqual(
            route_after_critique({"critique_verdict": "need_evidence", "round": 1, "extra_searches": 0}),
            "extra_search",
        )

    def test_need_evidence_without_quota_rewrites(self):
        self.assertEqual(
            route_after_critique({"critique_verdict": "need_evidence", "round": 1, "extra_searches": 1}),
            "write",
        )

    def test_exhausted_advances(self):
        self.assertEqual(route_after_critique({"critique_verdict": "exhausted", "round": 2}), "advance")

    def test_advance_to_web_before_explain(self):
        self.assertEqual(
            route_after_advance({"stage": "explain", "web_fetched": False, "all_done": False}),
            "fetch_web",
        )

    def test_advance_does_not_fetch_financials(self):
        self.assertEqual(
            route_after_advance({"stage": "factors", "web_fetched": True, "all_done": False}),
            "write",
        )

    def test_all_done_assembles(self):
        self.assertEqual(route_after_advance({"stage": "factors", "all_done": True}), "assemble")

    def test_stage_order(self):
        self.assertEqual(next_stage("businesses"), "explain")
        self.assertEqual(next_stage("explain"), "factors")
        self.assertIsNone(next_stage("factors"))


class CompileGraphTest(unittest.TestCase):
    def test_graph_has_writer_and_critic(self):
        from agent.essence_analyst.graph import compile_app

        app = compile_app()
        nodes = set(app.get_graph().nodes)
        self.assertTrue({"write", "critique", "extra_search", "advance", "fetch_web"} <= nodes)
        self.assertNotIn("fetch_financials", nodes)


class LayoutTest(unittest.TestCase):
    def test_three_chapters_no_buffett(self):
        report = assemble_markdown(
            {
                "stock_name": "测试",
                "stock_code": "000000",
                "data_cutoff": "2026-09-17",
                "market": "sse",
                "chapters": {
                    "businesses": "卖糖。〔来源：年报〕",
                    "explain": "食品厂付钱买糖。〔来源：年报〕",
                    "factors": "糖价。〔来源：年报〕",
                },
                "confirm_log": [
                    {"stage": "factors", "round": 1, "verdict": "confirm", "issues": []},
                ],
            }
        )
        self.assertIn("## 一、主营业务（官方）", report)
        self.assertIn("## 二、这些业务究竟干什么", report)
        self.assertIn("## 三、关键影响因素", report)
        self.assertNotIn("巴菲特", report)
        self.assertNotIn("所有者盈余", report)
        self.assertIn("质疑与确认记录", report)


if __name__ == "__main__":
    unittest.main()
