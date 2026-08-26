"""雪球个股讨论：个股页「讨论 / 交易 / 全部」。

    GET https://api.xueqiu.com/query/v1/symbol/search/status.json
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

from company.emotion.xueqiu._common import (
    CHANNEL_POSTS,
    REQUEST_PAUSE_SEC,
    community_item,
    stock_page_url,
    to_int,
)
from company.news.xueqiu.search import (
    SEARCH_SOURCES,
    fetch_discuss,
    query_page,
    resolve_sort,
    resolve_source,
)

logger = logging.getLogger(__name__)

KINDS = SEARCH_SOURCES
PAGE_SIZE = 10
MAX_PAGES = 20


def resolve_kind(kind: str | None) -> str:
    return resolve_source(kind or "user")


def fetch_posts(
    code_or_name: str,
    *,
    kind: str | None = "user",
    sort: str | None = "time",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    max_pages: int = 3,
    page_size: int = PAGE_SIZE,
    with_replies: bool = False,
    max_reply_posts: int = 10,
    max_reply_pages: int = 1,
    strict: bool = False,
) -> dict[str, Any]:
    """按股票拉雪球讨论帖。``days`` 为空则只按 ``max_pages`` 截断。"""
    src = resolve_kind(kind)
    pack = fetch_discuss(
        code_or_name,
        source=src,
        sort=sort or "time",
        start=start,
        end=end,
        days=days,
        max_pages=max(1, min(int(max_pages), MAX_PAGES)),
        page_size=page_size,
        strict=strict,
    )
    items = [
        community_item(row, channel=CHANNEL_POSTS)
        for row in pack.get("items") or []
        if isinstance(row, dict)
    ]
    items = [row for row in items if row]
    if with_replies:
        items = _attach_replies(items, max_posts=max_reply_posts, max_pages=max_reply_pages)
    out = dict(pack)
    out["channel"] = CHANNEL_POSTS
    out["kind"] = src
    out["sort"] = resolve_sort(sort)
    out["items"] = items
    out["count"] = len(items)
    if not out.get("page"):
        out["page"] = stock_page_url(str(out.get("symbol") or code_or_name))
    return out


def _attach_replies(
    items: list[dict[str, Any]],
    *,
    max_posts: int,
    max_pages: int,
) -> list[dict[str, Any]]:
    from company.emotion.xueqiu.replies import fetch_replies

    budget = max(0, int(max_posts))
    attached = 0
    for item in items:
        if attached >= budget:
            break
        if to_int(item.get("comment_count")) <= 0:
            item["replies"] = []
            continue
        pack = fetch_replies(
            item.get("post_id") or "",
            code=item.get("code") or "",
            max_pages=max(1, int(max_pages)),
        )
        item["replies"] = pack.get("items") or []
        if pack.get("error"):
            item["replies_error"] = pack["error"]
        attached += 1
        time.sleep(REQUEST_PAUSE_SEC)
    return items
