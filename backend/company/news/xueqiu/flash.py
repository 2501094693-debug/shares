"""雪球 7×24 快讯：``/statuses/livenews/list.json``。

    GET https://xueqiu.com/statuses/livenews/list.json
    - since_id  固定 -1
    - max_id    首页 -1，下一页用返回的 next_max_id
    - count     每页条数

这是全市场短讯，不能按股票代码检索。``code`` 只做事后过滤。
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

from core.codes import normalize_code, safe_str

from company.news.xueqiu._common import (
    FLASH_API,
    REQUEST_PAUSE_SEC,
    SOURCE,
    WEB_HOST,
    article_url,
    date_range,
    dedupe,
    empty_pack,
    fmt_dt,
    get_payload,
    headers_for,
    in_range,
    normalize_status,
    oldest_day,
    relevant,
    resolve_keyword,
    strip_html,
    xq_symbol,
)

logger = logging.getLogger(__name__)

FLASH_PAGE = f"{WEB_HOST}/today"
PAGE_SIZE = 15
MAX_PAGES = 5


def query_page(
    *,
    max_id: int | str = -1,
    count: int = PAGE_SIZE,
    since_id: int | str = -1,
) -> dict[str, Any]:
    """快讯单页原始 JSON。"""
    payload = get_payload(
        FLASH_API,
        params={
            "since_id": since_id,
            "max_id": max_id,
            "count": max(1, min(int(count), 50)),
        },
        headers=headers_for(FLASH_PAGE, origin=WEB_HOST),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def _normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    item = normalize_status(row, channel="flash")
    text = strip_html(safe_str(row.get("text") or row.get("description")))
    if item:
        if text and not item.get("summary"):
            item["summary"] = text[:400]
            if not item.get("title"):
                item["title"] = text[:80]
        item["flash_id"] = safe_str(row.get("id") or item.get("article_id"))
        return item
    if not text:
        return None
    flash_id = safe_str(row.get("id"))
    target = safe_str(row.get("target"))
    return {
        "code": "",
        "name": "",
        "symbol": "",
        "article_id": flash_id,
        "status_id": flash_id,
        "flash_id": flash_id,
        "title": text[:80],
        "summary": text[:400],
        "published_at": fmt_dt(row.get("created_at")),
        "url": article_url(target) if target else "",
        "target": target,
        "source": SOURCE,
        "channel": "flash",
        "media_name": "雪球快讯",
        "related_stocks": [],
    }


def _hits_stock(item: dict[str, Any], code: str, name: str, symbol: str) -> bool:
    if not code and not name and not symbol:
        return True
    for row in item.get("related_stocks") or []:
        if symbol and safe_str(row.get("symbol")) == symbol:
            return True
        if code and code in safe_str(row.get("symbol")):
            return True
        if name and name in safe_str(row.get("name")):
            return True
    return relevant(item, code=code, name=name, keyword=name)


def fetch_flash(
    *,
    code: str = "",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    max_pages: int = MAX_PAGES,
    page_size: int = PAGE_SIZE,
    since_id: str = "",
) -> dict[str, Any]:
    """全市场快讯。``code`` 非空时按关联股票 / 标题过滤。

    ``since_id``：只保留 id 更大的条目，便于增量。
    """
    resolved = resolve_keyword(code) if code else {"code": "", "name": "", "keyword": "", "symbol": ""}
    stock = resolved["code"] or normalize_code(code)
    name = resolved["name"]
    symbol = resolved.get("symbol") or xq_symbol(code)
    start_d, end_d = date_range(start, end, days)
    since_num = 0
    if since_id:
        try:
            since_num = int(str(since_id).strip())
        except ValueError:
            since_num = 0

    items: list[dict[str, Any]] = []
    page = 1
    limit = max(1, int(max_pages))
    size = max(1, min(int(page_size), 50))
    max_id: int | str = -1
    next_max_id = ""
    while page <= limit:
        try:
            payload = query_page(max_id=max_id, count=size)
        except Exception as exc:  # noqa: BLE001
            logger.warning("雪球快讯失败 max_id=%s: %s", max_id, exc)
            if page == 1:
                return empty_pack(
                    code=stock,
                    name=name,
                    keyword=resolved.get("keyword") or "",
                    channel="flash",
                    error=str(exc),
                    page=FLASH_PAGE,
                    symbol=symbol,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        rows = payload.get("items") or payload.get("list") or []
        next_max_id = safe_str(payload.get("next_max_id"))
        if not isinstance(rows, list) or not rows:
            break
        page_items: list[dict[str, Any]] = []
        stop_older = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _normalize_row(row)
            if not item:
                continue
            if since_num:
                try:
                    if int(item.get("flash_id") or item.get("article_id") or 0) <= since_num:
                        stop_older = True
                        continue
                except ValueError:
                    pass
            page_items.append(item)
            if stock or name or symbol:
                if not _hits_stock(item, stock, name, symbol):
                    continue
            if in_range(item, start_d, end_d):
                items.append(item)
        if start_d:
            old = oldest_day(page_items)
            if old and old < start_d:
                break
        if stop_older or not next_max_id or len(rows) < size:
            break
        max_id = next_max_id
        page += 1
        if page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = dedupe(items)
    return {
        "code": stock,
        "name": name,
        "keyword": resolved.get("keyword") or "",
        "symbol": symbol,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": "flash",
        "count": len(items),
        "total": len(items),
        "items": items,
        "page": FLASH_PAGE,
        "next_max_id": next_max_id,
        "since_id": safe_str(since_id),
    }
