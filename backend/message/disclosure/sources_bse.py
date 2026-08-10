"""北交所公司公告检索。"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from .constants import BSE_ANN_URL, BSE_PAGE_SIZE, BSE_PDF_PREFIX, MAX_PAGES, REQUEST_PAUSE_SEC
from .http_util import normalize_code, parse_jsonp, parse_time, safe_str, sleep_pause, http_post
from .normalize import make_item
from .sources_cninfo import fetch_cninfo_announcements


def fetch_bse_announcements(
    code: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    max_pages: int = MAX_PAGES,
    allow_cninfo_fallback: bool = True,
) -> list[dict[str, Any]]:
    """北交所 companyAnnouncement JSONP 接口。"""
    code = normalize_code(code)
    if not code:
        return []

    headers = {
        "Referer": "https://www.bse.cn/disclosure/announcement.html",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }

    items: list[dict[str, Any]] = []
    page = 0  # 北交所页码从 0 开始
    total_pages = 1

    while page < total_pages and page < max(1, max_pages):
        cb = f"jQuery{int(time.time() * 1000)}"
        url = f"{BSE_ANN_URL}?callback={cb}"
        form = [
            ("page", str(page)),
            ("pageSize", str(BSE_PAGE_SIZE)),
            ("companyCd", code),
            ("disclosureType[]", "5"),
            ("xxfcbj[]", "2"),
            ("isNewThree", "1"),
            ("siteId", "1"),
            ("keyword", ""),
        ]
        try:
            resp = http_post(url, data=form, headers=headers)
            resp.raise_for_status()
            payload = parse_jsonp(resp.text)
        except Exception:  # noqa: BLE001
            break

        # payload: [{"listInfo": {...}}]
        block = payload[0] if isinstance(payload, list) and payload else payload
        if not isinstance(block, dict):
            break
        info = block.get("listInfo") or {}
        rows = info.get("content") or []
        if not isinstance(rows, list) or not rows:
            break

        total_pages = int(info.get("totalPages") or 1)

        for row in rows:
            if not isinstance(row, dict):
                continue
            title = safe_str(row.get("disclosureTitle") or row.get("disclosurePostTitle"))
            if not title:
                continue
            path = safe_str(row.get("destFilePath"))
            url_pdf = urljoin(BSE_PDF_PREFIX, path) if path else ""
            published = parse_time(row.get("publishDate"))
            if start and published and published < start:
                continue
            if end and published and published > end:
                continue
            items.append(
                make_item(
                    title=title,
                    published_at=published.strftime("%Y-%m-%d %H:%M:%S")
                    if published
                    else safe_str(row.get("publishDate")),
                    url=url_pdf,
                    source="北京证券交易所",
                    channel="bse",
                    kind="notice",
                    summary="",
                    why="北交所公告",
                    code=safe_str(row.get("companyCd")) or code,
                    name=safe_str(row.get("companyName")),
                    extra={"file_ext": safe_str(row.get("fileExt"))},
                )
            )

        page += 1
        if page < total_pages and page < max_pages:
            sleep_pause(REQUEST_PAUSE_SEC)

    if items or not allow_cninfo_fallback:
        return items

    fallback = fetch_cninfo_announcements(
        code, start=start, end=end, max_pages=max_pages, column="bj"
    )
    for item in fallback:
        item["channel"] = "bse"
        item["source"] = "北京证券交易所(经巨潮)"
        item["why"] = safe_str(item.get("why")) or "北交所公告"
        item["via"] = "cninfo_fallback"
    return fallback
