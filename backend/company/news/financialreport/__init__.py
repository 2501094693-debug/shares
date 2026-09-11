"""东方财富 F10 财务报表。

- ``statements``  五类报表拉取与按报告期合并
- ``fetcher``     带缓存的统一入口
- ``api``         FastAPI 路由
"""

from company.news.financialreport.fetcher import get_financial_report
from company.news.financialreport.statements import fetch_all_statements, fetch_statement

__all__ = [
    "fetch_all_statements",
    "fetch_statement",
    "get_financial_report",
]
