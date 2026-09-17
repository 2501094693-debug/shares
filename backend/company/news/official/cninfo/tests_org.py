"""巨潮 orgId 解析：静态表优先，规则推断只覆盖已验证号段。"""

from __future__ import annotations

import unittest

from company.news.official.cninfo.request import infer_org_from_code


class InferOrgIdTests(unittest.TestCase):
    def test_shanghai_main_board(self):
        self.assertEqual(infer_org_from_code("600519")["org_id"], "gssh0600519")
        self.assertEqual(infer_org_from_code("600990")["org_id"], "gssh0600990")

    def test_shenzhen_main_board_000(self):
        self.assertEqual(infer_org_from_code("000001")["org_id"], "gssz0000001")

    def test_sme_002_is_not_guessed(self):
        self.assertIsNone(infer_org_from_code("002415"))
        self.assertIsNone(infer_org_from_code("002001"))

    def test_chinext_and_star_are_not_guessed(self):
        self.assertIsNone(infer_org_from_code("300750"))
        self.assertIsNone(infer_org_from_code("688981"))


if __name__ == "__main__":
    unittest.main()
