"""同花顺 7×24 快讯：``news.10jqka.com.cn/tapp/news/push/stock/``。

    GET https://news.10jqka.com.cn/tapp/news/push/stock/
    - page / pagesize / tag="" / track=website

这是全市场电报，``code`` / ``tag=股票`` 不会按个股过滤。
个股请走 ``news.fetch_news``；这里只提供全市场流，可选事后按 ``stock[].stockCode`` 过滤。
水位用 ``ctime``（Unix 秒）或 ``id``。
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

from core.codes import normalize_code, safe_str

from company.news.platforms.tonghuashun._common import (
    FLASH_API,
    FLASH_PAGE,
    REQUEST_PAUSE_SEC,
    SOURCE,
    date_range,
    dedupe,
    empty_pack,
    fmt_dt,
    get_payload,
    headers_for,
    in_range,
    oldest_day,
    relevant,
    resolve_keyword,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 40
MAX_PAGES = 5


def query_page(
    *,
    page: int = 1,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """快讯单页原始 JSON。"""
    payload = get_payload(
        FLASH_API,
        params={
            "page": max(1, int(page)),
            "tag": "",
            "track": "website",
            "pagesize": max(1, min(int(page_size), 400)),
        },
        headers=headers_for(FLASH_PAGE, origin="https://news.10jqka.com.cn"),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def _related_stocks(row: dict[str, Any]) -> list[dict[str, str]]:
    stocks = row.get("stock") or []
    if not isinstance(stocks, list):
        return []
    out: list[dict[str, str]] = []
    for item in stocks:
        if not isinstance(item, dict):
            continue
        code = normalize_code(safe_str(item.get("stockCode")))
        name = safe_str(item.get("name"))
        if not code and not name:
            continue
        out.append(
            {
                "name": name,
                "stockCode": code or safe_str(item.get("stockCode")),
                "stockMarket": safe_str(item.get("stockMarket")),
            }
        )
    return out


def _hits_stock(item: dict[str, Any], code: str, name: str) -> bool:
    if not code and not name:
        return True
    for row in item.get("related_stocks") or []:
        if code and safe_str(row.get("stockCode")) == code:
            return True
        if name and name in safe_str(row.get("name")):
            return True
    return relevant(item, code=code, name=name, keyword=name)


def _normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    title = safe_str(row.get("title"))
    seq = safe_str(row.get("seq") or row.get("id"))
    if not title:
        return None
    url = safe_str(row.get("url") or row.get("shareUrl") or row.get("appUrl"))
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    stocks = _related_stocks(row)
    tags = row.get("tags") or []
    tag_names = []
    if isinstance(tags, list):
        tag_names = [safe_str(x.get("name")) for x in tags if isinstance(x, dict) and x.get("name")]
    if not tag_names:
        tag_names = [t for t in safe_str(row.get("tag")).split(",") if t]
    return {
        "code": stocks[0]["stockCode"] if stocks else "",
        "name": stocks[0]["name"] if stocks else "",
        "article_id": seq,
        "seq": safe_str(row.get("seq")),
        "flash_id": safe_str(row.get("id")),
        "title": title,
        "summary": safe_str(row.get("digest") or row.get("short")),
        "published_at": fmt_dt(row.get("ctime") or row.get("rtime")),
        "ctime": safe_str(row.get("ctime")),
        "url": url,
        "mobile_url": safe_str(row.get("appUrl")),
        "share_url": safe_str(row.get("shareUrl")),
        "source": SOURCE,
        "channel": "flash",
        "media_name": safe_str(row.get("source")),
        "tags": tag_names,
        "related_stocks": stocks,
        "important": safe_str(row.get("import")),
    }


def fetch_flash(
    *,
    code: str = "",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    max_pages: int = MAX_PAGES,
    page_size: int = PAGE_SIZE,
    since_ctime: str = "",
    since_id: str = "",
) -> dict[str, Any]:
    """全市场快讯。``code`` 非空时按关联股票 / 标题过滤。

    ``since_ctime`` / ``since_id``：只保留严格更新的条目，便于增量。
    """
    resolved = resolve_keyword(code) if code else {"code": "", "name": "", "keyword": ""}
    stock = resolved["code"] or normalize_code(code)
    name = resolved["name"]
    start_d, end_d = date_range(start, end, days)
    since_ts = 0
    if since_ctime:
        try:
            since_ts = int(str(since_ctime).strip())
        except ValueError:
            since_ts = 0
    since_num = 0
    if since_id:
        try:
            since_num = int(str(since_id).strip())
        except ValueError:
            since_num = 0

    items: list[dict[str, Any]] = []
    total = 0
    page = 1
    limit = max(1, int(max_pages))
    size = max(1, min(int(page_size), 400))
    while page <= limit:
        try:
            payload = query_page(page=page, page_size=size)
        except Exception as exc:  # noqa: BLE001
            logger.warning("同花顺快讯失败 page=%s: %s", page, exc)
            if page == 1:
                return empty_pack(
                    code=stock,
                    name=name,
                    keyword=resolved.get("keyword") or "",
                    channel="flash",
                    error=str(exc),
                    page=FLASH_PAGE,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        if safe_str(payload.get("code")) not in {"", "200"}:
            msg = safe_str(payload.get("msg")) or f"code={payload.get('code')}"
            if page == 1:
                return empty_pack(
                    code=stock,
                    name=name,
                    keyword=resolved.get("keyword") or "",
                    channel="flash",
                    error=msg,
                    page=FLASH_PAGE,
                )
            break
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        rows = data.get("list") or []
        total = int(data.get("total") or total)
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
            if since_ts:
                try:
                    if int(item.get("ctime") or 0) <= since_ts:
                        stop_older = True
                        continue
                except ValueError:
                    pass
            if since_num:
                try:
                    if int(item.get("flash_id") or 0) <= since_num:
                        stop_older = True
                        continue
                except ValueError:
                    pass
            page_items.append(item)
            if stock or name:
                if not _hits_stock(item, stock, name):
                    continue
            if in_range(item, start_d, end_d):
                items.append(item)
        if start_d:
            old = oldest_day(page_items)
            if old and old < start_d:
                break
        if stop_older or len(rows) < size:
            break
        page += 1
        if page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = dedupe(items)
    return {
        "code": stock,
        "name": name,
        "keyword": resolved.get("keyword") or "",
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": "flash",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": FLASH_PAGE,
        "since_ctime": safe_str(since_ctime),
        "since_id": safe_str(since_id),
    }
