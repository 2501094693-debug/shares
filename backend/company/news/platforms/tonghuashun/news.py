"""同花顺个股新闻：F10「热点新闻列表」。

个股资讯页：https://basic.10jqka.com.cn/600519/news.html

    GET https://basic.10jqka.com.cn/basicapi/notice/news
    - type     stock
    - code     六位代码
    - current  页码，从 1 起（不是 page）
    - limit    每页条数

这是 F10 热点窗口，``total`` 经常卡在 100，不是全历史。
列表只有标题和链接；正文见 ``article.fetch_article``。
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

from core.codes import normalize_code, safe_str

from company.news.platforms.tonghuashun._common import (
    NEWS_API,
    REQUEST_PAUSE_SEC,
    SOURCE,
    date_range,
    dedupe,
    empty_pack,
    f10_news_url,
    fmt_dt,
    get_payload,
    headers_for,
    in_range,
    oldest_day,
    relevant,
    resolve_keyword,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 15
MAX_PAGES = 8
NEWS_CAP = 100


def query_page(
    code: str,
    *,
    page: int = 1,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """个股热点新闻单页原始 JSON。"""
    stock = normalize_code(code) or safe_str(code)
    payload = get_payload(
        NEWS_API,
        params={
            "type": "stock",
            "code": stock,
            "current": max(1, int(page)),
            "limit": max(1, min(int(page_size), 50)),
        },
        headers=headers_for(f10_news_url(stock), origin="https://basic.10jqka.com.cn"),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def _normalize_row(
    row: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
) -> dict[str, Any] | None:
    title = safe_str(row.get("title"))
    seq = safe_str(row.get("seq"))
    if not title:
        return None
    url = safe_str(row.get("pc_url") or row.get("client_url") or row.get("mobile_url"))
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    published = fmt_dt(row.get("time") or row.get("date"))
    ymd = published[:10].replace("-", "")
    if not url and seq and ymd:
        url = f"https://stock.10jqka.com.cn/{ymd}/c{seq}.shtml"
    return {
        "code": code,
        "name": name,
        "article_id": seq,
        "seq": seq,
        "title": title,
        "summary": "",
        "published_at": published,
        "url": url,
        "mobile_url": safe_str(row.get("mobile_url")),
        "source": SOURCE,
        "channel": "news",
        "media_name": safe_str(row.get("source") or row.get("author")),
        "author": safe_str(row.get("author")),
    }


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
    """按股票代码或公司名拉 F10 热点新闻。

    接口按六位代码过滤，不是关键词搜索。``strict`` 为真时再按标题命中简称/代码。
    """
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    name = resolved["name"]
    page_url = f10_news_url(code)
    if not code:
        return empty_pack(
            code=code,
            name=name,
            keyword=resolved["keyword"],
            error="缺少股票代码",
            page=page_url,
        )

    start_d, end_d = date_range(start, end, days)
    items: list[dict[str, Any]] = []
    total = 0
    total_pages = 1
    page = 1
    limit = max(1, int(max_pages))
    size = max(1, min(int(page_size), 50))
    while page <= total_pages and page <= limit:
        try:
            payload = query_page(code, page=page, page_size=size)
        except Exception as exc:  # noqa: BLE001
            logger.warning("同花顺个股新闻失败 page=%s: %s", page, exc)
            if page == 1:
                return empty_pack(
                    code=code,
                    name=name,
                    keyword=resolved["keyword"],
                    error=str(exc),
                    page=page_url,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        status = payload.get("status_code")
        if status not in (0, "0", None):
            msg = safe_str(payload.get("status_msg")) or f"status_code={status}"
            if page == 1:
                return empty_pack(
                    code=code,
                    name=name,
                    keyword=resolved["keyword"],
                    error=msg,
                    page=page_url,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        rows = data.get("data") or []
        total = int(data.get("total") or total)
        if total:
            total_pages = max(1, (min(total, NEWS_CAP) + size - 1) // size)
        if not isinstance(rows, list) or not rows:
            break
        page_items: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _normalize_row(row, code=code, name=name)
            if not item:
                continue
            if strict and not relevant(item, code=code, name=name, keyword=resolved["keyword"]):
                continue
            if in_range(item, start_d, end_d):
                items.append(item)
            page_items.append(item)
        if start_d:
            old = oldest_day(page_items)
            if old and old < start_d:
                break
        if page >= total_pages or len(rows) < size:
            break
        page += 1
        if page <= total_pages and page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = dedupe(items)
    return {
        "code": code,
        "name": name,
        "keyword": resolved["keyword"],
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": "news",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": page_url,
    }


def search_news(code_or_name: str, **kwargs: Any) -> dict[str, Any]:
    return fetch_news(code_or_name, **kwargs)
