"""雪球帖子正文：``statuses/show.json``，可附带评论。"""

from __future__ import annotations

from typing import Any

from core.codes import safe_str

from company.emotion.xueqiu._common import (
    CHANNEL_ARTICLE,
    community_item,
    empty_pack,
    status_id_of,
)
from company.news.platforms.xueqiu.article import fetch_article as fetch_status
from company.news.platforms.xueqiu.article import query_show


def fetch_article(
    post_ref: str,
    *,
    code: str = "",
    with_replies: bool = False,
    max_reply_pages: int = 3,
) -> dict[str, Any]:
    """拉一篇雪球帖子 / 专栏正文。``post_ref`` 可以是状态 id 或 URL。"""
    sid = status_id_of(post_ref) or safe_str(post_ref)
    if not sid:
        return empty_pack(channel=CHANNEL_ARTICLE, error="缺少帖子 ID", code=code)
    pack = fetch_status(sid)
    item = community_item(pack, channel=CHANNEL_ARTICLE) or pack
    if code and not item.get("code"):
        item["code"] = code
    if with_replies and not item.get("error"):
        from company.emotion.xueqiu.replies import fetch_replies

        replies = fetch_replies(sid, code=item.get("code") or code, max_pages=max_reply_pages)
        item["replies"] = replies.get("items") or []
        item["reply_count"] = replies.get("count") or 0
        item["reply_total"] = replies.get("total") or 0
        if replies.get("error"):
            item["replies_error"] = replies["error"]
        if not item.get("comment_count"):
            item["comment_count"] = replies.get("total") or replies.get("count") or 0
    return item
