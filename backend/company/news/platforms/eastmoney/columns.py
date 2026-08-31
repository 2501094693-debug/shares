"""东财栏目新闻：``getNewsByColumns``。

财经早餐等栏目页走这套接口。栏目 ID 以页面 Network 里的 ``column=`` 为准；
本模块内置若干别名，也接受纯数字 ID。

    GET https://np-listapi.eastmoney.com/comm/web/getNewsByColumns
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

from core.codes import safe_str

from company.news.platforms.eastmoney._common import (
    REQUEST_PAUSE_SEC,
    SOURCE,
    article_url,
    date_range,
    dedupe,
    empty_pack,
    fmt_dt,
    get_payload,
    headers_for,
    in_range,
    map_choice,
    req_trace,
)

logger = logging.getLogger(__name__)

COLUMN_API = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
COLUMN_FIELDS = "code,showTime,title,mediaName,summary,image,url,uniqueUrl,Np_dst"
PAGE_SIZE = 20

# 已知栏目。其它 ID 直接传数字即可。
COLUMNS: dict[str, str] = {
    "breakfast": "1207",
    "财经早餐": "1207",
    "cjzc": "1207",
    "1207": "1207",
}


def resolve_column(column: str | None) -> str:
    raw = safe_str(column)
    if raw.isdigit():
        return raw
    return map_choice(column, COLUMNS, "breakfast", "column")


def column_page_url(column: str) -> str:
    col = resolve_column(column)
    if col == "1207":
        return "https://finance.eastmoney.com/a/cjzc.html"
    return f"https://finance.eastmoney.com/news/{col}.html"


def query_page(
    column: str = "1207",
    *,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    order: int = 1,
) -> dict[str, Any]:
    """栏目单页原始 JSON。``req_trace`` 必填。"""
    ts = req_trace()
    payload = get_payload(
        COLUMN_API,
        params={
            "client": "web",
            "biz": "web_news_col",
            "column": str(column),
            "order": str(order),
            "needInteractData": "0",
            "page_index": max(1, int(page)),
            "page_size": max(1, min(int(page_size), 200)),
            "req_trace": ts,
            "fields": COLUMN_FIELDS,
            "types": "1,20",
        },
        headers=headers_for("https://finance.eastmoney.com/"),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def _normalize_row(row: dict[str, Any], *, column: str) -> dict[str, Any] | None:
    title = safe_str(row.get("title"))
    if not title:
        return None
    article_id = safe_str(row.get("code"))
    url = safe_str(row.get("uniqueUrl") or row.get("url")) or article_url(article_id)
    return {
        "article_id": article_id,
        "title": title,
        "summary": safe_str(row.get("summary")),
        "published_at": fmt_dt(row.get("showTime")),
        "url": url.replace("http://", "https://", 1) if url else "",
        "source": SOURCE,
        "channel": "column",
        "column": column,
        "media_name": safe_str(row.get("mediaName")),
        "image": safe_str(row.get("image")),
        "np_dst": safe_str(row.get("np_dst") or row.get("Np_dst")),
    }


def fetch_column_news(
    column: str | None = "breakfast",
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    max_pages: int = 2,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """按栏目拉新闻列表。默认财经早餐。"""
    col = resolve_column(column)
    page_url = column_page_url(col)
    start_d, end_d = date_range(start, end, days)
    items: list[dict[str, Any]] = []
    total = 0
    total_pages = 1
    page = 1
    limit = max(1, int(max_pages))
    while page <= total_pages and page <= limit:
        try:
            payload = query_page(col, page=page, page_size=page_size)
        except Exception as exc:  # noqa: BLE001
            logger.warning("东财栏目失败 column=%s page=%s: %s", col, page, exc)
            if page == 1:
                return empty_pack(
                    channel="column",
                    error=str(exc),
                    page=page_url,
                    column=col,
                )
            break
        if safe_str(payload.get("code")) not in {"1", "0"} and page == 1:
            return empty_pack(
                channel="column",
                error=safe_str(payload.get("message")) or "栏目接口失败",
                page=page_url,
                column=col,
            )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        rows = data.get("list") or []
        total = int(data.get("totle_hits") or data.get("total_hits") or total)
        if total:
            total_pages = max(1, (total + page_size - 1) // page_size)
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _normalize_row(row, column=col)
            if item and in_range(item, start_d, end_d):
                items.append(item)
        if page >= total_pages:
            break
        page += 1
        if page <= total_pages and page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = dedupe(items)
    return {
        "code": "",
        "name": "",
        "keyword": "",
        "column": col,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": "column",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": page_url,
    }
