"""股吧帖子列表：个股吧 HTML 内嵌 ``var article_list``。

    https://guba.eastmoney.com/list,600519,f_1.html
    https://guba.eastmoney.com/list,600519,99.html
    https://guba.eastmoney.com/list,600519,1,f.html
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

from core.codes import normalize_code, safe_str
from core.http import browser_get

from company.emotion.eastmoney._common import (
    CHANNEL_POSTS,
    REQUEST_PAUSE_SEC,
    SOURCE,
    date_range,
    dedupe,
    empty_pack,
    extract_article_list,
    headers_for,
    in_range,
    kind_type_code,
    list_page_url,
    map_choice,
    normalize_post,
    parse_day,
    resolve_keyword,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 80
MAX_PAGES = 50

# 股吧顶部分类。取值是规范化名，URL type 见 kind_type_code。
KINDS: dict[str, str] = {
    "all": "all",
    "全部": "all",
    "0": "all",
    "news": "news",
    "新闻": "news",
    "1": "news",
    "reports": "reports",
    "研报": "reports",
    "2": "reports",
    "notices": "notices",
    "公告": "notices",
    "3": "notices",
    "margin": "margin",
    "融资融券": "margin",
    "4": "margin",
    "other": "other",
    "其他": "other",
    "7": "other",
    "qa": "qa",
    "问董秘": "qa",
    "11": "qa",
    "meeting": "meeting",
    "说明会": "meeting",
    "20": "meeting",
    "hot": "hot",
    "热门": "hot",
    "99": "hot",
}

# reply=最新回复（默认列表）；time=发帖时间；hot=热门帖。
SORTS: dict[str, str] = {
    "time": "time",
    "发帖": "time",
    "最新": "time",
    "reply": "reply",
    "回复": "reply",
    "评论": "reply",
    "hot": "hot",
    "热门": "hot",
}


def resolve_kind(kind: str | None) -> str:
    return map_choice(kind, KINDS, "all", "kind")


def resolve_sort(sort: str | None) -> str:
    return map_choice(sort, SORTS, "time", "sort")


def query_page(
    code: str,
    *,
    kind: str = "all",
    sort: str = "time",
    page: int = 1,
) -> dict[str, Any]:
    """个股吧单页原始 ``article_list``。"""
    stock = normalize_code(code) or safe_str(code)
    url = list_page_url(stock, kind=kind, sort=sort, page=page)
    resp = browser_get(
        url,
        headers=headers_for(list_page_url(stock, kind=kind, sort=sort, page=1)),
        timeout=25,
    )
    resp.raise_for_status()
    payload = extract_article_list(resp.text or "")
    if not payload:
        raise RuntimeError(f"股吧列表未找到 article_list: {url}")
    payload["_page_url"] = url
    return payload


def fetch_posts(
    code_or_name: str,
    *,
    kind: str | None = "all",
    sort: str | None = "time",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    max_pages: int = 3,
    with_replies: bool = False,
    max_reply_posts: int = 10,
    max_reply_pages: int = 1,
) -> dict[str, Any]:
    """按股票拉股吧帖子。``days`` 为空则只按 ``max_pages`` 截断。"""
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    name = resolved["name"]
    api_kind = resolve_kind(kind)
    api_sort = resolve_sort(sort)
    page_url = list_page_url(code, kind=api_kind, sort=api_sort, page=1)
    if not code:
        return empty_pack(
            code=code,
            name=name,
            keyword=resolved["keyword"],
            channel=CHANNEL_POSTS,
            error="缺少股票代码",
            page=page_url,
            kind=api_kind,
            sort=api_sort,
        )

    start_d, end_d = date_range(start, end, days)
    items: list[dict[str, Any]] = []
    total = 0
    bar_name = name
    page = 1
    limit = max(1, min(int(max_pages), MAX_PAGES))
    stop_early = api_sort in {"time", "hot"} or api_kind != "all"

    while page <= limit:
        try:
            payload = query_page(code, kind=api_kind, sort=api_sort, page=page)
        except Exception as exc:  # noqa: BLE001
            logger.warning("股吧列表失败 %s page=%s: %s", code, page, exc)
            if page == 1:
                return empty_pack(
                    code=code,
                    name=name,
                    keyword=resolved["keyword"],
                    channel=CHANNEL_POSTS,
                    error=str(exc),
                    page=page_url,
                    kind=api_kind,
                    sort=api_sort,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        rows = payload.get("re") or []
        total = to_total(payload.get("count"), total)
        bar_name = safe_str(payload.get("bar_name")) or bar_name or name
        if not isinstance(rows, list) or not rows:
            break
        oldest_on_page = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = normalize_post(row, code=code, name=bar_name or name, kind=api_kind)
            if not item:
                continue
            day = parse_day(item.get("published_at"))
            if day and (oldest_on_page is None or day < oldest_on_page):
                oldest_on_page = day
            if in_range(item, start_d, end_d):
                items.append(item)
        if stop_early and start_d and oldest_on_page and oldest_on_page < start_d:
            break
        if len(rows) < 10:
            break
        page += 1
        if page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = dedupe(items)
    if with_replies:
        items = _attach_replies(items, max_posts=max_reply_posts, max_pages=max_reply_pages)

    return {
        "code": code,
        "name": bar_name or name,
        "keyword": resolved["keyword"],
        "kind": api_kind,
        "sort": api_sort,
        "type_code": kind_type_code(api_kind),
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": CHANNEL_POSTS,
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": page_url,
    }


def to_total(value: Any, fallback: int) -> int:
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        return fallback
    return n or fallback


def _attach_replies(
    items: list[dict[str, Any]],
    *,
    max_posts: int,
    max_pages: int,
) -> list[dict[str, Any]]:
    from company.emotion.eastmoney.replies import fetch_replies

    budget = max(0, int(max_posts))
    attached = 0
    for item in items:
        if attached >= budget:
            break
        if int(item.get("comment_count") or 0) <= 0:
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
