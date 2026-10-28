"""个股详情扩展：同花顺手机端行情通道。"""

from company.detail.ths_mobile import (
    ThsMobileError,
    fetch_snapshot,
    fetch_ticks,
    fetch_trace,
    fetch_trend,
    market_of,
)

__all__ = [
    "ThsMobileError",
    "fetch_snapshot",
    "fetch_ticks",
    "fetch_trace",
    "fetch_trend",
    "market_of",
]
