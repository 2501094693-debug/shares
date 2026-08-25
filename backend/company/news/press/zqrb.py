"""证券日报网文章检索：按公司简称搜证券日报 / 证券日报网新闻。

官网检索页（仅 HTTP；HTTPS 不可用）：
  http://search.zqrb.cn/search.php?src=news&q=贵州茅台&f=title&s=newsdate_DESC

公开接口（迅搜 xunsearch HTML，需带官网 Referer）：
  GET http://search.zqrb.cn/search.php
  - q    关键词（用简称，不要用六位代码）
  - src  all=全部 / news=新闻 / epaper=电子报
  - f    title=标题 / author_name=作者 / _all=全文
  - s    newsdate_DESC=按时间 / relevance=按相关度
  - m    yes=模糊搜索
  - p    页码，从 1 起；每页约 15 条

全文检索会把中文拆成单字（「贵州茅台」可能命中「九州通」），
公司新闻默认按标题搜。

    python company/news/press/zqrb.py 600519
    python company/news/press/zqrb.py 贵州茅台 --days 7
    python company/news/press/zqrb.py 600519 --src all --field all --json
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
from urllib.parse import quote, urljoin

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from bs4 import BeautifulSoup

from core.codes import normalize_code, safe_str
from core.http import browser_get

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))

HOME = "http://www.zqrb.cn/"
SEARCH_API = "http://search.zqrb.cn/search.php"
PAGE_SIZE = 15
REQUEST_PAUSE_SEC = 0.25
MAX_PAGES = 50
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_RANK_RE = re.compile(r"^\d+\s+")
_TOTAL_RE = re.compile(r"大约有\s*([\d,]+)\s*项")
_DATE_CN_RE = re.compile(
    r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
_DATE_IN_URL_RE = re.compile(r"/(\d{4}-\d{2}-\d{2})/")
_ARTICLE_ID_RE = re.compile(r"/(A\d+)\.html", re.I)
_EPAPER_ID_RE = re.compile(r"content_(\d+)\.htm", re.I)

SOURCES: dict[str, str] = {
    "all": "all",
    "全部": "all",
    "news": "news",
    "新闻": "news",
    "资讯": "news",
    "epaper": "epaper",
    "电子报": "epaper",
    "报纸": "epaper",
}
FIELDS: dict[str, str] = {
    "all": "_all",
    "全部": "_all",
    "全文": "_all",
    "_all": "_all",
    "title": "title",
    "标题": "title",
    "author": "author_name",
    "author_name": "author_name",
    "作者": "author_name",
}
SORTS: dict[str, str] = {
    "time": "newsdate_DESC",
    "newsdate_DESC": "newsdate_DESC",
    "时间": "newsdate_DESC",
    "relevance": "relevance",
    "相关度": "relevance",
}


# ---------------------------------------------------------------------------
# HTTP / 文本
# ---------------------------------------------------------------------------


def _headers(keyword: str = "") -> dict[str, str]:
    referer = search_page_url(keyword) if keyword else HOME
    return {
        "Referer": referer,
        "Origin": "http://www.zqrb.cn",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def search_page_url(
    keyword: str = "",
    *,
    src: str = "news",
    field: str = "title",
    sort: str = "newsdate_DESC",
    fuzzy: bool = False,
    page: int = 1,
) -> str:
    params = [
        f"src={quote(src or 'news')}",
        f"q={quote(safe_str(keyword))}",
        f"f={quote(field or 'title')}",
        f"s={quote(sort or 'newsdate_DESC')}",
    ]
    if fuzzy:
        params.append("m=yes")
    if int(page) > 1:
        params.append(f"p={int(page)}")
    return f"{SEARCH_API}?{'&'.join(params)}"


def strip_html(text: str) -> str:
    cleaned = _HTML_TAG_RE.sub("", safe_str(text))
    return (
        cleaned.replace("&nbsp;", " ")
        .replace("&ensp;", " ")
        .replace("&emsp;", " ")
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


def _map_choice(value: str | None, table: dict[str, str], default: str, label: str) -> str:
    key = safe_str(value) or default
    if key in table:
        return table[key]
    mapped = table.get(key.lower())
    if mapped is not None:
        return mapped
    raise ValueError(f"未知 {label}: {value}；可用 {', '.join(sorted(set(table)))}")


def resolve_src(src: str | None) -> str:
    return _map_choice(src, SOURCES, "news", "src")


def resolve_field(field: str | None) -> str:
    return _map_choice(field, FIELDS, "title", "field")


def resolve_sort(sort: str | None) -> str:
    return _map_choice(sort, SORTS, "time", "sort")


def _parse_day(value: str | date | datetime | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=TZ_CN)
        return dt.astimezone(TZ_CN).date()
    if isinstance(value, date):
        return value
    text = safe_str(value).replace("/", "-")
    m = _DATE_CN_RE.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
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


# ---------------------------------------------------------------------------
# 列表解析
# ---------------------------------------------------------------------------


def _parse_pub_time(text: str, url: str = "") -> str:
    raw = strip_html(text)
    day = _parse_day(raw)
    if day is None and url:
        m = _DATE_IN_URL_RE.search(url)
        if m:
            day = _parse_day(m.group(1))
    if day is None:
        return ""
    return datetime(day.year, day.month, day.day, tzinfo=TZ_CN).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _node_text(node: Any) -> str:
    if node is None:
        return ""
    if hasattr(node, "decode_contents"):
        return strip_html(node.decode_contents())
    return strip_html(node.get_text())


def _field_map(info: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if info is None:
        return out
    for span in info.select("span"):
        strong = span.find("strong")
        label = _node_text(strong).rstrip("：:")
        if not label:
            continue
        value = _node_text(span)
        if value.startswith(label):
            value = value[len(label) :].lstrip("：:").strip()
        out[label] = value
    return out


def _article_id(url: str) -> str:
    m = _ARTICLE_ID_RE.search(url)
    if m:
        return m.group(1)
    m = _EPAPER_ID_RE.search(url)
    if m:
        return m.group(1)
    return ""


def _clean_title(title: str) -> str:
    return _RANK_RE.sub("", strip_html(title)).strip()


def _normalize_pair(
    dt: Any,
    dd: Any,
    *,
    code: str = "",
    name: str = "",
) -> dict[str, Any] | None:
    title_a = dt.find("a", href=True) if dt is not None else None
    if title_a is None:
        return None
    title = _clean_title(_node_text(title_a.find("h4") or title_a))
    if not title:
        return None
    href = safe_str(title_a.get("href"))
    url = urljoin(HOME, href) if href else ""
    info = dd.select_one(".field-info") if dd is not None else None
    fields = _field_map(info)
    summary_p = None
    if dd is not None:
        for p in dd.find_all("p"):
            classes = p.get("class") or []
            if "field-info" in classes:
                continue
            summary_p = p
            break
    origin = fields.get("媒体") or ""
    return {
        "code": code,
        "name": name,
        "title": title,
        "summary": _node_text(summary_p),
        "published_at": _parse_pub_time(fields.get("时间", ""), url),
        "url": url,
        "source": origin or "证券日报",
        "channel": "zqrb",
        "column": fields.get("栏目") or "",
        "author": fields.get("作者") or "",
        "origin": origin,
        "article_id": _article_id(url),
    }


def parse_list_html(
    html: str,
    *,
    code: str = "",
    name: str = "",
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "lxml")
    items: list[dict[str, Any]] = []
    result_list = soup.select_one("dl.result-list")
    if result_list is None:
        return items
    dts = result_list.find_all("dt", recursive=False)
    for dt in dts:
        sibling = dt.find_next_sibling()
        dd = sibling if sibling is not None and sibling.name == "dd" else None
        item = _normalize_pair(dt, dd, code=code, name=name)
        if item:
            items.append(item)
    return items


def parse_total(html: str) -> int:
    soup = BeautifulSoup(html or "", "lxml")
    result = soup.select_one("p.result")
    text = _node_text(result) if result is not None else ""
    m = _TOTAL_RE.search(text) or _TOTAL_RE.search(html or "")
    if not m:
        return 0
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return 0


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
    src: str = "news",
    field: str = "title",
    sort: str = "newsdate_DESC",
    fuzzy: bool = False,
) -> dict[str, Any]:
    """证券日报网检索单页原始 HTML。"""
    kw = safe_str(keyword)
    params: dict[str, Any] = {
        "src": src or "news",
        "q": kw,
        "f": field or "title",
        "s": sort or "newsdate_DESC",
        "p": max(1, int(page)),
    }
    if fuzzy:
        params["m"] = "yes"
    resp = browser_get(
        SEARCH_API,
        params=params,
        headers=_headers(kw),
        timeout=25,
    )
    resp.raise_for_status()
    html = resp.content.decode("utf-8", errors="replace")
    return {
        "url": search_page_url(
            kw,
            src=params["src"],
            field=params["f"],
            sort=params["s"],
            fuzzy=fuzzy,
            page=int(params["p"]),
        ),
        "html": html,
        "total": parse_total(html),
        "items": parse_list_html(html),
    }


def _empty_pack(code: str, name: str, keyword: str, *, error: str = "", **extra: Any) -> dict[str, Any]:
    pack = {
        "code": code,
        "name": name,
        "keyword": keyword,
        "source": "zqrb",
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
    src: str | None = "news",
    field: str | None = "title",
    sort: str | None = "time",
    fuzzy: bool | None = False,
    max_pages: int = 5,
) -> dict[str, Any]:
    """按股票代码或公司简称拉取证券日报网新闻。

    接口按关键词全文检索，代码请先解析成简称（本函数会自动 resolve）。
    ``src``：``news`` 新闻 / ``all`` 全部 / ``epaper`` 电子报。
    ``field``：``title`` 标题 / ``all`` 全文 / ``author`` 作者。
    接口无日期参数，按时间倒序翻页后在本地按起止日期过滤。
    """
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"]
    name = resolved["name"]
    keyword = resolved["keyword"]
    if not keyword:
        return _empty_pack(code, name, keyword, error="缺少检索关键词")

    api_src = resolve_src(src)
    api_field = resolve_field(field)
    api_sort = resolve_sort(sort)
    use_fuzzy = bool(fuzzy)
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
                src=api_src,
                field=api_field,
                sort=api_sort,
                fuzzy=use_fuzzy,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("证券日报网检索失败 page=%s: %s", page, exc)
            if page == 1:
                return _empty_pack(
                    code,
                    name,
                    keyword,
                    error=str(exc),
                    src=api_src,
                    field=api_field,
                    sort=api_sort,
                    fuzzy=use_fuzzy,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        rows = payload.get("items") or []
        if not isinstance(rows, list):
            rows = []
        total = int(payload.get("total") or total)
        if total:
            total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        if not rows:
            break
        oldest: date | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            item["code"] = code
            item["name"] = name
            day = _parse_day(item.get("published_at"))
            if day and (oldest is None or day < oldest):
                oldest = day
            if _in_range(item, start_d, end_d):
                items.append(item)
        if start_d and oldest and oldest < start_d:
            break
        if len(rows) < 1:
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
        "src": api_src,
        "field": api_field,
        "sort": api_sort,
        "fuzzy": use_fuzzy,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": "zqrb",
        "channel": "news",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": search_page_url(
            keyword,
            src=api_src,
            field=api_field,
            sort=api_sort,
            fuzzy=use_fuzzy,
        ),
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
    parser = argparse.ArgumentParser(description="从证券日报网检索上市公司相关新闻")
    parser.add_argument("code", help="股票代码或公司简称，如 600519 / 贵州茅台")
    parser.add_argument("--days", type=int, default=31, help="回溯天数，默认 31")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--src",
        default="news",
        help="news 新闻 / all 全部 / epaper 电子报",
    )
    parser.add_argument(
        "--field",
        default="title",
        help="title 标题 / all 全文 / author 作者",
    )
    parser.add_argument(
        "--sort",
        default="time",
        help="time 按时间 / relevance 按相关度",
    )
    parser.add_argument("--fuzzy", action="store_true", help="模糊搜索")
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
        src=args.src,
        field=args.field,
        sort=args.sort,
        fuzzy=args.fuzzy,
        max_pages=args.max_pages,
    )
    _print_items(pack, args.limit, args.json)
    return 1 if pack.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
