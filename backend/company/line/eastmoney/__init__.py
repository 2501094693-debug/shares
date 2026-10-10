"""东财行情：K 线 + 实时逐笔。"""

from company.line.eastmoney.kline import (
    ALL_PERIODS,
    BAR_PERIODS,
    DEFAULT_PERIODS,
    MINUTE_PERIODS,
    PERIOD_KLT,
    fetch_line,
    fetch_lines,
    resolve_secid,
)
from company.line.eastmoney.ticks import fetch_ticks

__all__ = [
    "ALL_PERIODS",
    "BAR_PERIODS",
    "DEFAULT_PERIODS",
    "MINUTE_PERIODS",
    "PERIOD_KLT",
    "fetch_line",
    "fetch_lines",
    "fetch_ticks",
    "resolve_secid",
]
