"""MACD：快慢线差离值 + 信号线 + 柱线。

- ``compute_macd``  纯函数：在日线序列上算 DIF / DEA / MACD
- ``analyze_macd``  主入口：拉日线后调用 ``compute_macd``
- ``analyze_prior_below``  金叉前 DIF<DEA 段相对对数匀速路径的偏离加速度

默认参数：快线 10、慢线 20、信号线 7；价格默认收盘价。
"""

from __future__ import annotations

from company.analysis.line.MACD.core import (
    DEFAULT_FAST,
    DEFAULT_SIGNAL,
    DEFAULT_SLOW,
    PRICE_LABELS,
    PRICE_OPTIONS,
    compute_macd,
)
from company.analysis.line.MACD.prior_below import (
    DEFAULT_MIN_BARS,
    DEFAULT_MIN_LOG_MOVE,
    UNDER_SIGNALS,
    analyze_prior_below,
    find_dif_below_span,
    log_uniform_sum_dev,
)
from company.analysis.line.MACD.service import analyze_macd

__all__ = [
    "DEFAULT_FAST",
    "DEFAULT_SLOW",
    "DEFAULT_SIGNAL",
    "DEFAULT_MIN_BARS",
    "DEFAULT_MIN_LOG_MOVE",
    "PRICE_LABELS",
    "PRICE_OPTIONS",
    "UNDER_SIGNALS",
    "analyze_macd",
    "analyze_prior_below",
    "compute_macd",
    "find_dif_below_span",
    "log_uniform_sum_dev",
]
