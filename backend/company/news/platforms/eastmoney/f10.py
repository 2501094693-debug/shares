"""东财 F10「资讯公告」快照：相关资讯 + 相关公告各约 10 条。

个股资料页：
  https://emweb.securities.eastmoney.com/PC_HSF10/NewsBulletin/Index?type=web&code=SH600519

    GET .../PC_HSF10/NewsBulletin/PageAjax?code=SH600519

``gszx`` 资讯、``gsgg`` 公告。这是资料页首屏，不是全量；全量用 search / notices。
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from core.codes import em_code, safe_str

from company.news.platforms.eastmoney._common import (
    SOURCE,
    article_url,
    date_range,
    empty_pack,
    f10_page_url,
    fmt_dt,
    get_payload,
    headers_for,
    in_range,
    notice_page_url,
    resolve_keyword,
)

logger = logging.getLogger(__name__)

F10_API = "https://emweb.securities.eastmoney.com/PC_HSF10/NewsBulletin/PageAjax"


def query_page(code: str) -> dict[str, Any]:
    """F10 资讯公告原始 JSON。``code`` 用 ``SH600519``。"""
    em = em_code(code) or safe_str(code).upper()
    payload = get_payload(
        F10_API,
        params={"code": em},
        headers=headers_for(f10_page_url(code)),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def _news_item(row: dict[str, Any], *, code: str, name: str) -> dict[str, Any] | None:
    title = safe_str(row.get("title"))
    if not title:
        return None
    article_id = safe_str(row.get("code") or row.get("infoCode"))
    url = safe_str(row.get("uniqueUrl") or row.get("url")) or article_url(article_id)
    published = row.get("showDateTime") or row.get("publishDate")
    return {
        "code": code,
        "name": name,
        "article_id": article_id,
        "title": title,
        "summary": safe_str(row.get("summary")),
        "published_at": fmt_dt(published),
        "url": url.replace("http://", "https://", 1) if url else "",
        "source": SOURCE,
        "channel": "f10_news",
        "info_code": safe_str(row.get("infoCode")),
    }


def _notice_item(row: dict[str, Any], *, code: str, name: str) -> dict[str, Any] | None:
    title = safe_str(row.get("title"))
    art = safe_str(row.get("art_code"))
    if not title:
        return None
    return {
        "code": code,
        "name": name,
        "art_code": art,
        "article_id": art,
        "title": title,
        "summary": safe_str(row.get("content")),
        "published_at": fmt_dt(row.get("display_time") or row.get("notice_date")),
        "notice_date": fmt_dt(row.get("notice_date")),
        "url": notice_page_url(code, art),
        "source": SOURCE,
        "channel": "f10_notice",
    }


def fetch_f10(
    code_or_name: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
) -> dict[str, Any]:
    """个股 F10 资讯 + 公告快照。"""
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"]
    name = resolved["name"]
    page_url = f10_page_url(code or code_or_name)
    if not code and not em_code(code_or_name):
        em = safe_str(code_or_name).upper()
        if not (len(em) >= 8 and em[:2] in {"SH", "SZ", "BJ"}):
            return empty_pack(
                code=code,
                name=name,
                channel="f10",
                error="缺少股票代码",
                page=page_url,
            )
        code = em[2:]

    start_d, end_d = date_range(start, end, days)
    try:
        payload = query_page(code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("东财 F10 资讯失败 %s: %s", code, exc)
        return empty_pack(code=code, name=name, channel="f10", error=str(exc), page=page_url)

    gszx = payload.get("gszx") if isinstance(payload.get("gszx"), dict) else {}
    zx_data = gszx.get("data") if isinstance(gszx.get("data"), dict) else {}
    news_rows = zx_data.get("items") or []
    news: list[dict[str, Any]] = []
    if isinstance(news_rows, list):
        for row in news_rows:
            if not isinstance(row, dict):
                continue
            item = _news_item(row, code=code, name=name)
            if item and in_range(item, start_d, end_d):
                news.append(item)

    gsgg = payload.get("gsgg") or []
    notices: list[dict[str, Any]] = []
    if isinstance(gsgg, list):
        for row in gsgg:
            if not isinstance(row, dict):
                continue
            item = _notice_item(row, code=code, name=name)
            if item and in_range(item, start_d, end_d):
                notices.append(item)

    items = news + notices
    return {
        "code": code,
        "name": name,
        "keyword": resolved["keyword"],
        "em_code": em_code(code),
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": "f10",
        "count": len(items),
        "total": len(items),
        "news_count": len(news),
        "notice_count": len(notices),
        "news": news,
        "notices": notices,
        "items": items,
        "page": page_url,
    }


def fetch_f10_news(code_or_name: str, **kwargs: Any) -> dict[str, Any]:
    pack = fetch_f10(code_or_name, **kwargs)
    items = pack.get("news") or []
    pack["items"] = items
    pack["channel"] = "f10_news"
    pack["count"] = len(items)
    pack["total"] = len(items)
    return pack


def fetch_f10_notices(code_or_name: str, **kwargs: Any) -> dict[str, Any]:
    pack = fetch_f10(code_or_name, **kwargs)
    items = pack.get("notices") or []
    pack["items"] = items
    pack["channel"] = "f10_notice"
    pack["count"] = len(items)
    pack["total"] = len(items)
    return pack
