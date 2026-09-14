"""个股盘口编排与数据源适配。"""

from company.statistics.quote.fetcher import QUOTE_TTL, fetch_live_quote, fetch_stock_quote

__all__ = ["QUOTE_TTL", "fetch_live_quote", "fetch_stock_quote"]
