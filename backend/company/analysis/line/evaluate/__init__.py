"""区间评估：最新交易日起的最大 ±band 波动区间 + 最低价日评分 + 股 / 指 σ 坐标。

- ``core``    纯函数：波动筛选、最低价日、极值评分、σ 汇总
- ``service`` 取数 + 主流程（``analyze_evaluate``）

这里对外只暴露 ``analyze_evaluate`` 及若干纯函数，便于脚本 / CLI 复用。
"""

from __future__ import annotations

from company.analysis.line.evaluate.core import (
    DEFAULT_BAND,
    LOW_FACTOR_CHOICES,
    TEST_FACTOR_CHOICES,
    find_max_range,
    lowest_day,
    score_low_point,
    slim_window,
    summarize_sigma,
    window_within,
)
from company.analysis.line.evaluate.service import (
    DEFAULT_INDEX,
    DEFAULT_LOOKBACK_DAYS,
    analyze_evaluate,
)

__all__ = [
    "DEFAULT_BAND",
    "DEFAULT_INDEX",
    "DEFAULT_LOOKBACK_DAYS",
    "LOW_FACTOR_CHOICES",
    "TEST_FACTOR_CHOICES",
    "analyze_evaluate",
    "find_max_range",
    "lowest_day",
    "score_low_point",
    "slim_window",
    "summarize_sigma",
    "window_within",
]
