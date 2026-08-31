"""同花顺圈子共用：模拟手机客户端拉个股讨论。

同花顺没有文档化的公开社区 API。只走 WAP / App 同源接口：
``forum/v2/index``（板块与热度）+ ``hot_feed``（推荐流，含评论预览）。
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

from core.codes import normalize_code, safe_str
from core.http import browser_get

from company.news.platforms.tonghuashun._common import (  # noqa: F401
    REQUEST_PAUSE_SEC,
    SOURCE,
    TZ_CN,
    cli_print,
    date_range,
    dedupe,
    empty_pack,
    fmt_dt,
    in_range,
    map_choice,
    parse_day,
    print_items,
    resolve_keyword,
    strip_html,
    ths_market,
)

CIRCLE_HOST = "https://t.10jqka.com.cn"
LGT_HOST = "https://c.10jqka.com.cn"
FORUM_INDEX_API = f"{LGT_HOST}/lgt/cache/open/api/forum/v2/index"
HOT_FEED_API = f"{LGT_HOST}/lgt/post/open/api/forum/content/v1/hot_feed"
RECENT_API = f"{LGT_HOST}/lgt/post/open/api/forum/content/v1/recent"
HEXIN_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36 "
    "Hexin_Gphone/11.20.40 (Phone; Android 13; zh)"
)
MOBILE_PAGE_SIZE = 8

CHANNEL_POSTS = "ths_post"
CHANNEL_REPLY = "ths_reply"
CHANNEL_SEARCH = "ths_search"
CHANNEL_RANK = "ths_rank"
CHANNEL_SCORES = "ths_scores"

_HX_STOCK_RE = re.compile(
    r"<hx_stock>\s*stockName:([^,<]+)[^<]*</hx_stock>",
    re.I,
)


def to_int(value: Any, default: int = 0) -> int:
    text = safe_str(value)
    if not text:
        return default
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return default


def mobile_page_url(code: str = "") -> str:
    stock = normalize_code(code) or safe_str(code)
    if stock:
        return f"{CIRCLE_HOST}/m/guba/{stock}/"
    return f"{CIRCLE_HOST}/m/guba/"


list_page_url = mobile_page_url
rank_page_url = mobile_page_url


def search_page_url(keyword: str = "") -> str:
    kw = safe_str(keyword)
    code = normalize_code(kw)
    if code:
        return mobile_page_url(code)
    if kw:
        return f"{CIRCLE_HOST}/m/guba/?keyword={quote(kw)}"
    return f"{CIRCLE_HOST}/m/guba/"


def mobile_headers(code: str = "") -> dict[str, str]:
    referer = mobile_page_url(code) if code else f"{CIRCLE_HOST}/m/guba/"
    return {
        "User-Agent": HEXIN_UA,
        "Accept": "application/json, text/plain, */*",
        "Referer": referer,
        "Origin": CIRCLE_HOST,
    }


def strip_hx(text: str) -> str:
    """手机流正文里的 ``<hx_stock>stockName:茅台,...`` 标签 → 股票名。"""
    raw = _HX_STOCK_RE.sub(r"\1", safe_str(text))
    return strip_html(raw)


def parse_jsonp(text: str) -> Any:
    raw = safe_str(text).lstrip()
    if not raw:
        return {}
    if raw[0] in "{[":
        return json.loads(raw)
    start = raw.find("(")
    end = raw.rfind(")")
    if start < 0 or end <= start:
        return json.loads(raw)
    return json.loads(raw[start + 1 : end])


def get_payload(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
) -> Any:
    resp = browser_get(url, params=params, headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    payload = parse_jsonp(resp.text)
    return payload if payload is not None else {}


def mobile_data(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    code: str = "",
    timeout: int = 25,
) -> dict[str, Any]:
    """手机 LGT JSON：``status_code==0`` 时返回 ``data``。"""
    payload = get_payload(
        url,
        params=params,
        headers=mobile_headers(code),
        timeout=timeout,
    )
    if not isinstance(payload, dict):
        return {}
    err = payload.get("status_code")
    if err not in {0, "0", None}:
        msg = safe_str(payload.get("status_msg")) or f"status_code={err}"
        raise RuntimeError(msg)
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def query_forum_index(code: str, *, market_id: str = "") -> dict[str, Any]:
    """个股讨论页初始化：fid、名称、market_id、热度名次。"""
    stock = normalize_code(code) or safe_str(code)
    if not stock:
        return {}
    params: dict[str, Any] = {"code": stock, "source": "stock"}
    mid = safe_str(market_id) or ths_market(stock)
    if mid:
        params["marketId"] = mid
    return mobile_data(FORUM_INDEX_API, params=params, code=stock)


def comments_from_feed(
    row: dict[str, Any],
    *,
    code: str = "",
    post_id: str = "",
    url: str = "",
) -> list[dict[str, Any]]:
    """手机推荐流自带的评论预览。"""
    block = row.get("comment") if isinstance(row.get("comment"), dict) else {}
    comments = block.get("comments") if isinstance(block, dict) else None
    if not isinstance(comments, list):
        return []
    info = row.get("info") if isinstance(row.get("info"), dict) else {}
    page = url or safe_str(info.get("jump_url") or info.get("client_url"))
    items: list[dict[str, Any]] = []
    for raw in comments:
        if not isinstance(raw, dict):
            continue
        text = strip_hx(safe_str(raw.get("content")))
        if not text:
            continue
        author = safe_str(raw.get("nickname") or raw.get("name"))
        uid = safe_str(raw.get("uid") or raw.get("id"))
        items.append(
            {
                "code": code,
                "article_id": uid,
                "post_id": post_id,
                "reply_id": uid,
                "parent_id": "",
                "title": text[:80],
                "summary": text[:200],
                "content": text,
                "published_at": "",
                "url": page,
                "source": SOURCE,
                "channel": CHANNEL_REPLY,
                "author": author,
                "author_id": uid,
                "media_name": author,
                "like_count": 0,
                "comment_count": 0,
                "is_child": False,
            }
        )
    return items


def normalize_feed_item(
    row: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
    kind: str = "user",
) -> dict[str, Any] | None:
    """手机 ``hot_feed`` / ``recent`` 单条 → 社区帖字段。"""
    if not isinstance(row, dict):
        return None
    info = row.get("info") if isinstance(row.get("info"), dict) else {}
    author_b = row.get("author") if isinstance(row.get("author"), dict) else {}
    title_b = row.get("title") if isinstance(row.get("title"), dict) else {}
    abstract = row.get("abstract") if isinstance(row.get("abstract"), dict) else {}
    stat = row.get("stat") if isinstance(row.get("stat"), dict) else {}
    post_id = safe_str(info.get("id") or row.get("pid") or row.get("id"))
    title = strip_hx(safe_str(title_b.get("content") if title_b else row.get("title")))
    content = strip_hx(safe_str(abstract.get("content") if abstract else row.get("content")))
    if not post_id and not title and not content:
        return None
    author = safe_str(author_b.get("name") or row.get("author"))
    url = safe_str(info.get("jump_url") or info.get("client_url")) or mobile_page_url(code)
    return {
        "code": code,
        "name": name,
        "article_id": post_id,
        "post_id": post_id,
        "title": title or (content[:40] if content else post_id),
        "summary": content[:200],
        "content": content,
        "published_at": fmt_dt(info.get("ctime") or row.get("ctime") or row.get("published_at")),
        "url": url,
        "source": SOURCE,
        "channel": CHANNEL_POSTS,
        "kind": kind,
        "author": author,
        "author_id": safe_str(author_b.get("id") or row.get("userid")),
        "media_name": author,
        "like_count": to_int(stat.get("like_num") or row.get("like_count")),
        "comment_count": to_int(stat.get("comment_num") or row.get("comment_count")),
        "forward_count": to_int(stat.get("forward_num") or row.get("forward_count")),
        "post_type": safe_str(info.get("type")),
    }
