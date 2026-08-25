"""同花顺个股研报：F10 ``news.html`` 内嵌 ``#report_list_contents`` JSON。

研报不是独立 JSON 接口，列表 SSR 在资讯页里。翻页/筛选只在浏览器本地做。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from typing import Any

from core.codes import normalize_code, safe_str
from core.http import browser_get

from company.news.tonghuashun._common import (
    SOURCE,
    date_range,
    decode_html,
    dedupe,
    empty_pack,
    f10_news_url,
    fmt_dt,
    headers_for,
    in_range,
    resolve_keyword,
)

logger = logging.getLogger(__name__)

_BLOCK_RE = re.compile(
    r'id=["\']report_list_contents["\'][^>]*>(.*?)</(?:textarea|script|div)>',
    re.I | re.S,
)


def query_page(code: str) -> list[dict[str, Any]]:
    """从 F10 资讯页抽出研报 JSON 列表。"""
    stock = normalize_code(code) or safe_str(code)
    resp = browser_get(
        f10_news_url(stock),
        headers=headers_for(f10_news_url(stock)),
        timeout=25,
    )
    resp.raise_for_status()
    html = decode_html(resp)
    m = _BLOCK_RE.search(html)
    if not m:
        m = re.search(
            r'id=["\']report_list_contents["\'][^>]*>(.*)$',
            html,
            re.I | re.S,
        )
    if not m:
        return []
    raw = m.group(1).strip()
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S).strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = json.loads(raw.replace("\xa0", " "))
    if isinstance(data, dict):
        rows = data.get("data") or data.get("list") or []
        return [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _normalize_row(
    row: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
) -> dict[str, Any] | None:
    title = safe_str(row.get("title"))
    if not title:
        return None
    url = safe_str(row.get("url"))
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    return {
        "code": code,
        "name": name,
        "article_id": safe_str(row.get("seq") or row.get("id")),
        "title": title,
        "summary": "",
        "published_at": fmt_dt(row.get("date")),
        "url": url,
        "source": SOURCE,
        "channel": "report",
        "media_name": safe_str(row.get("source")),
        "researcher": safe_str(row.get("researcher")),
        "rating": safe_str(row.get("thspj")),
    }


def fetch_reports(
    code_or_name: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    rating: str = "",
) -> dict[str, Any]:
    """按股票拉 F10 研报列表（单次 SSR，不再翻页）。"""
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    name = resolved["name"]
    page_url = f10_news_url(code)
    if not code:
        return empty_pack(
            code=code,
            name=name,
            keyword=resolved["keyword"],
            channel="report",
            error="缺少股票代码",
            page=page_url,
        )

    start_d, end_d = date_range(start, end, days)
    want_rating = safe_str(rating)
    try:
        rows = query_page(code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("同花顺研报失败 %s: %s", code, exc)
        return empty_pack(
            code=code,
            name=name,
            keyword=resolved["keyword"],
            channel="report",
            error=str(exc),
            page=page_url,
            begin_date=start_d.isoformat() if start_d else "",
            end_date=end_d.isoformat() if end_d else "",
        )

    items: list[dict[str, Any]] = []
    for row in rows:
        item = _normalize_row(row, code=code, name=name)
        if not item:
            continue
        if want_rating and want_rating not in {"", "all", "全部"} and item.get("rating") != want_rating:
            continue
        if in_range(item, start_d, end_d):
            items.append(item)

    items = dedupe(items)
    return {
        "code": code,
        "name": name,
        "keyword": resolved["keyword"],
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": "report",
        "count": len(items),
        "total": len(items),
        "items": items,
        "page": page_url,
    }
