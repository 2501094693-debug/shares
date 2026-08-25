"""个股盘口：东财 / 腾讯并行拉取，拼成公司详情页指标。"""

from company.statistics.fetcher import QUOTE_TTL, fetch_stock_quote

__all__ = ["QUOTE_TTL", "fetch_stock_quote"]
