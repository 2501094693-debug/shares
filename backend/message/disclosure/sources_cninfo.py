"""巨潮资讯公告检索。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .constants import (
    CNINFO_PAGE_SIZE,
    CNINFO_PDF_PREFIX,
    CNINFO_QUERY_URL,
    CNINFO_SEARCH_URL,
    MAX_PAGES,
    REQUEST_PAUSE_SEC,
)
from .http_util import (
    detect_market,
    http_post,
    normalize_code,
    parse_time,
    safe_str,
    sleep_pause,
)
from .normalize import make_item

_COLUMN_BY_MARKET = {
    "sse": "sse",
    "szse": "szse",
    "bse": "bj",
}


def resolve_org(code: str) -> dict[str, str] | None:
    """通过巨潮 topSearch 解析 orgId / 简称。"""
    code = normalize_code(code)
    if not code:
        return None
    headers = {
        "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/search",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    try:
        resp = http_post(
            CNINFO_SEARCH_URL,
            params={"keyWord": code, "maxNum": 10},
            headers=headers,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if normalize_code(safe_str(row.get("code"))) == code:
            return {
                "code": code,
                "org_id": safe_str(row.get("orgId")),
                "name": safe_str(row.get("zwjc")),
                "type": safe_str(row.get("type")),
            }
    # 兜底取第一条同代码长度匹配
    for row in rows:
        if isinstance(row, dict) and safe_str(row.get("orgId")):
            return {
                "code": normalize_code(safe_str(row.get("code"))) or code,
                "org_id": safe_str(row.get("orgId")),
                "name": safe_str(row.get("zwjc")),
                "type": safe_str(row.get("type")),
            }
    return None


def _column_for(code: str, column: str | None) -> str:
    if column:
        return column
    market = detect_market(code)
    return _COLUMN_BY_MARKET.get(market, "szse")


def fetch_cninfo_announcements(
    code: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    max_pages: int = MAX_PAGES,
    column: str | None = None,
    search_key: str = "",
) -> list[dict[str, Any]]:
    """按股票代码分页拉取巨潮公告。"""
    code = normalize_code(code)
    if not code:
        return []

    meta = resolve_org(code)
    if not meta or not meta.get("org_id"):
        return []

    end_d = (end or datetime.now()).date()
    begin_d = (start or datetime(end_d.year - 1, end_d.month, end_d.day)).date()
    se_date = f"{begin_d.isoformat()}~{end_d.isoformat()}"
    col = _column_for(code, column)

    headers = {
        "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/search",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://www.cninfo.com.cn",
    }

    items: list[dict[str, Any]] = []
    total_pages = 1
    page = 1
    while page <= total_pages and page <= max(1, max_pages):
        form = {
            "pageNum": page,
            "pageSize": CNINFO_PAGE_SIZE,
            "column": col,
            "tabName": "fulltext",
            "plate": "",
            "searchkey": search_key or "",
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": se_date,
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
            "stock": f"{meta['code']},{meta['org_id']}",
        }
        try:
            resp = http_post(CNINFO_QUERY_URL, data=form, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:  # noqa: BLE001
            break

        rows = payload.get("announcements") or []
        if not isinstance(rows, list) or not rows:
            break

        total_pages = int(payload.get("totalpages") or 1)
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = safe_str(row.get("announcementTitle"))
            if not title:
                continue
            adjunct = safe_str(row.get("adjunctUrl"))
            url = f"{CNINFO_PDF_PREFIX}{adjunct}" if adjunct else ""
            published = parse_time(row.get("announcementTime"))
            items.append(
                make_item(
                    title=title,
                    published_at=published.strftime("%Y-%m-%d %H:%M:%S")
                    if published
                    else "",
                    url=url,
                    source="巨潮资讯",
                    channel="cninfo",
                    kind="notice",
                    summary=safe_str(
                        row.get("announcementTypeName") or row.get("announcementType")
                    ),
                    why=safe_str(row.get("announcementTypeName")) or "公告",
                    code=safe_str(row.get("secCode")) or code,
                    name=safe_str(row.get("secName")) or meta.get("name", ""),
                    extra={
                        "announcement_id": safe_str(row.get("announcementId")),
                        "org_id": safe_str(row.get("orgId")) or meta["org_id"],
                    },
                )
            )

        page += 1
        if page <= total_pages and page <= max_pages:
            sleep_pause(REQUEST_PAUSE_SEC)

    return items
