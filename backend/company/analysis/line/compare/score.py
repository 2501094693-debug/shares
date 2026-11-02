"""方向分类、单日股−指差值与区间反向偏离分。"""

from __future__ import annotations

from typing import Any, Sequence

FLAT_EPS = 0.0003  # 约 0.03% 内视为平

DIR_SAME_UP = "同涨"
DIR_SAME_DOWN = "同跌"
DIR_STOCK_UP_INDEX_DOWN = "股涨指跌"
DIR_STOCK_DOWN_INDEX_UP = "股跌指涨"

_REVERSE_DIRS = frozenset({DIR_STOCK_UP_INDEX_DOWN, DIR_STOCK_DOWN_INDEX_UP})
_SCORE_DIGITS = 2


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


def _row_dir(row: dict[str, Any]) -> str | None:
    """从已有 pair 行或 {rs,rb} 取出方向；无效则 None。"""
    d = row.get("dir")
    if d in (
        DIR_SAME_UP,
        DIR_SAME_DOWN,
        DIR_STOCK_UP_INDEX_DOWN,
        DIR_STOCK_DOWN_INDEX_UP,
    ):
        return str(d)
    rs, rb = row.get("rs"), row.get("rb")
    if rs is None or rb is None:
        return None
    return classify_dir(float(rs), float(rb))


def score_divergence(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """区间偏离分 = 反向日数 / 有效日数 × 100，∈ [0, 100]。

    反向日：股涨指跌 / 股跌指涨。``rows`` 须含 ``dir`` 或 ``rs``/``rb``。
    """
    dirs = {
        DIR_SAME_UP: 0,
        DIR_SAME_DOWN: 0,
        DIR_STOCK_UP_INDEX_DOWN: 0,
        DIR_STOCK_DOWN_INDEX_UP: 0,
    }
    for row in rows:
        d = _row_dir(row)
        if d is None:
            continue
        dirs[d] += 1

    count = sum(dirs.values())
    if count < 1:
        raise ValueError("有效对比日须至少 1 个")

    reverse_count = (
        dirs[DIR_STOCK_UP_INDEX_DOWN] + dirs[DIR_STOCK_DOWN_INDEX_UP]
    )
    score = reverse_count / count * 100.0
    return {
        "score": round(score, _SCORE_DIGITS),
        "count": count,
        "reverse_count": reverse_count,
        "dirs": {
            "same_up": dirs[DIR_SAME_UP],
            "same_down": dirs[DIR_SAME_DOWN],
            "stock_up_index_down": dirs[DIR_STOCK_UP_INDEX_DOWN],
            "stock_down_index_up": dirs[DIR_STOCK_DOWN_INDEX_UP],
        },
    }
