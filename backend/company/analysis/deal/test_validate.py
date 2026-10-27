"""需求约束验收 / 修复 单测。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from company.analysis.deal.validate import (
    enforce_constraints,
    repair_tape,
    validate_tape,
)
from company.analysis.deal.window import reconstruct_windows


class ValidateTapeTests(unittest.TestCase):
    def test_happy_path_passes(self) -> None:
        ticks = [
            {"time": "09:30:03", "price": 10.0, "volume": 10, "count": 5, "side": "buy"},
            {"time": "09:30:06", "price": 10.0, "volume": 8, "count": 4, "side": "sell"},
        ]
        big = [
            {
                "time": "09:30:03",
                "price": 10.0,
                "volume": 300,
                "amount": 300000,
                "side": "buy",
                "aggressor": "active",
            },
        ]
        pack = reconstruct_windows(ticks, big, view="aggressor")
        self.assertTrue(pack["reconcile"]["constraints_ok"])
        self.assertEqual(pack["reconcile"]["constraints_hard_count"], 0)

    def test_repair_restores_time_and_order_price(self) -> None:
        ticks = [
            {"time": "09:30:35", "price": 17.48, "volume": 123, "count": 8, "side": "buy"},
            {"time": "09:30:38", "price": 17.49, "volume": 87, "count": 12, "side": "buy"},
        ]
        big = [
            {
                "time": "09:30:35",
                "price": 17.48,
                "volume": 20000,
                "volume_lots": 200,
                "amount": 349600,
                "side": "sell",
                "aggressor": "passive",
            },
        ]
        pack = reconstruct_windows(ticks, big, view="all")
        rows = pack["rows"]
        windows = [
            {"time": b["time"], "lots": b["lots"], "count": b["count"], "price": b["price"]}
            for b in pack["window_bars"]
        ]
        orders = [
            {
                "order_id": "O00001",
                "time": "09:30:35",
                "price": 17.48,
                "lots": 200.0,
                "side": "sell",
            }
        ]
        # 人为破坏：改价、清掉 order_time
        for row in rows:
            if row.get("kind") == "order":
                row["price"] = 17.49
                row["order_time"] = ""
        broken = validate_tape(rows, windows, orders)
        self.assertFalse(broken["ok"])
        actions = repair_tape(rows, windows, orders, broken)
        self.assertTrue(actions)
        fixed = validate_tape(rows, windows, orders)
        self.assertTrue(fixed["ok"], msg=fixed.get("hard"))

    def test_enforce_on_cross_window_case(self) -> None:
        ticks = [
            {"time": "09:30:35", "price": 17.48, "volume": 123, "count": 8, "side": "buy"},
            {"time": "09:30:38", "price": 17.49, "volume": 87, "count": 12, "side": "buy"},
        ]
        big = [
            {
                "time": "09:30:35",
                "price": 17.48,
                "volume": 20000,
                "volume_lots": 200,
                "amount": 349600,
                "side": "sell",
                "aggressor": "passive",
            },
        ]
        pack = reconstruct_windows(ticks, big, view="all")
        self.assertTrue(pack["reconcile"]["constraints_ok"])
        # 按分时档汇总不得把 200 叠进 87 手档
        by_win: dict[str, float] = {}
        for row in pack["rows"]:
            t = str(row.get("window_time") or row["time"])
            by_win[t] = by_win.get(t, 0.0) + float(row["lots"])
        self.assertAlmostEqual(by_win["09:30:35"], 123.0, places=2)
        self.assertAlmostEqual(by_win["09:30:38"], 87.0, places=2)
        # 跨窗大单成块，不被小单夹心
        sell_id = next(r["sell_id"] for r in pack["rows"] if r.get("order_id"))
        ordered = sorted(pack["rows"], key=lambda r: r.get("seq") or 0)
        flags = [r.get("kind") == "order" and r.get("sell_id") == sell_id for r in ordered]
        first = flags.index(True)
        last = len(flags) - 1 - flags[::-1].index(True)
        self.assertTrue(all(flags[first : last + 1]))


class RealCacheValidateTests(unittest.TestCase):
    CODE = "600990"
    DAY = "2026-10-26"

    def test_real_day_constraints_ok(self) -> None:
        root = Path(__file__).resolve().parents[3] / "cache"
        tick_path = root / "ticks" / f"{self.CODE}_{self.DAY}.json"
        flow_path = root / "fundflow" / f"{self.CODE}_{self.DAY}.json"
        if not tick_path.exists() or not flow_path.exists():
            self.skipTest("无缓存")
        ticks = json.loads(tick_path.read_text(encoding="utf-8"))
        flow = json.loads(flow_path.read_text(encoding="utf-8"))
        payload = ticks.get("data") if isinstance(ticks.get("data"), dict) else ticks
        pack = reconstruct_windows(
            payload.get("items") or [],
            flow.get("items") or [],
            code=self.CODE,
            day=self.DAY,
            view="all",
        )
        self.assertTrue(
            pack["reconcile"]["constraints_ok"],
            msg=pack["reconcile"].get("constraints"),
        )


if __name__ == "__main__":
    unittest.main()
