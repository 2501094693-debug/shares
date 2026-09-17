"""巴菲特读表报告固定骨架与空章节回退。"""

from __future__ import annotations

import unittest

from agent.buffett_analyst.layout import (
    has_prose,
    llm_text,
    normalize_section,
    render_section,
    rule_engine_fallback,
    strip_scaffold_headings,
)
from agent.buffett_analyst.nodes import _report_filename, assemble_report


class LayoutTests(unittest.TestCase):
    def test_strips_duplicate_headings(self):
        raw = """### 解读

### 解读

**1. 一句话**
卖糖果，毛利率 **60.00%**。

### 本章小结
能力圈内，能看懂。
"""
        body, summary = normalize_section(raw, "一、生意能否看懂")
        self.assertNotIn("### 解读", body)
        self.assertNotIn("## ", body)
        self.assertIn("60.00%", body)
        self.assertEqual(summary, "能力圈内，能看懂。")

    def test_strips_repeated_chapter_title(self):
        raw = """## 二、所有者盈余

### 解读

上沿 **20亿**，下沿 **19.9亿**。

### 本章小结
利润基本是现金。
"""
        body, summary = normalize_section(raw, "二、所有者盈余")
        self.assertNotIn("所有者盈余", body)
        self.assertNotIn("解读", body)
        self.assertIn("20亿", body)
        self.assertIn("现金", summary)

    def test_empty_llm_content_is_detected(self):
        self.assertFalse(has_prose(""))
        self.assertFalse(has_prose("### 解读\n\n### 本章小结\n"))
        self.assertTrue(
            has_prose(
                "1. 所有者盈余上沿 **20亿**，下沿 **19.9亿**，经营现金流覆盖净利润。\n本章小结：维持性投入接近折旧，利润基本是现金。"
            )
        )

    def test_llm_text_handles_list_blocks(self):
        self.assertEqual(llm_text(None), "")
        self.assertEqual(llm_text([]), "")
        self.assertEqual(llm_text([{"type": "text", "text": "上沿 20亿"}]), "上沿 20亿")

    def test_render_section_always_has_fixed_skeleton(self):
        messy = """### 二、所有者盈余

### 解读

上沿 **20亿**。

### 本章小结
上沿约等于报告盈利。
"""
        md = render_section(
            "二、所有者盈余",
            "| 报告期 | 上沿 |\n|---|---|\n| 2025年报 | 20亿 |",
            messy,
        )
        self.assertEqual(md.splitlines()[0], "## 二、所有者盈余")
        self.assertEqual(md.count("## 二、所有者盈余"), 1)
        self.assertEqual(md.count("### 原始数据"), 1)
        self.assertEqual(md.count("### 解读"), 1)
        self.assertEqual(md.count("### 本章小结"), 1)
        self.assertIn("20亿", md)

    def test_empty_section_keeps_skeleton_and_fallback(self):
        fallback = rule_engine_fallback("二、所有者盈余", "| 上沿 | 20亿 |", "")
        md = render_section("二、所有者盈余", "| 上沿 | 20亿 |", fallback)
        self.assertIn("### 解读", md)
        self.assertIn("### 本章小结", md)
        self.assertIn("模型未完成本节解读", md)
        self.assertIn("20亿", md)

    def test_assemble_report_uses_fixed_chapter_order(self):
        state = {
            "stock_name": "喜诗糖果",
            "stock_code": "000000",
            "industry": {"name": "食品"},
            "data_cutoff_date": "2026-09-17",
            "business_type": "伟大",
            "buffett_tables": {
                "owner_earnings": "| 上沿 | 20亿 |\n\n**计算公式**\n\n| 指标 | 计算公式 |\n|---|---|\n| 上沿 | (a)+(b)−(b) |",
                "capital": "| 有形ROE | 25% |",
                "allocation": "| 商誉 | 0 |",
                "diagnosis": "| 生意类型 | 伟大 |",
            },
            "buffett_flags": ["示例警示"],
            "buffett_summary": "生意类型：伟大",
            "sources_used": ["东方财富 F10", "东方财富盘口", "东方财富盘口", "申万行业"],
            "section_understand": "### 解读\n卖糖果。\n本章小结：能看懂。",
            "section_owner": "上沿 20亿。\n本章小结：利润是现金。",
            "section_capital": "",
            "section_honesty": "商誉为零。\n本章小结：记分卡干净。",
            "section_synthesis": "## 五、综合判决\n### 解读\n值得进一步研究。\n本章小结：伟大生意、价格另议。",
        }
        report = assemble_report(state)["final_report"]
        expected = [
            "## 一、生意能否看懂",
            "## 二、所有者盈余",
            "## 三、资本饥饿与四种生意",
            "## 四、会计诚实与资本配置",
            "## 五、综合判决",
        ]
        positions = [report.find(title) for title in expected]
        self.assertTrue(all(pos >= 0 for pos in positions))
        self.assertEqual(positions, sorted(positions))
        for title in expected:
            self.assertEqual(report.count(title), 1)
        capital_chunk = report[report.find("## 三、资本饥饿与四种生意") : report.find("## 四、会计诚实与资本配置")]
        self.assertIn("本节解读缺失", capital_chunk)
        owner_chunk = report[report.find("## 二、所有者盈余") : report.find("## 三、资本饥饿与四种生意")]
        self.assertIn("计算公式", owner_chunk)
        self.assertNotIn("核心利润", report)
        self.assertNotIn("两头吃", report)
        self.assertNotIn("三脱节", report)
        appendix = report[report.find("### 数据来源") :]
        self.assertEqual(appendix.count("- 东方财富盘口"), 1)
        self.assertIn("维持性资本开支 (c) 不可观测", appendix)

    def test_report_filename_does_not_double_code(self):
        self.assertEqual(
            _report_filename("药明康德", "药明康德", "603259", "20260917"),
            "药明康德_603259巴菲特读表_20260917.md",
        )
        self.assertEqual(
            _report_filename("药明康德_603259", "药明康德_603259", "603259", "20260917"),
            "药明康德_603259巴菲特读表_20260917.md",
        )

    def test_strip_keeps_substantive_subheads_as_bold(self):
        cleaned = strip_scaffold_headings("#### 1. 商誉规模\n商誉为零。", "四、会计诚实与资本配置")
        self.assertTrue(cleaned.startswith("**1. 商誉规模**"))
        self.assertIn("商誉为零", cleaned)


if __name__ == "__main__":
    unittest.main()
