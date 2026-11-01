"""方向分类与单日股−指差值。"""

from __future__ import annotations

from typing import Any

FLAT_EPS = 0.0003  # 约 0.03% 内视为平

DIR_SAME_UP = "同涨"
DIR_SAME_DOWN = "同跌"
DIR_STOCK_UP_INDEX_DOWN = "股涨指跌"
DIR_STOCK_DOWN_INDEX_UP = "股跌指涨"


def classify_dir(rs: float, rb: float, *, eps: float = FLAT_EPS) -> str:
    """按股/指涨跌幅符号分类四向关系。"""
    s = 1 if rs > eps else (-1 if rs < -eps else 0)
    b = 1 if rb > eps else (-1 if rb < -eps else 0)
    if s == 1 and b == 1:
        return DIR_SAME_UP
    if s == -1 and b == -1:
        return DIR_SAME_DOWN
    if s >= 0 and b <= 0 and s != b:
        return DIR_STOCK_UP_INDEX_DOWN
    return DIR_STOCK_DOWN_INDEX_UP


def pair_row(rs: float, rb: float) -> dict[str, Any]:
    dif = float(rs) - float(rb)
    return {
        "rs": round(rs, 6),
        "rb": round(rb, 6),
        "dif": round(dif, 6),
        "dir": classify_dir(rs, rb),
    }
