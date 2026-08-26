"""东财社区（股吧）共用：列表页 JSON、帖子 URL、规范化字段。

东财没有文档化的公开社区 API。列表走股吧 HTML 内嵌 ``var article_list``，
回复走 ``GetData.aspx``，搜索走 ``search-api-web`` 的 ``gubaArticle``，
人气榜走 ``emappdata.eastmoney.com/stockrank``。
``gbapi.eastmoney.com`` 需要签名，当前会返回「系统繁忙」，不用。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from core.codes import normalize_code, safe_str
from core.http import browser_post

from company.news.eastmoney._common import (  # noqa: F401
    REQUEST_PAUSE_SEC,
    SOURCE,
    TZ_CN,
    cli_print,
    date_range,
    dedupe,
    empty_pack,
    fmt_dt,
    get_payload,
    headers_for,
    in_range,
    jsonp_callback,
    map_choice,
    parse_day,
    parse_jsonp,
    print_items,
    req_trace,
    resolve_keyword,
    strip_em,
    strip_html,
)

logger = logging.getLogger(__name__)

GUBA_HOST = "https://guba.eastmoney.com"
GETDATA_API = "https://guba.eastmoney.com/interface/GetData.aspx"
SEARCH_API = "https://search-api-web.eastmoney.com/search/jsonp"
RANK_API = "https://emappdata.eastmoney.com/stockrank"
SCORES_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
SCORES_PAGE = "https://data.eastmoney.com/stockcomment/"

CHANNEL_POSTS = "guba"
CHANNEL_ARTICLE = "guba_article"
CHANNEL_REPLY = "guba_reply"
CHANNEL_SEARCH = "guba_search"
CHANNEL_RANK = "guba_rank"
CHANNEL_SCORES = "guba_scores"

_POST_REF_RE = re.compile(
    r"(?:guba\.eastmoney\.com/news,)?(?:([A-Za-z0-9]+),)?(\d{6,})(?:\.html)?",
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


def list_page_url(
    code: str,
    *,
    kind: str = "all",
    sort: str = "time",
    page: int = 1,
) -> str:
    """个股吧列表页。

    - 全部 + 最新回复：``/list,{code}.html`` / ``/list,{code}_{page}.html``
    - 全部 + 发帖时间：``/list,{code},f_{page}.html``
    - 分类：``/list,{code},{type},f_{page}.html``（新闻 1 / 研报 2 / 公告 3 / 融资融券 4 / 其他 7 / 问董秘 11 / 说明会 20）
    - 热门：``/list,{code},99.html`` / ``/list,{code},99_{page}.html``
    """
    c = normalize_code(code) or safe_str(code)
    if not c:
        return f"{GUBA_HOST}/"
    page = max(1, int(page))
    type_code = kind_type_code(kind)
    use_hot = kind == "hot" or (not type_code and sort == "hot")
    if use_hot:
        if page == 1:
            return f"{GUBA_HOST}/list,{c},99.html"
        return f"{GUBA_HOST}/list,{c},99_{page}.html"
    if type_code:
        return f"{GUBA_HOST}/list,{c},{type_code},f_{page}.html"
    if sort == "reply":
        if page == 1:
            return f"{GUBA_HOST}/list,{c}.html"
        return f"{GUBA_HOST}/list,{c}_{page}.html"
    if page == 1:
        return f"{GUBA_HOST}/list,{c},f_1.html"
    return f"{GUBA_HOST}/list,{c},f_{page}.html"


def post_url(code: str, post_id: str) -> str:
    pid = safe_str(post_id)
    if not pid:
        return ""
    c = normalize_code(code) or safe_str(code) or "guba"
    return f"{GUBA_HOST}/news,{c},{pid}.html"


def search_page_url(keyword: str = "") -> str:
    from urllib.parse import quote

    kw = safe_str(keyword)
    if kw:
        return f"https://so.eastmoney.com/web/s?keyword={quote(kw)}"
    return "https://so.eastmoney.com/web/s"


def scores_page_url(code: str = "") -> str:
    c = normalize_code(code)
    if c:
        return f"{SCORES_PAGE}stock/{c}.html"
    return SCORES_PAGE


def rank_page_url() -> str:
    return f"{GUBA_HOST}/rank/"


def parse_post_ref(value: str, default_code: str = "") -> tuple[str, str]:
    """文章 ID 或 ``news,{code},{id}.html`` → ``(code, post_id)``。"""
    raw = safe_str(value)
    if not raw:
        return normalize_code(default_code), ""
    if raw.isdigit() and len(raw) >= 6:
        return normalize_code(default_code), raw
    m = _POST_REF_RE.search(raw)
    if not m:
        return normalize_code(default_code), ""
    bar = safe_str(m.group(1))
    post_id = safe_str(m.group(2))
    code = normalize_code(bar) or normalize_code(default_code)
    if not code and bar and bar.lower() not in {"news", "guba"}:
        code = bar
    return code, post_id


def extract_article_list(html: str) -> dict[str, Any]:
    """从列表页 HTML 取出 ``var article_list={...}``。按括号配对，避免正则截断。"""
    text = safe_str(html)
    marker = "var article_list"
    i = text.find(marker)
    if i < 0:
        return {}
    start = text.find("{", i)
    if start < 0:
        return {}
    depth = 0
    in_str = False
    escape = False
    quote = ""
    for j, ch in enumerate(text[start:], start):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_str = False
            continue
        if ch in "\"'":
            in_str = True
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    payload = json.loads(text[start : j + 1])
                except json.JSONDecodeError:
                    return {}
                return payload if isinstance(payload, dict) else {}
    return {}


def post_payload(
    url: str,
    *,
    data: dict[str, Any] | None = None,
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
) -> Any:
    """POST 后解析 JSON / JSONP。空响应当成 ``{}``。"""
    resp = browser_post(
        url,
        data=data,
        json_body=json_body,
        headers=headers or {},
        timeout=timeout,
    )
    resp.raise_for_status()
    raw = safe_str(resp.text)
    if not raw:
        return {}
    payload = parse_jsonp(raw)
    return payload if payload is not None else {}


def user_name(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        block = row.get(key)
        if isinstance(block, dict):
            name = safe_str(block.get("user_nickname") or block.get("user_name"))
            if name:
                return name
        elif block:
            name = safe_str(block)
            if name:
                return name
    return ""


def user_id(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        block = row.get(key)
        if isinstance(block, dict):
            uid = safe_str(block.get("user_id") or block.get("id"))
            if uid:
                return uid
        elif key.endswith("_id"):
            uid = safe_str(block)
            if uid:
                return uid
    return safe_str(row.get("user_id"))


def guba_name_of(row: dict[str, Any]) -> str:
    block = row.get("post_guba")
    if isinstance(block, dict):
        return safe_str(block.get("stockbar_name") or block.get("stockbar_code"))
    return safe_str(row.get("gubaName") or row.get("bar_name"))


def kind_type_code(kind: str) -> str:
    return {
        "all": "",
        "news": "1",
        "reports": "2",
        "notices": "3",
        "margin": "4",
        "other": "7",
        "qa": "11",
        "meeting": "20",
        "hot": "99",
    }.get(kind, "")


def normalize_post(
    row: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
    kind: str = "all",
    channel: str = CHANNEL_POSTS,
) -> dict[str, Any] | None:
    post_id = safe_str(row.get("post_id") or row.get("id"))
    title = strip_html(strip_em(safe_str(row.get("post_title") or row.get("title"))))
    content = strip_html(strip_em(safe_str(row.get("post_content") or row.get("content"))))
    if not post_id and not title:
        return None
    author = user_name(row, "post_user") or safe_str(row.get("nickname"))
    bar = guba_name_of(row)
    url = post_url(code, post_id)
    return {
        "code": code,
        "name": name,
        "article_id": post_id,
        "post_id": post_id,
        "title": title or (content[:40] if content else post_id),
        "summary": content[:200],
        "content": content,
        "published_at": fmt_dt(row.get("post_publish_time") or row.get("date") or row.get("post_display_time")),
        "updated_at": fmt_dt(row.get("post_last_time") or row.get("post_mod_time")),
        "url": url,
        "source": SOURCE,
        "channel": channel,
        "kind": kind,
        "author": author,
        "author_id": user_id(row, "post_user"),
        "media_name": author or bar,
        "guba_name": bar,
        "click_count": to_int(row.get("post_click_count")),
        "comment_count": to_int(row.get("post_comment_count") or row.get("commentNum")),
        "like_count": to_int(row.get("post_like_count") or row.get("likeNum")),
        "post_type": row.get("post_type") if row.get("post_type") is not None else row.get("type"),
        "post_from": safe_str(row.get("post_from")),
        "ip": safe_str(row.get("post_ip") or row.get("post_address")),
    }
