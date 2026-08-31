"""雪球首页分类资讯流：``public_timeline_by_category``。

    GET https://xueqiu.com/v4/statuses/public_timeline_by_category.json
    - category   头条 -1 / 今日话题 0 / 直播 6 / 沪深 105 / 港股 102 / 美股 101 / 基金 104
    - since_id   -1
    - max_id     首页 -1，下一页用 next_max_id
    - count      每页条数

``list[i].data`` 是 JSON 字符串，不是对象。
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

from core.codes import safe_str

from company.news.platforms.xueqiu._common import (
    COLUMN_API,
    REQUEST_PAUSE_SEC,
    SOURCE,
    WEB_HOST,
    date_range,
    decode_embedded,
    dedupe,
    empty_pack,
    get_payload,
    headers_for,
    in_range,
    map_choice,
    normalize_status,
    oldest_day,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 10
MAX_PAGES = 5

COLUMNS: dict[str, str] = {
    "headline": "-1",
    "头条": "-1",
    "all": "-1",
    "-1": "-1",
    "today": "0",
    "今日话题": "0",
    "0": "0",
    "live": "6",
    "直播": "6",
    "6": "6",
    "cn": "105",
    "沪深": "105",
    "105": "105",
    "hk": "102",
    "港股": "102",
    "102": "102",
    "us": "101",
    "美股": "101",
    "101": "101",
    "fund": "104",
    "基金": "104",
    "104": "104",
    "pe": "113",
    "私募": "113",
    "113": "113",
    "estate": "111",
    "房产": "111",
    "111": "111",
    "auto": "114",
    "汽车": "114",
    "114": "114",
    "insurance": "110",
    "保险": "110",
    "110": "110",
}
COLUMN_LABELS: dict[str, str] = {
    "-1": "头条",
    "0": "今日话题",
    "6": "直播",
    "105": "沪深",
    "102": "港股",
    "101": "美股",
    "104": "基金",
    "113": "私募",
    "111": "房产",
    "114": "汽车",
    "110": "保险",
}


def resolve_column(column: str | None) -> str:
    raw = safe_str(column)
    if raw.lstrip("-").isdigit():
        return raw
    return map_choice(column, COLUMNS, "headline", "column")


def column_page_url(column: str | None = None) -> str:
    col = resolve_column(column)
    if col == "0":
        return f"{WEB_HOST}/today"
    return WEB_HOST + "/"


def query_page(
    column: str = "-1",
    *,
    max_id: int | str = -1,
    count: int = PAGE_SIZE,
    since_id: int | str = -1,
) -> dict[str, Any]:
    """分类资讯单页原始 JSON。"""
    payload = get_payload(
        COLUMN_API,
        params={
            "since_id": since_id,
            "max_id": max_id,
            "count": max(1, min(int(count), 20)),
            "category": resolve_column(column),
        },
        headers=headers_for(WEB_HOST + "/", origin=WEB_HOST),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def _normalize_row(row: dict[str, Any], *, column: str) -> dict[str, Any] | None:
    data = decode_embedded(row)
    item = normalize_status(data or row, channel="column")
    if not item:
        return None
    item["category"] = COLUMN_LABELS.get(column, column)
    item["column"] = column
    if isinstance(row, dict) and row.get("column"):
        item["media_name"] = item.get("media_name") or safe_str(row.get("column"))
    return item


def fetch_column_news(
    column: str = "headline",
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    max_pages: int = MAX_PAGES,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """首页分类资讯流。"""
    col = resolve_column(column)
    label = COLUMN_LABELS.get(col, col)
    page_url = column_page_url(col)
    start_d, end_d = date_range(start, end, days)
    items: list[dict[str, Any]] = []
    page = 1
    limit = max(1, int(max_pages))
    size = max(1, min(int(page_size), 20))
    max_id: int | str = -1
    next_max_id = ""
    while page <= limit:
        try:
            payload = query_page(col, max_id=max_id, count=size)
        except Exception as exc:  # noqa: BLE001
            logger.warning("雪球栏目失败 category=%s: %s", col, exc)
            if page == 1:
                return empty_pack(
                    channel="column",
                    error=str(exc),
                    page=page_url,
                    category=label,
                    column=col,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        rows = payload.get("list") or []
        next_max_id = safe_str(payload.get("next_max_id"))
        if not isinstance(rows, list) or not rows:
            break
        page_items: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _normalize_row(row, column=col)
            if not item:
                continue
            page_items.append(item)
            if in_range(item, start_d, end_d):
                items.append(item)
        if start_d:
            old = oldest_day(page_items)
            if old and old < start_d:
                break
        if not next_max_id or len(rows) < size:
            break
        max_id = next_max_id
        page += 1
        if page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = dedupe(items)
    return {
        "code": "",
        "name": "",
        "keyword": label,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": "column",
        "category": label,
        "column": col,
        "count": len(items),
        "total": len(items),
        "items": items,
        "page": page_url,
        "next_max_id": next_max_id,
    }
