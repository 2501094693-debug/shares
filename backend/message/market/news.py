"""东方财富媒体新闻。

说明：
- ``cmsArticleWebOld``：按时间排序好，但大约只覆盖近半年可检索结果；
- ``cmsArticleWeb``：含更长历史（可回溯多年），排序较乱，需全量翻页后本地过滤。
深回溯时合并两路结果。
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

from message.disclosure.http_util import (
    http_get,
    parse_time,
    safe_str,
    sleep_pause,
    strip_em_tags,
    within_lookback,
)

from .constants import (
    EM_NEWS_CB,
    EM_NEWS_URL,
    NEWS_ARCHIVE_MAX_PAGES,
    NEWS_MAX_PAGES,
    NEWS_PAGE_SIZE,
    REQUEST_PAUSE_SEC,
)

# 近期索引覆盖大约半年；再往前必须打归档索引
_RECENT_INDEX_DAYS = 180


def fetch_em_news_page(
    keyword: str,
    page_index: int,
    *,
    index_type: str = "cmsArticleWebOld",
) -> tuple[int, list[dict[str, Any]]]:
    typ = (index_type or "cmsArticleWebOld").strip() or "cmsArticleWebOld"
    inner = {
        "uid": "",
        "keyword": keyword,
        "type": [typ],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            typ: {
                "searchScope": "default",
                "sort": "time",
                "pageIndex": page_index,
                "pageSize": NEWS_PAGE_SIZE,
                "preTag": "<em>",
                "postTag": "</em>",
            }
        },
    }
    headers = {
        "Referer": f"https://so.eastmoney.com/news/s?keyword={quote(keyword)}",
        "Accept": "*/*",
    }
    try:
        resp = http_get(
            EM_NEWS_URL,
            params={
                "cb": EM_NEWS_CB,
                "param": json.dumps(inner, ensure_ascii=False),
                "_": str(int(time.time() * 1000)),
            },
            headers=headers,
            timeout=25,
        )
        resp.raise_for_status()
        text = resp.text
        start = text.find("(")
        end = text.rfind(")")
        if start < 0 or end <= start:
            return 0, []
        payload = json.loads(text[start + 1 : end])
    except Exception:  # noqa: BLE001
        return 0, []

    hits = int(payload.get("hitsTotal") or 0)
    rows = ((payload.get("result") or {}).get(typ)) or []
    if isinstance(rows, dict):
        rows = rows.get("list") or rows.get("data") or []
    if not isinstance(rows, list):
        rows = []

    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = strip_em_tags(safe_str(row.get("title")))
        if not title:
            continue
        code_id = safe_str(row.get("code"))
        url = safe_str(row.get("url"))
        if not url and code_id:
            url = f"http://finance.eastmoney.com/a/{code_id}.html"
        media = safe_str(row.get("mediaName")) or "东方财富"
        items.append(
            {
                "title": title,
                "summary": strip_em_tags(safe_str(row.get("content"))),
                "source": media,
                "media_name": media,
                "url": url,
                "published_at": safe_str(row.get("date")),
                "kind": "news",
                "channel": "news",
                "why": "",
                "em_index": typ,
            }
        )
    return hits, items


def _collect_recent(keyword: str, start: datetime) -> list[dict[str, Any]]:
    """cmsArticleWebOld：可按时间提前停止翻页。"""
    hits, first = fetch_em_news_page(keyword, 1, index_type="cmsArticleWebOld")
    collected = list(first)
    total_pages = (
        min(NEWS_MAX_PAGES, max(1, math.ceil(hits / NEWS_PAGE_SIZE)))
        if hits
        else NEWS_MAX_PAGES
    )

    for page in range(2, total_pages + 1):
        if collected:
            dated = [parse_time(x.get("published_at")) for x in collected]
            dated = [d for d in dated if d is not None]
            if dated and min(dated) < start:
                break
        sleep_pause(REQUEST_PAUSE_SEC)
        _, rows = fetch_em_news_page(keyword, page, index_type="cmsArticleWebOld")
        if not rows:
            break
        collected.extend(rows)
        page_dates = [parse_time(x.get("published_at")) for x in rows]
        page_dates = [d for d in page_dates if d is not None]
        if page_dates and min(page_dates) < start:
            break

    return [x for x in collected if within_lookback(x, start)]


def _collect_archive(keyword: str, start: datetime) -> list[dict[str, Any]]:
    """cmsArticleWeb：排序不可靠，尽量翻满后再按 start 过滤。"""
    hits, first = fetch_em_news_page(keyword, 1, index_type="cmsArticleWeb")
    collected = list(first)
    total_pages = (
        min(NEWS_ARCHIVE_MAX_PAGES, max(1, math.ceil(hits / NEWS_PAGE_SIZE)))
        if hits
        else NEWS_ARCHIVE_MAX_PAGES
    )
    # 东财该索引硬顶约 10 页
    total_pages = min(total_pages, 10)

    for page in range(2, total_pages + 1):
        sleep_pause(REQUEST_PAUSE_SEC)
        _, rows = fetch_em_news_page(keyword, page, index_type="cmsArticleWeb")
        if not rows:
            break
        collected.extend(rows)

    return [x for x in collected if within_lookback(x, start)]


def _need_archive(start: datetime, recent: list[dict[str, Any]]) -> bool:
    """回溯超过近期索引能力，或近期结果的最早日期仍新于目标窗口。"""
    horizon = datetime.now() - timedelta(days=_RECENT_INDEX_DAYS)
    if start < horizon:
        return True
    dated = [parse_time(x.get("published_at")) for x in recent]
    dated = [d for d in dated if d is not None]
    if not dated:
        return start < horizon
    return min(dated) > start + timedelta(days=3)


def fetch_media_news(keyword: str, start: datetime) -> list[dict[str, Any]]:
    keyword = (keyword or "").strip()
    if not keyword:
        return []

    collected = _collect_recent(keyword, start)
    if _need_archive(start, collected):
        collected.extend(_collect_archive(keyword, start))

    return [x for x in collected if within_lookback(x, start)]
