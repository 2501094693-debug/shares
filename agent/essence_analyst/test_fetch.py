"""第一步官方资料拼装：公告 PDF，不含财报数字。"""

from __future__ import annotations

import unittest

from agent.essence_analyst.fetch import _pick_official_pdfs, assemble_official_text
from agent.tools.notice_pdf import pick_full_reports, pick_latest_full_report


class AssembleOfficialTextTest(unittest.TestCase):
    def test_announcement_sections_come_first(self):
        text = assemble_official_text(
            {
                "七网报道": "七网正文",
                "公告 PDF 正文": "PDF正文",
                "经营相关公告": "公告目录",
            },
            name="茅台",
            code="600519",
        )
        self.assertIn("官方公告", text)
        self.assertIn("不采集东财 F10", text)
        self.assertNotIn("近 5 年年报", text)
        pos_pdf = text.index("## 公告 PDF 正文")
        pos_notice = text.index("## 经营相关公告")
        pos_press = text.index("## 七网报道")
        self.assertLess(pos_pdf, pos_notice)
        self.assertLess(pos_notice, pos_press)


class PickOfficialPdfsTest(unittest.TestCase):
    def test_skips_summary_and_keeps_limit(self):
        items = [
            {"title": "2024年年度报告摘要", "url": "http://a/summary.pdf", "published_at": "2025-04-01"},
            {"title": "2024年年度报告", "url": "http://a/2024.pdf", "published_at": "2025-04-01"},
            {"title": "2023年年度报告", "url": "http://a/2023.pdf", "published_at": "2024-04-01"},
        ]
        picked = pick_full_reports(items, limit=1)
        self.assertEqual(picked[0]["title"], "2024年年度报告")
        self.assertIs(pick_latest_full_report(items), picked[0])

    def test_latest_report_per_kind_not_history(self):
        by_kind = {
            "年报": [
                {"title": "2024年年度报告", "url": "http://a/2024.pdf"},
                {"title": "2023年年度报告", "url": "http://a/2023.pdf"},
            ],
            "半年报": [{"title": "2025年半年度报告", "url": "http://a/2025h.pdf"}],
        }
        notices = [{"title": "关于投产的公告", "url": "http://a/notice.pdf"}]
        picked = _pick_official_pdfs(by_kind, notices)
        urls = [row["url"] for row in picked]
        self.assertIn("http://a/2024.pdf", urls)
        self.assertNotIn("http://a/2023.pdf", urls)
        self.assertIn("http://a/2025h.pdf", urls)
        self.assertIn("http://a/notice.pdf", urls)


if __name__ == "__main__":
    unittest.main()
