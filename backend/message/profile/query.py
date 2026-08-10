"""公司信息画像汇总：分通道采集 → 分类 → 分组返回。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from message.disclosure.http_util import (
    dedupe,
    default_start,
    lookback_start,
    normalize_code,
    sort_key,
)
from message.market import fetch_media_news, fetch_research_reports
from message.disclosure.query import query_announcements, query_regulatory
from message.press.query import query_press
from message.press.resolve import resolve_keywords
from message.taxonomy.classify import classify_item
from message.taxonomy.constants import (
    ALL_SECTIONS,
    CATEGORIES,
    CATEGORY_DESIGNATED_PRESS,
    CATEGORY_DISCLOSURE,
    CATEGORY_MARKET_NEWS,
    CATEGORY_REGULATORY,
    CATEGORY_RESEARCH,
    DEFAULT_SECTIONS,
    SECTION_DESIGNATED_PRESS,
    SECTION_DISCLOSURE,
    SECTION_MARKET_NEWS,
    SECTION_REGULATORY,
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
        raise ValueError(
            f"未知 sections: {unknown}；可选: {', '.join(ALL_SECTIONS)} 或 all"
        )
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _empty_groups() -> dict[str, list[dict[str, Any]]]:
    return {cat: [] for cat in CATEGORIES}


def _classify_list(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [classify_item(x) for x in rows]


def _put(
    groups: dict[str, list[dict[str, Any]]],
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        cat = row.get("category") or CATEGORY_MARKET_NEWS
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(row)


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
    """汇总指定公司的分类信息。

    sections:
      - 默认 ``disclosure,regulatory,designated_press``
      - ``all`` 含 market_news / research
      - 也可逗号组合
    """
    resolved = resolve_keywords(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    resolved_name = name.strip() or resolved["name"]
    keyword = resolved["keyword"] or resolved_name or code

    if not code and not keyword:
        raise ValueError("缺少公司代码或名称")

    if start is None and days is not None:
        start = default_start(days)

    selected = _parse_sections(sections)
    groups = _empty_groups()
    errors: dict[str, str] = {}

    # 1) 法定公告
    if SECTION_DISCLOSURE in selected and code:
        try:
            rows = query_announcements(
                code,
                channel=announcement_channel,
                start=start,
                end=end,
                days=None,
                max_pages=max_pages,
            )
            _put(groups, _classify_list(rows))
        except Exception as exc:  # noqa: BLE001
            errors[SECTION_DISCLOSURE] = str(exc)

    # 2) 监管
    if SECTION_REGULATORY in selected and code:
        try:
            rows = query_regulatory(
                code, start=start, end=end, days=None, max_pages=max_pages
            )
            _put(groups, _classify_list(rows))
        except Exception as exc:  # noqa: BLE001
            errors[SECTION_REGULATORY] = str(exc)

    # 3) 指定报刊
    if SECTION_DESIGNATED_PRESS in selected and keyword:
        try:
            press = query_press(
                code or keyword,
                outlet="all",
                start=start,
                end=end,
                days=None,
                max_pages=max(2, min(max_pages, 4)),
                include_direct=False,
            )
            rows = list(press.get("items") or [])
            # 确保 code/name
            for r in rows:
                r.setdefault("code", code)
                r.setdefault("name", resolved_name)
            _put(groups, _classify_list(rows))
        except Exception as exc:  # noqa: BLE001
            errors[SECTION_DESIGNATED_PRESS] = str(exc)

    # 4) 市场化新闻（东财）
    if SECTION_MARKET_NEWS in selected and (code or keyword):
        try:
            news_start = start or lookback_start(days or 365)
            collected: list[dict[str, Any]] = []
            if code:
                collected.extend(fetch_media_news(code, news_start))
            if keyword and keyword != code:
                collected.extend(fetch_media_news(keyword, news_start))
            for r in collected:
                r.setdefault("code", code)
                r.setdefault("name", resolved_name)
                r.setdefault("channel", "news")
            _put(groups, _classify_list(collected))
        except Exception as exc:  # noqa: BLE001
            errors[SECTION_MARKET_NEWS] = str(exc)

    # 5) 研报
    if SECTION_RESEARCH in selected and code:
        try:
            report_start = start or lookback_start(days or 365)
            rows = fetch_research_reports(code, report_start)
            for r in rows:
                r.setdefault("code", code)
                r.setdefault("name", resolved_name)
                r.setdefault("channel", "report")
            _put(groups, _classify_list(rows))
        except Exception as exc:  # noqa: BLE001
            errors[SECTION_RESEARCH] = str(exc)

    # 组内去重排序
    for cat, rows in list(groups.items()):
        groups[cat] = sorted(dedupe(rows), key=sort_key)

    counts = {cat: len(rows) for cat, rows in groups.items()}
    # 只统计有业务意义的主类（与计划返回结构一致）
    main_keys = (
        CATEGORY_DISCLOSURE,
        CATEGORY_REGULATORY,
        CATEGORY_DESIGNATED_PRESS,
        CATEGORY_MARKET_NEWS,
        CATEGORY_RESEARCH,
    )
    main_groups = {k: groups.get(k, []) for k in main_keys}
    main_counts = {k: len(main_groups[k]) for k in main_keys}

    return {
        "code": code,
        "name": resolved_name,
        "keyword": keyword,
        "days": days,
        "sections": selected,
        "groups": main_groups,
        "counts": main_counts,
        "errors": errors,
        "view": "profile",
        "note": "系统性分类视图；详情页三栏请用 /api/stocks/news（message.feed）",
    }
