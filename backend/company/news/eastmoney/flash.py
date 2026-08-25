"""东财 7×24 快讯：``kuaixun.eastmoney.com`` 列表 + 增量计数。

    GET https://np-weblist.eastmoney.com/comm/web/getFastNewsList
    GET https://np-weblist.eastmoney.com/comm/web/getFastNewsCount

``realSort`` 是水位：记下上次最大值，下次只收更大的。
``stockList`` 形如 ``1.600519`` / ``0.000001`` / ``90.BK0477``。
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

from core.codes import normalize_code, safe_str, secid

from company.news.eastmoney._common import (
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
    resolve_keyword,
)

logger = logging.getLogger(__name__)

FLASH_API = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
FLASH_COUNT_API = "https://np-weblist.eastmoney.com/comm/web/getFastNewsCount"
FLASH_PAGE = "https://kuaixun.eastmoney.com/"
PAGE_SIZE = 20
BIZ = "web_724"

# kuaixun 页签 fastColumn
COLUMNS: dict[str, str] = {
    "focus": "101",
    "焦点": "101",
    "101": "101",
    "global": "102",
    "live": "102",
    "7x24": "102",
    "快讯": "102",
    "102": "102",
    "listed": "103",
    "company": "103",
    "上市公司": "103",
    "103": "103",
    "stock": "105",
    "股市": "105",
    "105": "105",
    "commodity": "106",
    "商品": "106",
    "106": "106",
    "fx": "107",
    "forex": "107",
    "外汇": "107",
    "107": "107",
    "bond": "108",
    "债券": "108",
    "108": "108",
    "fund": "109",
    "基金": "109",
    "109": "109",
}


def resolve_column(column: str | None) -> str:
    return map_choice(column, COLUMNS, "global", "flash column")


def query_page(
    *,
    column: str = "102",
    page_size: int = PAGE_SIZE,
    sort_end: str = "",
) -> dict[str, Any]:
    """快讯单页。``sort_end`` 空=最新一页；传入上页最旧 ``realSort`` 继续往旧翻。"""
    ts = req_trace()
    payload = get_payload(
        FLASH_API,
        params={
            "client": "web",
            "biz": BIZ,
            "fastColumn": str(column),
            "sortEnd": sort_end or "",
            "pageSize": max(1, min(int(page_size), 100)),
            "req_trace": ts,
            "_": ts,
        },
        headers=headers_for(FLASH_PAGE, origin="https://kuaixun.eastmoney.com"),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def query_count(*, column: str = "102", sort_start: str) -> int:
    """``realSort`` 之后的新增条数。"""
    ts = req_trace()
    payload = get_payload(
        FLASH_COUNT_API,
        params={
            "client": "web",
            "biz": BIZ,
            "fastColumn": str(column),
            "sortStart": str(sort_start),
            "req_trace": ts,
        },
        headers=headers_for(FLASH_PAGE, origin="https://kuaixun.eastmoney.com"),
        timeout=15,
    )
    if not isinstance(payload, dict):
        return 0
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    try:
        return int(data.get("count") or 0)
    except (TypeError, ValueError):
        return 0


def _match_stock(stock_list: list[Any], code: str) -> bool:
    if not code:
        return True
    sid = secid(code)
    digits = normalize_code(code)
    for item in stock_list:
        token = safe_str(item)
        if not token:
            continue
        if sid and token == sid:
            return True
        if digits and (token.endswith("." + digits) or token == digits):
            return True
    return False


def _normalize_row(
    row: dict[str, Any],
    *,
    column: str,
    code: str = "",
    name: str = "",
) -> dict[str, Any] | None:
    title = safe_str(row.get("title"))
    if not title:
        return None
    article_id = safe_str(row.get("code"))
    stocks = row.get("stockList") if isinstance(row.get("stockList"), list) else []
    return {
        "code": code,
        "name": name,
        "article_id": article_id,
        "title": title,
        "summary": safe_str(row.get("summary") or row.get("digest")),
        "published_at": fmt_dt(row.get("showTime") or row.get("createTime")),
        "url": article_url(article_id),
        "source": SOURCE,
        "channel": "flash",
        "column": column,
        "real_sort": safe_str(row.get("realSort")),
        "title_color": row.get("titleColor"),
        "stock_list": [safe_str(x) for x in stocks],
    }


def fetch_flash(
    *,
    column: str | None = "global",
    code: str = "",
    page_size: int = PAGE_SIZE,
    max_pages: int = 1,
    since_sort: str = "",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
) -> dict[str, Any]:
    """拉 7×24 快讯。``code`` 非空时按 ``stockList`` 过滤。

    ``since_sort`` 只保留 ``realSort`` 更大的增量。
    """
    resolved = resolve_keyword(code) if code else {"code": "", "name": "", "keyword": ""}
    stock = resolved["code"]
    name = resolved["name"]
    col = resolve_column(column)
    start_d, end_d = date_range(start, end, days)
    floor = int(since_sort) if safe_str(since_sort).isdigit() else 0

    items: list[dict[str, Any]] = []
    total = 0
    sort_end = ""
    newest_sort = ""
    limit = max(1, int(max_pages))
    for page in range(1, limit + 1):
        try:
            payload = query_page(column=col, page_size=page_size, sort_end=sort_end)
        except Exception as exc:  # noqa: BLE001
            logger.warning("东财快讯失败 page=%s: %s", page, exc)
            if page == 1:
                return empty_pack(
                    code=stock,
                    name=name,
                    channel="flash",
                    error=str(exc),
                    page=FLASH_PAGE,
                    column=col,
                )
            break
        if safe_str(payload.get("code")) not in {"1", "0"} and page == 1:
            return empty_pack(
                code=stock,
                name=name,
                channel="flash",
                error=safe_str(payload.get("message")) or "快讯接口失败",
                page=FLASH_PAGE,
                column=col,
            )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        rows = data.get("fastNewsList") or []
        total = int(data.get("total") or total)
        if not isinstance(rows, list) or not rows:
            break
        oldest = ""
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _normalize_row(row, column=col, code=stock, name=name)
            if not item:
                continue
            rs = item["real_sort"]
            if rs and (not newest_sort or int(rs) > int(newest_sort)):
                newest_sort = rs
            if floor and rs and int(rs) <= floor:
                continue
            if stock and not _match_stock(item.get("stock_list") or [], stock):
                continue
            if in_range(item, start_d, end_d):
                items.append(item)
            if rs and (not oldest or int(rs) < int(oldest)):
                oldest = rs
        sort_end = safe_str(data.get("sortEnd")) or oldest
        if page < limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = dedupe(items)
    return {
        "code": stock,
        "name": name,
        "keyword": "",
        "column": col,
        "since_sort": since_sort or "",
        "newest_sort": newest_sort,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": "flash",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": FLASH_PAGE,
    }
