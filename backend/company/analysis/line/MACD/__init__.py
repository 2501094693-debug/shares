"""MACD：快慢线差离值 + 信号线 + 柱线。

- ``compute_macd``  纯函数：在日线序列上算 DIF / DEA / MACD
- ``analyze_macd``  主入口：拉日线后调用 ``compute_macd``

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
from company.analysis.line.MACD.service import analyze_macd

__all__ = [
    "DEFAULT_FAST",
    "DEFAULT_SLOW",
    "DEFAULT_SIGNAL",
    "PRICE_LABELS",
    "PRICE_OPTIONS",
    "analyze_macd",
    "compute_macd",
]
