"""解析数据：原始 JSON → 统一字段。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from core.codes import normalize_code, safe_str
from company.news.official.cninfo.constants import PDF_PREFIX, TZ_CN


def strip_em(text: str) -> str:
    """去掉 isHLtitle=true 时标题里的 <em> 高亮标签。"""
    return re.sub(r"</?em[^>]*>", "", safe_str(text), flags=re.IGNORECASE)


def parse_announcement_time(value: Any) -> datetime | None:
    """announcementTime 是毫秒时间戳，按北京时间换算。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=TZ_CN)
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts > 1e12:
        ts /= 1000.0
    if ts <= 0:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=TZ_CN)
    except (OverflowError, OSError, ValueError):
        return None


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(TZ_CN)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def pdf_url(adjunct_url: str) -> str:
    """把 adjunctUrl 拼成可下载的 PDF 地址。"""
    path = safe_str(adjunct_url).lstrip("/")
    if not path:
        return ""
    if path.lower().startswith("http://") or path.lower().startswith("https://"):
        return path
    return PDF_PREFIX + path


def parse_orgs(rows: Any) -> list[dict[str, str]]:
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for row in rows:
        parsed = parse_org_row(row)
        if parsed:
            out.append(parsed)
    return out


def parse_org_map(rows: Any) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    if not isinstance(rows, list):
        return mapping
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = normalize_code(safe_str(row.get("code")))
        org_id = safe_str(row.get("orgId"))
        if not code or not org_id:
            continue
        mapping[code] = {
            "code": code,
            "org_id": org_id,
            "name": safe_str(row.get("zwjc")),
            "category": safe_str(row.get("category")),
            "pinyin": safe_str(row.get("pinyin")),
        }
    return mapping


def parse_org_row(row: Any) -> dict[str, str] | None:
    if not isinstance(row, dict):
        return None
    org_id = safe_str(row.get("orgId"))
    if not org_id:
        return None

    code = normalize_code(safe_str(row.get("code"))) or safe_str(row.get("code"))
    return {
        "code": code,
        "org_id": org_id,
        "name": safe_str(row.get("zwjc")),
        "pinyin": safe_str(row.get("pinyin")),
        "category": safe_str(row.get("category") or row.get("type")),
    }


def parse_item(
    row: dict[str, Any],
    *,
    column: str,
    tab: str,
    fallback_code: str = "",
    fallback_name: str = "",
    fallback_org: str = "",
) -> dict[str, Any] | None:
    title = strip_em(row.get("announcementTitle"))
    if not title:
        return None
    adjunct = safe_str(row.get("adjunctUrl"))
    published = parse_announcement_time(row.get("announcementTime"))
    return {
        "code": safe_str(row.get("secCode")) or fallback_code,
        "name": safe_str(row.get("secName")) or fallback_name,
        "org_id": safe_str(row.get("orgId")) or fallback_org,
        "announcement_id": safe_str(row.get("announcementId")),
        "title": title,
        "published_at": _fmt_dt(published),
        "published_ms": int(row["announcementTime"])
        if isinstance(row.get("announcementTime"), (int, float))
        else None,
        "url": pdf_url(adjunct),
        "adjunct_url": adjunct,
        "adjunct_type": safe_str(row.get("adjunctType")) or "PDF",
        "adjunct_size": row.get("adjunctSize"),
        "category": safe_str(row.get("announcementTypeName")),
        "category_code": safe_str(row.get("announcementType")),
        "column": column,
        "tab": tab,
        "source": "巨潮资讯",
    }


def parse_pack(raw: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """各页原始 JSON → 统一公告包。"""
    if params.get("error"):
        return {
            "code": params.get("code") or "",
            "name": "",
            "org_id": "",
            "column": "",
            "tab": params.get("tab") or "",
            "se_date": "",
            "source": "cninfo",
            "count": 0,
            "total": 0,
            "items": [],
            "error": params["error"],
        }

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payload in raw.get("pages") or []:
        rows = payload.get("announcements") or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = parse_item(
                row,
                column=params.get("column") or "",
                tab=params.get("tab") or "",
                fallback_code=params.get("code") or "",
                fallback_name=params.get("name") or "",
                fallback_org=params.get("org_id") or "",
            )
            if not item:
                continue
            key = item["announcement_id"] or f"{item['title']}|{item['published_at'][:10]}"
            if key in seen:
                continue
            seen.add(key)
            items.append(item)

    out: dict[str, Any] = {
        "code": params.get("code") or "",
        "name": params.get("name") or "",
        "org_id": params.get("org_id") or "",
        "column": params.get("column") or "",
        "tab": params.get("tab") or "",
        "category": params.get("category") or "",
        "keyword": params.get("keyword") or "",
        "se_date": params.get("se_date") or "",
        "source": "cninfo",
        "count": len(items),
        "total": int(raw.get("total") or 0),
        "items": items,
    }
    if params.get("has_plate"):
        out["plate"] = params.get("plate") or ""
    return out


def safe_filename(title: str, announcement_id: str, url: str) -> str:
    stem = Path(unquote(urlparse(url).path)).name or f"{announcement_id}.PDF"
    if not title:
        return stem
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", title).strip(" .")
    cleaned = cleaned[:80] or announcement_id or "announcement"
    suffix = Path(stem).suffix or ".PDF"
    return f"{cleaned}{suffix}"
