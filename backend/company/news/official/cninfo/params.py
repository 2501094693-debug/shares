"""参数设计：认出公司，算出 stock / 市场 / 日期 / 分类。"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Sequence

from core.codes import detect_market, normalize_code, safe_str
from company.news.official.cninfo.constants import (
    CATEGORIES,
    COLUMN_BY_MARKET,
    COLUMNS,
    MAX_PAGES,
    PAGE_SIZE,
    TABS,
)

_ORG_CACHE: dict[str, dict[str, str]] = {}


def resolve_column(column: str | None, code: str = "") -> str:
    key = safe_str(column).lower()
    if key in COLUMNS and COLUMNS[key] != "auto":
        return COLUMNS[key]
    market = detect_market(code)
    return COLUMN_BY_MARKET.get(market, "szse")


def resolve_tab(tab: str | None) -> str:
    key = safe_str(tab).lower() or "fulltext"
    if key in TABS:
        return TABS[key]
    if safe_str(tab) in TABS:
        return TABS[safe_str(tab)]
    return "fulltext"


def resolve_category(category: str | Sequence[str] | None) -> str:
    """别名或原始 category_xxx 都接受；多个用分号拼接。"""
    if category is None or category == "":
        return ""
    if isinstance(category, str):
        parts = [p.strip() for p in re.split(r"[;,|]", category) if p.strip()]
    else:
        parts = [safe_str(p) for p in category if safe_str(p)]
    codes: list[str] = []
    for part in parts:
        raw = part.strip().rstrip(";")
        if not raw:
            continue
        if raw.startswith("category_"):
            codes.append(raw)
            continue
        mapped = CATEGORIES.get(raw) or CATEGORIES.get(raw.lower())
        if mapped:
            codes.append(mapped)
        else:
            raise ValueError(
                f"未知 category: {raw}；可用 {', '.join(sorted(set(CATEGORIES)))}"
            )
    return ";".join(codes)


def a_share_code(code: str, org_id: str = "") -> str:
    """B 股代码转对应 A 股。巨潮 stock 参数不接受 200/900 开头。"""
    c = normalize_code(code)
    if not c:
        return ""
    if c.startswith("200"):
        return "000" + c[3:]
    if c.startswith("900"):
        oid = safe_str(org_id)
        if oid.startswith("gssh") and len(oid) >= 11:
            digits = re.sub(r"\D", "", oid)
            if len(digits) >= 6:
                return digits[-6:]
        return c
    return c


def _parse_day(value: str | date | datetime | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = safe_str(value).replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text[:8], fmt).date()
        except ValueError:
            continue
    return None


def se_date(
    start: str | date | datetime | None,
    end: str | date | datetime | None,
    days: int | None,
) -> str:
    """收成巨潮要的 ``YYYY-MM-DD~YYYY-MM-DD``。"""
    end_d = _parse_day(end) or date.today()
    start_d = _parse_day(start)
    if start_d is None:
        lookback = 365 if days is None else max(1, int(days))
        start_d = end_d - timedelta(days=lookback)
    if start_d > end_d:
        start_d, end_d = end_d, start_d
    return f"{start_d.isoformat()}~{end_d.isoformat()}"


def resolve_org(code_or_name: str) -> dict[str, str] | None:
    """认出公司：orgId / 简称。优先联想，静态表兜底。B 股自动转到 A 股代码。"""
    from company.news.official.cninfo.request import load_org_map, search_orgs

    raw = safe_str(code_or_name)
    if not raw:
        return None
    code = normalize_code(raw)
    cache_key = code or raw
    cached = _ORG_CACHE.get(cache_key)
    if cached:
        return dict(cached)

    keyword = code or raw
    rows = search_orgs(keyword, max_num=10)
    picked: dict[str, str] | None = None
    if code:
        for row in rows:
            if normalize_code(row.get("code", "")) == code:
                picked = row
                break
    if picked is None and rows:
        picked = rows[0]

    if picked is None and code:
        picked = load_org_map().get(code)

    if not picked or not picked.get("org_id"):
        return None

    query_code = a_share_code(picked.get("code") or code, picked["org_id"])
    if query_code and query_code != normalize_code(picked.get("code", "")):
        a_rows = search_orgs(query_code, max_num=10)
        for row in a_rows:
            if normalize_code(row.get("code", "")) == query_code:
                picked = row
                break
        else:
            picked = {**picked, "code": query_code, "input_code": code or raw}
    elif query_code:
        picked = {**picked, "code": query_code}

    _ORG_CACHE[cache_key] = picked
    if picked.get("code"):
        _ORG_CACHE[picked["code"]] = picked
    return dict(picked)


def for_stock(
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
    """个股查询：认出公司，并算出 stock / column / tab / seDate / category。"""
    tab_name = resolve_tab(tab)
    org = resolve_org(code)
    if not org:
        return {
            "error": f"找不到 orgId: {code}",
            "code": normalize_code(code) or safe_str(code),
            "name": "",
            "org_id": "",
            "column": "",
            "tab": tab_name,
            "category": "",
            "keyword": safe_str(keyword),
            "plate": safe_str(plate),
            "se_date": "",
            "stock": "",
            "max_pages": max(1, int(max_pages)),
        }
    query_code = org["code"]
    return {
        "error": "",
        "code": query_code,
        "name": org.get("name", ""),
        "org_id": org["org_id"],
        "column": resolve_column(column, query_code),
        "tab": tab_name,
        "category": resolve_category(category),
        "keyword": safe_str(keyword),
        "plate": safe_str(plate),
        "se_date": se_date(start, end, days),
        "stock": f"{query_code},{org['org_id']}",
        "max_pages": max(1, int(max_pages)),
    }


def for_market(
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
    """全市场切片：stock 留空，必须自己带市场 / 分类 / 日期。"""
    return {
        "error": "",
        "code": "",
        "name": "",
        "org_id": "",
        "column": resolve_column(column),
        "tab": "fulltext",
        "category": resolve_category(category),
        "keyword": safe_str(keyword),
        "plate": safe_str(plate),
        "se_date": se_date(start, end, days),
        "stock": "",
        "max_pages": max(1, int(max_pages)),
        "has_plate": True,
    }


def list_form(
    *,
    stock: str = "",
    page_num: int = 1,
    page_size: int = PAGE_SIZE,
    column: str = "szse",
    tab: str = "fulltext",
    se_date: str = "",
    category: str = "",
    search_key: str = "",
    plate: str = "",
    trade: str = "",
    sort_name: str = "",
    sort_type: str = "",
    highlight_title: bool = True,
) -> dict[str, Any]:
    """一页 hisAnnouncement 表单。"""
    return {
        "pageNum": max(1, int(page_num)),
        "pageSize": max(1, min(int(page_size), PAGE_SIZE)),
        "column": column or "szse",
        "tabName": tab or "fulltext",
        "plate": plate or "",
        "searchkey": search_key or "",
        "secid": "",
        "category": category or "",
        "trade": trade or "",
        "seDate": se_date or "",
        "sortName": sort_name or "",
        "sortType": sort_type or "",
        "isHLtitle": "true" if highlight_title else "false",
        "stock": stock or "",
    }
