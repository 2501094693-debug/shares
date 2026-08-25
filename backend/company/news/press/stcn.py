"""证券时报网文章检索：按公司简称搜证券时报 / 证券时报网新闻。

官网检索页：
  https://www.stcn.com/article/search.html?keyword=贵州茅台&search_type=news&sorter=time

公开接口（需先访问官网首页 + 检索页拿到 Cookie，并带 XHR Referer）：
  GET https://www.stcn.com/article/search_data.html
  - keyword       关键词（用简称，不要用六位代码）
  - search_type   all / news / report / activity / video / topic / stock
  - sorter        time=按时间 / relative=按相关度
  - uncertainty   1=精确（默认） / 0=模糊
  - page_time     页码，从 1 起；返回 HTML 列表片段

    python company/news/press/stcn.py 600519
    python company/news/press/stcn.py 贵州茅台 --days 7
    python company/news/press/stcn.py 600519 --type all --json
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

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))

HOME = "https://www.stcn.com/"
SEARCH_API = "https://www.stcn.com/article/search_data.html"
SEARCH_PAGE = "https://www.stcn.com/article/search.html"
SITE_ORIGIN = "https://www.stcn.com"
PAGE_SIZE = 20
REQUEST_PAUSE_SEC = 0.25
MAX_PAGES = 50
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

TYPES: dict[str, str] = {
    "all": "all",
    "全部": "all",
    "news": "news",
    "资讯": "news",
    "新闻": "news",
    "report": "report",
    "公告": "report",
    "activity": "activity",
    "直播": "activity",
    "video": "video",
    "视频": "video",
    "topic": "topic",
    "专题": "topic",
    "stock": "stock",
    "股票": "stock",
}
SORTS: dict[str, str] = {
    "time": "time",
    "时间": "time",
    "relative": "relative",
    "relevance": "relative",
    "相关度": "relative",
}


# ---------------------------------------------------------------------------
# HTTP / 文本
# ---------------------------------------------------------------------------


def _new_session():
    try:
        from curl_cffi import requests as curl_requests

        return curl_requests.Session(impersonate="chrome")
    except ImportError:  # pragma: no cover
        import requests

        sess = requests.Session()
        sess.headers.update({"User-Agent": _UA})
        return sess


def _warm_session(
    sess: Any,
    keyword: str = "",
    *,
    search_type: str = "news",
    sorter: str = "time",
    uncertainty: str = "1",
) -> None:
    """证券时报检索接口依赖 Cookie；需先打首页，再打开检索页。"""
    html_headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    sess.get(HOME, timeout=20, headers=html_headers)
    page = search_page_url(
        keyword,
        search_type=search_type,
        sorter=sorter,
        uncertainty=uncertainty,
    )
    sess.get(page, timeout=25, headers={**html_headers, "Referer": HOME})


def search_page_url(
    keyword: str = "",
    *,
    search_type: str = "news",
    sorter: str = "time",
    uncertainty: str = "1",
) -> str:
    kw = safe_str(keyword)
    params = [
        f"search_type={quote(search_type or 'news')}",
        f"uncertainty={quote(uncertainty or '1')}",
        f"sorter={quote(sorter or 'time')}",
    ]
    if kw:
        params.insert(0, f"keyword={quote(kw)}")
    return f"{SEARCH_PAGE}?{'&'.join(params)}"


def strip_html(text: str) -> str:
    cleaned = _HTML_TAG_RE.sub("", safe_str(text))
    return (
        cleaned.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("\xa0", " ")
        .replace("\u3000", " ")
        .strip()
    )


def resolve_type(kind: str | None) -> str:
    key = safe_str(kind) or "news"
    if key in TYPES:
        return TYPES[key]
    mapped = TYPES.get(key.lower())
    if mapped is not None:
        return mapped
    raise ValueError(
        f"未知 type: {kind}；可用 all / news / report / activity / video / topic / stock"
    )


def resolve_sort(sort: str | None) -> str:
    key = safe_str(sort) or "time"
    if key in SORTS:
        return SORTS[key]
    mapped = SORTS.get(key.lower())
    if mapped is not None:
        return mapped
    raise ValueError(f"未知 sort: {sort}；可用 time / relative")


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


def _parse_pub_time(text: str) -> str:
    raw = strip_html(text)
    if not raw:
        return ""
    now = datetime.now(TZ_CN)
    for fmt, size in (
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%d %H:%M", 16),
        ("%Y-%m-%d", 10),
    ):
        try:
            dt = datetime.strptime(raw[:size], fmt).replace(tzinfo=TZ_CN)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    m = re.match(r"^(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?$", raw)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        hour = int(m.group(3) or 0)
        minute = int(m.group(4) or 0)
        year = now.year
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=TZ_CN)
        except ValueError:
            return ""
        if dt.date() > now.date():
            try:
                dt = dt.replace(year=year - 1)
            except ValueError:
                return ""
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return ""


def _node_text(node: Any) -> str:
    if node is None:
        return ""
    return strip_html(node.decode_contents() if hasattr(node, "decode_contents") else node.get_text())


def _extract_html(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        html = data.get("data")
        return html if isinstance(html, str) else ""
    return ""


def _normalize_li(
    li: Any,
    *,
    code: str = "",
    name: str = "",
) -> dict[str, Any] | None:
    title_a = li.select_one(".tt a[href*='/article/detail']") or li.select_one(
        "a[href*='/article/detail']"
    )
    if title_a is None:
        return None
    title = _node_text(title_a)
    if not title:
        return None
    href = safe_str(title_a.get("href"))
    url = urljoin(SITE_ORIGIN, href) if href else ""
    summary_a = li.select_one(".text a")
    summary = _node_text(summary_a)
    spans = [_node_text(s) for s in li.select(".info span")]
    spans = [s for s in spans if s]
    published_at = ""
    column = ""
    author = ""
    if spans:
        published_at = _parse_pub_time(spans[-1])
        if len(spans) >= 2:
            column = spans[0]
        if len(spans) >= 3:
            author = spans[1]
        elif len(spans) == 2 and not published_at:
            column = spans[0]
            published_at = _parse_pub_time(spans[1])
    tags = [
        _node_text(a)
        for a in li.select(".tags a")
        if _node_text(a)
    ]
    article_id = ""
    m = re.search(r"/article/detail/(\d+)", href)
    if m:
        article_id = m.group(1)
    return {
        "code": code,
        "name": name,
        "title": title,
        "summary": summary,
        "published_at": published_at,
        "url": url,
        "source": "证券时报",
        "channel": "stcn",
        "column": column,
        "author": author,
        "tags": tags,
        "article_id": article_id,
    }


def parse_list_html(
    html: str,
    *,
    code: str = "",
    name: str = "",
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "lxml")
    items: list[dict[str, Any]] = []
    for li in soup.select("li"):
        item = _normalize_li(li, code=code, name=name)
        if item:
            items.append(item)
    return items


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
    search_type: str = "news",
    sorter: str = "time",
    uncertainty: str = "1",
    session: Any | None = None,
) -> dict[str, Any]:
    """证券时报网检索单页原始 JSON（``data`` 多为 HTML 片段）。"""
    kw = safe_str(keyword)
    own_session = session is None
    sess = session or _new_session()
    if own_session:
        _warm_session(
            sess,
            kw,
            search_type=search_type,
            sorter=sorter,
            uncertainty=uncertainty,
        )
    params = {
        "search_type": search_type or "news",
        "keyword": kw,
        "uncertainty": uncertainty or "1",
        "sorter": sorter or "time",
        "page_time": max(1, int(page)),
    }
    referer = search_page_url(
        kw,
        search_type=search_type,
        sorter=sorter,
        uncertainty=uncertainty,
    )
    headers = {
        "User-Agent": _UA,
        "Referer": referer,
        "Origin": SITE_ORIGIN,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    resp = sess.get(SEARCH_API, params=params, headers=headers, timeout=25)
    resp.raise_for_status()
    payload = resp.json()
    return payload if isinstance(payload, dict) else {}


def _empty_pack(code: str, name: str, keyword: str, *, error: str = "", **extra: Any) -> dict[str, Any]:
    pack = {
        "code": code,
        "name": name,
        "keyword": keyword,
        "source": "stcn",
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
    type_: str | None = "news",
    sort: str | None = "time",
    uncertainty: str | int | None = 1,
    max_pages: int = 5,
) -> dict[str, Any]:
    """按股票代码或公司简称拉取证券时报网新闻。

    接口按关键词全文检索，代码请先解析成简称（本函数会自动 resolve）。
    ``type_``：``news`` 资讯 / ``all`` 全部 / ``report`` 公告 等。
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
    unc = safe_str(uncertainty if uncertainty is not None else "1") or "1"
    start_d, end_d = _date_range(start, end, days)

    sess = _new_session()
    try:
        _warm_session(
            sess,
            keyword,
            search_type=api_type,
            sorter=api_sort,
            uncertainty=unc,
        )
    except Exception as exc:  # noqa: BLE001
        return _empty_pack(
            code,
            name,
            keyword,
            error=f"初始化会话失败: {exc}",
            type=api_type,
            sort=api_sort,
        )

    items: list[dict[str, Any]] = []
    page = 1
    limit = max(1, int(max_pages))
    while page <= limit:
        try:
            payload = query_page(
                keyword,
                page=page,
                search_type=api_type,
                sorter=api_sort,
                uncertainty=unc,
                session=sess,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("证券时报网检索失败 page=%s: %s", page, exc)
            if page == 1:
                return _empty_pack(
                    code,
                    name,
                    keyword,
                    error=str(exc),
                    type=api_type,
                    sort=api_sort,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        if int(payload.get("state") if payload.get("state") is not None else 1) == 0 and page == 1:
            return _empty_pack(
                code,
                name,
                keyword,
                error=safe_str(payload.get("msg")) or "检索接口返回失败",
                type=api_type,
                sort=api_sort,
            )
        html = _extract_html(payload)
        rows = parse_list_html(html, code=code, name=name)
        if not rows:
            break
        oldest: date | None = None
        for item in rows:
            day = _parse_day(item.get("published_at"))
            if day and (oldest is None or day < oldest):
                oldest = day
            if _in_range(item, start_d, end_d):
                items.append(item)
        if start_d and oldest and oldest < start_d:
            break
        if len(rows) < 1:
            break
        page += 1
        if page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = _dedupe(items)
    return {
        "code": code,
        "name": name,
        "keyword": keyword,
        "type": api_type,
        "sort": api_sort,
        "uncertainty": unc,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": "stcn",
        "channel": "news",
        "count": len(items),
        "total": len(items),
        "items": items,
        "page": search_page_url(
            keyword,
            search_type=api_type,
            sorter=api_sort,
            uncertainty=unc,
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
        origin = row.get("column") or row.get("source") or ""
        origin_bit = f" [{origin}]" if origin else ""
        _cli_print(f"  [{i}] {day}{origin_bit} {row.get('title')}")
        if row.get("url"):
            _cli_print(f"       {row['url']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="从证券时报网检索上市公司相关新闻")
    parser.add_argument("code", help="股票代码或公司简称，如 600519 / 贵州茅台")
    parser.add_argument("--days", type=int, default=31, help="回溯天数，默认 31")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--type",
        dest="kind",
        default="news",
        help="news 资讯 / all 全部 / report 公告 / video 视频 / topic 专题 / stock 股票",
    )
    parser.add_argument(
        "--sort",
        default="time",
        help="time 按时间 / relative 按相关度",
    )
    parser.add_argument(
        "--fuzzy",
        action="store_true",
        help="模糊搜索（uncertainty=0）",
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
        type_=args.kind,
        sort=args.sort,
        uncertainty="0" if args.fuzzy else "1",
        max_pages=args.max_pages,
    )
    _print_items(pack, args.limit, args.json)
    return 1 if pack.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
