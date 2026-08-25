"""雪球帖子 / 新闻正文。

优先 ``statuses/show.json``；失败再抓详情页 ``.article__bd__detail``。
参数可以是状态 id、``/user/status`` 路径或完整 URL。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from core.codes import safe_str

from company.news.xueqiu._common import (
    SHOW_API,
    SOURCE,
    WEB_HOST,
    article_url,
    empty_pack,
    get_html,
    get_payload,
    headers_for,
    normalize_status,
    status_id_of,
    strip_html,
)

logger = logging.getLogger(__name__)

_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_DETAIL_RE = re.compile(
    r'<div[^>]*class=["\'][^"\']*article__bd(?:__detail)?[^"\']*["\'][^>]*>',
    re.I,
)
_STATUS_JSON_RE = re.compile(r"SNOWMAN_STATUS\s*=\s*(\{.*?\});", re.S)
_OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)


def _extract_div(html: str, start_match: re.Match[str]) -> str:
    start = start_match.end()
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


def query_show(status_id: str) -> dict[str, Any]:
    """状态详情原始 JSON。"""
    payload = get_payload(
        SHOW_API,
        params={"id": status_id},
        headers=headers_for(WEB_HOST + "/", origin=WEB_HOST),
        timeout=20,
        fallback=f"{WEB_HOST}/statuses/show.json",
    )
    if isinstance(payload, dict):
        status = payload.get("status")
        if isinstance(status, dict):
            return status
        return payload
    return {}


def _from_status(data: dict[str, Any], url: str) -> dict[str, Any] | None:
    item = normalize_status(data, channel="article")
    if not item:
        return None
    text = strip_html(safe_str(data.get("text") or data.get("description")))
    item["content"] = text
    item["summary"] = text[:200]
    item["url"] = item.get("url") or url
    item["page"] = item["url"]
    item["count"] = 1 if text else 0
    item["items"] = []
    return item


def _parse_html(html: str, url: str) -> dict[str, Any] | None:
    m = _STATUS_JSON_RE.search(html)
    if m:
        try:
            data = json.loads(m.group(1))
        except ValueError:
            data = None
        if isinstance(data, dict):
            parsed = _from_status(data, url)
            if parsed and parsed.get("content"):
                return parsed
    body = ""
    dm = _DETAIL_RE.search(html)
    if dm:
        body = _extract_div(html, dm)
    text = strip_html(body)
    title = ""
    hm = _H1_RE.search(html)
    if hm:
        title = strip_html(hm.group(1))
    if not title:
        om = _OG_TITLE_RE.search(html)
        if om:
            title = strip_html(om.group(1))
    if not title and not text:
        return None
    return {
        "article_id": status_id_of(url),
        "title": title,
        "summary": text[:200],
        "content": text,
        "published_at": "",
        "url": url,
        "source": SOURCE,
        "channel": "article",
        "page": url,
        "count": 1 if text else 0,
        "items": [],
    }


def fetch_article(target_or_url: str) -> dict[str, Any]:
    """拉一篇雪球帖子 / 新闻正文。"""
    raw = safe_str(target_or_url)
    if not raw:
        return empty_pack(channel="article", error="缺少文章地址")
    url = article_url(raw)
    sid = status_id_of(raw) or status_id_of(url)
    last_error = ""
    if sid:
        try:
            data = query_show(sid)
            parsed = _from_status(data, url or article_url(sid))
            if parsed and parsed.get("content"):
                return parsed
            if parsed:
                last_error = "接口无正文"
            else:
                last_error = "接口无数据"
        except Exception as exc:  # noqa: BLE001
            logger.debug("雪球 show.json 失败 %s: %s", sid, exc)
            last_error = str(exc)
    if not url:
        return empty_pack(
            channel="article",
            error=last_error or "缺少文章地址",
            article_id=sid,
        )
    try:
        html = get_html(url, headers=headers_for(url))
    except Exception as exc:  # noqa: BLE001
        logger.debug("雪球正文页失败 %s: %s", url, exc)
        return empty_pack(
            channel="article",
            error=str(exc) or last_error,
            page=url,
            article_id=sid,
        )
    parsed = _parse_html(html, url)
    if parsed and (parsed.get("content") or parsed.get("title")):
        if sid and not parsed.get("article_id"):
            parsed["article_id"] = sid
        return parsed
    return empty_pack(
        channel="article",
        error=last_error or "页面无正文",
        page=url,
        article_id=sid,
    )
