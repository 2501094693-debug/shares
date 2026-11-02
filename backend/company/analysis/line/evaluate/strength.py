"""相对强弱分：两条 undulate 累计涨跌幅谁强谁弱。

口径与 ``undulate`` 一致（涨跌幅为小数）。对齐后价差
``s_t = pct_A - pct_B``，再：

- ``raw = 0.6 * s_end + 0.4 * mean(s)``
- ``z = raw / max(std(s), 0.01)``
- ``strength = 100 * tanh(z)`` ∈ [-100, 100]

正分表示 A 相对 B 更强，负分表示 B 更强。无网络、无 IO。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from company.analysis.line.undulate.stats import compute_stats

# 价差样本标准差下限（约 1%），避免几乎贴齐时 z 爆炸
_STD_FLOOR = 0.01
_END_W = 0.6
_MEAN_W = 0.4
_DIGITS = 6
_SCORE_DIGITS = 2


def score_strength(spreads: Sequence[float | None]) -> dict[str, Any]:
    """由已对齐的价差序列计算强弱分。

    ``spreads`` 中 ``None`` / 非有限值会被跳过。有效样本须 ≥ 2。
    """
    pts = [
        float(v)
        for v in spreads
        if v is not None and math.isfinite(float(v))
    ]
    count = len(pts)
    if count < 2:
        raise ValueError(f"价差样本须至少 2 个，收到 {count}")

    stats = compute_stats(pts)
    mean = float(stats["mean"])
    std = float(stats["std"] if stats["std"] is not None else 0.0)
    s_end = pts[-1]
    raw = _END_W * s_end + _MEAN_W * mean
    z = raw / max(std, _STD_FLOOR)
    strength = 100.0 * math.tanh(z)

    return {
        "strength": round(strength, _SCORE_DIGITS),
        "raw": round(raw, _DIGITS),
        "z": round(z, _DIGITS),
        "end": round(s_end, _DIGITS),
        "mean": round(mean, _DIGITS),
        "std": round(std, _DIGITS),
        "count": count,
    }


def _as_date_map(
    pcts: Sequence[float | None],
    dates: Sequence[str] | None,
) -> dict[str, float] | list[float]:
    """有日期则建成 date→pct；否则退回按位置对齐的列表。"""
    if dates is None:
        return [
            float(v)
            for v in pcts
            if v is not None and math.isfinite(float(v))
        ]
    if len(dates) != len(pcts):
        raise ValueError(
            f"dates 与 pct 长度须一致: {len(dates)} != {len(pcts)}"
        )
    out: dict[str, float] = {}
    for d, v in zip(dates, pcts):
        if not d or v is None or not math.isfinite(float(v)):
            continue
        out[str(d)[:10]] = float(v)
    return out


def strength_from_pct(
    pct_a: Sequence[float | None],
    pct_b: Sequence[float | None],
    *,
    dates_a: Sequence[str] | None = None,
    dates_b: Sequence[str] | None = None,
) -> dict[str, Any]:
    """由两条累计涨跌幅序列对齐后计算强弱分（A 相对 B）。

    - 两侧都给 ``dates_*``：按日期交集对齐（排序后）。
    - 都不给日期：按位置 zip，长度取较短一侧。
    - 只给一侧日期：抛 ``ValueError``。
    """
    if (dates_a is None) ^ (dates_b is None):
        raise ValueError("dates_a 与 dates_b 须同时提供或同时省略")

    map_a = _as_date_map(pct_a, dates_a)
    map_b = _as_date_map(pct_b, dates_b)

    aligned_dates: list[str] = []
    spreads: list[float] = []

    if isinstance(map_a, dict) and isinstance(map_b, dict):
        for d in sorted(set(map_a) & set(map_b)):
            aligned_dates.append(d)
            spreads.append(map_a[d] - map_b[d])
    else:
        assert isinstance(map_a, list) and isinstance(map_b, list)
        n = min(len(map_a), len(map_b))
        spreads = [map_a[i] - map_b[i] for i in range(n)]

    scored = score_strength(spreads)
    return {
        **scored,
        "dates": aligned_dates or None,
    }
