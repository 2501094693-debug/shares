"""股吧帖子正文：详情页 ``.newstitle`` / ``.newstext`` / ``.xeditor_content``。

列表通常只有摘要。把 ``post_id`` 或 ``news,{code},{id}.html`` 丢进来即可。

    https://guba.eastmoney.com/news,600519,1759863886.html
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.codes import normalize_code, safe_str
from core.http import browser_get

from company.emotion.eastmoney._common import (
    CHANNEL_ARTICLE,
    SOURCE,
    empty_pack,
    fmt_dt,
    headers_for,
    list_page_url,
    parse_post_ref,
    post_url,
    strip_html,
    to_int,
)

logger = logging.getLogger(__name__)

_TITLE_RE = re.compile(r'class="newstitle"[^>]*>([\s\S]*?)</div>', re.I)
_AUTHOR_RE = re.compile(r'class="name"[^>]*>([\s\S]*?)</a>', re.I)
_TIME_RE = re.compile(r'class="time"[^>]*>([\s\S]*?)</div>', re.I)
_ADDR_RE = re.compile(r'class="address"[^>]*>([\s\S]*?)</div>', re.I)
_LIKE_RE = re.compile(r'class="likemodule"[\s\S]*?</em>(\d+)', re.I)
_REPLY_RE = re.compile(r'class="replybtn"[\s\S]*?<span>(\d+)</span>', re.I)


def _extract_div_by_class(html: str, class_name: str) -> str:
    pattern = rf'<div[^>]*class="[^"]*{re.escape(class_name)}[^"]*"[^>]*>'
    match = re.search(pattern, html, re.I)
    if not match:
        return ""
    start = match.end()
    depth = 1
    i = start
    lower = html.lower()
    while i < len(html) and depth:
        nxt_open = lower.find("<div", i)
        nxt_close = lower.find("</div", i)
        if nxt_close < 0:
            return html[start:]
        if 0 <= nxt_open < nxt_close:
            depth += 1
            i = nxt_open + 4
        else:
            depth -= 1
            if depth == 0:
                return html[start:nxt_close]
            i = nxt_close + 5
    return html[start:]


def fetch_article(
    post_ref: str,
    *,
    code: str = "",
    with_replies: bool = False,
    max_reply_pages: int = 3,
) -> dict[str, Any]:
    """拉一篇股吧帖子正文。``post_ref`` 可以是 ID 或完整 URL。"""
    stock, post_id = parse_post_ref(post_ref, default_code=code)
    stock = normalize_code(stock) or stock
    url = post_url(stock, post_id)
    if not post_id or not url:
        return empty_pack(channel=CHANNEL_ARTICLE, error="缺少帖子 ID", code=stock)
    try:
        resp = browser_get(
            url,
            headers=headers_for(list_page_url(stock) if stock else "https://guba.eastmoney.com/"),
            timeout=25,
        )
        resp.raise_for_status()
        html = resp.text or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("股吧正文失败 %s: %s", url, exc)
        return empty_pack(channel=CHANNEL_ARTICLE, error=str(exc), page=url, code=stock)

    title_m = _TITLE_RE.search(html)
    author_m = _AUTHOR_RE.search(html)
    time_m = _TIME_RE.search(html)
    addr_m = _ADDR_RE.search(html)
    title = strip_html(title_m.group(1) if title_m else "")
    author = strip_html(author_m.group(1) if author_m else "")
    published = fmt_dt(strip_html(time_m.group(1) if time_m else ""))
    body_html = _extract_div_by_class(html, "xeditor_content") or _extract_div_by_class(html, "newstext")
    text = strip_html(body_html)
    if not title:
        tm = re.search(r"<title>([^<]+)</title>", html, re.I)
        if tm:
            title = re.sub(r"[_—\-].*$", "", strip_html(tm.group(1))).strip()
    if not title and not text:
        return empty_pack(
            channel=CHANNEL_ARTICLE,
            error="页面无正文",
            page=url,
            code=stock,
            article_id=post_id,
        )

    like_m = _LIKE_RE.search(html)
    reply_m = _REPLY_RE.search(html)
    pack = {
        "code": stock,
        "name": "",
        "article_id": post_id,
        "post_id": post_id,
        "title": title,
        "summary": text[:200],
        "content": text,
        "published_at": published,
        "url": url,
        "source": SOURCE,
        "channel": CHANNEL_ARTICLE,
        "author": author,
        "media_name": author,
        "like_count": to_int(like_m.group(1) if like_m else 0),
        "comment_count": to_int(reply_m.group(1) if reply_m else 0),
        "ip": strip_html(addr_m.group(1) if addr_m else ""),
        "page": url,
        "count": 1 if text or title else 0,
        "items": [],
    }
    if with_replies:
        from company.emotion.eastmoney.replies import fetch_replies

        replies = fetch_replies(post_id, code=stock, max_pages=max_reply_pages)
        pack["replies"] = replies.get("items") or []
        pack["reply_count"] = replies.get("count") or 0
        pack["reply_total"] = replies.get("total") or 0
        if replies.get("error"):
            pack["replies_error"] = replies["error"]
    return pack
