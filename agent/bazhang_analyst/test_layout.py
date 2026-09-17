"""八看报告固定骨架与空章节回退。"""

from __future__ import annotations

import unittest

from agent.bazhang_analyst.layout import (
    has_prose,
    llm_text,
    normalize_section,
    render_section,
    rule_engine_fallback,
    strip_scaffold_headings,
)
from agent.bazhang_analyst.nodes import _report_filename, assemble_report


class LayoutTests(unittest.TestCase):
    def test_strips_duplicate_headings(self):
        raw = """### 解读

### 解读

**1. 战略类型判定**
经营性资产占比 **77.23%**。

### 本章小结
经营主导型，聚焦主业。
"""
        body, summary = normalize_section(raw, "一看：战略——资源配置揭示什么？")
        self.assertNotIn("### 解读", body)
        self.assertNotIn("## ", body)
        self.assertIn("77.23%", body)
        self.assertEqual(summary, "经营主导型，聚焦主业。")

    def test_strips_repeated_chapter_title(self):
        raw = """## 八看：前景

### 解读

从资产结构看仍在扩张。

### 本章小结
扩张未停，需盯存货。
"""
        body, summary = normalize_section(raw, "八看：前景")
        self.assertNotIn("八看", body)
        self.assertNotIn("解读", body)
        self.assertIn("扩张", body)
        self.assertIn("存货", summary)

    def test_empty_llm_content_is_detected(self):
        self.assertFalse(has_prose(""))
        self.assertFalse(has_prose("### 解读\n\n### 本章小结\n"))
        self.assertTrue(
            has_prose(
                "1. ROE 为 **28.56%**，较上年 **16.78%** 明显抬升，主要来自净利率。\n本章小结：高回报来自利润率。"
            )
        )

    def test_llm_text_handles_list_blocks(self):
        self.assertEqual(llm_text(None), "")
        self.assertEqual(llm_text([]), "")
        self.assertEqual(llm_text([{"type": "text", "text": "ROE 28.56%"}]), "ROE 28.56%")

    def test_render_section_always_has_fixed_skeleton(self):
        messy = """### 四看：价值创造

### 解读

ROE **28.56%**，ROIC **24.30%**。

### 本章小结
价值创造能力强。
"""
        md = render_section(
            "四看：价值创造",
            "| 报告期 | ROE |\n|---|---|\n| 2025年报 | 28.56% |",
            messy,
        )
        self.assertEqual(md.splitlines()[0], "## 四看：价值创造")
        self.assertEqual(md.count("## 四看：价值创造"), 1)
        self.assertEqual(md.count("### 原始数据"), 1)
        self.assertEqual(md.count("### 解读"), 1)
        self.assertEqual(md.count("### 本章小结"), 1)
        self.assertNotIn("### 四看", md)
        self.assertIn("28.56%", md)

    def test_empty_value_section_keeps_skeleton_and_fallback(self):
        fallback = rule_engine_fallback("四看：价值创造", "| ROE | 28.56% |", "")
        md = render_section("四看：价值创造", "| ROE | 28.56% |", fallback)
        self.assertIn("### 解读", md)
        self.assertIn("### 本章小结", md)
        self.assertIn("模型未完成本节解读", md)
        self.assertIn("28.56%", md)

    def test_assemble_report_uses_fixed_chapter_order(self):
        state = {
            "stock_name": "药明康德",
            "stock_code": "603259",
            "industry": {"name": "医疗研发外包"},
            "data_cutoff_date": "2026-09-17",
            "strategy_type": "经营主导型",
            "zhang_tables": {
                "asset_structure": "| 经营性资产 | 77% |",
                "competitiveness": "| 两头吃 | 0.69x |\n\n**计算公式**\n\n| 指标 | 计算公式 |\n|---|---|\n| 两头吃指数 | (应付+预收)÷(应收+预付) |",
                "core_profit": "| 核心利润 | 163亿 |",
                "value": "| ROE | 28.56% |",
                "cost_structure": "| 毛利率 | 47.64% |",
                "liability_structure": "| 金融性负债 | 35% |",
                "cash_quality": "| OCF | 172亿 |",
                "diagnosis": "| 价值创造 | 优 |",
            },
            "zhang_flags": ["存货增速快于营收"],
            "zhang_summary": "战略类型：经营主导型",
            "sources_used": ["东方财富 F10", "东方财富盘口", "东方财富盘口", "申万行业"],
            "section_strategy": "### 解读\n经营性资产占比高。\n本章小结：经营主导。",
            "section_operating": "两头吃指数 0.69x。\n本章小结：议价偏弱。",
            "section_profit": "核心利润率 35.88%。\n本章小结：主业盈利强。",
            "section_value": "",
            "section_cost": "毛利率升至 47.64%。\n本章小结：成本改善。",
            "section_quality": "OCF/核心利润超过 100%。\n本章小结：含金量高。",
            "section_risk": "## 七看：风险\n存货增速过快。\n本章小结：盯存货。",
            "section_outlook": "## 八看：前景\n### 解读\n仍在扩张。\n本章小结：跟踪自由现金流。",
            "section_synthesis": "### 综合诊断\n战略与现金流基本自洽。\n本章小结：主业强、存货需盯。",
        }
        report = assemble_report(state)["final_report"]
        expected = [
            "## 一看：战略——资源配置揭示什么？",
            "## 二看：经营资产管理与竞争力",
            "## 三看：效益与质量（核心利润视角）",
            "## 四看：价值创造",
            "## 五看：成本决定机制",
            "## 六看：财务状况质量",
            "## 七看：风险",
            "## 八看：前景",
            "## 综合诊断",
        ]
        positions = [report.find(title) for title in expected]
        self.assertTrue(all(pos >= 0 for pos in positions))
        self.assertEqual(positions, sorted(positions))
        for title in expected:
            self.assertEqual(report.count(title), 1)
            chunk = report[report.find(title) : report.find(title) + 400]
            self.assertIn("### 原始数据", chunk)
            self.assertIn("### 解读", chunk)
        value_chunk = report[report.find("## 四看：价值创造") : report.find("## 五看：成本决定机制")]
        self.assertIn("本节解读缺失", value_chunk)
        self.assertEqual(value_chunk.count("### 解读"), 1)
        outlook_chunk = report[report.find("## 八看：前景") : report.find("## 综合诊断")]
        self.assertEqual(outlook_chunk.count("## 八看：前景"), 1)
        self.assertEqual(outlook_chunk.count("### 解读"), 1)
        self.assertIn("仍在扩张", outlook_chunk)
        operating_chunk = report[report.find("## 二看：经营资产管理与竞争力") : report.find("## 三看：效益与质量（核心利润视角）")]
        self.assertIn("计算公式", operating_chunk)
        self.assertIn("(应付+预收)÷(应收+预付)", operating_chunk)
        appendix = report[report.find("### 数据来源") :]
        self.assertEqual(appendix.count("- 东方财富盘口"), 1)
        self.assertIn("- 东方财富 F10", appendix)
        self.assertIn("二次加工指标按表下计算公式生成", appendix)

    def test_report_filename_does_not_double_code(self):
        self.assertEqual(
            _report_filename("药明康德", "药明康德", "603259", "20260917"),
            "药明康德_603259八看财报解读_20260917.md",
        )
        self.assertEqual(
            _report_filename("药明康德_603259", "药明康德_603259", "603259", "20260917"),
            "药明康德_603259八看财报解读_20260917.md",
        )

    def test_strip_keeps_substantive_subheads_as_bold(self):
        cleaned = strip_scaffold_headings("#### 一、资产质量：分项诊断\n货币资金充裕。", "六看：财务状况质量")
        self.assertTrue(cleaned.startswith("**一、资产质量：分项诊断**"))
        self.assertIn("货币资金充裕", cleaned)


if __name__ == "__main__":
    unittest.main()
