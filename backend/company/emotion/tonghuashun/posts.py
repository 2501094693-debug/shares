"""同花顺个股社区：模拟手机客户端拉讨论流（含评论预览）。

    GET https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/index
    GET https://c.10jqka.com.cn/lgt/post/open/api/forum/post/v2/recent
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
    RECENT_PAGE_SIZE,
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
    "热门": "hot",
    "recommend": "hot",
    "time": "time",
    "最新": "time",
    "最新发布": "time",
    "发帖": "time",
    "publish": "time",
    "reply": "reply",
    "最新回复": "reply",
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
    recent_pid: Any = None,
) -> dict[str, Any]:
    mid = safe_str(market_id) or ths_market(code) or "17"
    if sort in {"time", "reply"}:
        recent = _query_recent(
            code,
            sort=sort,
            market_id=mid,
            pid=recent_pid,
        )
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


def _query_recent(
    code: str,
    *,
    sort: str,
    market_id: str,
    pid: Any = None,
) -> dict[str, Any]:
    api_sort = "reply" if sort == "reply" else "publish"
    # page=1 只回 8 条且忽略 pid。page>=2、time=0、pid=上一页最后一条，才是下一页。
    params: dict[str, Any] = {
        "code": code,
        "page": 2,
        "page_size": RECENT_PAGE_SIZE,
        "pid": 0 if pid in {None, ""} else pid,
        "time": 0,
        "sort": api_sort,
        "market_id": market_id,
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
    recent_pid: Any = 0
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
                recent_pid=recent_pid,
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
            oldest_on_page = None
            for item in page_items:
                day = parse_day(item.get("published_at"))
                if day and (oldest_on_page is None or day < oldest_on_page):
                    oldest_on_page = day
                if in_range(item, start_d, end_d):
                    items.append(item)
            sent_pid = recent_pid
            recent_pid = _recent_cursor(feed)
            if start_d and oldest_on_page and oldest_on_page < start_d:
                break
            if recent_pid in {None, "", 0, "0"} or str(recent_pid) == str(sent_pid):
                break
            if page < limit:
                time.sleep(REQUEST_PAUSE_SEC)
            continue
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

    items = _order_posts(dedupe(items), api_sort, via)
    if with_replies:
        items = _attach_replies(items, raw_feeds=raw_feeds, max_posts=max_reply_posts)

    rank = forum.get("stock_rank") if isinstance(forum.get("stock_rank"), dict) else {}
    vote = _vote_from_forum(forum) if api_sort in {"time", "reply"} else None
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
        "vote": vote,
    }


def _recent_cursor(feed: list[Any]) -> Any:
    """下一页用上一页最后一条的 pid。带上发帖时间时接口会返回空。"""
    if not feed or not isinstance(feed[-1], dict):
        return 0
    last = feed[-1]
    info = last.get("info") if isinstance(last.get("info"), dict) else {}
    return last.get("pid") or last.get("id") or info.get("id") or 0


def _vote_from_forum(forum: dict[str, Any]) -> dict[str, Any] | None:
    """讨论页顶部的投票条，插在最新列表第一条后面。"""
    components = forum.get("components") if isinstance(forum.get("components"), dict) else {}
    tabs = components.get("tab_configs") if isinstance(components.get("tab_configs"), list) else []
    for tab in tabs:
        blocks = tab.get("components") if isinstance(tab, dict) else None
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict) or safe_str(block.get("type")).upper() != "VOTE":
                continue
            data = block.get("data") if isinstance(block.get("data"), dict) else {}
            detail = data.get("vote_detail") if isinstance(data.get("vote_detail"), dict) else {}
            title = safe_str(detail.get("title"))
            options = detail.get("option_list") if isinstance(detail.get("option_list"), list) else []
            if not title:
                continue
            return {
                "title": title,
                "total": to_int(detail.get("total_count")),
                "options": [
                    {"text": safe_str(opt.get("content")), "count": to_int(opt.get("vote_count"))}
                    for opt in options
                    if isinstance(opt, dict) and safe_str(opt.get("content"))
                ],
            }
    return None


def _order_posts(items: list[dict[str, Any]], sort: str, via: str) -> list[dict[str, Any]]:
    """热门保持推荐流顺序。最新发布、最新回复在推荐流回退时按时间重排。"""
    if sort == "hot" or via == "recent":
        return items

    def stamp(row: dict[str, Any]) -> str:
        if sort == "reply":
            return safe_str(row.get("replied_at") or row.get("published_at"))
        return safe_str(row.get("published_at"))

    return sorted(items, key=stamp, reverse=True)


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
        pid = pid or safe_str(row.get("pid") or row.get("id") if isinstance(row, dict) else "")
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
