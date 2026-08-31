"""入口：参数 → 请求 → 解析。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Sequence

from company.news.official.cninfo.constants import MAX_PAGES
from company.news.official.cninfo.params import for_market, for_stock
from company.news.official.cninfo.parse import parse_pack
from company.news.official.cninfo.request import fetch_pages


def fetch_announcements(
    code: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    column: str | None = None,
    tab: str = "fulltext",
    category: str | Sequence[str] | None = None,
    keyword: str = "",
    plate: str = "",
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """按股票拉取巨潮公告（主入口）。

    ``category`` 可用 ``annual`` / ``年报`` / ``category_ndbg_szsh``。
    ``tab`` 可用 ``fulltext`` / ``relation`` / ``supervise``。
    """
    params = for_stock(
        code,
        start=start,
        end=end,
        days=days,
        column=column,
        tab=tab,
        category=category,
        keyword=keyword,
        plate=plate,
        max_pages=max_pages,
    )
    if params.get("error"):
        return parse_pack({"pages": [], "total": 0}, params)
    return parse_pack(fetch_pages(params), params)


def fetch_periodic_reports(
    code: str,
    *,
    kind: str | Sequence[str] = "annual",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365 * 5,
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """定期报告：annual / semi / q1 / q3，可多选。"""
    return fetch_announcements(
        code,
        start=start,
        end=end,
        days=days,
        category=kind,
        max_pages=max_pages,
    )


def search_announcements(
    code: str,
    keyword: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """按标题关键词搜该公司公告。"""
    return fetch_announcements(
        code,
        start=start,
        end=end,
        days=days,
        keyword=keyword,
        max_pages=max_pages,
    )


def fetch_surveys(
    code: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """投资者关系 / 调研记录（tabName=relation）。"""
    return fetch_announcements(
        code,
        start=start,
        end=end,
        days=days,
        tab="relation",
        max_pages=max_pages,
    )


def fetch_supervise(
    code: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """持续督导（tabName=supervise）。"""
    return fetch_announcements(
        code,
        start=start,
        end=end,
        days=days,
        tab="supervise",
        max_pages=max_pages,
    )


def fetch_market_announcements(
    *,
    column: str = "szse",
    category: str | Sequence[str] | None = None,
    keyword: str = "",
    plate: str = "",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 7,
    max_pages: int = 5,
) -> dict[str, Any]:
    """不指定个股的全市场切片（例如近一周年报）。"""
    params = for_market(
        column=column,
        category=category,
        keyword=keyword,
        plate=plate,
        start=start,
        end=end,
        days=days,
        max_pages=max_pages,
    )
    return parse_pack(fetch_pages(params), params)
