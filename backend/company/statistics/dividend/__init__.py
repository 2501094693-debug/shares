"""个股分红数据。

- ``_common``  东财请求与解析（datacenter ``RPT_SHAREBONUS_DET`` + F10 ``BonusFinancing``）
- ``ths``      同花顺 F10 分红页解析（直接给出「AH分红总额」，含特别分红）
- ``fetcher``  带缓存的统一入口 ``get_dividends``（``source=eastmoney|ths``）
"""

from company.statistics.dividend.fetcher import DIVIDEND_TTL, get_dividends

__all__ = [
    "DIVIDEND_TTL",
    "get_dividends",
]
