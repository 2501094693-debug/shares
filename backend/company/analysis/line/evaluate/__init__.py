"""区间评估：最大 ±band 区间 + 最低价日评分 + 股指四价走势 + 股指反向偏离分。

- ``core``     纯函数：波动筛选、最低价日、极值评分、σ 汇总
- ``strength`` 纯函数：相对强弱分（历史模块，主流程已改用四价走势）
- ``service``  取数 + 主流程（``analyze_evaluate``）；四价走势走 undulate.volatility，
               偏离分复用 ``compare``

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
    DEFAULT_LAYERS,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_SMOOTH_WINDOW,
    EXTREMA_LOOKBACK_BARS,
    EXTREMA_LOOKBACK_DAYS,
    analyze_evaluate,
)
from company.analysis.line.evaluate.strength import (
    score_strength,
    strength_from_pct,
)

__all__ = [
    "DEFAULT_BAND",
    "DEFAULT_INDEX",
    "DEFAULT_LAYERS",
    "DEFAULT_LOOKBACK_DAYS",
    "DEFAULT_SMOOTH_WINDOW",
    "EXTREMA_LOOKBACK_BARS",
    "EXTREMA_LOOKBACK_DAYS",
    "LOW_FACTOR_CHOICES",
    "TEST_FACTOR_CHOICES",
    "analyze_evaluate",
    "find_max_range",
    "lowest_day",
    "score_low_point",
    "score_strength",
    "slim_window",
    "strength_from_pct",
    "summarize_sigma",
    "window_within",
]
