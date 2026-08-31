"""雪球个股资讯：个股页「资讯」Tab。

    GET https://api.xueqiu.com/statuses/stock_timeline.json
    - symbol_id / symbol  SH600519
    - source              自选股新闻
    - count / page

讨论 / 交易走 ``search``；公告、研报见同目录其它模块。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from company.news.platforms.xueqiu._common import (
    fetch_stock_statuses,
    query_timeline,
    resolve_timeline_source,
)

PAGE_SIZE = 10
MAX_PAGES = 8


def query_page(
    symbol: str,
    *,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    source: str = "自选股新闻",
) -> dict[str, Any]:
    """个股资讯单页原始 JSON。"""
    src = resolve_timeline_source(source, "news")
    return query_timeline(symbol, source=src, page=page, count=page_size)


def fetch_news(
    code_or_name: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 31,
    max_pages: int = MAX_PAGES,
    page_size: int = PAGE_SIZE,
    strict: bool = False,
) -> dict[str, Any]:
    """按股票代码或公司名拉雪球个股资讯。"""
    return fetch_stock_statuses(
        code_or_name,
        source="自选股新闻",
        channel="news",
        start=start,
        end=end,
        days=days,
        max_pages=max_pages,
        page_size=page_size,
        strict=strict,
    )


def search_news(code_or_name: str, **kwargs: Any) -> dict[str, Any]:
    return fetch_news(code_or_name, **kwargs)
