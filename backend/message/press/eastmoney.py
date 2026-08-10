"""经东方财富新闻索引检索，并按七报媒体名筛选。

七家官网站内搜索接口变动频繁、反爬较强；东财索引会保留原媒体署名
（mediaName），可作为稳定的「按指定披露媒体归类」检索通道。
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

from message.disclosure.http_util import (
    http_get,
    safe_str,
    sleep_pause,
    within_range,
)
from message.disclosure.normalize import make_item

from .constants import (
    EM_MAX_PAGES,
    EM_NEWS_CB,
    EM_NEWS_URL,
    EM_PAGE_SIZE,
    OUTLETS,
    Outlet,
    REQUEST_PAUSE_SEC,
)


def _strip_em(text: str) -> str:
    return (
        safe_str(text)
        .replace("<em>", "")
        .replace("</em>", "")
        .replace("<EM>", "")
        .replace("</EM>", "")
    )


def match_outlet(media_name: str, outlet: Outlet) -> bool:
    media = safe_str(media_name)
    if not media:
        return False
    for alias in outlet["aliases"]:
        if len(alias) <= 2:
            continue
        if alias in media:
            return True
    return False


def classify_outlet(media_name: str, outlets: list[Outlet] | tuple[Outlet, ...]) -> Outlet | None:
    """最长别名优先，减少交叉误伤。"""
    media = safe_str(media_name)
    best: Outlet | None = None
    best_len = -1
    for outlet in outlets:
        for alias in outlet["aliases"]:
            if len(alias) <= 2:
                continue
            if alias in media and len(alias) > best_len:
                best = outlet
                best_len = len(alias)
    return best


def _fetch_em_page(keyword: str, page_index: int) -> tuple[int, list[dict[str, Any]]]:
    inner = {
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "time",
                "pageIndex": page_index,
                "pageSize": EM_PAGE_SIZE,
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
    rows = ((payload.get("result") or {}).get("cmsArticleWebOld")) or []
    if isinstance(rows, dict):
        rows = rows.get("list") or rows.get("data") or []
    if not isinstance(rows, list):
        rows = []

    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _strip_em(safe_str(row.get("title")))
        if not title:
            continue
        code_id = safe_str(row.get("code"))
        url = safe_str(row.get("url"))
        if not url and code_id:
            url = f"http://finance.eastmoney.com/a/{code_id}.html"
        items.append(
            {
                "title": title,
                "summary": _strip_em(safe_str(row.get("content"))),
                "media_name": safe_str(row.get("mediaName")),
                "url": url,
                "published_at": safe_str(row.get("date")),
            }
        )
    return hits, items


def _collect_em(keyword: str, max_pages: int) -> list[dict[str, Any]]:
    hits, first = _fetch_em_page(keyword, 1)
    collected = list(first)
    total_pages = (
        min(max_pages, max(1, math.ceil(hits / EM_PAGE_SIZE)))
        if hits
        else min(max_pages, 3)
    )
    for page in range(2, total_pages + 1):
        sleep_pause(REQUEST_PAUSE_SEC)
        _, rows = _fetch_em_page(keyword, page)
        if not rows:
            break
        collected.extend(rows)
    return collected


def _to_item(
    row: dict[str, Any],
    outlet: Outlet,
    *,
    code: str,
    name: str,
) -> dict[str, Any]:
    media = safe_str(row.get("media_name"))
    return make_item(
        title=safe_str(row.get("title")),
        published_at=safe_str(row.get("published_at")),
        url=safe_str(row.get("url")),
        source=outlet["paper"],
        channel=outlet["id"],
        kind="press",
        summary=safe_str(row.get("summary")),
        why=media or outlet["name"],
        code=code,
        name=name,
        extra={
            "outlet": outlet["id"],
            "outlet_name": outlet["name"],
            "paper": outlet["paper"],
            "domain": outlet["domain"],
            "media_name": media,
            "via": "eastmoney",
        },
    )


def _relevant(row: dict[str, Any], keyword: str, code: str, name: str) -> bool:
    blob = f"{row.get('title', '')} {row.get('summary', '')}"
    tokens = [t for t in (keyword, name, code) if t and len(t) >= 2]
    if not tokens:
        return True
    return any(t in blob for t in tokens)


def fetch_all_outlets_via_eastmoney(
    company_keyword: str,
    *,
    outlets: tuple[Outlet, ...] | list[Outlet] = OUTLETS,
    start: datetime | None = None,
    end: datetime | None = None,
    max_pages: int = EM_MAX_PAGES,
    code: str = "",
    name: str = "",
) -> dict[str, list[dict[str, Any]]]:
    """先按公司名检索，再按 mediaName 归入七报；空桶的媒体再补搜「公司+报名」。"""
    outlet_list = list(outlets)
    result: dict[str, list[dict[str, Any]]] = {o["id"]: [] for o in outlet_list}

    raw = _collect_em(company_keyword, max_pages)
    for row in raw:
        if not _relevant(row, company_keyword, code, name):
            continue
        outlet = classify_outlet(safe_str(row.get("media_name")), outlet_list)
        if outlet is None:
            continue
        item = _to_item(row, outlet, code=code, name=name)
        if within_range(item, start, end):
            result[outlet["id"]].append(item)

    # 对仍为空的媒体，追加「公司名 + 报纸名」定向检索
    for outlet in outlet_list:
        if result[outlet["id"]]:
            continue
        kw = f"{company_keyword} {outlet['paper']}"
        sleep_pause(REQUEST_PAUSE_SEC)
        extra_raw = _collect_em(kw, max(2, min(max_pages, 4)))
        for row in extra_raw:
            if not _relevant(row, company_keyword, code, name):
                continue
            if not match_outlet(safe_str(row.get("media_name")), outlet):
                continue
            item = _to_item(row, outlet, code=code, name=name)
            if within_range(item, start, end):
                result[outlet["id"]].append(item)

    return result


def fetch_outlet_via_eastmoney(
    company_keyword: str,
    outlet: Outlet,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    max_pages: int = EM_MAX_PAGES,
    code: str = "",
    name: str = "",
) -> list[dict[str, Any]]:
    grouped = fetch_all_outlets_via_eastmoney(
        company_keyword,
        outlets=[outlet],
        start=start,
        end=end,
        max_pages=max_pages,
        code=code,
        name=name,
    )
    return grouped.get(outlet["id"]) or []
