"""段永平看业务报告骨架与过滤器跳过。"""

from __future__ import annotations

import unittest

from agent.duan_analyst.graph import route_after_business, route_after_culture
from agent.duan_analyst.layout import (
    has_prose,
    llm_text,
    normalize_section,
    render_section,
    skipped_section,
)
from agent.duan_analyst.nodes import _report_filename, assemble_report


class LayoutTests(unittest.TestCase):
    def test_strips_duplicate_headings(self):
        raw = """### 解读

差异化是口味，5% 折扣换不走。

过滤器判决：通过

### 本章小结
生意模式过关。
"""
        body, summary = normalize_section(raw, "一、刮彩票：生意模式")
        self.assertNotIn("### 解读", body)
        self.assertIn("5%", body)
        self.assertEqual(summary, "生意模式过关。")

    def test_skipped_section_has_verdict(self):
        text = skipped_section("二、企业文化", "刮到谢字，不再往下刮。", "跳过")
        self.assertIn("过滤器判决：跳过", text)
        self.assertTrue(has_prose(text, "二、企业文化"))

    def test_llm_text_handles_list_blocks(self):
        self.assertEqual(llm_text(None), "")
        self.assertEqual(llm_text([{"type": "text", "text": "毛利率 60%"}]), "毛利率 60%")

    def test_render_section_always_has_fixed_skeleton(self):
        md = render_section(
            "一、刮彩票：生意模式",
            "| 报告期 | 毛利率 |\n|---|---|\n| 2025年报 | 60% |",
            "1. 卖糖果。\n过滤器判决：通过\n本章小结：过关。",
        )
        self.assertIn("## 一、刮彩票：生意模式", md)
        self.assertIn("### 原始数据", md)
        self.assertIn("### 解读", md)
        self.assertIn("### 本章小结", md)


class GraphRouteTests(unittest.TestCase):
    def test_reject_skips_culture(self):
        self.assertEqual(route_after_business({"business_verdict": "离开"}), "skip_after_business")
        self.assertEqual(route_after_business({"business_verdict": "通过"}), "filter_culture")

    def test_culture_reject_skips_price(self):
        self.assertEqual(route_after_culture({"culture_verdict": "看不懂"}), "skip_after_culture")
        self.assertEqual(route_after_culture({"culture_verdict": "存疑"}), "filter_price")


class AssembleTests(unittest.TestCase):
    def test_report_filename(self):
        self.assertEqual(
            _report_filename("贵州茅台", "600519", "600519", "20260917"),
            "贵州茅台_600519段永平看业务_20260917.md",
        )

    def test_assemble_keeps_filter_header(self):
        out = assemble_report(
            {
                "stock_name": "喜诗糖果",
                "stock_code": "000000",
                "industry": {},
                "data_cutoff_date": "2026-09-17",
                "numeric_hint": "数字上像好生意",
                "business_verdict": "通过",
                "culture_verdict": "通过",
                "price_verdict": "贵",
                "final_attitude": "等待好价钱",
                "section_business": "卖糖果。\n过滤器判决：通过\n本章小结：过关。",
                "section_culture": "本分。\n过滤器判决：通过\n本章小结：文化过关。",
                "section_price": "不便宜。\n价格判决：贵\n本章小结：等。",
                "section_synthesis": "能看懂。\n综合态度：等待好价钱\n本章小结：等好价钱。",
                "duan_tables": {"long_term": "表", "diagnosis": "诊断"},
                "duan_flags": [],
                "sources_used": ["东方财富 F10 定期报告"],
                "duan_summary": "数字提示：数字上像好生意",
            }
        )
        report = out["final_report"]
        self.assertIn("过滤器：生意模式 **通过**", report)
        self.assertIn("综合态度：**等待好价钱**", report)
        self.assertIn("## 一、刮彩票：生意模式", report)
        self.assertIn("必要条件", report)


if __name__ == "__main__":
    unittest.main()
