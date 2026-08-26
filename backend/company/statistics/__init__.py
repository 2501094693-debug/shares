"""个股盘口：东财 / 腾讯并行拉取，拼成公司详情页指标。"""

from company.statistics.fetcher import QUOTE_TTL, fetch_stock_quote
from company.statistics.pe_history import PE_TTL, fetch_pe_history

__all__ = ["PE_TTL", "QUOTE_TTL", "fetch_pe_history", "fetch_stock_quote"]
