"""同花顺实时逐笔 + 多周期 K + 分时成交。统一入口见 ``company.line.fetcher``。"""

from company.line.tonghuashun import auth
from company.line.tonghuashun.hq_ticks import fetch_time_and_sales
from company.line.tonghuashun.kline import fetch_line as fetch_kline
from company.line.tonghuashun.kline import fetch_lines as fetch_klines

# 分时成交延迟导入：支持 ``from company.line.tonghuashun import fetch_intraday``，
# 同时避免 ``python -m company.line.tonghuashun.intraday`` 触发重复导入告警。
_LAZY = {"fetch_day_trend", "fetch_intraday"}

__all__ = [
    "fetch_kline",
    "fetch_klines",
    "fetch_time_and_sales",
    "fetch_day_trend",
    "fetch_intraday",
]


def __getattr__(name: str):
    if name in _LAZY:
        from company.line.tonghuashun import intraday

        return getattr(intraday, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
