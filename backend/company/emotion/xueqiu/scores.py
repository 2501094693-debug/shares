"""雪球个股社区快照：关注人数、热门讨论用户、粉丝同时关注。

关注列表：
    GET https://api.xueqiu.com/friendships/stockfollowers.json

热门用户：
    GET https://xueqiu.com/recommend/user/stock_hot_user.json

粉丝同时关注：
    GET https://xueqiu.com/stock/portfolio/popstocks.json
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.codes import normalize_code, safe_str
from core.fmt import to_float

from company.emotion.xueqiu._common import (
    CHANNEL_FANS,
    CHANNEL_SCORES,
    FOLLOWERS_API,
    HOT_USER_API,
    POPSTOCKS_API,
    REQUEST_PAUSE_SEC,
    SOURCE,
    WEB_HOST,
    empty_pack,
    fmt_dt,
    get_payload,
    headers_for,
    query_quote,
    resolve_keyword,
    stock_page_url,
    to_int,
    user_profile_url,
    xq_symbol,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 14
MAX_PAGES = 10


def _fmt_num(value: Any, digits: int = 2) -> str:
    number = to_float(value)
    if number is None:
        return ""
    if abs(number) >= 10000:
        return f"{number / 10000:.1f}万".rstrip("0").rstrip(".")
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def query_followers(symbol: str, *, page: int = 1, page_size: int = PAGE_SIZE) -> dict[str, Any]:
    """个股关注用户单页原始 JSON。"""
    payload = get_payload(
        FOLLOWERS_API,
        params={
            "code": symbol,
            "pageNo": max(1, int(page)),
            "size": max(1, min(int(page_size), 50)),
            "x": "0.75",
        },
        headers=headers_for(stock_page_url(symbol), origin=WEB_HOST),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def query_hot_users(symbol: str, *, start: int = 0, count: int = 10) -> list[dict[str, Any]]:
    """个股热门讨论用户原始列表。"""
    payload = get_payload(
        HOT_USER_API,
        params={"symbol": symbol, "start": max(0, int(start)), "count": max(1, min(int(count), 20))},
        headers=headers_for(stock_page_url(symbol), origin=WEB_HOST),
        timeout=20,
    )
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("list") or payload.get("users") or payload.get("items") or []
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    return []


def query_popstocks(symbol: str, *, count: int = 10) -> list[dict[str, Any]]:
    """关注该股的人同时关注的股票。"""
    payload = get_payload(
        POPSTOCKS_API,
        params={"code": symbol, "start": 0, "count": max(1, min(int(count), 20))},
        headers=headers_for(stock_page_url(symbol), origin=WEB_HOST),
        timeout=20,
    )
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("list") or payload.get("items") or []
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    return []


def query_scores(code: str) -> dict[str, Any]:
    """个股社区快照原始包：行情 + 关注第一页。"""
    symbol = xq_symbol(code)
    quote = query_quote(symbol) if symbol else {}
    fans = query_followers(symbol, page=1, page_size=1) if symbol else {}
    return {"quote": quote, "followers": fans, "symbol": symbol}


def _normalize_user(row: dict[str, Any], *, code: str, name: str, channel: str) -> dict[str, Any] | None:
    uid = safe_str(row.get("id"))
    author = safe_str(row.get("screen_name") or row.get("name"))
    if not uid and not author:
        return None
    intro = strip_or_empty(row.get("description") or row.get("intro"))
    followers = to_int(row.get("followers_count"))
    title = author or uid
    if followers:
        title = f"{author} · 粉丝 {_fmt_num(followers)}"
    return {
        "code": code,
        "name": name,
        "article_id": uid,
        "title": title,
        "summary": intro[:200],
        "content": intro,
        "published_at": "",
        "url": user_profile_url(row, uid),
        "source": SOURCE,
        "channel": channel,
        "author": author,
        "author_id": uid,
        "media_name": author,
        "followers_count": followers,
        "friends_count": to_int(row.get("friends_count")),
        "status_count": to_int(row.get("status_count")),
        "stocks_count": to_int(row.get("stocks_count")),
        "verified": bool(row.get("verified")),
    }


def strip_or_empty(value: Any) -> str:
    from company.emotion.xueqiu._common import strip_html

    return strip_html(safe_str(value))


def _normalize_popstock(row: dict[str, Any], *, code: str) -> dict[str, Any] | None:
    symbol = safe_str(row.get("code") or row.get("symbol"))
    name = safe_str(row.get("name"))
    if not symbol and not name:
        return None
    stock = normalize_code(symbol) or symbol
    title = f"{name or stock} {stock}".strip()
    return {
        "code": stock,
        "name": name,
        "symbol": symbol,
        "title": title,
        "summary": title,
        "price": to_float(row.get("current") or row.get("close")),
        "change_pct": to_float(row.get("percentage") or row.get("percent")),
        "url": stock_page_url(symbol),
        "source": SOURCE,
        "channel": CHANNEL_SCORES,
        "related_of": code,
    }


def fetch_followers(
    code_or_name: str,
    *,
    max_pages: int = 1,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """拉关注该股的用户列表。"""
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    name = resolved["name"]
    symbol = resolved.get("symbol") or xq_symbol(code or code_or_name)
    page_url = stock_page_url(symbol)
    if not symbol:
        return empty_pack(channel=CHANNEL_FANS, error="缺少股票代码", page=page_url)
    items: list[dict[str, Any]] = []
    total = 0
    page = 1
    limit = max(1, min(int(max_pages), MAX_PAGES))
    size = max(1, min(int(page_size), 50))
    while page <= limit:
        try:
            payload = query_followers(symbol, page=page, page_size=size)
        except Exception as exc:  # noqa: BLE001
            logger.warning("雪球关注列表失败 %s page=%s: %s", symbol, page, exc)
            if page == 1:
                return empty_pack(
                    code=code,
                    name=name,
                    symbol=symbol,
                    channel=CHANNEL_FANS,
                    error=str(exc),
                    page=page_url,
                )
            break
        rows = payload.get("followers") or payload.get("friends") or payload.get("list") or []
        total = to_int(payload.get("count") or payload.get("totalcount"), total)
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _normalize_user(row, code=code, name=name, channel=CHANNEL_FANS)
            if item:
                items.append(item)
        if len(rows) < size:
            break
        page += 1
        if page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)
    return {
        "code": code,
        "name": name,
        "symbol": symbol,
        "source": SOURCE,
        "channel": CHANNEL_FANS,
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": page_url,
        "follower_count": total or len(items),
    }


def fetch_scores(code_or_name: str) -> dict[str, Any]:
    """个股社区快照：关注人数 / 现价 / 热门用户 / 粉丝同时关注。"""
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    name = resolved["name"]
    symbol = resolved.get("symbol") or xq_symbol(code or code_or_name)
    page = stock_page_url(symbol)
    if not symbol:
        return empty_pack(channel=CHANNEL_SCORES, error="缺少股票代码", page=page)
    try:
        quote = query_quote(symbol)
        fans = query_followers(symbol, page=1, page_size=1)
        hot_users_raw = query_hot_users(symbol, count=10)
        pop_raw = query_popstocks(symbol, count=8)
    except Exception as exc:  # noqa: BLE001
        logger.warning("雪球社区快照失败 %s: %s", symbol, exc)
        return empty_pack(
            code=code,
            name=name,
            symbol=symbol,
            channel=CHANNEL_SCORES,
            error=str(exc),
            page=page,
        )
    name = safe_str(quote.get("name")) or name
    follower_count = to_int(fans.get("count") or fans.get("totalcount"))
    price = to_float(quote.get("current"))
    change = to_float(quote.get("percent"))
    title = f"关注 {_fmt_num(follower_count)} · 现价 {_fmt_num(price)} · {change}%"
    if change is None:
        title = f"关注 {_fmt_num(follower_count)} · 现价 {_fmt_num(price)}"
    hot_users = [
        item
        for row in hot_users_raw
        if (item := _normalize_user(row, code=code, name=name, channel=CHANNEL_SCORES))
    ]
    popstocks = [
        item for row in pop_raw if (item := _normalize_popstock(row, code=code))
    ]
    item = {
        "code": code,
        "name": name,
        "symbol": symbol,
        "title": title,
        "summary": title,
        "published_at": fmt_dt(quote.get("timestamp") or quote.get("time")),
        "url": page,
        "source": SOURCE,
        "channel": CHANNEL_SCORES,
        "media_name": "雪球关注",
        "price": price,
        "change_pct": change,
        "follower_count": follower_count,
        "turnover_rate": to_float(quote.get("turnover_rate")),
        "volume": to_float(quote.get("volume")),
        "market_capital": to_float(quote.get("market_capital")),
    }
    return {
        "code": code,
        "name": name,
        "symbol": symbol,
        "source": SOURCE,
        "channel": CHANNEL_SCORES,
        "count": 1,
        "total": 1,
        "items": [item],
        "page": page,
        "title": title,
        "follower_count": follower_count,
        "price": price,
        "change_pct": change,
        "hot_users": hot_users,
        "popstocks": popstocks,
        "trade_date": item["published_at"],
    }
