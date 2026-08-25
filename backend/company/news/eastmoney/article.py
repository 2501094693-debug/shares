"""东财新闻正文：详情页 ``#ContentBody``。

列表接口通常只有摘要。把搜索/快讯/栏目返回的 ``url`` 或文章 ``code`` 丢进来即可。

    https://finance.eastmoney.com/a/{code}.html
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.codes import safe_str
from core.http import browser_get

from company.news.eastmoney._common import (
    SOURCE,
    article_url,
    empty_pack,
    fmt_dt,
    headers_for,
    strip_html,
)

logger = logging.getLogger(__name__)

_TITLE_RE = re.compile(r'<div class="title">([^<]+)</div>', re.I)
_H1_RE = re.compile(r"<h1[^>]*>([^<]+)</h1>", re.I)
_INFOS_RE = re.compile(r'<div class="infos">([\s\S]*?)</div>\s*<div class="aboutctrl"', re.I)
_SOURCE_RE = re.compile(r"来源[:：]\s*(\S+)")


def _extract_div(html: str, div_id: str) -> str:
    match = re.search(rf'<div[^>]*id=["\']{re.escape(div_id)}["\'][^>]*>', html, re.I)
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
    for cre in (_TITLE_RE, _H1_RE):
        m = cre.search(html)
        if m:
            text = strip_html(m.group(1))
            text = re.sub(r"_?东方财富网$", "", text).strip()
            if text:
                return text
    m = re.search(r"<title>([^<]+)</title>", html, re.I)
    if m:
        return re.sub(r"[_—\-].*$", "", strip_html(m.group(1))).strip()
    return ""


def fetch_article(code_or_url: str) -> dict[str, Any]:
    """拉一篇东财新闻正文。参数可以是文章 ID 或完整 URL。"""
    url = article_url(code_or_url)
    if not url:
        return empty_pack(channel="article", error="缺少文章地址")
    try:
        resp = browser_get(
            url,
            headers=headers_for("https://finance.eastmoney.com/"),
            timeout=25,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("东财正文失败 %s: %s", url, exc)
        return empty_pack(channel="article", error=str(exc), page=url)

    body_html = _extract_div(html, "ContentBody")
    if not body_html:
        body_html = _extract_div(html, "Content")
    text = strip_html(body_html)
    title = _page_title(html)
    published = ""
    media = ""
    infos = _INFOS_RE.search(html)
    if infos:
        info_text = strip_html(infos.group(1))
        published = fmt_dt(info_text)
        sm = _SOURCE_RE.search(info_text)
        if sm:
            media = sm.group(1).strip()

    article_id = ""
    m = re.search(r"/a/(\d{12,})\.html", url)
    if m:
        article_id = m.group(1)

    if not title and not text:
        return empty_pack(channel="article", error="页面无正文", page=url, article_id=article_id)

    return {
        "article_id": article_id,
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
