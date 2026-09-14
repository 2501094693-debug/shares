"""东方财富个股资金流向。

- ``stock``    历史日线、当日分钟、当日快照
- ``fetcher``  带缓存的统一入口
"""

from company.statistics.fundflow.eastmoney.fetcher import get_fund_flow
from company.statistics.fundflow.eastmoney.stock import fetch_daily, fetch_minute, fetch_snapshot

__all__ = [
    "fetch_daily",
    "fetch_minute",
    "fetch_snapshot",
    "get_fund_flow",
]
