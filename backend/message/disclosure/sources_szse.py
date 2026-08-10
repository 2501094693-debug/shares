"""深交所公司公告与问询函。"""

from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from .constants import (
    MAX_PAGES,
    REQUEST_PAUSE_SEC,
    SZSE_ANN_URL,
    SZSE_INQUIRE_CATALOG,
    SZSE_INQUIRE_TABS,
    SZSE_INQUIRE_URL,
    SZSE_PAGE_SIZE,
    SZSE_PDF_PREFIX,
)
from .http_util import (
    extract_href,
    http_get,
    http_post,
    normalize_code,
    parse_time,
    safe_str,
    sleep_pause,
)
from .normalize import make_item


def fetch_szse_announcements(
    code: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    max_pages: int = MAX_PAGES,
) -> list[dict[str, Any]]:
    """深交所 listedNotice 公告列表。"""
    code = normalize_code(code)
    if not code:
        return []

    end_dt = end or datetime.now()
    begin_dt = start or datetime(end_dt.year - 1, end_dt.month, end_dt.day)
    se_date = [begin_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")]

    headers = {
        "Content-Type": "application/json",
        "Referer": "https://www.szse.cn/disclosure/listed/notice/index.html",
        "X-Requested-With": "XMLHttpRequest",
        "X-Request-Type": "ajax",
        "Origin": "https://www.szse.cn",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    items: list[dict[str, Any]] = []
    page = 1
    total_pages = 1
    while page <= total_pages and page <= max(1, max_pages):
        payload = {
            "stock": [code],
            "channelCode": ["listedNotice_disc"],
            "pageSize": SZSE_PAGE_SIZE,
            "pageNum": page,
            "seDate": se_date,
        }
        try:
            resp = http_post(
                f"{SZSE_ANN_URL}?random={random.random()}",
                data=json.dumps(payload, ensure_ascii=False),
                headers=headers,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception:  # noqa: BLE001
            break

        rows = body.get("data") or []
        if not isinstance(rows, list) or not rows:
            break

        count = int(body.get("announceCount") or 0)
        total_pages = max(1, (count + SZSE_PAGE_SIZE - 1) // SZSE_PAGE_SIZE) if count else page

        for row in rows:
            if not isinstance(row, dict):
                continue
            title = safe_str(row.get("title"))
            if not title:
                continue
            attach = safe_str(row.get("attachPath"))
            url = urljoin(SZSE_PDF_PREFIX, attach) if attach else ""
            published = parse_time(row.get("publishTime"))
            sec_codes = row.get("secCode") or []
            sec_names = row.get("secName") or []
            items.append(
                make_item(
                    title=title,
                    published_at=published.strftime("%Y-%m-%d %H:%M:%S")
                    if published
                    else "",
                    url=url,
                    source="深圳证券交易所",
                    channel="szse",
                    kind="notice",
                    summary="",
                    why="深交所公告",
                    code=(sec_codes[0] if sec_codes else code),
                    name=(sec_names[0] if sec_names else ""),
                    extra={"ann_id": row.get("annId") or row.get("id")},
                )
            )

        page += 1
        if page <= total_pages and page <= max_pages:
            sleep_pause(REQUEST_PAUSE_SEC)

    return items


def fetch_szse_inquiries(
    code: str,
    *,
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    """深交所监管问询函（关注函/问询函等）。"""
    code = normalize_code(code)
    if not code:
        return []

    headers = {
        "Referer": "https://www.szse.cn/disclosure/supervision/inquire/index.html",
        "Accept": "application/json, text/plain, */*",
    }
    items: list[dict[str, Any]] = []

    for tab in SZSE_INQUIRE_TABS:
        page = 1
        total_pages = 1
        while page <= total_pages and page <= max(1, max_pages):
            params = {
                "SHOWTYPE": "JSON",
                "CATALOGID": SZSE_INQUIRE_CATALOG,
                "TABKEY": tab,
                "txtZqdm": code,
                "PAGENO": page,
                "random": random.random(),
            }
            try:
                resp = http_get(SZSE_INQUIRE_URL, params=params, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
            except Exception:  # noqa: BLE001
                break

            block = payload[0] if isinstance(payload, list) and payload else {}
            meta = block.get("metadata") or {}
            rows = block.get("data") or []
            if not isinstance(rows, list) or not rows:
                break

            record_count = int(meta.get("recordcount") or 0)
            page_size = int(meta.get("pagesize") or 20) or 20
            total_pages = (
                max(1, (record_count + page_size - 1) // page_size)
                if record_count
                else int(meta.get("pagecount") or 1)
            )

            for row in rows:
                if not isinstance(row, dict):
                    continue
                gsdm = normalize_code(safe_str(row.get("gsdm")))
                if gsdm and gsdm != code:
                    continue
                hjlb = safe_str(row.get("hjlb")) or "问询函"
                name = safe_str(row.get("gsjc"))
                fhrq = safe_str(row.get("fhrq"))
                path = extract_href(safe_str(row.get("ck")))
                url = urljoin("https://www.szse.cn", path) if path else ""
                reply = extract_href(safe_str(row.get("hfck")))
                reply_url = urljoin("https://www.szse.cn", reply) if reply else ""
                title = f"{name or code}：收到深交所{hjlb}"
                items.append(
                    make_item(
                        title=title,
                        published_at=fhrq,
                        url=url,
                        source="深圳证券交易所",
                        channel="szse",
                        kind="inquiry",
                        summary=hjlb,
                        why=hjlb,
                        code=gsdm or code,
                        name=name,
                        extra={
                            "letter_type": hjlb,
                            "reply_url": reply_url,
                            "tab": tab,
                        },
                    )
                )

            page += 1
            if page <= total_pages and page <= max_pages:
                sleep_pause(REQUEST_PAUSE_SEC)

    return items
