"""官网侧尽力检索（失败不影响主流程）。

目前多数站点搜索需浏览器环境；此处仅保留少量可直连接口的尝试，
主数据仍来自 eastmoney 按媒体署名筛选。中证网走 ``company.news.press.cs``，
中国证券网走 ``company.news.press.cnstock``，证券时报网走 ``company.news.press.stcn``，
证券日报网走 ``company.news.press.zqrb``，金融时报网走 ``company.news.press.financialnews``，
经济参考网走 ``company.news.press.jjckb``，中国日报网走 ``company.news.press.chinadaily``。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from message.disclosure.http_util import safe_str, within_range
from message.disclosure.normalize import make_item

from .constants import Outlet


def fetch_stcn_direct(
    keyword: str,
    outlet: Outlet,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    code: str = "",
    name: str = "",
) -> list[dict[str, Any]]:
    """证券时报网 search_data（见 ``company.news.press.stcn``）。"""
    from company.news.press.stcn import fetch_news

    query = name or keyword or code
    if not query:
        return []
    try:
        pack = fetch_news(
            query,
            start=start,
            end=end,
            days=None if start is not None else 31,
            type_="news",
            sort="time",
            max_pages=4,
        )
    except Exception:  # noqa: BLE001
        return []

    items: list[dict[str, Any]] = []
    for row in pack.get("items") or []:
        published = safe_str(row.get("published_at"))
        item = make_item(
            title=safe_str(row.get("title")),
            published_at=published,
            url=safe_str(row.get("url")),
            source=outlet["paper"],
            channel=outlet["id"],
            kind="press",
            summary=safe_str(row.get("summary")),
            why=safe_str(row.get("column")) or outlet["name"],
            code=code,
            name=name,
            extra={
                "outlet": outlet["id"],
                "outlet_name": outlet["name"],
                "paper": outlet["paper"],
                "domain": outlet["domain"],
                "media_name": safe_str(row.get("column")) or outlet["name"],
                "via": "stcn_direct",
            },
        )
        if within_range(item, start, end):
            items.append(item)
    return items


def fetch_chinadaily_direct(
    keyword: str,
    outlet: Outlet,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    code: str = "",
    name: str = "",
) -> list[dict[str, Any]]:
    """中国日报网 rest/cn/search（见 ``company.news.press.chinadaily``）。"""
    from company.news.press.chinadaily import fetch_news

    query = name or keyword or code
    if not query:
        return []
    try:
        pack = fetch_news(
            query,
            start=start,
            end=end,
            days=None if start is not None else 31,
            type_="story",
            sort="time",
            lang="cn",
            max_pages=4,
        )
    except Exception:  # noqa: BLE001
        return []

    items: list[dict[str, Any]] = []
    for row in pack.get("items") or []:
        published = safe_str(row.get("published_at"))
        item = make_item(
            title=safe_str(row.get("title")),
            published_at=published,
            url=safe_str(row.get("url")),
            source=outlet["paper"],
            channel=outlet["id"],
            kind="press",
            summary=safe_str(row.get("summary")),
            why=safe_str(row.get("origin")) or outlet["name"],
            code=code,
            name=name,
            extra={
                "outlet": outlet["id"],
                "outlet_name": outlet["name"],
                "paper": outlet["paper"],
                "domain": outlet["domain"],
                "media_name": safe_str(row.get("origin")) or outlet["name"],
                "via": "chinadaily_direct",
            },
        )
        if within_range(item, start, end):
            items.append(item)
    return items


def fetch_cs_direct(
    keyword: str,
    outlet: Outlet,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    code: str = "",
    name: str = "",
) -> list[dict[str, Any]]:
    """中证网 search_articles（见 ``company.news.press.cs``）。"""
    from company.news.press.cs import fetch_news

    query = name or keyword or code
    if not query:
        return []
    try:
        pack = fetch_news(
            query,
            start=start,
            end=end,
            days=None if start is not None else 31,
            field="all",
            sort="time",
            max_pages=4,
        )
    except Exception:  # noqa: BLE001
        return []

    items: list[dict[str, Any]] = []
    for row in pack.get("items") or []:
        published = safe_str(row.get("published_at"))
        item = make_item(
            title=safe_str(row.get("title")),
            published_at=published,
            url=safe_str(row.get("url")),
            source=outlet["paper"],
            channel=outlet["id"],
            kind="press",
            summary=safe_str(row.get("summary")),
            why=safe_str(row.get("origin")) or outlet["name"],
            code=code,
            name=name,
            extra={
                "outlet": outlet["id"],
                "outlet_name": outlet["name"],
                "paper": outlet["paper"],
                "domain": outlet["domain"],
                "media_name": safe_str(row.get("origin")) or outlet["name"],
                "via": "cs_direct",
            },
        )
        if within_range(item, start, end):
            items.append(item)
    return items


def fetch_cnstock_direct(
    keyword: str,
    outlet: Outlet,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    code: str = "",
    name: str = "",
) -> list[dict[str, Any]]:
    """中国证券网 search/v2/news（见 ``company.news.press.cnstock``）。"""
    from company.news.press.cnstock import fetch_news

    query = name or keyword or code
    if not query:
        return []
    try:
        pack = fetch_news(
            query,
            start=start,
            end=end,
            days=None if start is not None else 31,
            type_="news",
            max_pages=4,
        )
    except Exception:  # noqa: BLE001
        return []

    items: list[dict[str, Any]] = []
    for row in pack.get("items") or []:
        published = safe_str(row.get("published_at"))
        item = make_item(
            title=safe_str(row.get("title")),
            published_at=published,
            url=safe_str(row.get("url")),
            source=outlet["paper"],
            channel=outlet["id"],
            kind="press",
            summary=safe_str(row.get("summary")),
            why=safe_str(row.get("column")) or outlet["name"],
            code=code,
            name=name,
            extra={
                "outlet": outlet["id"],
                "outlet_name": outlet["name"],
                "paper": outlet["paper"],
                "domain": outlet["domain"],
                "media_name": outlet["name"],
                "via": "cnstock_direct",
            },
        )
        if within_range(item, start, end):
            items.append(item)
    return items


def fetch_zqrb_direct(
    keyword: str,
    outlet: Outlet,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    code: str = "",
    name: str = "",
) -> list[dict[str, Any]]:
    """证券日报网 search.php（见 ``company.news.press.zqrb``）。"""
    from company.news.press.zqrb import fetch_news

    query = name or keyword or code
    if not query:
        return []
    try:
        pack = fetch_news(
            query,
            start=start,
            end=end,
            days=None if start is not None else 31,
            src="news",
            field="title",
            sort="time",
            max_pages=4,
        )
    except Exception:  # noqa: BLE001
        return []

    items: list[dict[str, Any]] = []
    for row in pack.get("items") or []:
        published = safe_str(row.get("published_at"))
        item = make_item(
            title=safe_str(row.get("title")),
            published_at=published,
            url=safe_str(row.get("url")),
            source=outlet["paper"],
            channel=outlet["id"],
            kind="press",
            summary=safe_str(row.get("summary")),
            why=safe_str(row.get("column")) or outlet["name"],
            code=code,
            name=name,
            extra={
                "outlet": outlet["id"],
                "outlet_name": outlet["name"],
                "paper": outlet["paper"],
                "domain": outlet["domain"],
                "media_name": safe_str(row.get("origin")) or outlet["name"],
                "via": "zqrb_direct",
            },
        )
        if within_range(item, start, end):
            items.append(item)
    return items


def fetch_financialnews_direct(
    keyword: str,
    outlet: Outlet,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    code: str = "",
    name: str = "",
) -> list[dict[str, Any]]:
    """中国金融新闻网 Search.do（见 ``company.news.press.financialnews``）。"""
    from company.news.press.financialnews import fetch_news

    query = name or keyword or code
    if not query:
        return []
    try:
        pack = fetch_news(
            query,
            start=start,
            end=end,
            days=None if start is not None else 31,
            field="all",
            sort="time",
            max_pages=4,
        )
    except Exception:  # noqa: BLE001
        return []

    items: list[dict[str, Any]] = []
    for row in pack.get("items") or []:
        published = safe_str(row.get("published_at"))
        item = make_item(
            title=safe_str(row.get("title")),
            published_at=published,
            url=safe_str(row.get("url")),
            source=outlet["paper"],
            channel=outlet["id"],
            kind="press",
            summary=safe_str(row.get("summary")),
            why=safe_str(row.get("column")) or outlet["name"],
            code=code,
            name=name,
            extra={
                "outlet": outlet["id"],
                "outlet_name": outlet["name"],
                "paper": outlet["paper"],
                "domain": outlet["domain"],
                "media_name": safe_str(row.get("origin")) or outlet["name"],
                "via": "financialnews_direct",
            },
        )
        if within_range(item, start, end):
            items.append(item)
    return items


def fetch_jjckb_direct(
    keyword: str,
    outlet: Outlet,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    code: str = "",
    name: str = "",
) -> list[dict[str, Any]]:
    """经济参考网 getNewsFromAllData（见 ``company.news.press.jjckb``）。"""
    from company.news.press.jjckb import fetch_news

    query = name or keyword or code
    if not query:
        return []
    try:
        pack = fetch_news(
            query,
            start=start,
            end=end,
            days=None if start is not None else 31,
            max_pages=4,
        )
    except Exception:  # noqa: BLE001
        return []

    items: list[dict[str, Any]] = []
    for row in pack.get("items") or []:
        published = safe_str(row.get("published_at"))
        item = make_item(
            title=safe_str(row.get("title")),
            published_at=published,
            url=safe_str(row.get("url")),
            source=outlet["paper"],
            channel=outlet["id"],
            kind="press",
            summary=safe_str(row.get("summary")),
            why=safe_str(row.get("column")) or outlet["name"],
            code=code,
            name=name,
            extra={
                "outlet": outlet["id"],
                "outlet_name": outlet["name"],
                "paper": outlet["paper"],
                "domain": outlet["domain"],
                "media_name": safe_str(row.get("origin")) or outlet["name"],
                "via": "jjckb_direct",
            },
        )
        if within_range(item, start, end):
            items.append(item)
    return items


def fetch_outlet_direct(
    keyword: str,
    outlet: Outlet,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    oid = outlet["id"]
    if oid == "cs":
        return fetch_cs_direct(keyword, outlet, **kwargs)
    if oid == "cnstock":
        return fetch_cnstock_direct(keyword, outlet, **kwargs)
    if oid == "stcn":
        return fetch_stcn_direct(keyword, outlet, **kwargs)
    if oid == "zqrb":
        return fetch_zqrb_direct(keyword, outlet, **kwargs)
    if oid == "financialnews":
        return fetch_financialnews_direct(keyword, outlet, **kwargs)
    if oid == "jjckb":
        return fetch_jjckb_direct(keyword, outlet, **kwargs)
    if oid == "chinadaily":
        return fetch_chinadaily_direct(keyword, outlet, **kwargs)
    return []
