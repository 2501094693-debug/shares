"""阴跌 / 横盘：走势切片。K 线清洗复用 decline.bars。"""

from __future__ import annotations

from typing import Any

from analysis.decline.bars import parse_bars, segment_stats  # noqa: F401

__all__ = ["parse_bars", "segment_stats", "build_sparkline"]


def _round_price(value: Any, digits: int = 3) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def build_sparkline(
    bars: list[dict[str, Any]],
    phases: dict[str, Any],
    *,
    pad_before: int,
    pad_after: int,
    max_bars: int,
    ma_warmup: int = 0,
) -> dict[str, Any]:
    """截一段日 K；下标相对切片，锚定最近一根。"""
    empty = {
        "bars": [],
        "warmup": 0,
        "decline": [None, None],
        "consolidation": [None, None],
        "as_of": None,
    }
    if not bars:
        return empty

    last = len(bars) - 1
    cons = phases.get("consolidation") or {}
    dec = phases.get("decline") or {}
    starts = [
        int(dec.get("start", -1)),
        int(cons.get("start", -1)),
    ]
    valid_starts = [s for s in starts if s >= 0]
    start = min(valid_starts) if valid_starts else max(0, last - max(20, max_bars // 2))
    start = max(0, start - max(0, pad_before))
    end = min(last, last + max(0, pad_after))
    if end - start + 1 > max_bars:
        start = max(0, end - max_bars + 1)

    warmup = max(0, int(ma_warmup or 0))
    warm_start = max(0, start - warmup)
    warmup = start - warm_start

    compact: list[list[Any]] = []
    for bar in bars[warm_start : end + 1]:
        vol = bar.get("volume")
        try:
            vol_i = int(vol) if vol else 0
        except (TypeError, ValueError):
            vol_i = 0
        compact.append(
            [
                bar.get("date") or "",
                _round_price(bar.get("open")),
                _round_price(bar.get("high")),
                _round_price(bar.get("low")),
                _round_price(bar.get("close")),
                vol_i,
            ]
        )

    def rel(idx: Any) -> int | None:
        try:
            raw = int(idx)
        except (TypeError, ValueError):
            return None
        if raw < 0:
            return None
        pos = raw - warm_start
        if 0 <= pos < len(compact):
            return pos
        return None

    return {
        "bars": compact,
        "warmup": warmup,
        "decline": [rel(dec.get("start", -1)), rel(dec.get("end", -1))],
        "consolidation": [rel(cons.get("start", -1)), rel(cons.get("end", -1))],
        "as_of": rel(last),
    }
