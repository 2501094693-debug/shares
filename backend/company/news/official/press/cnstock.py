"""中国证券网文章检索：按公司简称搜上海证券报 / 中国证券网新闻。

官网检索页：
  https://www.cnstock.com/searchResult?word=贵州茅台

公开接口（需带 ``cnstock-client-type: 01``）：
  POST https://api.cnstock.com/search/v2/news
  - word      关键词（用简称，不要用六位代码）
  - pageNum   页码，从 1 起
  - pageSize  官网固定按 20 条返回
  - type      0=全部 / 1=新闻 / 2=视频 / 3=专题 / 4=活动 / 5=路演 / 6=股票

    python company/news/press/cnstock.py 600519
    python company/news/press/cnstock.py 贵州茅台 --days 7
    python company/news/press/cnstock.py 600519 --type all --json
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

SEARCH_API = "https://api.cnstock.com/search/v2/news"
SEARCH_PAGE = "https://www.cnstock.com/searchResult"
ARTICLE_BASE = "https://www.cnstock.com/commonDetail"
PAGE_SIZE = 20
REQUEST_PAUSE_SEC = 0.25
MAX_PAGES = 50
_HTML_TAG_RE = re.compile(r"<[^>]+>")

TYPES: dict[str, str] = {
    "all": "0",
    "全部": "0",
    "0": "0",
    "news": "1",
    "新闻": "1",
    "1": "1",
    "video": "2",
    "视频": "2",
    "2": "2",
    "topic": "3",
    "专题": "3",
    "3": "3",
    "activity": "4",
    "活动": "4",
    "4": "4",
    "roadshow": "5",
    "路演": "5",
    "5": "5",
    "stock": "6",
    "股票": "6",
    "6": "6",
}


# ---------------------------------------------------------------------------
# HTTP / 文本
# ---------------------------------------------------------------------------


def _headers(keyword: str = "") -> dict[str, str]:
    referer = search_page_url(keyword) if keyword else f"{SEARCH_PAGE}?word="
    return {
        "Referer": referer,
        "Origin": "https://www.cnstock.com",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "cnstock-client-type": "01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def search_page_url(keyword: str = "") -> str:
    kw = safe_str(keyword)
    if kw:
        return f"{SEARCH_PAGE}?word={quote(kw)}"
    return SEARCH_PAGE


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
    raise ValueError(f"未知 type: {kind}；可用 all / news / video / topic / activity / roadshow / stock")


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


# ---------------------------------------------------------------------------
# 列表解析
# ---------------------------------------------------------------------------


def _intish(value: Any, default: int = 0) -> int:
    text = safe_str(value)
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def _date_info(row: dict[str, Any]) -> dict[str, Any]:
    share = row.get("shareInfo") if isinstance(row.get("shareInfo"), dict) else {}
    info = share.get("dateInfo") if isinstance(share.get("dateInfo"), dict) else {}
    return info if isinstance(info, dict) else {}


def _published_at(row: dict[str, Any]) -> str:
    info = _date_info(row)
    year = info.get("year")
    month = info.get("month")
    day = info.get("day")
    if year not in (None, "") and month not in (None, "") and day not in (None, ""):
        hour = info.get("hour") if info.get("hour") not in (None, "") else 0
        minute = info.get("minute") if info.get("minute") not in (None, "") else 0
        try:
            dt = datetime(
                int(year),
                int(month),
                int(day),
                int(hour),
                int(minute),
                tzinfo=TZ_CN,
            )
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            pass
    return _parse_pub_time(safe_str(row.get("pubTime")))


def _parse_pub_time(text: str) -> str:
    raw = strip_html(text)
    if not raw:
        return ""
    now = datetime.now(TZ_CN)
    compact = raw.replace(" ", "")
    if compact in {"刚刚", "刚才"}:
        return now.strftime("%Y-%m-%d %H:%M:%S")
    m = re.match(r"^(\d+)(秒|分钟|小时|天)前$", compact)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        delta = {
            "秒": timedelta(seconds=n),
            "分钟": timedelta(minutes=n),
            "小时": timedelta(hours=n),
            "天": timedelta(days=n),
        }[unit]
        return (now - delta).strftime("%Y-%m-%d %H:%M:%S")
    if compact == "昨天":
        return (now - timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    if compact == "前天":
        return (now - timedelta(days=2)).strftime("%Y-%m-%d 00:00:00")
    for fmt, size in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10), ("%m-%d", 5)):
        try:
            dt = datetime.strptime(raw[:size], fmt)
        except ValueError:
            continue
        if fmt == "%m-%d":
            dt = dt.replace(year=now.year)
            if dt.date() > now.date():
                dt = dt.replace(year=now.year - 1)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_CN)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return ""


def _article_url(row: dict[str, Any]) -> str:
    link = safe_str(row.get("link"))
    if link.startswith("http"):
        return link
    cont_id = safe_str(row.get("contId"))
    if cont_id:
        return f"{ARTICLE_BASE}/{cont_id}"
    share = row.get("shareInfo") if isinstance(row.get("shareInfo"), dict) else {}
    share_url = safe_str(share.get("shareUrl"))
    if share_url.startswith("http"):
        return share_url.replace("https://m.cnstock.com/", "https://www.cnstock.com/")
    return ""


def _normalize_row(
    row: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
) -> dict[str, Any] | None:
    title = strip_html(safe_str(row.get("name") or row.get("title")))
    if not title:
        return None
    node = row.get("nodeInfo") if isinstance(row.get("nodeInfo"), dict) else {}
    tag = row.get("tagInfo") if isinstance(row.get("tagInfo"), dict) else {}
    return {
        "code": code,
        "name": name,
        "title": title,
        "summary": strip_html(safe_str(row.get("summary"))),
        "published_at": _published_at(row),
        "url": _article_url(row),
        "source": "上海证券报",
        "channel": "cnstock",
        "column": strip_html(safe_str(node.get("name"))),
        "author": strip_html(safe_str(row.get("author"))),
        "tag": strip_html(safe_str(tag.get("name"))).lstrip("#"),
        "cont_id": safe_str(row.get("contId")),
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
    type_: str = "1",
) -> dict[str, Any]:
    """中国证券网检索单页原始 JSON。"""
    kw = safe_str(keyword)
    body = {
        "word": kw,
        "pageNum": max(1, int(page)),
        "pageSize": max(1, min(int(page_size), 50)),
        "type": type_ or "1",
    }
    resp = browser_post(
        SEARCH_API,
        json_body=body,
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
        "source": "cnstock",
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
    max_pages: int = 5,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """按股票代码或公司简称拉取中国证券网新闻。

    接口按关键词全文检索，代码请先解析成简称（本函数会自动 resolve）。
    ``type_``：``news`` 新闻 / ``all`` 全部 / ``video`` 视频 等。
    接口无日期参数，按时间倒序翻页后在本地按起止日期过滤。
    """
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"]
    name = resolved["name"]
    keyword = resolved["keyword"]
    if not keyword:
        return _empty_pack(code, name, keyword, error="缺少检索关键词")

    api_type = resolve_type(type_)
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
                page_size=page_size,
                type_=api_type,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("中国证券网检索失败 page=%s: %s", page, exc)
            if page == 1:
                return _empty_pack(
                    code,
                    name,
                    keyword,
                    error=str(exc),
                    type=api_type,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        if int(payload.get("code") or 0) != 200 and page == 1:
            return _empty_pack(
                code,
                name,
                keyword,
                error=safe_str(payload.get("desc")) or "检索接口返回失败",
                type=api_type,
            )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        rows = data.get("list") or []
        if not isinstance(rows, list):
            rows = []
        total = _intish(data.get("total"), total)
        total_pages = _intish(data.get("pages"), 0) or total_pages
        if total and not _intish(data.get("pages"), 0):
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
        if start_d and oldest and oldest < start_d:
            break
        has_next = bool(data.get("hasNext"))
        if page >= total_pages or not has_next:
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
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": "cnstock",
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
        origin = row.get("column") or row.get("source") or ""
        origin_bit = f" [{origin}]" if origin else ""
        _cli_print(f"  [{i}] {day}{origin_bit} {row.get('title')}")
        if row.get("url"):
            _cli_print(f"       {row['url']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="从中国证券网检索上市公司相关新闻")
    parser.add_argument("code", help="股票代码或公司简称，如 600519 / 贵州茅台")
    parser.add_argument("--days", type=int, default=31, help="回溯天数，默认 31")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--type",
        dest="kind",
        default="news",
        help="news 新闻 / all 全部 / video 视频 / topic 专题 / stock 股票",
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
        max_pages=args.max_pages,
    )
    _print_items(pack, args.limit, args.json)
    return 1 if pack.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
