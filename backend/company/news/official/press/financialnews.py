"""金融时报网 / 中国金融新闻网文章检索：按公司简称搜金融时报新闻。

官网检索页：
  https://www.financialnews.com.cn/founder/SearchServlet.do?content=贵州茅台&siteID=1

公开接口（方正翔宇，需带检索页 Referer）：
  POST https://www.financialnews.com.cn/xy/Search.do
  - q / title / content / author  关键词（用简称，不要用六位代码）
  - pageNo     页码，从 1 起（0 与 1 同为首页）
  - pageSize   官网固定 20
  - siteID     1
  - channel    1
  - sort       date desc=按时间 / 空=按相关度 / date asc=时间升序
  - startDate / endDate  YYYY-MM-DD

    python company/news/press/financialnews.py 600519
    python company/news/press/financialnews.py 贵州茅台 --days 7
    python company/news/press/financialnews.py 600519 --field title --json
"""

from __future__ import annotations

import argparse
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
from core.http import browser_post

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))

HOME = "https://www.financialnews.com.cn/"
SEARCH_API = "https://www.financialnews.com.cn/xy/Search.do"
SEARCH_PAGE = "https://www.financialnews.com.cn/founder/SearchServlet.do"
SITE_ID = "1"
CHANNEL = "1"
PAGE_SIZE = 20
REQUEST_PAUSE_SEC = 0.25
MAX_PAGES = 50
_HTML_TAG_RE = re.compile(r"<[^>]+>")

FIELDS: dict[str, str] = {
    "all": "q",
    "全部": "q",
    "全文": "q",
    "q": "q",
    "title": "title",
    "标题": "title",
    "content": "content",
    "正文": "content",
    "author": "author",
    "作者": "author",
}
SORTS: dict[str, str] = {
    "time": "date desc",
    "date desc": "date desc",
    "时间": "date desc",
    "relevance": "",
    "相关度": "",
    "time_asc": "date asc",
    "date asc": "date asc",
    "时间升序": "date asc",
}


# ---------------------------------------------------------------------------
# HTTP / 文本
# ---------------------------------------------------------------------------


def _headers(keyword: str = "") -> dict[str, str]:
    referer = search_page_url(keyword) if keyword else SEARCH_PAGE
    return {
        "Referer": referer,
        "Origin": "https://www.financialnews.com.cn",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def search_page_url(keyword: str = "") -> str:
    kw = safe_str(keyword)
    if kw:
        return f"{SEARCH_PAGE}?content={quote(kw)}&siteID={SITE_ID}"
    return f"{SEARCH_PAGE}?siteID={SITE_ID}"


def strip_html(text: str) -> str:
    cleaned = (
        safe_str(text)
        .replace("<br>", " ")
        .replace("<br/>", " ")
        .replace("<br />", " ")
        .replace("<BR>", " ")
    )
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    return (
        cleaned.replace("&nbsp;", " ")
        .replace("&ldquo;", "“")
        .replace("&rdquo;", "”")
        .replace("&mdash;", "—")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("\xa0", " ")
        .replace("\u3000", " ")
        .strip()
    )


def resolve_field(field: str | None) -> str:
    key = safe_str(field) or "all"
    if key in FIELDS:
        return FIELDS[key]
    mapped = FIELDS.get(key.lower())
    if mapped is not None:
        return mapped
    raise ValueError(f"未知 field: {field}；可用 all / title / content / author")


def resolve_sort(sort: str | None) -> str:
    key = safe_str(sort) or "time"
    if key in SORTS:
        return SORTS[key]
    mapped = SORTS.get(key.lower())
    if mapped is not None:
        return mapped
    raise ValueError(f"未知 sort: {sort}；可用 time / relevance / time_asc")


def _parse_day(value: str | date | datetime | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=TZ_CN)
        return dt.astimezone(TZ_CN).date()
    if isinstance(value, date):
        return value
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
            from company.news.official.cninfo import resolve_org

            org = resolve_org(raw)
        except Exception as exc:  # noqa: BLE001
            logger.info("解析公司简称失败 %s: %s", raw, exc)
            org = None
        if org:
            code = safe_str(org.get("code")) or code
            name = safe_str(org.get("name"))
    keyword = name or (raw if not code or raw != code else code)
    return {"code": code, "name": name, "keyword": keyword}


def _https_url(url: str) -> str:
    raw = safe_str(url)
    if raw.startswith("http://www.financialnews.com.cn"):
        return "https://" + raw[len("http://") :]
    return raw


# ---------------------------------------------------------------------------
# 列表解析
# ---------------------------------------------------------------------------


def _normalize_row(
    row: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
) -> dict[str, Any] | None:
    title = strip_html(safe_str(row.get("title")))
    if not title:
        return None
    day = _parse_day(row.get("date"))
    published = (
        datetime(day.year, day.month, day.day, tzinfo=TZ_CN).strftime("%Y-%m-%d %H:%M:%S")
        if day
        else safe_str(row.get("date"))
    )
    origin = strip_html(safe_str(row.get("sourcename")))
    summary = strip_html(safe_str(row.get("Abstract") or row.get("enpcontent")))
    article_id = row.get("articleid")
    return {
        "code": code,
        "name": name,
        "title": title,
        "summary": summary,
        "published_at": published,
        "url": _https_url(safe_str(row.get("url") or row.get("urlpad"))),
        "source": origin or "金融时报",
        "channel": "financialnews",
        "column": strip_html(safe_str(row.get("nodesearchname") or row.get("cascadeName"))),
        "author": strip_html(safe_str(row.get("author"))),
        "journalist": strip_html(safe_str(row.get("journalist"))),
        "origin": origin,
        "article_id": safe_str(article_id) if article_id not in (None, "") else "",
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
    page_size: int = PAGE_SIZE,
    field: str = "q",
    sort: str = "date desc",
    start_date: str = "",
    end_date: str = "",
) -> dict[str, Any]:
    """中国金融新闻网检索单页原始 JSON。"""
    kw = safe_str(keyword)
    body: dict[str, Any] = {
        "pageNo": max(1, int(page)),
        "pageSize": max(1, min(int(page_size), 50)),
        "channel": CHANNEL,
        "siteID": SITE_ID,
        "sort": sort or "",
        "nodeID": "",
    }
    query_key = field or "q"
    body[query_key] = kw
    if start_date:
        body["startDate"] = start_date
    if end_date:
        body["endDate"] = end_date
    resp = browser_post(
        SEARCH_API,
        data=body,
        headers=_headers(kw),
        timeout=25,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload if isinstance(payload, dict) else {}


def _empty_pack(code: str, name: str, keyword: str, *, error: str = "", **extra: Any) -> dict[str, Any]:
    pack = {
        "code": code,
        "name": name,
        "keyword": keyword,
        "source": "financialnews",
        "channel": "news",
        "count": 0,
        "total": 0,
        "items": [],
        "page": search_page_url(keyword),
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
    field: str | None = "all",
    sort: str | None = "time",
    max_pages: int = 5,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """按股票代码或公司简称拉取中国金融新闻网新闻。

    接口按关键词全文检索，代码请先解析成简称（本函数会自动 resolve）。
    ``field``：``all`` 全文 / ``title`` 标题 / ``content`` 正文 / ``author`` 作者。
    ``sort``：``time`` 按时间 / ``relevance`` 按相关度。
    日期会传给接口的 ``startDate`` / ``endDate``，并在本地再筛一遍。
    """
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"]
    name = resolved["name"]
    keyword = resolved["keyword"]
    if not keyword:
        return _empty_pack(code, name, keyword, error="缺少检索关键词")

    api_field = resolve_field(field)
    api_sort = resolve_sort(sort)
    start_d, end_d = _date_range(start, end, days)
    start_token = start_d.isoformat() if start_d else ""
    end_token = end_d.isoformat() if end_d else ""

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
                page_size=page_size,
                field=api_field,
                sort=api_sort,
                start_date=start_token,
                end_date=end_token,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("中国金融新闻网检索失败 page=%s: %s", page, exc)
            if page == 1:
                return _empty_pack(
                    code,
                    name,
                    keyword,
                    error=str(exc),
                    field=api_field,
                    sort=api_sort or "relevance",
                    begin_date=start_token,
                    end_date=end_token,
                )
            break
        if payload.get("errMsg") and page == 1 and not payload.get("article"):
            return _empty_pack(
                code,
                name,
                keyword,
                error=safe_str(payload.get("errMsg")) or "检索接口返回失败",
                field=api_field,
                sort=api_sort or "relevance",
            )
        rows = payload.get("article") or []
        if not isinstance(rows, list):
            rows = []
        total = int(payload.get("foundNum") or total)
        if total:
            total_pages = max(1, (total + page_size - 1) // page_size)
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
        if api_sort.startswith("date") and start_d and oldest and oldest < start_d:
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
        "field": api_field,
        "sort": api_sort or "relevance",
        "begin_date": start_token,
        "end_date": end_token,
        "source": "financialnews",
        "channel": "news",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": search_page_url(keyword),
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
        origin = row.get("column") or row.get("origin") or row.get("source") or ""
        origin_bit = f" [{origin}]" if origin else ""
        _cli_print(f"  [{i}] {day}{origin_bit} {row.get('title')}")
        if row.get("url"):
            _cli_print(f"       {row['url']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="从中国金融新闻网检索上市公司相关新闻")
    parser.add_argument("code", help="股票代码或公司简称，如 600519 / 贵州茅台")
    parser.add_argument("--days", type=int, default=31, help="回溯天数，默认 31")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--field",
        default="all",
        help="all 全文 / title 标题 / content 正文 / author 作者",
    )
    parser.add_argument(
        "--sort",
        default="time",
        help="time 按时间 / relevance 按相关度",
    )
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
        field=args.field,
        sort=args.sort,
        max_pages=args.max_pages,
    )
    _print_items(pack, args.limit, args.json)
    return 1 if pack.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
