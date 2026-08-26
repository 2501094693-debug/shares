"""雪球社区共用：会话走 ``company.news.xueqiu``，这里补社区字段和频道名。

雪球没有文档化的公开社区 API。讨论 / 搜索 / 正文 / 评论 / 热股都是官网前端 XHR，
必须带 ``xq_a_token``。token 优先 ``XUEQIU_TOKEN`` / ``XUEQIU_COOKIES``，否则预热首页。
"""

from __future__ import annotations

from typing import Any

from core.codes import safe_str

from company.news.xueqiu._common import (  # noqa: F401
    API_HOST,
    REQUEST_PAUSE_SEC,
    SOURCE,
    STOCK_HOST,
    TZ_CN,
    WEB_HOST,
    article_url,
    cli_print,
    current_token,
    date_range,
    dedupe,
    empty_pack,
    fmt_dt,
    get_payload,
    headers_for,
    in_range,
    map_choice,
    normalize_status,
    oldest_day,
    print_items,
    query_quote,
    resolve_keyword,
    search_page_url,
    set_token,
    status_id_of,
    stock_page_url,
    strip_html,
    xq_symbol,
)

CHANNEL_POSTS = "xq_post"
CHANNEL_ARTICLE = "xq_article"
CHANNEL_REPLY = "xq_reply"
CHANNEL_SEARCH = "xq_search"
CHANNEL_RANK = "xq_rank"
CHANNEL_SCORES = "xq_scores"
CHANNEL_HOT = "xq_hot"
CHANNEL_FANS = "xq_fans"

COMMENTS_API = f"{API_HOST}/statuses/comments.json"
HOT_STOCK_API = f"{STOCK_HOST}/v5/stock/hot_stock/list.json"
HOT_POST_API = f"{API_HOST}/statuses/hot/listV2.json"
FOLLOWERS_API = f"{API_HOST}/friendships/stockfollowers.json"
POFRIENDS_API = f"{WEB_HOST}/recommend/pofriends.json"
HOT_USER_API = f"{WEB_HOST}/recommend/user/stock_hot_user.json"
POPSTOCKS_API = f"{WEB_HOST}/stock/portfolio/popstocks.json"


def to_int(value: Any, default: int = 0) -> int:
    text = safe_str(value)
    if not text:
        return default
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return default


def user_profile_url(user: dict[str, Any] | None, user_id: str = "") -> str:
    block = user if isinstance(user, dict) else {}
    profile = safe_str(block.get("profile"))
    if profile:
        if profile.lower().startswith("http"):
            return profile
        return WEB_HOST + (profile if profile.startswith("/") else "/" + profile)
    uid = user_id or safe_str(block.get("id"))
    return f"{WEB_HOST}/{uid}" if uid else ""


def community_item(item: dict[str, Any] | None, *, channel: str = "") -> dict[str, Any] | None:
    """新闻层 status 字段对齐到社区：``post_id`` / ``comment_count`` / ``author_id``。"""
    if not item:
        return None
    out = dict(item)
    sid = safe_str(item.get("status_id") or item.get("article_id") or item.get("post_id"))
    out["post_id"] = sid
    out["article_id"] = sid or safe_str(item.get("article_id"))
    out["status_id"] = sid or safe_str(item.get("status_id"))
    out["comment_count"] = to_int(item.get("comment_count") or item.get("reply_count"))
    out["author_id"] = safe_str(item.get("author_id") or item.get("user_id"))
    if not out.get("content"):
        out["content"] = safe_str(item.get("summary"))
    if channel:
        out["channel"] = channel
    return out
