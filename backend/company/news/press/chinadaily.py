"""中国日报网文章检索：按公司简称搜中国日报 / 中国日报网新闻。

官网检索页：
  https://newssearch.chinadaily.com.cn/cn/search?keywords=贵州茅台

公开接口（需带检索页 Referer）：
  GET https://newssearch.chinadaily.com.cn/rest/cn/search
  - keywords  关键词（用简称，不要用六位代码）
  - curType   story=文章 / comment=评论 / blog=博客 / photo=图片
  - sort      dp=最新 / ap=最早 / 空=相关度
  - page      页码，从 0 起；每页 10 条

接口无日期参数，按时间倒序翻页后在本地按起止日期过滤。

    python company/news/press/chinadaily.py 600519
    python company/news/press/chinadaily.py 贵州茅台 --days 7
    python company/news/press/chinadaily.py 600519 --sort relevance --json
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import normalize_code, safe_str
from core.http import browser_get

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))

HOME = "https://cn.chinadaily.com.cn/"
SEARCH_HOST = "https://newssearch.chinadaily.com.cn"
SEARCH_API = f"{SEARCH_HOST}/rest/cn/search"
SEARCH_PAGE = f"{SEARCH_HOST}/cn/search"
PAGE_SIZE = 10
REQUEST_PAUSE_SEC = 0.25
MAX_PAGES = 50
_HTML_TAG_RE = re.compile(r"<[^>]+>")

TYPES: dict[str, str] = {
    "story": "story",
    "news": "story",
    "article": "story",
    "articles": "story",
    "新闻": "story",
    "文章": "story",
    "comment": "comment",
    "comments": "comment",
    "评论": "comment",
    "blog": "blog",
    "blogs": "blog",
    "博客": "blog",
    "photo": "photo",
    "photos": "photo",
    "图片": "photo",
}
SORTS: dict[str, str] = {
    "time": "dp",
    "dp": "dp",
    "newest": "dp",
    "最新": "dp",
    "时间": "dp",
    "oldest": "ap",
    "ap": "ap",
    "最早": "ap",
    "relevance": "",
    "相关度": "",
    "": "",
}
LANGS: dict[str, str] = {
    "cn": "cn",
    "zh": "cn",
    "中文": "cn",
    "en": "en",
    "english": "en",
    "英文": "en",
}


# ---------------------------------------------------------------------------
# HTTP / 文本
# ---------------------------------------------------------------------------


def _api_url(lang: str = "cn") -> str:
    if lang == "en":
        return f"{SEARCH_HOST}/rest/search"
    return f"{SEARCH_HOST}/rest/{lang}/search"


def search_page_url(keyword: str = "", *, lang: str = "cn") -> str:
    path = f"{SEARCH_HOST}/{lang}/search" if lang != "en" else f"{SEARCH_HOST}/search"
    kw = safe_str(keyword)
    if kw:
        return f"{path}?keywords={quote(kw)}"
    return path


def _headers(keyword: str = "", *, lang: str = "cn") -> dict[str, str]:
    return {
        "Referer": search_page_url(keyword, lang=lang),
        "Origin": "https://newssearch.chinadaily.com.cn",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def strip_html(text: str) -> str:
    cleaned = html.unescape(safe_str(text))
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    return (
        cleaned.replace("&nbsp;", " ")
        .replace("\xa0", " ")
        .replace("\u3000", " ")
        .strip()
    )


def _map_choice(value: str | None, table: dict[str, str], default: str, label: str) -> str:
    key = safe_str(value) or default
    if key in table:
        return table[key]
    mapped = table.get(key.lower())
    if mapped is not None:
        return mapped
    raise ValueError(f"未知 {label}: {value}；可用 {', '.join(sorted(set(table)))}")


def resolve_type(kind: str | None) -> str:
    return _map_choice(kind, TYPES, "story", "type")


def resolve_sort(sort: str | None) -> str:
    return _map_choice(sort, SORTS, "time", "sort")


def resolve_lang(lang: str | None) -> str:
    return _map_choice(lang, LANGS, "cn", "lang")


def _parse_day(value: str | date | datetime | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=TZ_CN)
        return dt.astimezone(TZ_CN).date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and value > 10_000_000_000:
        try:
            return datetime.fromtimestamp(int(value) / 1000, TZ_CN).date()
        except (OSError, OverflowError, ValueError):
            return None
    text = safe_str(value).replace("/", "-")
    for fmt, size in (("%Y-%m-%d", 10), ("%Y%m%d", 8)):
        try:
            return datetime.strptime(text[:size], fmt).date()
        except ValueError:
            continue
    return None


def _date_range(
    start: str | date | datetime | None,
    end: str | date | datetime | None,
    days: int | None,
) -> tuple[date | None, date | None]:
    end_d = _parse_day(end)
    start_d = _parse_day(start)
    if start_d is None and days is not None:
        end_d = end_d or date.today()
        start_d = end_d - timedelta(days=max(1, int(days)))
    if start_d and end_d and start_d > end_d:
        start_d, end_d = end_d, start_d
    return start_d, end_d


def resolve_keyword(code_or_name: str) -> dict[str, str]:
    """代码优先解析成简称；解析失败则原样当关键词。"""
    raw = safe_str(code_or_name)
    code = normalize_code(raw)
    name = ""
    if raw:
        try:
            from company.news.cninfo import resolve_org

            org = resolve_org(raw)
        except Exception as exc:  # noqa: BLE001
            logger.info("解析公司简称失败 %s: %s", raw, exc)
            org = None
        if org:
            code = safe_str(org.get("code")) or code
            name = safe_str(org.get("name"))
    keyword = name or (raw if not code or raw != code else code)
    return {"code": code, "name": name, "keyword": keyword}


def _parse_pub_time(row: dict[str, Any]) -> str:
    text = safe_str(row.get("pubDateStr"))
    for fmt, size in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        try:
            dt = datetime.strptime(text[:size], fmt).replace(tzinfo=TZ_CN)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    ts = row.get("publishTime") or row.get("created")
    if isinstance(ts, (int, float)) and ts > 10_000_000_000:
        try:
            return datetime.fromtimestamp(int(ts) / 1000, TZ_CN).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, OverflowError, ValueError):
            pass
    return text


def _join_authors(value: Any) -> str:
    if isinstance(value, list):
        parts = [strip_html(v) for v in value if strip_html(v)]
        return " ".join(parts)
    return strip_html(value)


# ---------------------------------------------------------------------------
# 列表解析
# ---------------------------------------------------------------------------


def _normalize_row(
    row: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
) -> dict[str, Any] | None:
    title = strip_html(safe_str(row.get("title") or row.get("highlightTitle")))
    if not title:
        return None
    origin = strip_html(safe_str(row.get("source")))
    summary = strip_html(
        safe_str(row.get("plainText") or row.get("summary") or row.get("highlightContent"))
    )
    return {
        "code": code,
        "name": name,
        "title": title,
        "summary": summary,
        "published_at": _parse_pub_time(row),
        "url": safe_str(row.get("url")),
        "source": origin or "中国日报",
        "channel": "chinadaily",
        "author": _join_authors(row.get("authors") or row.get("author_low")),
        "origin": origin,
        "article_id": safe_str(row.get("id")),
    }


def _dedupe(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        url = safe_str(item.get("url")).lower()
        title = safe_str(item.get("title"))
        day = safe_str(item.get("published_at"))[:10]
        key = url if url else f"{title}|{day}"
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _in_range(item: dict[str, Any], start_d: date | None, end_d: date | None) -> bool:
    day = _parse_day(item.get("published_at"))
    if day is None:
        return True
    if start_d and day < start_d:
        return False
    if end_d and day > end_d:
        return False
    return True


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


def query_page(
    keyword: str,
    *,
    page: int = 1,
    type_: str = "story",
    sort: str = "dp",
    lang: str = "cn",
) -> dict[str, Any]:
    """中国日报网检索单页原始 JSON。"""
    kw = safe_str(keyword)
    params: dict[str, Any] = {
        "keywords": kw,
        "curType": type_ or "story",
        "sort": sort or "",
        "page": max(0, int(page) - 1),
    }
    resp = browser_get(
        _api_url(lang),
        params=params,
        headers=_headers(kw, lang=lang),
        timeout=25,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload if isinstance(payload, dict) else {}


def _empty_pack(code: str, name: str, keyword: str, *, error: str = "", **extra: Any) -> dict[str, Any]:
    lang = extra.get("lang") or "cn"
    pack = {
        "code": code,
        "name": name,
        "keyword": keyword,
        "source": "chinadaily",
        "channel": "news",
        "count": 0,
        "total": 0,
        "items": [],
        "page": search_page_url(keyword, lang=lang),
    }
    pack.update(extra)
    if error:
        pack["error"] = error
    return pack


def fetch_news(
    code_or_name: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 31,
    type_: str | None = "story",
    sort: str | None = "time",
    lang: str | None = "cn",
    max_pages: int = 5,
) -> dict[str, Any]:
    """按股票代码或公司简称拉取中国日报网新闻。

    接口按关键词全文检索，代码请先解析成简称（本函数会自动 resolve）。
    ``type_``：``story`` 文章 / ``comment`` 评论 / ``blog`` 博客 / ``photo`` 图片。
    ``sort``：``time`` 最新 / ``oldest`` 最早 / ``relevance`` 相关度。
    ``lang``：``cn`` 中文 / ``en`` 英文。
    接口无日期参数，按时间倒序翻页后在本地按起止日期过滤。
    """
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"]
    name = resolved["name"]
    keyword = resolved["keyword"]
    if not keyword:
        return _empty_pack(code, name, keyword, error="缺少检索关键词")

    api_type = resolve_type(type_)
    api_sort = resolve_sort(sort)
    api_lang = resolve_lang(lang)
    start_d, end_d = _date_range(start, end, days)

    items: list[dict[str, Any]] = []
    total = 0
    total_pages = 1
    page = 1
    limit = max(1, int(max_pages))
    while page <= total_pages and page <= limit:
        try:
            payload = query_page(
                keyword,
                page=page,
                type_=api_type,
                sort=api_sort,
                lang=api_lang,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("中国日报网检索失败 page=%s: %s", page, exc)
            if page == 1:
                return _empty_pack(
                    code,
                    name,
                    keyword,
                    error=str(exc),
                    type=api_type,
                    sort=api_sort or "relevance",
                    lang=api_lang,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        rows = payload.get("content") or []
        if not isinstance(rows, list):
            rows = []
        total = int(payload.get("totalElements") or total)
        total_pages = int(payload.get("totalPages") or 0) or total_pages
        if total and not payload.get("totalPages"):
            total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        if not rows:
            break
        oldest: date | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _normalize_row(row, code=code, name=name)
            if not item:
                continue
            day = _parse_day(item.get("published_at"))
            if day and (oldest is None or day < oldest):
                oldest = day
            if _in_range(item, start_d, end_d):
                items.append(item)
        if api_sort == "dp" and start_d and oldest and oldest < start_d:
            break
        if page >= total_pages:
            break
        page += 1
        if page <= total_pages and page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = _dedupe(items)
    return {
        "code": code,
        "name": name,
        "keyword": keyword,
        "type": api_type,
        "sort": api_sort or "relevance",
        "lang": api_lang,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": "chinadaily",
        "channel": "news",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": search_page_url(keyword, lang=api_lang),
    }


def search_news(code_or_name: str, **kwargs: Any) -> dict[str, Any]:
    """``fetch_news`` 别名。"""
    return fetch_news(code_or_name, **kwargs)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def _print_items(pack: dict[str, Any], limit: int, as_json: bool) -> None:
    if as_json:
        payload = dict(pack)
        if limit > 0:
            payload["items"] = (pack.get("items") or [])[:limit]
        _cli_print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    items = pack.get("items") or []
    shown = items if limit <= 0 else items[:limit]
    extra = []
    if pack.get("code"):
        extra.append(pack["code"])
    if pack.get("name"):
        extra.append(pack["name"])
    bits = " ".join(extra)
    _cli_print(
        f"{bits}  keyword={pack.get('keyword')} "
        f"{pack.get('begin_date', '')}~{pack.get('end_date', '')} "
        f"count={pack.get('count')}"
        + (f"/{pack.get('total')}" if pack.get("total") else "")
    )
    if pack.get("error"):
        _cli_print(f"  error: {pack['error']}")
        return
    if not shown:
        _cli_print("  (empty)")
        return
    for i, row in enumerate(shown, 1):
        day = (row.get("published_at") or "")[:10]
        origin = row.get("origin") or row.get("source") or ""
        origin_bit = f" [{origin}]" if origin else ""
        _cli_print(f"  [{i}] {day}{origin_bit} {row.get('title')}")
        if row.get("url"):
            _cli_print(f"       {row['url']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="从中国日报网检索上市公司相关新闻")
    parser.add_argument("code", help="股票代码或公司简称，如 600519 / 贵州茅台")
    parser.add_argument("--days", type=int, default=31, help="回溯天数，默认 31")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--type",
        dest="kind",
        default="story",
        help="story 文章 / comment 评论 / blog 博客 / photo 图片",
    )
    parser.add_argument(
        "--sort",
        default="time",
        help="time 最新 / oldest 最早 / relevance 相关度",
    )
    parser.add_argument("--lang", default="cn", help="cn 中文 / en 英文")
    parser.add_argument("--max-pages", type=int, default=5, help="最多翻页，默认 5")
    parser.add_argument("--limit", type=int, default=10, help="打印前 N 条；0 为全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    pack = fetch_news(
        args.code,
        start=args.start or None,
        end=args.end or None,
        days=args.days,
        type_=args.kind,
        sort=args.sort,
        lang=args.lang,
        max_pages=args.max_pages,
    )
    _print_items(pack, args.limit, args.json)
    return 1 if pack.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
