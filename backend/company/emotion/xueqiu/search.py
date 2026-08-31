"""雪球关键词搜帖：``query/v1/search/status.json``。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from company.emotion.xueqiu._common import CHANNEL_SEARCH, community_item
from company.news.platforms.xueqiu.search import (
    query_keyword_page,
    resolve_sort,
    search_posts as search_statuses,
)

PAGE_SIZE = 10
MAX_PAGES = 20


def query_page(
    keyword: str,
    *,
    symbol: str = "",
    source: str = "all",
    sort: str = "time",
    page: int = 1,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """关键词搜帖单页原始 JSON。"""
    return query_keyword_page(
        keyword,
        symbol=symbol,
        source=source,
        sort=sort,
        page=page,
        page_size=page_size,
    )


def search_posts(
    keyword: str,
    *,
    code: str = "",
    source: str = "all",
    sort: str | None = "time",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    max_pages: int = 3,
    page_size: int = PAGE_SIZE,
    strict: bool = False,
) -> dict[str, Any]:
    """按关键词搜雪球帖。``code`` 非空时限定个股。"""
    pack = search_statuses(
        keyword,
        symbol=code,
        source=source,
        sort=sort or "time",
        start=start,
        end=end,
        days=days,
        max_pages=max(1, min(int(max_pages), MAX_PAGES)),
        page_size=page_size,
        strict=strict,
    )
    items = [
        community_item(row, channel=CHANNEL_SEARCH)
        for row in pack.get("items") or []
        if isinstance(row, dict)
    ]
    items = [row for row in items if row]
    out = dict(pack)
    out["channel"] = CHANNEL_SEARCH
    out["sort"] = resolve_sort(sort)
    out["items"] = items
    out["count"] = len(items)
    return out
