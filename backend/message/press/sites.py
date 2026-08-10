"""官网侧尽力检索（失败不影响主流程）。

目前多数站点搜索需浏览器环境；此处仅保留少量可直连接口的尝试，
主数据仍来自 eastmoney 按媒体署名筛选。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from message.disclosure.http_util import http_get, safe_str, within_range
from message.disclosure.normalize import make_item

from .constants import Outlet


def _abs(base: str, href: str) -> str:
    href = safe_str(href)
    if not href or href.startswith("javascript:"):
        return ""
    return urljoin(base, href)


def fetch_stcn_direct(
    keyword: str,
    outlet: Outlet,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    code: str = "",
    name: str = "",
) -> list[dict[str, Any]]:
    """证券时报网 search_data（常为空，成功则补充）。"""
    url = (
        "https://www.stcn.com/article/search_data.html"
        f"?search_type=news&keyword={quote(keyword)}&uncertainty=1&sorter=time"
    )
    try:
        resp = http_get(
            url,
            headers={
                "Referer": "https://www.stcn.com/article/search.html",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:  # noqa: BLE001
        return []

    data = payload.get("data")
    html = ""
    if isinstance(data, dict):
        html = safe_str(data.get("data"))
    elif isinstance(data, str):
        html = data
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    items: list[dict[str, Any]] = []
    for a in soup.select("a[href*='/article/detail']"):
        title = a.get_text(" ", strip=True)
        href = _abs("https://www.stcn.com", a.get("href") or "")
        if not title or not href:
            continue
        item = make_item(
            title=title,
            url=href,
            source=outlet["paper"],
            channel=outlet["id"],
            kind="press",
            why="证券时报网",
            code=code,
            name=name,
            extra={
                "outlet": outlet["id"],
                "outlet_name": outlet["name"],
                "paper": outlet["paper"],
                "domain": outlet["domain"],
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
    """中国日报网新闻搜索页。"""
    url = (
        "https://newssearch.chinadaily.com.cn/cn/search"
        f"?keywords={quote(keyword)}"
    )
    try:
        resp = http_get(
            url,
            headers={"Referer": "https://www.chinadaily.com.cn/"},
            timeout=25,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception:  # noqa: BLE001
        return []

    soup = BeautifulSoup(html, "lxml")
    items: list[dict[str, Any]] = []
    for a in soup.select("a[href]"):
        title = a.get_text(" ", strip=True)
        href = safe_str(a.get("href"))
        if len(title) < 8:
            continue
        if "chinadaily.com.cn" not in href and not href.startswith("/"):
            continue
        if not any(k in title for k in (keyword, keyword[:2])):
            # 搜索页噪音大，要求标题含关键词片段
            if keyword not in title:
                continue
        full = _abs("https://www.chinadaily.com.cn", href)
        item = make_item(
            title=title,
            url=full,
            source=outlet["paper"],
            channel=outlet["id"],
            kind="press",
            why="中国日报网",
            code=code,
            name=name,
            extra={
                "outlet": outlet["id"],
                "outlet_name": outlet["name"],
                "paper": outlet["paper"],
                "domain": outlet["domain"],
                "via": "chinadaily_direct",
            },
        )
        if within_range(item, start, end):
            items.append(item)
    # 去重
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in items:
        u = it.get("url") or ""
        if u in seen:
            continue
        seen.add(u)
        out.append(it)
    return out[:30]


def fetch_outlet_direct(
    keyword: str,
    outlet: Outlet,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    oid = outlet["id"]
    if oid == "stcn":
        return fetch_stcn_direct(keyword, outlet, **kwargs)
    if oid == "chinadaily":
        return fetch_chinadaily_direct(keyword, outlet, **kwargs)
    return []
