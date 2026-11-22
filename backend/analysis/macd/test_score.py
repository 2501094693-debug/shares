"""综合分纯函数单测。"""

from __future__ import annotations

import unittest

from analysis.macd.score import composite_score


class CompositeScoreTests(unittest.TestCase):
    def test_both_sides(self) -> None:
        out = composite_score(
            score_close=80.0,
            score_low=60.0,
            reverse_count=10,
            range_days=50,
            w_prior=0.7,
            w_div=0.3,
        )
        # prior = 70; div = 20; total = 0.7*70 + 0.3*20 = 55
        self.assertEqual(out["score_prior"], 70.0)
        self.assertEqual(out["div_score"], 20.0)
        self.assertEqual(out["score_total"], 55.0)
        self.assertEqual(out["reverse_count"], 10)

    def test_one_side_prior(self) -> None:
        out = composite_score(
            score_close=90.0,
            score_low=None,
            reverse_count=0,
            range_days=10,
            w_prior=0.7,
            w_div=0.3,
        )
        self.assertEqual(out["score_prior"], 90.0)
        self.assertEqual(out["div_score"], 0.0)
        self.assertEqual(out["score_total"], 63.0)

    def test_no_days(self) -> None:
        out = composite_score(
            score_close=50.0,
            score_low=50.0,
            reverse_count=None,
            range_days=0,
        )
        self.assertIsNone(out["div_score"])
        self.assertEqual(out["score_total"], 50.0)


if __name__ == "__main__":
    unittest.main()
