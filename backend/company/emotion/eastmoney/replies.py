"""股吧帖子回复：``GetData.aspx`` ``reply/api/Reply/ArticleNewReplyList``。

    POST https://guba.eastmoney.com/interface/GetData.aspx
    param   postid={id}&sort=1&sorttype=1&p=1&ps=20
    path    reply/api/Reply/ArticleNewReplyList
    env     2
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.codes import safe_str

from company.emotion.eastmoney._common import (
    CHANNEL_REPLY,
    GETDATA_API,
    REQUEST_PAUSE_SEC,
    SOURCE,
    empty_pack,
    fmt_dt,
    headers_for,
    parse_post_ref,
    post_payload,
    post_url,
    strip_html,
    to_int,
    user_id,
    user_name,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 20
MAX_PAGES = 20
REPLY_PATH = "reply/api/Reply/ArticleNewReplyList"


def query_page(
    post_id: str,
    *,
    code: str = "",
    page: int = 1,
    page_size: int = PAGE_SIZE,
    sort: int = 1,
) -> dict[str, Any]:
    """帖子回复单页原始 JSON。``sort=1`` 为最新。"""
    pid = safe_str(post_id)
    ps = max(1, min(int(page_size), 50))
    payload = post_payload(
        GETDATA_API,
        data={
            "param": f"postid={pid}&sort={int(sort)}&sorttype=1&p={max(1, int(page))}&ps={ps}",
            "path": REPLY_PATH,
            "env": "2",
        },
        headers={
            **headers_for(post_url(code, pid) or "https://guba.eastmoney.com/"),
            "Origin": "https://guba.eastmoney.com",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=25,
    )
    return payload if isinstance(payload, dict) else {}


def _normalize_reply(
    row: dict[str, Any],
    *,
    code: str,
    post_id: str,
    parent_id: str = "",
) -> dict[str, Any] | None:
    reply_id = safe_str(row.get("reply_id"))
    text = strip_html(safe_str(row.get("reply_text")))
    if not reply_id and not text:
        return None
    author = user_name(row, "reply_user")
    url = post_url(code, post_id)
    if reply_id and url:
        url = f"{url}#reply_{reply_id}"
    return {
        "code": code,
        "article_id": reply_id,
        "post_id": post_id,
        "reply_id": reply_id,
        "parent_id": parent_id,
        "title": text[:80] or reply_id,
        "summary": text[:200],
        "content": text,
        "published_at": fmt_dt(row.get("reply_publish_time") or row.get("reply_time")),
        "url": url,
        "source": SOURCE,
        "channel": CHANNEL_REPLY,
        "author": author,
        "author_id": user_id(row, "reply_user") or safe_str(row.get("user_id")),
        "media_name": author,
        "like_count": to_int(row.get("reply_like_count")),
        "comment_count": to_int(row.get("reply_count") or row.get("child_reply_count")),
        "ip": safe_str(row.get("reply_ip_address")),
        "is_child": bool(parent_id),
    }


def _flatten(row: dict[str, Any], *, code: str, post_id: str) -> list[dict[str, Any]]:
    parent = _normalize_reply(row, code=code, post_id=post_id)
    out: list[dict[str, Any]] = []
    if parent:
        out.append(parent)
    children = row.get("child_replys") or row.get("child_replies") or []
    if not isinstance(children, list):
        return out
    parent_id = parent["reply_id"] if parent else ""
    for child in children:
        if not isinstance(child, dict):
            continue
        item = _normalize_reply(child, code=code, post_id=post_id, parent_id=parent_id)
        if item:
            out.append(item)
    return out


def fetch_replies(
    post_ref: str,
    *,
    code: str = "",
    max_pages: int = 3,
    page_size: int = PAGE_SIZE,
    sort: int = 1,
) -> dict[str, Any]:
    """拉一篇帖子下的评论（含一级子评）。"""
    stock, post_id = parse_post_ref(post_ref, default_code=code)
    url = post_url(stock, post_id)
    if not post_id:
        return empty_pack(channel=CHANNEL_REPLY, error="缺少帖子 ID", code=stock, page=url)

    items: list[dict[str, Any]] = []
    total = 0
    page = 1
    limit = max(1, min(int(max_pages), MAX_PAGES))
    while page <= limit:
        try:
            payload = query_page(post_id, code=stock, page=page, page_size=page_size, sort=sort)
        except Exception as exc:  # noqa: BLE001
            logger.warning("股吧回复失败 %s page=%s: %s", post_id, page, exc)
            if page == 1:
                return empty_pack(
                    channel=CHANNEL_REPLY,
                    error=str(exc),
                    code=stock,
                    page=url,
                    article_id=post_id,
                )
            break
        rows = payload.get("re") or []
        total = to_int(payload.get("count") or payload.get("reply_total_count"), total)
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            if isinstance(row, dict):
                items.extend(_flatten(row, code=stock, post_id=post_id))
        if len(rows) < min(page_size, PAGE_SIZE):
            break
        page += 1
        if page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    return {
        "code": stock,
        "article_id": post_id,
        "post_id": post_id,
        "title": "",
        "url": url,
        "source": SOURCE,
        "channel": CHANNEL_REPLY,
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": url,
    }
