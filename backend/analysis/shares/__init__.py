"""日线多日条件筛选。

用法示例见 ``python -m analysis.shares --help``。
"""

from analysis.shares.compare import screen_compare
from analysis.shares.days import list_trade_days
from analysis.shares.pattern import screen_scheme
from analysis.shares.screen import screen_shares
from analysis.shares.service import service

__all__ = [
    "list_trade_days",
    "screen_shares",
    "screen_scheme",
    "screen_compare",
    "service",
]
