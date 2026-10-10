"""同花顺实时逐笔 + 日 K。统一入口见 ``company.line.fetcher``（同花顺优先）。"""

from company.line.tonghuashun.hq_ticks import fetch_time_and_sales
from company.line.tonghuashun.kline import fetch_line as fetch_kline
from company.line.tonghuashun.kline import fetch_lines as fetch_klines

__all__ = [
    "fetch_kline",
    "fetch_klines",
    "fetch_time_and_sales",
]
