"""东财搜索股吧帖：``so.eastmoney.com`` 背后的 ``gubaArticle`` JSONP。

    GET https://search-api-web.eastmoney.com/search/jsonp
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from core.codes import safe_str

from company.emotion.eastmoney._common import (
    CHANNEL_SEARCH,
    REQUEST_PAUSE_SEC,
    SEARCH_API,
    SOURCE,
    date_range,
    dedupe,
    empty_pack,
    get_payload,
    headers_for,
    in_range,
    jsonp_callback,
    map_choice,
    normalize_post,
    req_trace,
    resolve_keyword,
    search_page_url,
    strip_em,
    strip_html,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 20
MAX_PAGES = 50
SEARCH_TYPE = "gubaArticle"

SORTS: dict[str, str] = {
    "time": "time",
    "时间": "time",
    "最新": "time",
    "default": "default",
    "relevance": "default",
    "相关度": "default",
}


def resolve_sort(sort: str | None) -> str:
    return map_choice(sort, SORTS, "time", "sort")


def query_page(
    keyword: str,
    *,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    sort: str = "time",
) -> dict[str, Any]:
    """股吧搜索单页原始 JSON（已剥 JSONP）。"""
    kw = safe_str(keyword)
    inner = {
        "uid": "",
        "keyword": kw,
        "type": [SEARCH_TYPE],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            SEARCH_TYPE: {
                "searchScope": "default",
                "sort": sort or "time",
                "pageIndex": max(1, int(page)),
                "pageSize": max(1, min(int(page_size), 50)),
                "preTag": "",
                "postTag": "",
            }
        },
    }
    payload = get_payload(
        SEARCH_API,
        params={
            "cb": jsonp_callback(),
            "param": json.dumps(inner, ensure_ascii=False),
            "_": req_trace(),
        },
        headers=headers_for(f"https://so.eastmoney.com/web/s?keyword={quote(kw)}"),
        timeout=25,
    )
    return payload if isinstance(payload, dict) else {}


def _normalize_row(row: dict[str, Any], *, code: str = "", name: str = "") -> dict[str, Any] | None:
    item = normalize_post(row, code=code, name=name, kind="search", channel=CHANNEL_SEARCH)
    if not item:
        return None
    item["title"] = strip_html(strip_em(item.get("title") or ""))
    item["summary"] = strip_html(strip_em(safe_str(row.get("introduction") or item.get("summary"))))
    item["content"] = strip_html(strip_em(safe_str(row.get("content") or item.get("content"))))
    item["guba_name"] = safe_str(row.get("gubaName") or item.get("guba_name"))
    item["media_name"] = item.get("author") or item.get("guba_name")
    return item


def search_posts(
    keyword: str,
    *,
    code: str = "",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    sort: str | None = "time",
    max_pages: int = 3,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """按关键词搜股吧帖。``code`` 只写进结果，搜索接口本身不按代码过滤。"""
    resolved = resolve_keyword(code) if code else {"code": "", "name": "", "keyword": ""}
    kw = safe_str(keyword) or resolved.get("keyword") or resolved.get("code") or ""
    page_url = search_page_url(kw)
    if not kw:
        return empty_pack(channel=CHANNEL_SEARCH, error="缺少检索关键词", page=page_url)

    api_sort = resolve_sort(sort)
    start_d, end_d = date_range(start, end, days)
    items: list[dict[str, Any]] = []
    total = 0
    page = 1
    limit = max(1, min(int(max_pages), MAX_PAGES))
    stock = resolved.get("code") or ""
    name = resolved.get("name") or ""

    while page <= limit:
        try:
            payload = query_page(kw, page=page, page_size=page_size, sort=api_sort)
        except Exception as exc:  # noqa: BLE001
            logger.warning("股吧搜索失败 page=%s: %s", page, exc)
            if page == 1:
                return empty_pack(
                    code=stock,
                    name=name,
                    keyword=kw,
                    channel=CHANNEL_SEARCH,
                    error=str(exc),
                    page=page_url,
                    sort=api_sort,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        rows = (payload.get("result") or {}).get(SEARCH_TYPE) or []
        total = int(payload.get("hitsTotal") or total)
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _normalize_row(row, code=stock, name=name)
            if item and in_range(item, start_d, end_d):
                items.append(item)
        if page * page_size >= total > 0:
            break
        page += 1
        if page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = dedupe(items)
    return {
        "code": stock,
        "name": name,
        "keyword": kw,
        "sort": api_sort,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": CHANNEL_SEARCH,
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": page_url,
    }
