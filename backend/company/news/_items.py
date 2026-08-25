"""资讯条目规范化与时间/去重工具。"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from core.codes import safe_str

_PLATFORM_LABELS = {
    "eastmoney": "东方财富",
    "tonghuashun": "同花顺",
    "xueqiu": "雪球",
}
_KIND_PRIORITY = {"notice": 0, "inquiry": 0, "penalty": 0, "report": 1, "press": 2, "news": 2}


def parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        if ts > 1e9:
            try:
                return datetime.fromtimestamp(ts)
            except (OverflowError, OSError, ValueError):
                return None

    text = safe_str(value)
    if not text:
        return None
    text = re.sub(r":(\d{3})$", r".\1", text).replace("T", " ")
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def default_start(days: int = 365) -> datetime:
    return datetime.now() - timedelta(days=max(1, int(days)))


def lookback_start(days: int | None = None, *, years: int = 50) -> datetime:
    if days is None:
        days = 365 * years + 5
    return datetime.now() - timedelta(days=max(1, int(days)))


def full_lookback_days(*, years: int = 50) -> int:
    return 365 * years + 5


def within_lookback(
    item: dict[str, Any],
    start: datetime,
    *,
    require_time: bool = False,
) -> bool:
    dt = parse_time(item.get("published_at", ""))
    if dt is None:
        return not require_time
    return dt >= start


def within_range(
    item: dict[str, Any],
    start: datetime | None,
    end: datetime | None,
) -> bool:
    dt = parse_time(item.get("published_at"))
    if dt is None:
        return True
    if start is not None and dt < start:
        return False
    if end is not None and dt > end + timedelta(days=1):
        return False
    return True


def sort_key(item: dict[str, Any]) -> tuple[int, float]:
    dt = parse_time(item.get("published_at"))
    if dt is None:
        return (1, 0.0)
    return (0, -dt.timestamp())


def unpack(pack: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if isinstance(pack, list):
        return [x for x in pack if isinstance(x, dict)]
    if isinstance(pack, dict):
        rows = pack.get("items") or []
        return [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
    return []


def dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 url 优先、否则 title+date 去重；公告优先于新闻。"""
    ordered = sorted(
        items,
        key=lambda x: _KIND_PRIORITY.get(str(x.get("kind") or "news"), 2),
    )
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in ordered:
        url = safe_str(item.get("url")).lower()
        art = safe_str(item.get("article_id") or item.get("announcement_id") or item.get("status_id"))
        title = safe_str(item.get("title"))
        day = safe_str(item.get("published_at"))[:10]
        key = art or url or f"{title}|{day}"
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def display_source(item: dict[str, Any]) -> str:
    media = safe_str(item.get("media_name") or item.get("origin") or item.get("paper"))
    src = safe_str(item.get("source"))
    if media and media.lower() not in _PLATFORM_LABELS:
        return media
    if src.lower() in _PLATFORM_LABELS:
        return media or _PLATFORM_LABELS[src.lower()]
    return src or media or "新闻"


def as_notice(
    item: dict[str, Any],
    *,
    channel: str,
    code: str = "",
    name: str = "",
) -> dict[str, Any]:
    row = dict(item)
    row["kind"] = "notice"
    row["channel"] = channel
    if code:
        row.setdefault("code", code)
    if name:
        row.setdefault("name", name)
    if not row.get("why"):
        row["why"] = row.get("summary") or row.get("category") or "公告"
    if not row.get("summary"):
        row["summary"] = row.get("why") or ""
    return row


def as_regulatory(
    item: dict[str, Any],
    *,
    kind: str = "inquiry",
    code: str = "",
    name: str = "",
) -> dict[str, Any]:
    row = dict(item)
    row["kind"] = kind
    row["channel"] = "regulatory"
    if code:
        row.setdefault("code", code)
    if name:
        row.setdefault("name", name)
    if not row.get("why"):
        row["why"] = kind
    src = safe_str(row.get("source"))
    if src and "监管" not in src:
        row["source"] = f"{src}(监管相关披露)"
    return row


def as_press(
    item: dict[str, Any],
    *,
    outlet_id: str,
    paper: str = "",
    code: str = "",
    name: str = "",
) -> dict[str, Any]:
    row = dict(item)
    row["kind"] = "press"
    row["channel"] = outlet_id
    row["outlet"] = outlet_id
    if paper:
        row["paper"] = paper
    if code:
        row.setdefault("code", code)
    if name:
        row.setdefault("name", name)
    row["source"] = display_source(row) or paper or outlet_id
    row["why"] = row.get("why") or "新闻"
    return row


def as_news(
    item: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
) -> dict[str, Any]:
    row = dict(item)
    row["kind"] = "news"
    if code:
        row.setdefault("code", code)
    if name:
        row.setdefault("name", name)
    row["source"] = display_source(row)
    row["why"] = row.get("why") or "新闻"
    return row


def as_report(
    item: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
) -> dict[str, Any]:
    row = dict(item)
    row["kind"] = "report"
    row["channel"] = "report"
    if code:
        row.setdefault("code", code)
    if name:
        row.setdefault("name", name)
    org = safe_str(row.get("org") or row.get("media_name") or row.get("researcher"))
    rating = safe_str(row.get("rating"))
    if org:
        row["source"] = org
        row["org"] = org
    else:
        row["source"] = display_source(row) or "机构研报"
    if rating:
        row["rating"] = rating
    why_parts = [p for p in (org, rating) if p]
    row["why"] = row.get("why") or rating or "研报"
    if not row.get("summary"):
        row["summary"] = " · ".join(why_parts) if why_parts else "机构研报"
    return row


def span_meta(items: list[dict[str, Any]]) -> dict[str, str]:
    dates = [parse_time(x.get("published_at")) for x in items]
    dates = [d for d in dates if d is not None]
    if not dates:
        return {"from": "", "to": ""}
    return {
        "from": min(dates).strftime("%Y-%m-%d"),
        "to": max(dates).strftime("%Y-%m-%d"),
    }
