"""雪球个股研报。

个股页「研报」走搜索接口，``stock_timeline.json`` 的 ``source=研报`` 现在返回空列表。

    GET https://api.xueqiu.com/query/v1/symbol/search/status.json
    - symbol  SH600519
    - source  研报
    - sort / page / count
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from company.news.xueqiu.search import fetch_discuss, query_page as query_search_page

PAGE_SIZE = 10
MAX_PAGES = 8


def query_page(
    symbol: str,
    *,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    sort: str = "time",
) -> dict[str, Any]:
    """个股研报单页原始 JSON。"""
    return query_search_page(
        symbol, source="研报", sort=sort, page=page, page_size=page_size
    )


def fetch_reports(
    code_or_name: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    max_pages: int = MAX_PAGES,
    page_size: int = PAGE_SIZE,
    strict: bool = False,
    sort: str = "time",
) -> dict[str, Any]:
    """按股票拉雪球研报列表。"""
    pack = fetch_discuss(
        code_or_name,
        source="研报",
        sort=sort,
        start=start,
        end=end,
        days=days,
        max_pages=max_pages,
        page_size=page_size,
        strict=strict,
    )
    pack["channel"] = "report"
    pack["timeline_source"] = "研报"
    return pack
