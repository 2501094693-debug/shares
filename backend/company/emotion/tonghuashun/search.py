"""同花顺社区搜索：关键词解析成股票后拉手机讨论流。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from core.codes import normalize_code, safe_str

from company.emotion.tonghuashun._common import (
    CHANNEL_SEARCH,
    empty_pack,
    mobile_page_url,
    resolve_keyword,
    search_page_url,
)
from company.emotion.tonghuashun.posts import fetch_posts, query_page as query_post_page


def query_page(
    keyword: str,
    *,
    code: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    del page_size
    stock = normalize_code(code) or resolve_keyword(keyword).get("code") or ""
    if not stock:
        return {}
    return query_post_page(stock, page=page, first=page == 1)


def search_posts(
    keyword: str,
    *,
    code: str = "",
    days: int | None = None,
    sort: str | None = "hot",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    max_pages: int = 3,
    strict: bool = False,
) -> dict[str, Any]:
    """关键词能解析成股票则拉该股手机讨论。"""
    kw = safe_str(keyword)
    resolved = resolve_keyword(code or kw)
    stock = resolved["code"] or normalize_code(code) or normalize_code(kw)
    if not stock:
        return empty_pack(
            keyword=kw,
            channel=CHANNEL_SEARCH,
            error="缺少股票代码",
            page=search_page_url(kw),
        )
    pack = fetch_posts(
        stock,
        sort=sort,
        start=start,
        end=end,
        days=days,
        max_pages=max_pages,
    )
    items = list(pack.get("items") or [])
    needle = kw if kw and kw != stock and kw != resolved.get("name") else ""
    if needle and (strict or code):
        items = [
            row
            for row in items
            if needle in f"{row.get('title', '')} {row.get('content', '')}"
        ]
    out = dict(pack)
    out["channel"] = CHANNEL_SEARCH
    out["keyword"] = kw or pack.get("keyword") or ""
    out["items"] = items
    out["count"] = len(items)
    out["page"] = mobile_page_url(stock)
    return out
