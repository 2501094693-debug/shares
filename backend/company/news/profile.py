"""公司信息画像汇总：分通道采集 → 分类 → 分组返回。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from core.codes import normalize_code, safe_str

from company.news._items import as_news, as_report, default_start, dedupe, lookback_start, sort_key, unpack
from company.news.eastmoney.search import fetch_news as fetch_eastmoney_news
from company.news.query import (
    query_announcements,
    query_press,
    query_regulatory,
    resolve_keywords,
)
from company.news.taxonomy.classify import classify_item
from company.news.taxonomy.constants import (
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
from company.news.tonghuashun.news import fetch_news as fetch_ths_news
from company.news.tonghuashun.reports import fetch_reports as fetch_ths_reports
from company.news.xueqiu.news import fetch_news as fetch_xq_news
from company.news.xueqiu.reports import fetch_reports as fetch_xq_reports


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
    resolved_name = safe_str(name) or resolved["name"]
    keyword = resolved["keyword"] or resolved_name or code

    if not code and not keyword:
        raise ValueError("缺少公司代码或名称")

    if start is None and days is not None:
        start = default_start(days)

    selected = _parse_sections(sections)
    groups = _empty_groups()
    errors: dict[str, str] = {}

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

    if SECTION_REGULATORY in selected and code:
        try:
            rows = query_regulatory(
                code, start=start, end=end, days=None, max_pages=max_pages
            )
            _put(groups, _classify_list(rows))
        except Exception as exc:  # noqa: BLE001
            errors[SECTION_REGULATORY] = str(exc)

    if SECTION_DESIGNATED_PRESS in selected and keyword:
        try:
            press = query_press(
                code or keyword,
                outlet="all",
                start=start,
                end=end,
                days=None,
                max_pages=max(2, min(max_pages, 4)),
            )
            rows = list(press.get("items") or [])
            for r in rows:
                r.setdefault("code", code)
                r.setdefault("name", resolved_name)
            _put(groups, _classify_list(rows))
        except Exception as exc:  # noqa: BLE001
            errors[SECTION_DESIGNATED_PRESS] = str(exc)

    if SECTION_MARKET_NEWS in selected and (code or keyword):
        try:
            news_start = start or lookback_start(days or 365)
            collected: list[dict[str, Any]] = []
            target = code or keyword
            collected.extend(
                unpack(
                    fetch_eastmoney_news(
                        target, start=news_start, days=None, max_pages=max_pages
                    )
                )
            )
            if keyword and keyword != target:
                collected.extend(
                    unpack(
                        fetch_eastmoney_news(
                            keyword, start=news_start, days=None, max_pages=max_pages
                        )
                    )
                )
            if code:
                collected.extend(
                    unpack(
                        fetch_ths_news(
                            code, start=news_start, days=None, max_pages=min(max_pages, 8)
                        )
                    )
                )
                collected.extend(
                    unpack(
                        fetch_xq_news(
                            code, start=news_start, days=None, max_pages=min(max_pages, 8)
                        )
                    )
                )
            tagged = [
                as_news(r, code=code, name=resolved_name) for r in collected
            ]
            _put(groups, _classify_list(tagged))
        except Exception as exc:  # noqa: BLE001
            errors[SECTION_MARKET_NEWS] = str(exc)

    if SECTION_RESEARCH in selected and code:
        try:
            report_start = start or lookback_start(days or 365)
            rows = unpack(
                fetch_ths_reports(code, start=report_start, days=None)
            )
            rows.extend(
                unpack(
                    fetch_xq_reports(
                        code,
                        start=report_start,
                        days=None,
                        max_pages=min(max_pages, 8),
                    )
                )
            )
            tagged = [as_report(r, code=code, name=resolved_name) for r in rows]
            _put(groups, _classify_list(tagged))
        except Exception as exc:  # noqa: BLE001
            errors[SECTION_RESEARCH] = str(exc)

    for cat, rows in list(groups.items()):
        groups[cat] = sorted(dedupe(rows), key=sort_key)

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
        "note": "系统性分类视图；详情页分组请用 /api/stocks/news（company.news.feed）",
    }
