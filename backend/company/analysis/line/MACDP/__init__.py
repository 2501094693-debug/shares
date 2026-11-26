"""MACDP：成交均价 + 成交量加权快慢线 + 固定信号线。

- ``compute_macdp``  纯函数：均价序列上算 DIF / DEA / MACD
- ``analyze_macdp``  主入口：东财/同花顺日线（含成交额）后调用 ``compute_macdp``

默认参数：快线 10、慢线 20、信号线 7。
快慢线 ``α = V_t / (前 N 日量之和 + V_t)``；DEA ``α = 1/(signal+1)``。
"""

from __future__ import annotations

from company.analysis.line.MACDP.core import (
    DEFAULT_FAST,
    DEFAULT_SIGNAL,
    DEFAULT_SLOW,
    compute_macdp,
)
from company.analysis.line.MACDP.service import analyze_macdp

__all__ = [
    "DEFAULT_FAST",
    "DEFAULT_SLOW",
    "DEFAULT_SIGNAL",
    "analyze_macdp",
    "compute_macdp",
]
