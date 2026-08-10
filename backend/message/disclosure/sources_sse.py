"""上交所公司公告检索。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .constants import (
    MAX_PAGES,
    REQUEST_PAUSE_SEC,
    SSE_BULLETIN_URL,
    SSE_INQUIRE_CHANNEL_IDS,
    SSE_INQUIRE_PAGE_SIZE,
    SSE_INQUIRE_SITE_ID,
    SSE_INQUIRE_SQL_ID,
    SSE_INQUIRE_URL,
    SSE_PAGE_SIZE,
    SSE_PDF_PREFIX,
    SSE_SECURITY_TYPE_MAIN,
)
from .http_util import (
    http_get,
    normalize_code,
    parse_jsonp,
    parse_time,
    safe_str,
    sleep_pause,
)
from .normalize import make_item
from .sources_cninfo import fetch_cninfo_announcements


def _security_type(code: str) -> str:
    # 科创板官方 bulletin 接口常无数据，仍先尝试主板类型再回退巨潮
    if code.startswith("68"):
        return SSE_SECURITY_TYPE_MAIN
    return SSE_SECURITY_TYPE_MAIN


def fetch_sse_announcements(
    code: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    max_pages: int = MAX_PAGES,
    allow_cninfo_fallback: bool = True,
) -> list[dict[str, Any]]:
    """上交所公告；官方接口无结果时可选回退巨潮 column=sse。"""
    code = normalize_code(code)
    if not code:
        return []

    end_dt = end or datetime.now()
    begin_dt = start or datetime(end_dt.year - 1, end_dt.month, end_dt.day)
    begin = begin_dt.strftime("%Y-%m-%d")
    end_s = end_dt.strftime("%Y-%m-%d")

    headers = {
        "Referer": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
        "Host": "query.sse.com.cn",
    }

    items: list[dict[str, Any]] = []
    page = 1
    total_pages = 1
    while page <= total_pages and page <= max(1, max_pages):
        params = {
            "isPagination": "true",
            "productId": code,
            "securityType": _security_type(code),
            "beginDate": begin,
            "endDate": end_s,
            "pageHelp.pageSize": str(SSE_PAGE_SIZE),
            "pageHelp.pageCount": "50",
            "pageHelp.pageNo": str(page),
            "pageHelp.beginPage": str(page),
            "pageHelp.cacheSize": "1",
            "pageHelp.endPage": str(page),
        }
        try:
            resp = http_get(SSE_BULLETIN_URL, params=params, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:  # noqa: BLE001
            break

        help_ = payload.get("pageHelp") or {}
        rows = help_.get("data") or payload.get("result") or []
        if not isinstance(rows, list) or not rows:
            break

        total = int(help_.get("total") or 0)
        total_pages = max(1, (total + SSE_PAGE_SIZE - 1) // SSE_PAGE_SIZE) if total else page

        for row in rows:
            if not isinstance(row, dict):
                continue
            title = safe_str(row.get("TITLE") or row.get("title"))
            if not title:
                continue
            path = safe_str(row.get("URL") or row.get("url"))
            url = (
                path
                if path.startswith("http")
                else (f"{SSE_PDF_PREFIX}{path}" if path else "")
            )
            published = parse_time(
                row.get("SSEDATE") or row.get("ADDDATE") or row.get("sseDate")
            )
            items.append(
                make_item(
                    title=title,
                    published_at=published.strftime("%Y-%m-%d %H:%M:%S")
                    if published
                    else "",
                    url=url,
                    source="上海证券交易所",
                    channel="sse",
                    kind="notice",
                    summary=safe_str(
                        row.get("BULLETIN_TYPE") or row.get("BULLETIN_HEADING")
                    ),
                    why=safe_str(row.get("BULLETIN_HEADING")) or "上交所公告",
                    code=safe_str(row.get("SECURITY_CODE")) or code,
                    name=safe_str(row.get("SECURITY_NAME")),
                )
            )

        page += 1
        if page <= total_pages and page <= max_pages:
            sleep_pause(REQUEST_PAUSE_SEC)

    if items or not allow_cninfo_fallback:
        return items

    # 科创板等场景：官方接口经常为空，回退巨潮上交所栏目
    fallback = fetch_cninfo_announcements(
        code, start=start, end=end, max_pages=max_pages, column="sse"
    )
    for item in fallback:
        item["channel"] = "sse"
        item["source"] = "上海证券交易所(经巨潮)"
        item["why"] = safe_str(item.get("why")) or "上交所公告"
        item["via"] = "cninfo_fallback"
    return fallback


def _abs_sse_url(path: str) -> str:
    path = safe_str(path)
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith("//"):
        return f"https:{path}"
    if path.startswith("www."):
        return f"https://{path}"
    return f"{SSE_PDF_PREFIX.rstrip('/')}/{path.lstrip('/')}"


def fetch_sse_inquiries(
    code: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    """上交所监管问询函公开列表（commonSoaQuery / BS_KCB_GGLL）。"""
    code = normalize_code(code)
    if not code:
        return []

    headers = {
        "Referer": "https://www.sse.com.cn/disclosure/credibility/supervision/inquiries/",
        "Host": "query.sse.com.cn",
        "Accept": "*/*",
    }

    items: list[dict[str, Any]] = []
    page = 1
    total_pages = 1
    while page <= total_pages and page <= max(1, max_pages):
        params = {
            "jsonCallBack": "jsonpCallback1",
            "isPagination": "true",
            "pageHelp.pageSize": SSE_INQUIRE_PAGE_SIZE,
            "pageHelp.pageNo": page,
            "pageHelp.beginPage": page,
            "pageHelp.cacheSize": 1,
            "pageHelp.endPage": page,
            "sqlId": SSE_INQUIRE_SQL_ID,
            "siteId": SSE_INQUIRE_SITE_ID,
            "channelId": SSE_INQUIRE_CHANNEL_IDS,
            "stockcode": code,
            "extGGLX": "",
            "extGGDL": "",
            "order": "createTime|desc,stockcode|asc",
        }
        try:
            resp = http_get(SSE_INQUIRE_URL, params=params, headers=headers)
            resp.raise_for_status()
            payload = parse_jsonp(resp.text)
        except Exception:  # noqa: BLE001
            break

        if not isinstance(payload, dict):
            break
        help_ = payload.get("pageHelp") or {}
        rows = help_.get("data") or []
        if not isinstance(rows, list) or not rows:
            break

        total = int(help_.get("total") or 0)
        page_count = int(help_.get("pageCount") or 0)
        if page_count:
            total_pages = page_count
        elif total:
            total_pages = max(
                1, (total + SSE_INQUIRE_PAGE_SIZE - 1) // SSE_INQUIRE_PAGE_SIZE
            )
        else:
            total_pages = page

        for row in rows:
            if not isinstance(row, dict):
                continue
            row_code = normalize_code(
                safe_str(row.get("stockcode") or row.get("extSECURITY_CODE"))
            )
            if row_code and row_code != code:
                continue

            title = safe_str(row.get("docTitle"))
            if not title:
                continue
            letter_type = safe_str(row.get("extWTFL")) or "问询函"
            published = parse_time(row.get("createTime") or row.get("cmsOpDate"))
            if start and published and published < start:
                continue
            if end and published and published > end:
                continue

            name = safe_str(row.get("extGSJC"))
            items.append(
                make_item(
                    title=title,
                    published_at=published.strftime("%Y-%m-%d %H:%M:%S")
                    if published
                    else safe_str(row.get("createTime")),
                    url=_abs_sse_url(safe_str(row.get("docURL"))),
                    source="上海证券交易所",
                    channel="sse",
                    kind="inquiry",
                    summary=letter_type,
                    why=letter_type,
                    code=row_code or code,
                    name=name,
                    extra={
                        "letter_type": letter_type,
                        "doc_id": safe_str(row.get("docId")),
                        "sse_channel_id": safe_str(row.get("channelId")),
                        "doc_type": safe_str(row.get("docType")),
                    },
                )
            )

        page += 1
        if page <= total_pages and page <= max_pages:
            sleep_pause(REQUEST_PAUSE_SEC)

    return items
