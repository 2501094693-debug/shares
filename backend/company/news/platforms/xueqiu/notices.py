"""雪球个股公告：个股页「公告」Tab。

    GET https://api.xueqiu.com/statuses/stock_timeline.json
    - source  公告

这是雪球转载的监管披露，一手请走巨潮 / 交易所。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from company.news.platforms.xueqiu._common import fetch_stock_statuses, query_timeline

PAGE_SIZE = 10
MAX_PAGES = 8


def query_page(
    symbol: str,
    *,
    page: int = 1,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """个股公告单页原始 JSON。"""
    return query_timeline(symbol, source="公告", page=page, count=page_size)


def fetch_notices(
    code_or_name: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    max_pages: int = MAX_PAGES,
    page_size: int = PAGE_SIZE,
    strict: bool = False,
) -> dict[str, Any]:
    """按股票拉雪球公告列表。"""
    return fetch_stock_statuses(
        code_or_name,
        source="公告",
        channel="notice",
        start=start,
        end=end,
        days=days,
        max_pages=max_pages,
        page_size=page_size,
        strict=strict,
    )
