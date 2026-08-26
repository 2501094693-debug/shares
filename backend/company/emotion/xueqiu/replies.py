"""雪球帖子评论：``statuses/comments.json``。

    GET https://api.xueqiu.com/statuses/comments.json
    - id     状态 id
    - count  每页条数
    - page
    - asc    false=最新
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.codes import safe_str

from company.emotion.xueqiu._common import (
    CHANNEL_REPLY,
    COMMENTS_API,
    REQUEST_PAUSE_SEC,
    SOURCE,
    WEB_HOST,
    article_url,
    empty_pack,
    fmt_dt,
    get_payload,
    headers_for,
    status_id_of,
    strip_html,
    to_int,
    user_profile_url,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 20
MAX_PAGES = 20


def query_page(
    status_id: str,
    *,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    asc: bool = False,
) -> dict[str, Any]:
    """帖子评论单页原始 JSON。"""
    payload = get_payload(
        COMMENTS_API,
        params={
            "id": safe_str(status_id),
            "count": max(1, min(int(page_size), 20)),
            "page": max(1, int(page)),
            "asc": "true" if asc else "false",
        },
        headers=headers_for(article_url(status_id) or WEB_HOST + "/", origin=WEB_HOST),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def _normalize_reply(
    row: dict[str, Any],
    *,
    code: str,
    status_id: str,
    parent_id: str = "",
) -> dict[str, Any] | None:
    reply_id = safe_str(row.get("id"))
    text = strip_html(safe_str(row.get("text") or row.get("description")))
    if not reply_id and not text:
        return None
    user = row.get("user") if isinstance(row.get("user"), dict) else {}
    author = safe_str(user.get("screen_name"))
    uid = safe_str(user.get("id") or row.get("user_id"))
    url = article_url(status_id)
    if reply_id and url:
        url = f"{url}#{reply_id}"
    parent = parent_id or safe_str(row.get("in_reply_to_comment_id") or row.get("root_reply_to_cid"))
    if parent in {"0", "-1"}:
        parent = ""
    reply_to = safe_str(row.get("reply_screenName"))
    return {
        "code": code,
        "article_id": reply_id,
        "post_id": status_id,
        "status_id": status_id,
        "reply_id": reply_id,
        "parent_id": parent,
        "title": text[:80] or reply_id,
        "summary": text[:200],
        "content": text,
        "published_at": fmt_dt(row.get("created_at") or row.get("edited_at")),
        "url": url,
        "source": SOURCE,
        "channel": CHANNEL_REPLY,
        "author": author,
        "author_id": uid,
        "media_name": author,
        "user_url": user_profile_url(user, uid),
        "like_count": to_int(row.get("like_count")),
        "comment_count": to_int(row.get("reply_count") or row.get("comment_reply_count")),
        "reply_to": reply_to,
        "ip": safe_str(row.get("ip_location")),
        "is_child": bool(parent),
    }


def _flatten(row: dict[str, Any], *, code: str, status_id: str) -> list[dict[str, Any]]:
    parent = _normalize_reply(row, code=code, status_id=status_id)
    out: list[dict[str, Any]] = []
    if parent:
        out.append(parent)
    children = row.get("child_comments") or []
    if not isinstance(children, list):
        return out
    parent_id = parent["reply_id"] if parent else ""
    for child in children:
        if not isinstance(child, dict):
            continue
        item = _normalize_reply(child, code=code, status_id=status_id, parent_id=parent_id)
        if item:
            out.append(item)
    return out


def fetch_replies(
    post_ref: str,
    *,
    code: str = "",
    max_pages: int = 3,
    page_size: int = PAGE_SIZE,
    asc: bool = False,
) -> dict[str, Any]:
    """拉一篇雪球帖下的评论（含 ``child_comments``）。"""
    status_id = status_id_of(post_ref) or safe_str(post_ref)
    url = article_url(status_id)
    if not status_id:
        return empty_pack(channel=CHANNEL_REPLY, error="缺少帖子 ID", code=code, page=url)

    items: list[dict[str, Any]] = []
    total = 0
    page = 1
    limit = max(1, min(int(max_pages), MAX_PAGES))
    size = max(1, min(int(page_size), PAGE_SIZE))
    while page <= limit:
        try:
            payload = query_page(status_id, page=page, page_size=size, asc=asc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("雪球评论失败 %s page=%s: %s", status_id, page, exc)
            if page == 1:
                return empty_pack(
                    channel=CHANNEL_REPLY,
                    error=str(exc),
                    code=code,
                    page=url,
                    article_id=status_id,
                    post_id=status_id,
                )
            break
        rows = payload.get("comments") or payload.get("list") or []
        total = to_int(payload.get("count") or payload.get("total"), total)
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            if isinstance(row, dict):
                items.extend(_flatten(row, code=code, status_id=status_id))
        max_page = to_int(payload.get("maxPage") or payload.get("max_page"))
        if max_page and page >= max_page:
            break
        if len(rows) < size:
            break
        page += 1
        if page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    return {
        "code": code,
        "article_id": status_id,
        "post_id": status_id,
        "status_id": status_id,
        "title": "",
        "url": url,
        "source": SOURCE,
        "channel": CHANNEL_REPLY,
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": url,
    }
