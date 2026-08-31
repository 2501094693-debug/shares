"""东财搜索：``so.eastmoney.com`` 背后的 JSONP 个股/关键词新闻。

检索页：https://so.eastmoney.com/news/s?keyword=贵州茅台

    GET https://search-api-web.eastmoney.com/search/jsonp
    - cb     jQuery 回调名
    - param  JSON：keyword / type / cmsArticleWebOld.pageIndex|pageSize|sort|searchScope

列表只有标题和摘要；正文见 ``article.fetch_article``。
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from core.codes import safe_str

from company.news.platforms.eastmoney._common import (
    REQUEST_PAUSE_SEC,
    SOURCE,
    article_url,
    date_range,
    dedupe,
    empty_pack,
    get_payload,
    headers_for,
    in_range,
    jsonp_callback,
    map_choice,
    relevant,
    req_trace,
    resolve_keyword,
    search_page_url,
    strip_em,
    strip_html,
)

logger = logging.getLogger(__name__)

SEARCH_API = "https://search-api-web.eastmoney.com/search/jsonp"
PAGE_SIZE = 20
MAX_PAGES = 50

# 搜索结果类型。old 是官网新闻检索默认；web 是较新的 cms 索引。
TYPES: dict[str, str] = {
    "old": "cmsArticleWebOld",
    "news": "cmsArticleWebOld",
    "article": "cmsArticleWebOld",
    "新闻": "cmsArticleWebOld",
    "web": "cmsArticleWeb",
    "cms": "cmsArticleWeb",
    "all": "all",
    "全部": "all",
}
SORTS: dict[str, str] = {
    "time": "time",
    "时间": "time",
    "default": "default",
    "relevance": "default",
    "相关度": "default",
}
SCOPES: dict[str, str] = {
    "default": "default",
    "a": "default",
    "ashare": "default",
    "global": "global",
    "全球": "global",
    "hk": "global",
    "us": "global",
}


def resolve_type(kind: str | None) -> str:
    return map_choice(kind, TYPES, "old", "type")


def resolve_sort(sort: str | None) -> str:
    return map_choice(sort, SORTS, "time", "sort")


def resolve_scope(scope: str | None) -> str:
    return map_choice(scope, SCOPES, "default", "scope")


def _type_names(kind: str) -> list[str]:
    if kind == "all":
        return ["cmsArticleWebOld", "cmsArticleWeb"]
    return [kind]


def query_page(
    keyword: str,
    *,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    sort: str = "time",
    scope: str = "default",
    kind: str = "cmsArticleWebOld",
) -> dict[str, Any]:
    """搜索单页原始 JSON（已剥 JSONP）。"""
    kw = safe_str(keyword)
    types = _type_names(kind)
    inner: dict[str, Any] = {
        "uid": "",
        "keyword": kw,
        "type": types,
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {},
    }
    for type_name in types:
        inner["param"][type_name] = {
            "searchScope": scope or "default",
            "sort": sort or "time",
            "pageIndex": max(1, int(page)),
            "pageSize": max(1, min(int(page_size), 50)),
            "preTag": "",
            "postTag": "",
        }
    cb = jsonp_callback()
    payload = get_payload(
        SEARCH_API,
        params={
            "cb": cb,
            "param": json.dumps(inner, ensure_ascii=False),
            "_": req_trace(),
        },
        headers=headers_for(f"https://so.eastmoney.com/news/s?keyword={quote(kw)}"),
        timeout=25,
    )
    return payload if isinstance(payload, dict) else {}


def _rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    rows: list[dict[str, Any]] = []
    for key in ("cmsArticleWebOld", "cmsArticleWeb"):
        block = result.get(key) or []
        if isinstance(block, dict):
            block = block.get("list") or block.get("data") or []
        if isinstance(block, list):
            rows.extend(x for x in block if isinstance(x, dict))
    return rows


def _normalize_row(
    row: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
) -> dict[str, Any] | None:
    title = strip_html(strip_em(safe_str(row.get("title"))))
    if not title:
        return None
    article_id = safe_str(row.get("code"))
    url = safe_str(row.get("url")) or article_url(article_id)
    return {
        "code": code,
        "name": name,
        "article_id": article_id,
        "title": title,
        "summary": strip_html(strip_em(safe_str(row.get("content")))),
        "published_at": safe_str(row.get("date")),
        "url": url.replace("http://", "https://", 1) if url else "",
        "source": SOURCE,
        "channel": "search",
        "media_name": safe_str(row.get("mediaName")),
        "image": safe_str(row.get("image")),
    }


def fetch_news(
    code_or_name: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 31,
    sort: str | None = "time",
    scope: str | None = "default",
    kind: str | None = "old",
    keyword: str = "",
    max_pages: int = 5,
    page_size: int = PAGE_SIZE,
    strict: bool = False,
) -> dict[str, Any]:
    """按股票代码或公司名检索东财新闻索引。

    ``kind``：``old`` / ``web`` / ``all``。
    ``scope``：``default`` A 股为主；``global`` 含港美。
    ``strict`` 为真时，标题或摘要须命中简称/代码。
    """
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"]
    name = resolved["name"]
    kw = safe_str(keyword) or resolved["keyword"]
    page_url = search_page_url(kw)
    if not kw:
        return empty_pack(code=code, name=name, keyword=kw, error="缺少检索关键词", page=page_url)

    api_sort = resolve_sort(sort)
    api_scope = resolve_scope(scope)
    api_kind = resolve_type(kind)
    start_d, end_d = date_range(start, end, days)

    items: list[dict[str, Any]] = []
    total = 0
    total_pages = 1
    page = 1
    limit = max(1, int(max_pages))
    while page <= total_pages and page <= limit:
        try:
            payload = query_page(
                kw,
                page=page,
                page_size=page_size,
                sort=api_sort,
                scope=api_scope,
                kind=api_kind,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("东财搜索失败 page=%s: %s", page, exc)
            if page == 1:
                return empty_pack(
                    code=code,
                    name=name,
                    keyword=kw,
                    error=str(exc),
                    page=page_url,
                    sort=api_sort,
                    scope=api_scope,
                    kind=api_kind,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        rows = _rows_from_payload(payload)
        total = int(payload.get("hitsTotal") or total)
        if total:
            total_pages = max(1, (total + page_size - 1) // page_size)
        if not rows:
            break
        for row in rows:
            item = _normalize_row(row, code=code, name=name)
            if not item:
                continue
            if strict and not relevant(item, code=code, name=name, keyword=kw):
                continue
            if in_range(item, start_d, end_d):
                items.append(item)
        if page >= total_pages:
            break
        page += 1
        if page <= total_pages and page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = dedupe(items)
    return {
        "code": code,
        "name": name,
        "keyword": kw,
        "sort": api_sort,
        "scope": api_scope,
        "kind": api_kind,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": "search",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": page_url,
    }


def search_news(code_or_name: str, **kwargs: Any) -> dict[str, Any]:
    return fetch_news(code_or_name, **kwargs)
