"""prior_below 纯函数单测（无网络）。"""

from __future__ import annotations

import math
import unittest

from analysis.macd.signals import SIGNAL_UNDER_CROSS, SIGNAL_UNDER_NEAR
from company.analysis.line.MACD.prior_below import (
    analyze_prior_below,
    find_dif_below_span,
    log_uniform_sum_dev,
)


def _row(date: str, dif: float, dea: float, close: float) -> dict:
    return {
        "date": date,
        "dif": dif,
        "dea": dea,
        "macd": 2 * (dif - dea),
        "close": close,
        "price": close,
    }


class LogUniformSumDevTests(unittest.TestCase):
    def test_uniform_path_near_zero(self) -> None:
        # 对数匀速：e^0, e^{-0.1}, e^{-0.2}, e^{-0.3}
        closes = [math.exp(-0.1 * i) for i in range(4)]
        out = log_uniform_sum_dev(closes, min_bars=3, min_log_move=1e-6)
        self.assertTrue(out["ok"])
        self.assertAlmostEqual(out["sum_dev"], 0.0, places=6)

    def test_above_chord_positive_sum(self) -> None:
        # 端点 1→e^{-0.3}；中间偏高（加速跌形态）
        closes = [1.0, math.exp(-0.05), math.exp(-0.08), math.exp(-0.3)]
        out = log_uniform_sum_dev(closes, min_bars=3, min_log_move=1e-6)
        self.assertTrue(out["ok"])
        self.assertGreater(out["sum_dev"], 0.0)

    def test_below_chord_negative_sum(self) -> None:
        # 中间偏低（先急后缓）
        closes = [1.0, math.exp(-0.22), math.exp(-0.28), math.exp(-0.3)]
        out = log_uniform_sum_dev(closes, min_bars=3, min_log_move=1e-6)
        self.assertTrue(out["ok"])
        self.assertLess(out["sum_dev"], 0.0)

    def test_insufficient(self) -> None:
        out = log_uniform_sum_dev([1.0, 0.9], min_bars=3)
        self.assertFalse(out["ok"])
        self.assertIsNone(out["sum_dev"])


class DifBelowSpanTests(unittest.TestCase):
    def test_cross_excludes_signal_day(self) -> None:
        items = [
            _row("2026-01-06", -0.5, -0.6, 11.0),  # DIF>DEA，打断
            _row("2026-01-07", -1.2, -1.0, 10.5),
            _row("2026-01-08", -1.3, -1.0, 9.5),
            _row("2026-01-09", -1.1, -1.0, 10.0),
            _row("2026-01-10", -0.9, -1.0, 10.2),  # 金叉
        ]
        span = find_dif_below_span(items, 4, include_signal=False)
        self.assertTrue(span["found"])
        self.assertEqual(span["beg"], "2026-01-07")
        self.assertEqual(span["end"], "2026-01-09")
        self.assertEqual(span["count"], 3)

    def test_near_includes_signal_day(self) -> None:
        items = [
            _row("2026-01-07", -1.2, -1.0, 10.5),
            _row("2026-01-08", -1.3, -1.0, 9.5),
            _row("2026-01-09", -1.05, -1.0, 10.0),  # 即将
        ]
        span = find_dif_below_span(items, 2, include_signal=True)
        self.assertTrue(span["found"])
        self.assertEqual(span["end"], "2026-01-09")
        self.assertEqual(span["count"], 3)


class AnalyzePriorBelowTests(unittest.TestCase):
    def test_under_cross_down_accel_positive(self) -> None:
        # 先高位盘，后砸到谷，再稍抬 → 下跌腿中间偏高 → down_accel>0
        items = [
            _row("2026-01-05", -0.4, -0.5, 12.0),  # 上一段
            _row("2026-01-06", -1.20, -1.0, 10.0),
            _row("2026-01-07", -1.25, -1.0, 9.7),
            _row("2026-01-08", -1.30, -1.0, 9.5),
            _row("2026-01-09", -1.35, -1.0, 8.0),  # 谷
            _row("2026-01-10", -1.10, -1.0, 8.5),
            _row("2026-01-11", -0.90, -1.0, 9.0),  # 金叉
        ]
        out = analyze_prior_below(
            items, 6, signal=SIGNAL_UNDER_CROSS, min_bars=3, min_log_move=1e-6
        )
        self.assertTrue(out["found"])
        self.assertEqual(out["trough_date"], "2026-01-09")
        self.assertEqual(out["end"], "2026-01-10")
        self.assertTrue(out["down"]["found"])
        self.assertGreater(out["down_accel"], 0.0)

    def test_up_accel_sign_flip(self) -> None:
        # 谷底后慢启动再拉升：中间偏低 → sum_dev<0 → up_accel=-sum>0
        items = [
            _row("2026-01-06", -1.2, -1.0, 10.0),
            _row("2026-01-07", -1.3, -1.0, 8.0),  # 谷
            _row("2026-01-08", -1.25, -1.0, 8.05),
            _row("2026-01-09", -1.15, -1.0, 8.1),
            _row("2026-01-10", -1.05, -1.0, 9.5),  # 即将日
        ]
        out = analyze_prior_below(
            items, 4, signal=SIGNAL_UNDER_NEAR, min_bars=3, min_log_move=1e-6
        )
        self.assertTrue(out["found"])
        self.assertTrue(out["up"]["found"])
        self.assertLess(out["up"]["sum_dev"], 0.0)
        self.assertGreater(out["up_accel"], 0.0)

    def test_insufficient_leg_null_accel(self) -> None:
        items = [
            _row("2026-01-08", -1.2, -1.0, 10.0),
            _row("2026-01-09", -1.1, -1.0, 9.0),  # 谷=起点次日，上涨腿只有 2 根
            _row("2026-01-10", -0.9, -1.0, 9.5),  # 金叉
        ]
        out = analyze_prior_below(
            items, 2, signal=SIGNAL_UNDER_CROSS, min_bars=3
        )
        self.assertTrue(out["found"])
        # 下跌腿 2 根 → accel null；上涨腿 2 根 → null
        self.assertIsNone(out["down_accel"])
        self.assertIsNone(out["up_accel"])


if __name__ == "__main__":
    unittest.main()
