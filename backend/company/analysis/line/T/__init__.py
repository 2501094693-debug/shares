"""聪明投机者：首日低价买，其后每日高卖低买（量=成交量×比例）。

- ``compute_trader``  纯函数：在日线序列上模拟，返回期末股数 / 均价
- ``analyze_trader``  主入口：拉日线后调用 ``compute_trader``
"""

from __future__ import annotations

from company.analysis.line.T.core import DEFAULT_RATIO, compute_trader
from company.analysis.line.T.service import analyze_trader

__all__ = [
    "DEFAULT_RATIO",
    "analyze_trader",
    "compute_trader",
]
