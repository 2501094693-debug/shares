"""同花顺个股社区：模拟手机客户端拉讨论流（含评论预览）。

    GET https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/index
    GET https://c.10jqka.com.cn/lgt/post/open/api/forum/content/v1/hot_feed
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

from core.codes import normalize_code, safe_str

from company.emotion.tonghuashun._common import (
    CHANNEL_POSTS,
    HOT_FEED_API,
    MOBILE_PAGE_SIZE,
    RECENT_API,
    REQUEST_PAUSE_SEC,
    SOURCE,
    comments_from_feed,
    date_range,
    dedupe,
    empty_pack,
    in_range,
    map_choice,
    mobile_data,
    mobile_page_url,
    normalize_feed_item,
    parse_day,
    query_forum_index,
    resolve_keyword,
    ths_market,
    to_int,
)

logger = logging.getLogger(__name__)

MAX_PAGES = 20

KINDS: dict[str, str] = {
    "user": "user",
    "posts": "user",
    "guba": "user",
    "论股堂": "user",
    "讨论": "user",
    "all": "user",
    "全部": "user",
}

SORTS: dict[str, str] = {
    "hot": "hot",
    "推荐": "hot",
    "recommend": "hot",
    "time": "time",
    "最新": "time",
    "发帖": "time",
    "publish": "time",
    "reply": "reply",
    "回复": "reply",
}


def resolve_kind(kind: str | None) -> str:
    return map_choice(kind, KINDS, "user", "kind")


def resolve_sort(sort: str | None) -> str:
    return map_choice(sort, SORTS, "hot", "sort")


def query_page(
    code: str,
    *,
    kind: str = "user",
    page: int = 1,
    first: bool = False,
    sort: str = "hot",
    last_score: Any = None,
    last_publish_time: Any = None,
    market_id: str = "",
) -> dict[str, Any]:
    """论股堂单页原始 JSON（手机推荐流）。"""
    del kind, page, first
    stock = normalize_code(code) or safe_str(code)
    return _query_mobile_page(
        stock,
        sort=sort,
        last_score=last_score,
        last_publish_time=last_publish_time,
        market_id=market_id,
    )


def _query_mobile_page(
    code: str,
    *,
    sort: str = "hot",
    last_score: Any = None,
    last_publish_time: Any = None,
    market_id: str = "",
) -> dict[str, Any]:
    mid = safe_str(market_id) or ths_market(code) or "17"
    if sort in {"time", "reply"} and last_score in {None, ""} and not last_publish_time:
        recent = _query_recent(code, sort=sort, market_id=mid)
        feed = recent.get("feed") if isinstance(recent.get("feed"), list) else []
        if feed:
            recent["_via"] = "recent"
            return recent
    params: dict[str, Any] = {
        "code": code,
        "page": 1,
        "pageSize": MOBILE_PAGE_SIZE,
        "marketId": mid,
    }
    if last_score not in {None, ""}:
        params["lastScore"] = last_score
    if last_publish_time not in {None, "", 0, "0"}:
        params["lastPublishTime"] = last_publish_time
    data = mobile_data(HOT_FEED_API, params=params, code=code)
    data["_via"] = "hot_feed"
    return data


def _query_recent(code: str, *, sort: str, market_id: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "code": code,
        "page": 1,
        "pageSize": MOBILE_PAGE_SIZE,
        "pid": 0,
        "time": 0,
        "sort": "reply" if sort == "reply" else "publish",
        "marketId": market_id,
    }
    try:
        return mobile_data(RECENT_API, params=params, code=code)
    except Exception as exc:  # noqa: BLE001
        logger.info("同花顺 latest 列表空/失败 %s: %s", code, exc)
        return {}


def fetch_posts(
    code_or_name: str,
    *,
    kind: str | None = "user",
    sort: str | None = "hot",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    max_pages: int = 3,
    with_replies: bool = False,
    max_reply_posts: int = 10,
    max_reply_pages: int = 1,
) -> dict[str, Any]:
    """按股票拉同花顺手机社区讨论。"""
    del max_reply_pages
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    name = resolved["name"]
    api_sort = resolve_sort(sort)
    resolve_kind(kind)
    page_url = mobile_page_url(code)
    if not code:
        return empty_pack(
            code=code,
            name=name,
            keyword=resolved["keyword"],
            channel=CHANNEL_POSTS,
            error="缺少股票代码",
            page=page_url,
            kind="user",
            sort=api_sort,
        )

    forum: dict[str, Any] = {}
    try:
        forum = query_forum_index(code)
    except Exception as exc:  # noqa: BLE001
        logger.info("同花顺讨论页初始化失败 %s: %s", code, exc)
    forum_block = forum.get("forum") if isinstance(forum.get("forum"), dict) else {}
    name = safe_str(forum_block.get("name")) or name
    market_id = safe_str(forum_block.get("market_id") or forum_block.get("market")) or ths_market(code)

    start_d, end_d = date_range(start, end, days)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    last_score: Any = None
    last_publish_time: Any = None
    via = ""
    has_more = True
    limit = max(1, min(int(max_pages), MAX_PAGES))
    raw_feeds: list[dict[str, Any]] = []

    for page in range(1, limit + 1):
        try:
            payload = _query_mobile_page(
                code,
                sort=api_sort,
                last_score=last_score,
                last_publish_time=last_publish_time,
                market_id=market_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("同花顺论股堂失败 %s page=%s: %s", code, page, exc)
            if page == 1:
                return empty_pack(
                    code=code,
                    name=name,
                    keyword=resolved["keyword"],
                    channel=CHANNEL_POSTS,
                    error=str(exc),
                    page=page_url,
                    kind="user",
                    sort=api_sort,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        via = safe_str(payload.get("_via")) or via
        feed = payload.get("feed") if isinstance(payload.get("feed"), list) else []
        mapped = []
        for row in feed:
            if not isinstance(row, dict):
                continue
            item = normalize_feed_item(row, code=code, name=name, kind="user")
            if not item:
                continue
            mapped.append(item)
            raw_feeds.append(row)
        page_items = []
        for item in mapped:
            pid = safe_str(item.get("post_id"))
            if pid and pid in seen:
                continue
            if pid:
                seen.add(pid)
            page_items.append(item)
        has_more = bool(payload.get("has_more") if "has_more" in payload else len(page_items) > 0)
        last_score = payload.get("last_score")
        if page_items:
            last_row = feed[-1] if feed else {}
            info = last_row.get("info") if isinstance(last_row, dict) else {}
            last_publish_time = (info or {}).get("ctime") or last_publish_time

        if not page_items:
            break
        if via == "recent":
            for item in page_items:
                if in_range(item, start_d, end_d):
                    items.append(item)
            break
        oldest_on_page = None
        for item in page_items:
            day = parse_day(item.get("published_at"))
            if day and (oldest_on_page is None or day < oldest_on_page):
                oldest_on_page = day
            if in_range(item, start_d, end_d):
                items.append(item)
        if start_d and oldest_on_page and oldest_on_page < start_d:
            break
        if not has_more:
            break
        if last_score in {None, ""} and not last_publish_time:
            break
        if page < limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = dedupe(items)
    if with_replies:
        items = _attach_replies(items, raw_feeds=raw_feeds, max_posts=max_reply_posts)

    rank = forum.get("stock_rank") if isinstance(forum.get("stock_rank"), dict) else {}
    return {
        "code": code,
        "name": name,
        "keyword": resolved["keyword"],
        "kind": "user",
        "sort": api_sort,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": CHANNEL_POSTS,
        "count": len(items),
        "total": len(items),
        "items": items,
        "page": page_url,
        "fid": to_int(forum_block.get("fid")),
        "market_id": market_id,
        "via": via or "hot_feed",
        "rank": to_int(rank.get("rank")),
        "rank_amount": to_int(rank.get("rank_amount")),
        "rank_change": to_int(rank.get("rank_change")),
    }


def _attach_replies(
    items: list[dict[str, Any]],
    *,
    raw_feeds: list[dict[str, Any]],
    max_posts: int,
) -> list[dict[str, Any]]:
    by_pid: dict[str, dict[str, Any]] = {}
    for row in raw_feeds:
        info = row.get("info") if isinstance(row, dict) else None
        pid = safe_str((info or {}).get("id") if isinstance(info, dict) else "")
        if pid:
            by_pid[pid] = row
    budget = max(0, int(max_posts))
    attached = 0
    for item in items:
        if attached >= budget:
            break
        pid = safe_str(item.get("post_id"))
        preview = comments_from_feed(
            by_pid.get(pid) or {},
            code=item.get("code") or "",
            post_id=pid,
            url=safe_str(item.get("url")),
        )
        item["replies"] = preview
        attached += 1
    return items
