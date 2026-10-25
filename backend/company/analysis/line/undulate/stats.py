"""四价涨跌幅序列的统计量（纯函数，无网络、无 IO）。

输入一组涨跌幅（小数，如 ``0.0123`` 表示 +1.23%，**不是**百分数），
输出该序列的波动范围（最低 / 最高 / 极差）、均值与标准差。

标准差按**样本标准差**（n-1，无偏估计）计算；仅一个样本时记 0，
无样本时全部为 ``None``。所有数值保留 6 位小数，与 service 的涨跌幅口径一致。
"""

from __future__ import annotations

import math
from typing import Any, Iterable

# 涨跌幅以小数存储，6 位已到 0.0001% 精度，再细无意义
_DIGITS = 6


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), _DIGITS)


def compute_stats(values: Iterable[float | None]) -> dict[str, Any]:
    """对一组涨跌幅算统计量。

    返回：``count`` 样本数、``min`` / ``max`` 波动上下界、``range`` 极差
    （max - min）、``mean`` 均值、``std`` 样本标准差。空序列时数值均为 ``None``。
    """
    pts = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    count = len(pts)
    if not count:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "range": None,
            "mean": None,
            "std": None,
        }

    low = min(pts)
    high = max(pts)
    mean = sum(pts) / count
    if count > 1:
        variance = sum((x - mean) ** 2 for x in pts) / (count - 1)
        std: float | None = math.sqrt(variance)
    else:
        std = 0.0

    return {
        "count": count,
        "min": _round(low),
        "max": _round(high),
        "range": _round(high - low),
        "mean": _round(mean),
        "std": _round(std),
    }


def summarize_factors(
    series: dict[str, list[float | None]],
) -> dict[str, dict[str, Any]]:
    """按因子（open / high / low / close …）逐条算统计量。"""
    return {factor: compute_stats(values) for factor, values in series.items()}
