"""复权缓存接缝检测 / 合并失败语义单测（无网络）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from company.line import fetcher as F


def _bar(day: str, close: float, *, pct: float | None = None, open_: float | None = None) -> dict:
    o = open_ if open_ is not None else close
    row = {
        "time": day,
        "open": o,
        "high": max(o, close),
        "low": min(o, close),
        "close": close,
        "volume": 1.0,
    }
    if pct is not None:
        row["pct_chg"] = pct
    return row


class PctBasisMismatchTests(unittest.TestCase):
    def test_qfq_seam_pct_disagrees(self) -> None:
        # 旧因子收盘 27 → 新因子段 19.96，源站 pct 仍是 +4.8
        prev = _bar("2026-11-04", 27.04, pct=2.58)
        cur = _bar("2026-11-05", 19.96, pct=4.83)
        self.assertTrue(F._bar_pct_basis_mismatch(prev, cur))

    def test_raw_ex_rights_pct_agrees(self) -> None:
        # 不复权除权日：大跌但 pct_chg 同步，不算接缝
        prev = _bar("2026-11-09", 27.11, pct=-1.67)
        cur = _bar("2026-11-10", 19.53, pct=-27.96)
        self.assertFalse(F._bar_pct_basis_mismatch(prev, cur))

    def test_missing_pct_large_jump(self) -> None:
        prev = _bar("2026-09-18", 28.38)
        cur = _bar("2026-09-21", 20.34)
        self.assertTrue(F._bar_pct_basis_mismatch(prev, cur))

    def test_normal_day(self) -> None:
        prev = _bar("2026-11-03", 26.36, pct=0.46)
        cur = _bar("2026-11-04", 27.04, pct=2.58)
        self.assertFalse(F._bar_pct_basis_mismatch(prev, cur))


class FindSeamTests(unittest.TestCase):
    def test_finds_first_seam(self) -> None:
        items = [
            _bar("2026-11-03", 26.36, pct=0.46),
            _bar("2026-11-04", 27.04, pct=2.58),
            _bar("2026-11-05", 19.96, pct=4.83),
            _bar("2026-11-06", 19.42, pct=-2.71),
        ]
        self.assertEqual(F._find_adjust_seam(items), "2026-11-05")

    def test_clean_series(self) -> None:
        items = [
            _bar("2026-11-04", 19.04, pct=2.58),
            _bar("2026-11-05", 19.96, pct=4.83),
        ]
        self.assertEqual(F._find_adjust_seam(items), "")


class MergeTailAdjustTests(unittest.TestCase):
    def test_overlap_price_mismatch_returns_adjust(self) -> None:
        cached = [
            _bar("2026-11-03", 26.36),
            _bar("2026-11-04", 27.04),
            _bar("2026-11-05", 19.96),
        ]
        # 远程已按新因子重写 11.4
        remote = [
            _bar("2026-11-04", 19.04),
            _bar("2026-11-05", 19.96),
            _bar("2026-11-06", 19.42),
        ]
        merged, reason = F._merge_tail(cached, remote)
        self.assertIsNone(merged)
        self.assertEqual(reason, "adjust")


class SaveReplaceTests(unittest.TestCase):
    def test_replace_drops_old_factor_bars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(F, "KLINE_CACHE_DIR", root), mock.patch.object(
                F, "ensure_cache_dirs", lambda: None
            ):
                old = {
                    "code": "603596",
                    "adjust": "qfq",
                    "items": [
                        _bar("2026-09-01", 29.84),
                        _bar("2026-09-18", 28.38),
                        _bar("2026-09-21", 20.34),
                    ],
                }
                F._save_kline_disk("603596", "day", "qfq", old)
                new = {
                    "code": "603596",
                    "adjust": "qfq",
                    "items": [
                        _bar("2026-09-18", 19.99),
                        _bar("2026-09-21", 20.34),
                    ],
                    "full_history": False,
                }
                F._save_kline_disk("603596", "day", "qfq", new, replace=True)
                loaded = F._load_kline_disk("603596", "day", "qfq")
                assert loaded is not None
                times = [str(b.get("time"))[:10] for b in loaded["items"]]
                self.assertEqual(times, ["2026-09-18", "2026-09-21"])
                self.assertAlmostEqual(float(loaded["items"][0]["close"]), 19.99)


class RefreshRebuildTests(unittest.TestCase):
    def test_seam_triggers_rebuild_not_tail_merge(self) -> None:
        stored = {
            "code": "603596",
            "name": "伯特利",
            "period": "day",
            "adjust": "qfq",
            "items": [
                _bar("2026-11-04", 27.04, pct=2.58),
                _bar("2026-11-05", 19.96, pct=4.83),
            ],
        }
        rebuilt_items = [
            _bar("2026-11-04", 19.04, pct=2.58),
            _bar("2026-11-05", 19.96, pct=4.83),
        ]

        def _fake_rebuild(*_a, **_k):
            return {
                "code": "603596",
                "name": "伯特利",
                "period": "day",
                "adjust": "qfq",
                "items": rebuilt_items,
                "count": 2,
                "source": "tencent",
            }

        with mock.patch.object(F, "_rebuild_adjusted_kline", side_effect=_fake_rebuild) as reb:
            out = F._refresh_with_tail(
                stored,
                code="603596",
                period="day",
                adjust="qfq",
                disk_adjust="qfq",
                cap=500,
            )
        reb.assert_called_once()
        self.assertAlmostEqual(float(out["items"][0]["close"]), 19.04)


if __name__ == "__main__":
    unittest.main()
