"""雪球个股讨论 / 交易，以及关键词搜帖。

个股页「讨论」「交易」「全部」走搜索接口；「资讯 / 公告」请用 timeline。

    GET https://api.xueqiu.com/query/v1/symbol/search/status.json
    - symbol   SH600519
    - source   all / user / trans
    - sort     time / alpha
    - page / count

关键词：

    GET https://xueqiu.com/statuses/search.json
    - q / sort / page / count / source
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

from core.codes import normalize_code, safe_str

from company.news.platforms.xueqiu._common import (
    KEYWORD_SEARCH_API,
    REQUEST_PAUSE_SEC,
    SEARCH_API,
    SEARCH_API_FALLBACK,
    SOURCE,
    WEB_HOST,
    date_range,
    dedupe,
    empty_pack,
    get_payload,
    headers_for,
    in_range,
    map_choice,
    normalize_status,
    oldest_day,
    relevant,
    resolve_keyword,
    search_page_url,
    stock_page_url,
    xq_symbol,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 10
MAX_PAGES = 5

SEARCH_SOURCES: dict[str, str] = {
    "all": "all",
    "全部": "all",
    "user": "user",
    "discuss": "user",
    "讨论": "user",
    "trans": "trans",
    "交易": "trans",
    "report": "研报",
    "reports": "研报",
    "研报": "研报",
}
SORTS: dict[str, str] = {
    "time": "time",
    "最新": "time",
    "alpha": "alpha",
    "hot": "alpha",
    "热门": "alpha",
    "reply": "reply",
    "评论": "reply",
}


def resolve_source(source: str | None) -> str:
    return map_choice(source, SEARCH_SOURCES, "all", "source")


def resolve_sort(sort: str | None) -> str:
    return map_choice(sort, SORTS, "time", "sort")


def query_page(
    symbol: str,
    *,
    source: str = "all",
    sort: str = "time",
    page: int = 1,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """个股讨论单页原始 JSON。"""
    payload = get_payload(
        SEARCH_API,
        params={
            "count": max(1, min(int(page_size), 20)),
            "comment": "0",
            "symbol": symbol,
            "hl": "0",
            "source": resolve_source(source),
            "sort": resolve_sort(sort),
            "page": max(1, int(page)),
        },
        headers=headers_for(stock_page_url(symbol), origin=WEB_HOST),
        timeout=20,
        fallback=SEARCH_API_FALLBACK,
    )
    return payload if isinstance(payload, dict) else {}


def query_keyword_page(
    keyword: str,
    *,
    symbol: str = "",
    source: str = "all",
    sort: str = "time",
    page: int = 1,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """关键词搜帖单页原始 JSON。"""
    params: dict[str, Any] = {
        "q": keyword,
        "count": max(1, min(int(page_size), 20)),
        "page": max(1, int(page)),
        "sort": resolve_sort(sort),
    }
    src = resolve_source(source)
    if src and src != "all":
        params["source"] = src
    if symbol:
        params["symbol"] = symbol
    payload = get_payload(
        KEYWORD_SEARCH_API,
        params=params,
        headers=headers_for(WEB_HOST + "/", origin=WEB_HOST),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def _channel_of(source: str) -> str:
    return {"user": "discuss", "trans": "trans", "all": "discuss", "研报": "report"}.get(
        source, "discuss"
    )


def _collect(
    *,
    query,
    resolved: dict[str, str],
    source: str,
    start_d,
    end_d,
    max_pages: int,
    page_size: int,
    strict: bool,
    page_url: str,
    channel: str,
) -> dict[str, Any]:
    code = resolved["code"]
    name = resolved["name"]
    symbol = resolved.get("symbol") or ""
    items: list[dict[str, Any]] = []
    total = 0
    page = 1
    limit = max(1, int(max_pages))
    size = max(1, min(int(page_size), 20))
    while page <= limit:
        try:
            payload = query(page=page, page_size=size)
        except Exception as exc:  # noqa: BLE001
            logger.warning("雪球搜索失败 page=%s: %s", page, exc)
            if page == 1:
                return empty_pack(
                    code=code,
                    name=name,
                    keyword=resolved.get("keyword") or "",
                    channel=channel,
                    error=str(exc),
                    page=page_url,
                    symbol=symbol,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        rows = payload.get("list") or payload.get("statuses") or []
        total = int(payload.get("count") or payload.get("total") or total or 0)
        if not isinstance(rows, list) or not rows:
            break
        page_items: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = normalize_status(
                row, code=code, name=name, channel=channel, symbol=symbol
            )
            if not item:
                continue
            if strict and not relevant(
                item, code=code, name=name, keyword=resolved.get("keyword") or ""
            ):
                continue
            page_items.append(item)
            if in_range(item, start_d, end_d):
                items.append(item)
        if start_d:
            old = oldest_day(page_items)
            if old and old < start_d:
                break
        if len(rows) < size:
            break
        page += 1
        if page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = dedupe(items)
    return {
        "code": code,
        "name": name,
        "keyword": resolved.get("keyword") or "",
        "symbol": symbol,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": channel,
        "search_source": source,
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": page_url,
    }


def fetch_discuss(
    code_or_name: str,
    *,
    source: str = "user",
    sort: str = "time",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 7,
    max_pages: int = MAX_PAGES,
    page_size: int = PAGE_SIZE,
    strict: bool = False,
) -> dict[str, Any]:
    """个股讨论 / 交易 / 全部帖。"""
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    symbol = resolved["symbol"] or xq_symbol(code or code_or_name)
    page_url = stock_page_url(symbol)
    if not symbol:
        return empty_pack(
            code=code,
            name=resolved["name"],
            keyword=resolved["keyword"],
            channel="discuss",
            error="缺少股票代码",
            page=page_url,
        )
    src = resolve_source(source)
    start_d, end_d = date_range(start, end, days)

    def _query(*, page: int, page_size: int) -> dict[str, Any]:
        return query_page(symbol, source=src, sort=sort, page=page, page_size=page_size)

    return _collect(
        query=_query,
        resolved={**resolved, "code": code, "symbol": symbol},
        source=src,
        start_d=start_d,
        end_d=end_d,
        max_pages=max_pages,
        page_size=page_size,
        strict=strict,
        page_url=page_url,
        channel=_channel_of(src),
    )


def search_posts(
    keyword: str,
    *,
    symbol: str = "",
    source: str = "all",
    sort: str = "time",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    max_pages: int = MAX_PAGES,
    page_size: int = PAGE_SIZE,
    strict: bool = False,
) -> dict[str, Any]:
    """按关键词搜雪球帖子。``symbol`` 非空时限定个股。"""
    kw = safe_str(keyword)
    resolved = resolve_keyword(symbol) if symbol else {"code": "", "name": "", "keyword": kw, "symbol": ""}
    if not symbol:
        resolved["keyword"] = kw
    else:
        resolved["keyword"] = kw or resolved["keyword"]
    sym = resolved.get("symbol") or xq_symbol(symbol)
    page_url = search_page_url(kw or symbol)
    if not kw and not sym:
        return empty_pack(channel="search", error="缺少关键词", page=page_url)
    src = resolve_source(source)
    start_d, end_d = date_range(start, end, days)

    def _query(*, page: int, page_size: int) -> dict[str, Any]:
        return query_keyword_page(
            kw or resolved["keyword"],
            symbol=sym,
            source=src,
            sort=sort,
            page=page,
            page_size=page_size,
        )

    pack = _collect(
        query=_query,
        resolved={**resolved, "symbol": sym},
        source=src,
        start_d=start_d,
        end_d=end_d,
        max_pages=max_pages,
        page_size=page_size,
        strict=strict,
        page_url=page_url,
        channel="search",
    )
    pack["keyword"] = kw or pack.get("keyword") or ""
    return pack
