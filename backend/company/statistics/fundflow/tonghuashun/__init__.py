"""同花顺个股资金流向（stockpage spService + data ddzz）。

- ``stock``     当日快照、分钟序列
- ``big_deal``  数据中心逐笔大单
- ``fetcher``   带缓存的统一入口
"""

from company.statistics.fundflow.tonghuashun.big_deal import fetch_big_deals
from company.statistics.fundflow.tonghuashun.fetcher import get_fund_flow
from company.statistics.fundflow.tonghuashun.stock import fetch_daily, fetch_intraday, fetch_snapshot

__all__ = [
    "fetch_big_deals",
    "fetch_daily",
    "fetch_intraday",
    "fetch_snapshot",
    "get_fund_flow",
]
