"""信号后 DIF≥DEA 段涨跌纯函数单测。"""

from __future__ import annotations

import unittest

from analysis.macd.forward import forward_gains_after_signal


def _macd(
    date: str,
    *,
    dif: float,
    dea: float,
    close: float,
) -> dict:
    return {
        "date": date,
        "dif": dif,
        "dea": dea,
        "macd": 2.0 * (dif - dea),
        "price": close,
        "close": close,
    }


class ForwardGainsAfterSignalTests(unittest.TestCase):
    def test_cross_until_first_dif_below(self) -> None:
        # 金叉日 01-09 DIF>=DEA，01-10 仍上，01-13 首次 DIF<DEA → 截止
        items = [
            _macd("2026-01-08", dif=-0.2, dea=-0.1, close=9.5),
            _macd("2026-01-09", dif=0.1, dea=0.0, close=10.0),  # signal
            _macd("2026-01-10", dif=0.2, dea=0.05, close=11.0),
            _macd("2026-01-13", dif=-0.1, dea=0.0, close=10.5),  # break
            _macd("2026-01-14", dif=-0.2, dea=-0.05, close=12.0),  # 之后不计
        ]
        out = forward_gains_after_signal(
            items, signal_date="2026-01-09", is_near=False
        )
        self.assertTrue(out["valid"])
        self.assertEqual(out["end_date"], "2026-01-13")
        self.assertEqual(out["end_source"], "break")
        self.assertEqual(out["hold_days"], 3)
        self.assertAlmostEqual(out["max_close_gain"], 0.1, places=6)  # 11/10-1
        self.assertEqual(out["max_close_date"], "2026-01-10")
        self.assertAlmostEqual(out["max_close_drop"], 0.0, places=6)
        self.assertAlmostEqual(out["end_close_gain"], 0.05, places=6)  # 10.5/10-1

    def test_open_ended_uses_latest(self) -> None:
        items = [
            _macd("2026-01-09", dif=0.1, dea=0.0, close=10.0),
            _macd("2026-01-10", dif=0.2, dea=0.05, close=10.5),
            _macd("2026-01-13", dif=0.3, dea=0.1, close=11.0),
        ]
        out = forward_gains_after_signal(
            items, signal_date="2026-01-09", is_near=False
        )
        self.assertTrue(out["valid"])
        self.assertTrue(out["open_ended"])
        self.assertEqual(out["end_source"], "latest")
        self.assertEqual(out["end_date"], "2026-01-13")
        self.assertAlmostEqual(out["max_close_gain"], 0.1, places=6)
        self.assertAlmostEqual(out["end_close_gain"], 0.1, places=6)

    def test_near_ok_then_break(self) -> None:
        # 即将：01-09 DIF<DEA；01-10 金叉；01-13 跌破
        items = [
            _macd("2026-01-08", dif=-0.3, dea=-0.1, close=9.8),
            _macd("2026-01-09", dif=-0.05, dea=0.0, close=10.0),  # near
            _macd("2026-01-10", dif=0.1, dea=0.0, close=10.8),  # cross
            _macd("2026-01-13", dif=-0.05, dea=0.0, close=10.2),  # break
        ]
        out = forward_gains_after_signal(
            items, signal_date="2026-01-09", is_near=True
        )
        self.assertTrue(out["valid"])
        self.assertTrue(out["near_ok"])
        self.assertEqual(out["cross_date"], "2026-01-10")
        self.assertEqual(out["end_date"], "2026-01-13")
        self.assertAlmostEqual(out["max_close_gain"], 0.08, places=6)
        self.assertAlmostEqual(out["end_close_gain"], 0.02, places=6)

    def test_near_fail_invalid(self) -> None:
        # 即将后缺口继续扩大 → 无效
        items = [
            _macd("2026-01-09", dif=-0.05, dea=0.0, close=10.0),
            _macd("2026-01-10", dif=-0.2, dea=0.0, close=10.5),
        ]
        out = forward_gains_after_signal(
            items, signal_date="2026-01-09", is_near=True
        )
        self.assertFalse(out["valid"])
        self.assertFalse(out["near_ok"])
        self.assertTrue(out["judgment_failed"])
        self.assertIsNone(out["max_close_gain"])
        self.assertIsNone(out["end_close_gain"])

    def test_near_pending_invalid(self) -> None:
        # 数据用尽仍未分胜负 → 无效
        items = [
            _macd("2026-01-09", dif=-0.05, dea=0.0, close=10.0),
            _macd("2026-01-10", dif=-0.04, dea=0.0, close=10.2),
        ]
        out = forward_gains_after_signal(
            items, signal_date="2026-01-09", is_near=True
        )
        self.assertFalse(out["valid"])
        self.assertTrue(out["judgment_failed"])
        self.assertIsNone(out["max_close_gain"])

    def test_missing_signal_day(self) -> None:
        items = [_macd("2026-01-10", dif=0.1, dea=0.0, close=10.0)]
        out = forward_gains_after_signal(
            items, signal_date="2026-01-09", is_near=False
        )
        self.assertFalse(out["valid"])
        self.assertEqual(out["hold_days"], 0)


if __name__ == "__main__":
    unittest.main()
