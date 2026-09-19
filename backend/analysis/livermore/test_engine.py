"""利弗莫尔规则引擎：六栏、关键点、闸门。"""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from analysis.livermore.action import decide_action
from analysis.livermore.atr import last_atr
from analysis.livermore.engine import analyze_bars, apply_context
from analysis.livermore.gate import market_gate
from analysis.livermore.key import walk_key
from analysis.livermore.pivot import detect_pivots


def _bars(closes: list[float], *, vol: float = 200_000) -> list[dict]:
    day = date(2023, 1, 3)
    prev = closes[0]
    out: list[dict] = []
    for close in closes:
        while day.weekday() >= 5:
            day += timedelta(days=1)
        high = max(prev, close) + 0.03
        low = min(prev, close) - 0.03
        out.append(
            {
                "date": day.isoformat(),
                "open": prev,
                "high": high,
                "low": low,
                "close": close,
                "volume": vol,
                "amount": vol * 100 * close,
            }
        )
        prev = close
        day += timedelta(days=1)
    return out


def _uptrend(n: int = 40, start: float = 10.0, step: float = 0.15) -> list[float]:
    return [round(start + i * step, 4) for i in range(n)]


class LivermoreKeyTests(unittest.TestCase):
    def test_steady_rise_is_uptrend(self) -> None:
        bars = _bars(_uptrend(50))
        state = walk_key(bars)
        self.assertEqual(state["column"], "uptrend")
        self.assertEqual(state["family"], "bull")

    def test_pullback_becomes_natural_reaction(self) -> None:
        closes = _uptrend(40, start=10.0, step=0.2)
        peak = closes[-1]
        # 从高点连跌，幅度明显大于近期 ATR
        for i in range(1, 8):
            closes.append(round(peak - i * 0.55, 4))
        bars = _bars(closes)
        state = walk_key(bars)
        self.assertIn(state["column"], {"natural_reaction", "secondary_reaction", "downtrend"})
        self.assertIsNotNone(state["key_up"])

    def test_reclaim_key_returns_to_uptrend(self) -> None:
        closes = _uptrend(40, start=10.0, step=0.2)
        peak = closes[-1]
        for i in range(1, 6):
            closes.append(round(peak - i * 0.45, 4))
        trough = closes[-1]
        for i in range(1, 10):
            closes.append(round(trough + i * 0.4, 4))
        bars = _bars(closes)
        state = walk_key(bars)
        self.assertEqual(state["column"], "uptrend")

    def test_breakdown_flips_to_downtrend(self) -> None:
        closes = _uptrend(35, start=20.0, step=0.15)
        peak = closes[-1]
        for i in range(1, 18):
            closes.append(round(peak - i * 0.7, 4))
        bars = _bars(closes)
        state = walk_key(bars)
        self.assertEqual(state["family"], "bear")
        self.assertIn(state["column"], {"downtrend", "natural_rally", "secondary_rally"})


class LivermoreActionTests(unittest.TestCase):
    def test_index_downtrend_forces_cash(self) -> None:
        gate = market_gate({"column": "downtrend", "column_label": "下降趋势", "family": "bear"})
        self.assertFalse(gate["allow"])
        decided = decide_action(
            gate=gate,
            key_state={"column": "uptrend", "family": "bull", "column_since": "2024-01-01"},
            pivots=[{"kind": "swing_high", "price": 10, "status": "cleared", "side": "long"}],
            volume={"breakout_ok": True},
            follow={"status": "cleared", "follow_ok": True, "after_clear_days": 0},
            liveliness="live",
            industry_leading=True,
            rs_leader=True,
            atr=0.5,
            close=11.0,
        )
        self.assertEqual(decided["action"], "cash")
        self.assertIn("gate.blocked", decided["reason"])

    def test_failed_pivot_exits(self) -> None:
        gate = market_gate({"column": "uptrend", "family": "bull"})
        decided = decide_action(
            gate=gate,
            key_state={"column": "uptrend", "family": "bull"},
            pivots=[{"kind": "swing_high", "price": 10, "status": "failed", "side": "long"}],
            volume={"breakout_ok": True},
            follow={"status": "fail", "follow_ok": False, "after_clear_days": 4},
            liveliness="live",
            industry_leading=True,
            rs_leader=True,
            atr=0.4,
            close=9.5,
        )
        self.assertEqual(decided["action"], "exit")

    def test_unclear_is_cash(self) -> None:
        gate = market_gate({"column": "uptrend", "family": "bull"})
        decided = decide_action(
            gate=gate,
            key_state={"column": "unclear", "family": "unclear"},
            pivots=[],
            volume={},
            follow={},
            liveliness="live",
            industry_leading=True,
            rs_leader=True,
            atr=0.4,
            close=10.0,
        )
        self.assertEqual(decided["action"], "cash")


class LivermoreTapeTests(unittest.TestCase):
    def test_analyze_bars_has_pivots(self) -> None:
        bars = _bars(_uptrend(60, start=8.0, step=0.12))
        tape = analyze_bars(bars, bars)
        self.assertGreaterEqual(tape["bar_count"], 60)
        self.assertIsNotNone(tape["atr"])
        self.assertTrue(tape["pivotal"])
        kinds = {p["kind"] for p in tape["pivotal"]}
        self.assertTrue({"high_52w", "round"} & kinds)

    def test_apply_context_laggard_waits(self) -> None:
        bars = _bars(_uptrend(50))
        tape = analyze_bars(bars, bars)
        tape["code"] = "000001"
        tape["l3_code"] = "L3"
        index_snap = {
            "change_20d": 1.0,
            "gate": market_gate({"column": "uptrend", "family": "bull"}),
        }
        row = apply_context(
            tape,
            index_snap=index_snap,
            peer_changes=[80.0, 70.0, 60.0, 55.0, 50.0],
            industry_leading=True,
            industry_tag="again",
        )
        self.assertEqual(row["action"], "wait")
        self.assertIn("rs.laggard", row["reason"])

    def test_atr_positive(self) -> None:
        bars = _bars(_uptrend(30))
        self.assertGreater(last_atr(bars) or 0, 0)

    def test_detect_round_number(self) -> None:
        closes = _uptrend(40, start=9.2, step=0.05)
        bars = _bars(closes)
        state = walk_key(bars)
        atr = last_atr(bars) or 0.2
        pivots = detect_pivots(bars, bars, atr, state)
        self.assertTrue(any(p["kind"] == "round" for p in pivots))


if __name__ == "__main__":
    unittest.main()
