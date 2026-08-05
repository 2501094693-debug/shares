"""采集结果的整理：去重、分组过滤、时间跨度统计。"""

from __future__ import annotations

from typing import Any

from .constants import MAX_NEWS, MAX_NOTICES, MAX_REPORTS
from .utils import parse_time, sort_key


# 去重时的优先级：公告 > 研报 > 新闻（同 URL/标题时保留优先级高的）
_KIND_PRIORITY = {"notice": 0, "report": 1, "news": 2}


def dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 url（或 title）去重；冲突时优先保留公告。"""
    ordered = sorted(
        items,
        key=lambda x: _KIND_PRIORITY.get(x.get("kind") or "news", 2),
    )
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in ordered:
        key = (item.get("url") or item.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def filter_notices(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """整理公告列表：补全字段，按时间从新到旧，截断到上限。"""
    kept: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        row["kind"] = "notice"
        if not row.get("why"):
            row["why"] = row.get("summary") or "公告"
        kept.append(row)
    return sorted(kept, key=sort_key)[:MAX_NOTICES]


def filter_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """整理媒体新闻列表。"""
    kept: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        row["kind"] = "news"
        if not row.get("why"):
            row["why"] = "新闻"
        kept.append(row)
    return sorted(kept, key=sort_key)[:MAX_NEWS]


def filter_reports(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """整理研报列表。"""
    kept: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        row["kind"] = "report"
        if not row.get("why"):
            row["why"] = row.get("rating") or "研报"
        kept.append(row)
    return sorted(kept, key=sort_key)[:MAX_REPORTS]


def span_meta(items: list[dict[str, Any]]) -> dict[str, str]:
    """统计列表覆盖的最早 / 最晚发布日（YYYY-MM-DD）。"""
    dates = [parse_time(x.get("published_at")) for x in items]
    dates = [d for d in dates if d is not None]
    if not dates:
        return {"from": "", "to": ""}
    return {
        "from": min(dates).strftime("%Y-%m-%d"),
        "to": max(dates).strftime("%Y-%m-%d"),
    }
