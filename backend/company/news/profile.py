"""公司信息画像：分通道采集 → 分类 → 分组。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from core.codes import normalize_code, safe_str

from company.news._items import default_start, dedupe, lookback_start, sort_key
from company.news.query import (
    query_announcements,
    query_market_news,
    query_press,
    query_regulatory,
    query_reports,
    resolve_keywords,
)
from company.news.taxonomy.classify import classify_item
from company.news.taxonomy.constants import (
    ALL_SECTIONS,
    CATEGORIES,
    CATEGORY_MARKET_NEWS,
    DEFAULT_SECTIONS,
    SECTION_DESIGNATED_PRESS,
    SECTION_DISCLOSURE,
    SECTION_MARKET_NEWS,
    SECTION_REGULATORY,
    SECTION_RESEARCH,
)

_MAIN_KEYS = (
    SECTION_DISCLOSURE,
    SECTION_REGULATORY,
    SECTION_DESIGNATED_PRESS,
    SECTION_MARKET_NEWS,
    SECTION_RESEARCH,
)


def _parse_sections(sections: str | Iterable[str] | None) -> list[str]:
    if sections is None:
        return list(DEFAULT_SECTIONS)
    if isinstance(sections, str):
        raw = sections.strip().lower()
        if not raw or raw == "default":
            return list(DEFAULT_SECTIONS)
        if raw in {"all", "*"}:
            return list(ALL_SECTIONS)
        parts = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        parts = [str(p).strip().lower() for p in sections if str(p).strip()]
    if not parts:
        return list(DEFAULT_SECTIONS)
    unknown = [p for p in parts if p not in ALL_SECTIONS]
    if unknown:
        raise ValueError(f"未知 sections: {unknown}；可选: {', '.join(ALL_SECTIONS)} 或 all")
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _put(groups: dict[str, list[dict[str, Any]]], rows: list[dict[str, Any]]) -> None:
    for row in rows:
        tagged = classify_item(row)
        cat = tagged.get("category") or CATEGORY_MARKET_NEWS
        groups.setdefault(cat, []).append(tagged)


def query_company_profile(
    code_or_name: str,
    *,
    name: str = "",
    days: int | None = 365,
    start: datetime | None = None,
    end: datetime | None = None,
    sections: str | Iterable[str] | None = None,
    max_pages: int = 5,
    announcement_channel: str = "auto",
) -> dict[str, Any]:
    """汇总指定公司的分类信息。默认 disclosure / regulatory / designated_press。"""
    resolved = resolve_keywords(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    resolved_name = safe_str(name) or resolved["name"]
    keyword = resolved["keyword"] or resolved_name or code
    if not code and not keyword:
        raise ValueError("缺少公司代码或名称")

    if start is None and days is not None:
        start = default_start(days)

    selected = _parse_sections(sections)
    groups = {cat: [] for cat in CATEGORIES}
    errors: dict[str, str] = {}
    window = {"start": start, "end": end, "days": None, "max_pages": max_pages}

    def _run(section: str, fetch) -> None:
        try:
            rows = fetch()
            for row in rows:
                row.setdefault("code", code)
                row.setdefault("name", resolved_name)
            _put(groups, rows)
        except Exception as exc:  # noqa: BLE001
            errors[section] = str(exc)

    if SECTION_DISCLOSURE in selected and code:
        _run(SECTION_DISCLOSURE, lambda: query_announcements(code, channel=announcement_channel, **window))
    if SECTION_REGULATORY in selected and code:
        _run(SECTION_REGULATORY, lambda: query_regulatory(code, **window))
    if SECTION_DESIGNATED_PRESS in selected and keyword:
        _run(
            SECTION_DESIGNATED_PRESS,
            lambda: list(
                query_press(code or keyword, outlet="all", **window | {"max_pages": max(2, min(max_pages, 4))}).get("items")
                or []
            ),
        )
    if SECTION_MARKET_NEWS in selected and (code or keyword):
        news_start = start or lookback_start(days or 365)
        _run(
            SECTION_MARKET_NEWS,
            lambda: query_market_news(code or keyword, resolved_name, start=news_start, days=None, max_pages=max_pages),
        )
    if SECTION_RESEARCH in selected and code:
        report_start = start or lookback_start(days or 365)
        _run(
            SECTION_RESEARCH,
            lambda: query_reports(code, resolved_name, start=report_start, days=None, max_pages=max_pages),
        )

    for cat, rows in list(groups.items()):
        groups[cat] = sorted(dedupe(rows), key=sort_key)

    main_groups = {k: groups.get(k, []) for k in _MAIN_KEYS}
    return {
        "code": code,
        "name": resolved_name,
        "keyword": keyword,
        "days": days,
        "sections": selected,
        "groups": main_groups,
        "counts": {k: len(main_groups[k]) for k in _MAIN_KEYS},
        "errors": errors,
        "view": "profile",
        "note": "系统性分类视图；详情页分组请用 /api/stocks/news（company.news.feed）",
    }
