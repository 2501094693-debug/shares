"""当日分价表（同花顺 thsdk）：各价位已成交量汇总。

取数见 ``service``；CLI：``python -m company.analysis.deal.price_levels 600519``。
"""

from company.analysis.deal.price_levels.service import (
    SHARES_PER_LOT,
    fetch_price_levels,
    fetch_price_levels_pack,
)

__all__ = [
    "SHARES_PER_LOT",
    "fetch_price_levels",
    "fetch_price_levels_pack",
]
