"""个股相对大盘、相对三级的强度。"""

from __future__ import annotations

import math
from typing import Any

from analysis.livermore.bars import period_return
from analysis.livermore.config import MIN_L3_PEERS, RS_DAYS, RS_TOP_PCT


def change_nd(bars: list[dict[str, Any]], days: int = RS_DAYS) -> float | None:
    return period_return(bars, days)


def vs_benchmark(stock_chg: float | None, bench_chg: float | None) -> float | None:
    if stock_chg is None or bench_chg is None:
        return None
    return round(stock_chg - bench_chg, 3)


def rank_in_group(change: float | None, peers: list[float]) -> dict[str, Any]:
    """1 最好。样本不足则不算领头。"""
    valid = [p for p in peers if p is not None]
    n = len(valid)
    if change is None or n < MIN_L3_PEERS:
        return {"rank": None, "sample": n, "leader": False, "pct": None}
    better = sum(1 for p in valid if p > change)
    rank = better + 1
    cutoff = max(1, math.ceil(n * RS_TOP_PCT))
    return {
        "rank": rank,
        "sample": n,
        "leader": rank <= cutoff,
        "pct": round(rank / n, 3),
    }
