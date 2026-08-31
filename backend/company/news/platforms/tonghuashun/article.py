"""同花顺新闻正文：PC 详情页 ``.news-content-parsed``。

列表接口通常只有标题。把 ``pc_url``、``seq`` 或 ``20260825/c679277455`` 丢进来即可。

    https://stock.10jqka.com.cn/{YYYYMMDD}/c{seq}.shtml
    https://news.10jqka.com.cn/{YYYYMMDD}/c{seq}.shtml
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.codes import safe_str
from core.http import browser_get

from company.news.platforms.tonghuashun._common import (
    SOURCE,
    article_candidates,
    article_url,
    decode_html,
    empty_pack,
    fmt_dt,
    headers_for,
    strip_html,
)

logger = logging.getLogger(__name__)

_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_OG_TITLE_RE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.I)
_OG_DESC_RE = re.compile(r'<meta[^>]+(?:property=["\']og:description["\']|name=["\']description["\'])[^>]+content=["\']([^"\']+)["\']', re.I)
_SOURCE_RE = re.compile(r"来源[:：]\s*(?:<a[^>]*>)?([^<]+)", re.I)
_TIME_RE = re.compile(r"(20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_SEQ_RE = re.compile(r"(?:c|m|seq=)(\d{6,})", re.I)


def _extract_class(html: str, class_name: str) -> str:
    match = re.search(
        rf'<div[^>]*class=["\'][^"\']*{re.escape(class_name)}[^"\']*["\'][^>]*>',
        html,
        re.I,
    )
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


def _page_title(html: str) -> str:
    m = _H1_RE.search(html)
    if m:
        text = strip_html(m.group(1))
        if text and text not in {"同花顺财经", "同花顺", "财经"}:
            return text
    m = _OG_TITLE_RE.search(html)
    if m:
        return strip_html(m.group(1))
    m = re.search(r"<title>([^<]+)</title>", html, re.I)
    if m:
        return re.sub(r"[_—\-].*$", "", strip_html(m.group(1))).strip()
    return ""


def _page_meta(html: str) -> tuple[str, str]:
    published = ""
    media = ""
    m = _H1_RE.search(html)
    window = html[m.end() : m.end() + 1200] if m else html[:4000]
    tm = _TIME_RE.search(window) or _TIME_RE.search(html)
    if tm:
        published = fmt_dt(tm.group(1))
    sm = _SOURCE_RE.search(window) or _SOURCE_RE.search(html)
    if sm:
        media = strip_html(sm.group(1)).strip()
    return published, media


def _seq_of(url: str) -> str:
    m = _SEQ_RE.search(url)
    return m.group(1) if m else ""


def _parse_article(html: str, url: str) -> dict[str, Any] | None:
    body_html = _extract_class(html, "news-content-parsed")
    if not body_html:
        body_html = _extract_class(html, "news-content")
    if not body_html:
        for div_id in ("content", "mainText", "art_content", "articleContent"):
            m = re.search(rf'<div[^>]*id=["\']{div_id}["\'][^>]*>', html, re.I)
            if m:
                body_html = html[m.end() : m.end() + 20000]
                break
    text = strip_html(body_html)
    title = _page_title(html)
    published, media = _page_meta(html)
    if not text:
        desc = _OG_DESC_RE.search(html)
        if desc:
            text = strip_html(desc.group(1))
    if not title and not text:
        return None
    return {
        "article_id": _seq_of(url),
        "title": title,
        "summary": text[:200],
        "content": text,
        "published_at": published,
        "url": url,
        "source": SOURCE,
        "channel": "article",
        "media_name": media,
        "page": url,
        "count": 1 if text else 0,
        "items": [],
    }


def fetch_article(seq_or_url: str, *, day: str = "") -> dict[str, Any]:
    """拉一篇同花顺新闻正文。参数可以是 seq、含日期的路径或完整 URL。"""
    candidates = article_candidates(seq_or_url, day=day)
    if not candidates:
        return empty_pack(channel="article", error="缺少文章地址")

    last_error = ""
    last_url = candidates[0]
    for url in candidates:
        last_url = url
        try:
            resp = browser_get(
                url,
                headers=headers_for("https://news.10jqka.com.cn/"),
                timeout=25,
            )
            resp.raise_for_status()
            html = decode_html(resp)
        except Exception as exc:  # noqa: BLE001
            logger.debug("同花顺正文失败 %s: %s", url, exc)
            last_error = str(exc)
            continue
        parsed = _parse_article(html, url)
        if parsed and parsed.get("content") and parsed.get("title"):
            return parsed
        if parsed and parsed.get("content"):
            return parsed
        last_error = "页面无正文"
    return empty_pack(
        channel="article",
        error=last_error or "页面无正文",
        page=last_url,
        article_id=_seq_of(last_url) or _seq_of(article_url(seq_or_url, day=day)),
    )
