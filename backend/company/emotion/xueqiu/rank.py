"""雪球热股榜 + 全站热帖。

热股：
    GET https://stock.xueqiu.com/v5/stock/hot_stock/list.json
    type  全球 10 / 美股 11 / 沪深 12 / 港股 13 / 关注 20

热帖：
    GET https://api.xueqiu.com/statuses/hot/listV2.json
    since_id=-1，下一页用 next_max_id
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.codes import normalize_code, safe_str
from core.fmt import to_float

from company.emotion.xueqiu._common import (
    CHANNEL_HOT,
    CHANNEL_RANK,
    HOT_POST_API,
    HOT_STOCK_API,
    REQUEST_PAUSE_SEC,
    SOURCE,
    WEB_HOST,
    community_item,
    empty_pack,
    get_payload,
    headers_for,
    map_choice,
    normalize_status,
    resolve_keyword,
    stock_page_url,
    to_int,
    xq_symbol,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 50
HOT_POST_SIZE = 15

MARKETS: dict[str, str] = {
    "cn": "12",
    "沪深": "12",
    "a": "12",
    "12": "12",
    "us": "11",
    "美股": "11",
    "11": "11",
    "hk": "13",
    "港股": "13",
    "13": "13",
    "global": "10",
    "all": "10",
    "全球": "10",
    "10": "10",
    "follow": "20",
    "watch": "20",
    "关注": "20",
    "20": "20",
}

MARKET_LABELS: dict[str, str] = {
    "10": "全球",
    "11": "美股",
    "12": "沪深",
    "13": "港股",
    "20": "关注",
}


def resolve_market(market: str | None) -> str:
    return map_choice(market, MARKETS, "12", "market")


def rank_page_url(market: str = "12") -> str:
    return f"{WEB_HOST}/hq" if resolve_market(market) else WEB_HOST + "/"


def query_hot_page(
    *,
    market: str = "cn",
    page: int = 1,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """热股榜单页原始 JSON。"""
    payload = get_payload(
        HOT_STOCK_API,
        params={
            "type": resolve_market(market),
            "size": max(1, min(int(page_size), 100)),
            "page": max(1, int(page)),
        },
        headers=headers_for(WEB_HOST + "/", origin=WEB_HOST),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def query_hot_posts_page(*, size: int = HOT_POST_SIZE, max_id: int = -1) -> dict[str, Any]:
    """全站热帖单页原始 JSON。"""
    payload = get_payload(
        HOT_POST_API,
        params={"size": max(1, min(int(size), 20)), "since_id": -1, "max_id": int(max_id)},
        headers=headers_for(WEB_HOST + "/", origin=WEB_HOST),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def _normalize_hot_stock(
    row: dict[str, Any],
    *,
    market: str,
    rank_n: int,
) -> dict[str, Any]:
    symbol = safe_str(row.get("symbol") or row.get("code"))
    code = normalize_code(symbol) or safe_str(row.get("code"))
    name = safe_str(row.get("name"))
    rank_n = to_int(row.get("rank") or rank_n)
    value = to_float(row.get("value"))
    price = to_float(row.get("current"))
    change = to_float(row.get("percent"))
    title = f"{rank_n}  {name or symbol} {code or symbol}".strip()
    return {
        "code": code,
        "name": name,
        "symbol": symbol,
        "rank": rank_n,
        "rank_change": to_int(row.get("rank_change")),
        "value": value,
        "increment": to_int(row.get("increment")),
        "price": price,
        "change_pct": change,
        "exchange": safe_str(row.get("exchange")),
        "market": market,
        "title": title,
        "summary": title,
        "published_at": "",
        "url": stock_page_url(symbol),
        "source": SOURCE,
        "channel": CHANNEL_RANK,
        "media_name": f"热度{int(value) if value is not None else rank_n}",
    }


def fetch_hot_list(
    *,
    market: str = "cn",
    page: int = 1,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """全市场当前热股榜。"""
    mkt = resolve_market(market)
    page_url = rank_page_url(mkt)
    try:
        payload = query_hot_page(market=mkt, page=page, page_size=page_size)
    except Exception as exc:  # noqa: BLE001
        logger.warning("雪球热股榜失败 market=%s: %s", mkt, exc)
        return empty_pack(channel=CHANNEL_RANK, error=str(exc), page=page_url, market=mkt)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    rows = (data.get("items") or data.get("list") or []) if isinstance(data, dict) else []
    if not isinstance(rows, list):
        rows = []
    items: list[dict[str, Any]] = []
    for i, row in enumerate(rows, 1):
        if isinstance(row, dict):
            items.append(_normalize_hot_stock(row, market=mkt, rank_n=i))
    return {
        "code": "",
        "name": "",
        "source": SOURCE,
        "channel": CHANNEL_RANK,
        "kind": "hot_list",
        "market": mkt,
        "market_label": MARKET_LABELS.get(mkt, mkt),
        "count": len(items),
        "total": len(items),
        "items": items,
        "page": page_url,
        "page_no": page,
    }


def fetch_rank(code_or_name: str, *, market: str = "cn") -> dict[str, Any]:
    """个股在热股榜中的名次；未上榜则只回代码和市场。"""
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    name = resolved["name"]
    symbol = resolved.get("symbol") or xq_symbol(code or code_or_name)
    mkt = resolve_market(market)
    page_url = stock_page_url(symbol) if symbol else rank_page_url(mkt)
    if not symbol:
        return empty_pack(channel=CHANNEL_RANK, error="缺少股票代码", page=page_url)
    pack = fetch_hot_list(market=mkt, page=1, page_size=100)
    if pack.get("error"):
        return empty_pack(
            code=code,
            name=name,
            symbol=symbol,
            channel=CHANNEL_RANK,
            error=pack["error"],
            page=page_url,
            market=mkt,
        )
    hit: dict[str, Any] = {}
    for row in pack.get("items") or []:
        if not isinstance(row, dict):
            continue
        if safe_str(row.get("symbol")) == symbol or safe_str(row.get("code")) == code:
            hit = row
            name = name or safe_str(row.get("name"))
            break
    rank_n = to_int(hit.get("rank")) if hit else 0
    title = (
        f"{name or code} 热股第 {rank_n}"
        if rank_n
        else f"{name or code} 未进入{MARKET_LABELS.get(mkt, '')}热股榜"
    )
    return {
        "code": code,
        "name": name,
        "symbol": symbol,
        "rank": rank_n,
        "value": hit.get("value"),
        "rank_change": hit.get("rank_change"),
        "price": hit.get("price"),
        "change_pct": hit.get("change_pct"),
        "source": SOURCE,
        "channel": CHANNEL_RANK,
        "kind": "stock",
        "market": mkt,
        "market_label": MARKET_LABELS.get(mkt, mkt),
        "current": hit,
        "count": 1 if hit else 0,
        "total": 1 if hit else 0,
        "items": [hit] if hit else [],
        "page": page_url,
        "url": page_url,
        "title": title,
    }


def fetch_hot_posts(*, max_pages: int = 1, page_size: int = HOT_POST_SIZE) -> dict[str, Any]:
    """全站热帖时间线。"""
    items: list[dict[str, Any]] = []
    max_id = -1
    page = 1
    limit = max(1, int(max_pages))
    size = max(1, min(int(page_size), 20))
    while page <= limit:
        try:
            payload = query_hot_posts_page(size=size, max_id=max_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("雪球热帖失败 max_id=%s: %s", max_id, exc)
            if page == 1:
                return empty_pack(channel=CHANNEL_HOT, error=str(exc), page=WEB_HOST + "/")
            break
        rows = payload.get("items") or payload.get("list") or []
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            status = row.get("original_status") if isinstance(row.get("original_status"), dict) else row
            item = community_item(normalize_status(status, channel=CHANNEL_HOT), channel=CHANNEL_HOT)
            if item:
                items.append(item)
        nxt = payload.get("next_max_id")
        if nxt in (None, "", -1):
            break
        max_id = to_int(nxt)
        page += 1
        if page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)
    return {
        "code": "",
        "name": "",
        "source": SOURCE,
        "channel": CHANNEL_HOT,
        "kind": "hot_posts",
        "count": len(items),
        "total": len(items),
        "items": items,
        "page": WEB_HOST + "/",
    }
