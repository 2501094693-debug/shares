"""上市公司定期报告（年报 / 半年报 / 一季报 / 三季报）。

默认返回最新一期，并附带报告期列表供前端切换。
"""

from company.news.periodicreport.fetch import fetch_periodic_report
from company.news.periodicreport.fetcher import get_periodic_report

__all__ = [
    "fetch_periodic_report",
    "get_periodic_report",
]
