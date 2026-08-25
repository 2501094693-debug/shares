"""上海证券交易所公告：个股检索、分类/关键词、全市场最新、监管问询、PDF 下载。

官网个股页：
  https://www.sse.com.cn/assortment/stock/list/info/announcement/index.shtml?productId=600000
全市场最新：
  https://www.sse.com.cn/disclosure/listedinfo/announcement/
监管问询：
  https://www.sse.com.cn/disclosure/credibility/supervision/inquiries/

三套公开查询（均要带官网 Referer，否则 query.sse.com.cn 常 403）：
  1. queryCompanyBulletin.do     个股公告全文
  2. queryLatestBulletinNew.do   全市场 / 最新公告栏目
  3. commonSoaQuery.do           问询函 / 关注函 / 重组问询

    python company/news/sse.py 600519
    python company/news/sse.py 600519 --days 90
    python company/news/sse.py 600519 --category annual
    python company/news/sse.py 600519 --keyword 问询函
    python company/news/sse.py 600519 --inquiries
    python company/news/sse.py 688981 --category yearly --days 800
    python company/news/sse.py --latest --days 7 --limit 20
    python company/news/sse.py --latest --category annual --days 30
    python company/news/sse.py 600519 --download ./pdfs --limit 3
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
from typing import Any, Iterable, Sequence
from urllib.parse import unquote, urlparse

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import detect_market, normalize_code, safe_str
from core.http import browser_get

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))

BULLETIN_URL = "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do"
LATEST_URL = "https://query.sse.com.cn/infodisplay/queryLatestBulletinNew.do"
INQUIRE_URL = "https://query.sse.com.cn/commonSoaQuery.do"
PDF_PREFIX = "https://static.sse.com.cn"
SITE_PREFIX = "https://www.sse.com.cn"

BULLETIN_PAGE = (
    "https://www.sse.com.cn/assortment/stock/list/info/announcement/index.shtml"
)
LATEST_PAGE = "https://www.sse.com.cn/disclosure/listedinfo/announcement/"
INQUIRE_PAGE = "https://www.sse.com.cn/disclosure/credibility/supervision/inquiries/"

PAGE_SIZE = 25
INQUIRE_PAGE_SIZE = 15
REQUEST_PAUSE_SEC = 0.25
MAX_PAGES = 50
DEFAULT_CHUNK_DAYS = 366

# 个股页默认带上 A 股 / B 股 / 可转债等相关品种，避免漏可转债公告。
SECURITY_TYPE_ALL = "0101,120100,020100,020200,120200"
SECURITY_TYPES: dict[str, str] = {
    "all": SECURITY_TYPE_ALL,
    "full": SECURITY_TYPE_ALL,
    "a": "0101",
    "0101": "0101",
    "main": "0101",
    "主板": "0101",
    "star": "0101",
    "kcb": "0101",
    "科创板": "0101",
    "b": "020100",
    "020100": "020100",
    "bshare": "020100",
    "b股": "020100",
    "cbond": "120100",
    "120100": "120100",
    "可转债": "120100",
    "020200": "020200",
    "120200": "120200",
    "auto": "auto",
}

# (reportType, reportType2)。接口里季报拼写是 QUATER，少一个 R。
# 个股接口定期报告用 DQBG；最新公告栏目定期用 DQGG。
_REPORT_DQBG: dict[str, tuple[str, str]] = {
    "all": ("ALL", ""),
    "全部": ("ALL", ""),
    "yearly": ("YEARLY", "DQBG"),
    "annual": ("YEARLY", "DQBG"),
    "年报": ("YEARLY", "DQBG"),
    "year": ("YEARLY", "DQBG"),
    "semi": ("QUATER2", "DQBG"),
    "半年报": ("QUATER2", "DQBG"),
    "中报": ("QUATER2", "DQBG"),
    "q2": ("QUATER2", "DQBG"),
    "q1": ("QUATER1", "DQBG"),
    "一季报": ("QUATER1", "DQBG"),
    "quater1": ("QUATER1", "DQBG"),
    "q3": ("QUATER3", "DQBG"),
    "三季报": ("QUATER3", "DQBG"),
    "quater3": ("QUATER3", "DQBG"),
    "quarterly": ("QUATERLY", "DQBG"),
    "季报": ("QUATERLY", "DQBG"),
    "periodic": ("ALL", "DQBG"),
    "定期": ("ALL", "DQBG"),
    "定期报告": ("ALL", "DQBG"),
    "interim": ("ALL", "LSGG"),
    "临时": ("ALL", "LSGG"),
    "临时公告": ("ALL", "LSGG"),
    "listing": ("ALL", "SHGGBS"),
    "上市公告书": ("ALL", "SHGGBS"),
}

_REPORT_DQGG: dict[str, tuple[str, str]] = {
    key: (rt, "DQGG" if rt2 == "DQBG" else rt2)
    for key, (rt, rt2) in _REPORT_DQBG.items()
}

INQUIRE_SQL_ID = "BS_KCB_GGLL"
INQUIRE_SITE_ID = "28"
# 问询函 / 关注函 / 重组问询
INQUIRE_CHANNEL_IDS = "10743,10744,10012"

_JSONP_RE = re.compile(r"^[^(]+\((.*)\)\s*;?\s*$", re.DOTALL)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _headers(referer: str) -> dict[str, str]:
    return {
        "Referer": referer,
        "Origin": "https://www.sse.com.cn",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def _parse_jsonp(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = _JSONP_RE.match(raw)
    body = match.group(1).strip() if match else ""
    if not body:
        start, end = raw.find("("), raw.rfind(")")
        if start >= 0 and end > start:
            body = raw[start + 1 : end].strip()
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _get_payload(
    url: str,
    *,
    params: dict[str, Any],
    referer: str,
    timeout: int = 30,
) -> dict[str, Any]:
    resp = browser_get(
        url,
        params=params,
        headers=_headers(referer),
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = _parse_jsonp(resp.text)
    return payload if isinstance(payload, dict) else {}


def bulletin_page_url(code: str = "") -> str:
    c = normalize_code(code)
    if c:
        return f"{BULLETIN_PAGE}?productId={c}"
    return LATEST_PAGE


# ---------------------------------------------------------------------------
# 日期 / 路径
# ---------------------------------------------------------------------------


def _parse_day(value: str | date | datetime | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
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
) -> tuple[date, date]:
    end_d = _parse_day(end) or date.today()
    start_d = _parse_day(start)
    if start_d is None:
        lookback = 365 if days is None else max(1, int(days))
        start_d = end_d - timedelta(days=lookback)
    if start_d > end_d:
        start_d, end_d = end_d, start_d
    return start_d, end_d


def _date_windows(
    start_d: date,
    end_d: date,
    *,
    chunk_days: int,
) -> list[tuple[date, date]]:
    span = (end_d - start_d).days + 1
    size = max(1, int(chunk_days))
    if span <= size:
        return [(start_d, end_d)]
    windows: list[tuple[date, date]] = []
    cursor = start_d
    while cursor <= end_d:
        chunk_end = min(cursor + timedelta(days=size - 1), end_d)
        windows.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return windows


def _fmt_dt(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=TZ_CN)
        return dt.astimezone(TZ_CN).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=TZ_CN).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    text = safe_str(value)
    if not text:
        return ""
    parsed = _parse_day(text)
    if parsed and len(text) <= 10:
        return f"{parsed.isoformat()} 00:00:00"
    return text[:19]


def pdf_url(path: str) -> str:
    """把接口返回的相对路径拼成可下载地址。"""
    raw = safe_str(path).strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        return f"https:{raw}"
    if raw.lower().startswith("http://") or raw.lower().startswith("https://"):
        return raw
    if raw.startswith("www."):
        return f"https://{raw}"
    return f"{PDF_PREFIX.rstrip('/')}/{raw.lstrip('/')}"


def is_sse_code(code: str) -> bool:
    """沪市股票 / CDR / B 股 / 沪市可转债。"""
    c = normalize_code(code)
    if not c:
        return False
    if c.startswith(("60", "68", "90", "11")):
        return True
    return detect_market(c) == "sse"


# ---------------------------------------------------------------------------
# 参数规范化
# ---------------------------------------------------------------------------


def resolve_security_type(security_type: str | None, code: str = "") -> str:
    key = safe_str(security_type).lower() or "auto"
    if key in SECURITY_TYPES and SECURITY_TYPES[key] != "auto":
        return SECURITY_TYPES[key]
    c = normalize_code(code)
    if c.startswith("90"):
        return "020100"
    if c.startswith("11"):
        return "120100"
    # 科创板单独传 0101 经常 0 条；主板带全品种也不会串到别的公司（有 productId）
    return SECURITY_TYPE_ALL


def resolve_report_type(
    category: str | None,
    *,
    latest: bool = False,
    report_type: str | None = None,
    report_type2: str | None = None,
) -> tuple[str, str]:
    """返回 ``(reportType, reportType2)``。原始编码优先于别名。"""
    if report_type or report_type2:
        return (safe_str(report_type) or "ALL", safe_str(report_type2))
    key = safe_str(category).strip()
    if not key:
        return ("ALL", "")
    table = _REPORT_DQGG if latest else _REPORT_DQBG
    mapped = table.get(key) or table.get(key.lower())
    if mapped:
        return mapped
    raise ValueError(
        f"未知 category: {category}；可用 {', '.join(sorted(set(_REPORT_DQBG)))}"
    )


# ---------------------------------------------------------------------------
# 列表解析
# ---------------------------------------------------------------------------


def _rows_from_payload(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    help_ = payload.get("pageHelp") if isinstance(payload.get("pageHelp"), dict) else {}
    rows = help_.get("data") or payload.get("result") or []
    if not isinstance(rows, list):
        rows = []
    total = int(help_.get("total") or 0)
    page_count = int(help_.get("pageCount") or 0)
    return rows, total, page_count


def _normalize_bulletin(
    row: dict[str, Any],
    *,
    fallback_code: str = "",
    channel: str = "bulletin",
) -> dict[str, Any] | None:
    title = safe_str(row.get("TITLE") or row.get("title"))
    if not title:
        return None
    path = safe_str(row.get("URL") or row.get("url"))
    published = _fmt_dt(
        row.get("SSEDATE") or row.get("ADDDATE") or row.get("sseDate") or row.get("addDate")
    )
    code = normalize_code(safe_str(row.get("SECURITY_CODE") or row.get("securityCode")))
    return {
        "code": code or fallback_code,
        "name": safe_str(row.get("SECURITY_NAME") or row.get("securityName")),
        "title": title,
        "published_at": published,
        "url": pdf_url(path),
        "adjunct_url": path,
        "adjunct_type": "PDF" if path.lower().endswith(".pdf") else "",
        "category": safe_str(row.get("BULLETIN_TYPE") or row.get("bulletinType")),
        "heading": safe_str(row.get("BULLETIN_HEADING") or row.get("bulletinHeading")),
        "channel": channel,
        "source": "上海证券交易所",
    }


def _normalize_inquiry(
    row: dict[str, Any],
    *,
    fallback_code: str = "",
) -> dict[str, Any] | None:
    title = safe_str(row.get("docTitle"))
    if not title:
        return None
    letter_type = safe_str(row.get("extWTFL")) or "问询函"
    published = _fmt_dt(row.get("createTime") or row.get("cmsOpDate"))
    code = normalize_code(
        safe_str(row.get("stockcode") or row.get("extSECURITY_CODE"))
    )
    return {
        "code": code or fallback_code,
        "name": safe_str(row.get("extGSJC")),
        "title": title,
        "published_at": published,
        "url": pdf_url(safe_str(row.get("docURL"))),
        "adjunct_url": safe_str(row.get("docURL")),
        "adjunct_type": safe_str(row.get("docType")) or "PDF",
        "category": letter_type,
        "heading": letter_type,
        "channel": "inquiry",
        "source": "上海证券交易所",
        "doc_id": safe_str(row.get("docId")),
        "sse_channel_id": safe_str(row.get("channelId")),
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


# ---------------------------------------------------------------------------
# 个股公告 queryCompanyBulletin.do
# ---------------------------------------------------------------------------


def query_bulletin_page(
    *,
    product_id: str = "",
    page_no: int = 1,
    page_size: int = PAGE_SIZE,
    begin_date: str = "",
    end_date: str = "",
    security_type: str = SECURITY_TYPE_ALL,
    report_type: str = "ALL",
    report_type2: str = "",
    keyword: str = "",
) -> dict[str, Any]:
    """个股公告单页原始查询。"""
    params: dict[str, Any] = {
        "isPagination": "true",
        "productId": product_id or "",
        "securityType": security_type or SECURITY_TYPE_ALL,
        "reportType": report_type or "ALL",
        "reportType2": report_type2 or "",
        "beginDate": begin_date or "",
        "endDate": end_date or "",
        "keyWord": keyword or "",
        "pageHelp.pageSize": max(1, min(int(page_size), PAGE_SIZE)),
        "pageHelp.pageCount": "50",
        "pageHelp.pageNo": max(1, int(page_no)),
        "pageHelp.beginPage": max(1, int(page_no)),
        "pageHelp.cacheSize": "1",
        "pageHelp.endPage": max(1, int(page_no)),
        "_": int(time.time() * 1000),
    }
    return _get_payload(
        BULLETIN_URL,
        params=params,
        referer=bulletin_page_url(product_id),
    )


def query_latest_page(
    *,
    product_id: str = "",
    page_no: int = 1,
    page_size: int = PAGE_SIZE,
    begin_date: str = "",
    end_date: str = "",
    report_type: str = "ALL",
    report_type2: str = "",
    keyword: str = "",
) -> dict[str, Any]:
    """最新公告栏目单页原始查询。``product_id`` 可空（全市场）。"""
    params: dict[str, Any] = {
        "isPagination": "true",
        "productId": product_id or "",
        "reportType": report_type or "ALL",
        "reportType2": report_type2 or "",
        "beginDate": begin_date or "",
        "endDate": end_date or "",
        "keyWord": keyword or "",
        "pageHelp.pageSize": max(1, min(int(page_size), PAGE_SIZE)),
        "pageHelp.pageCount": "50",
        "pageHelp.pageNo": max(1, int(page_no)),
        "pageHelp.beginPage": max(1, int(page_no)),
        "pageHelp.cacheSize": "1",
        "pageHelp.endPage": max(1, int(page_no)),
        "_": int(time.time() * 1000),
    }
    return _get_payload(LATEST_URL, params=params, referer=LATEST_PAGE)


def _collect_bulletin_pages(
    *,
    product_id: str,
    begin_date: str,
    end_date: str,
    security_type: str,
    report_type: str,
    report_type2: str,
    keyword: str,
    max_pages: int,
    latest: bool,
    channel: str,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    total = 0
    total_pages = 1
    page = 1
    limit = max(1, int(max_pages))
    while page <= total_pages and page <= limit:
        try:
            if latest:
                payload = query_latest_page(
                    product_id=product_id,
                    page_no=page,
                    begin_date=begin_date,
                    end_date=end_date,
                    report_type=report_type,
                    report_type2=report_type2,
                    keyword=keyword,
                )
            else:
                payload = query_bulletin_page(
                    product_id=product_id,
                    page_no=page,
                    begin_date=begin_date,
                    end_date=end_date,
                    security_type=security_type,
                    report_type=report_type,
                    report_type2=report_type2,
                    keyword=keyword,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("上交所公告查询失败 page=%s: %s", page, exc)
            break
        rows, page_total, page_count = _rows_from_payload(payload)
        if page_total:
            total = page_total
        if page_count:
            total_pages = page_count
        elif total:
            total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        if not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _normalize_bulletin(
                row, fallback_code=product_id, channel=channel
            )
            if item:
                items.append(item)
        if page >= total_pages:
            break
        page += 1
        if page <= total_pages and page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)
    return _dedupe(items), total


def _empty_pack(code: str, *, error: str = "", **extra: Any) -> dict[str, Any]:
    pack = {
        "code": normalize_code(code) or safe_str(code),
        "name": "",
        "source": "sse",
        "count": 0,
        "total": 0,
        "items": [],
    }
    pack.update(extra)
    if error:
        pack["error"] = error
    return pack


def fetch_announcements(
    code: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    category: str | None = None,
    keyword: str = "",
    security_type: str | None = "auto",
    report_type: str | None = None,
    report_type2: str | None = None,
    max_pages: int = MAX_PAGES,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
) -> dict[str, Any]:
    """按股票拉取上交所公告（主入口）。

    ``category`` 可用 ``annual`` / ``年报`` / ``semi`` / ``q1`` / ``q3`` /
    ``periodic`` / ``interim``。也可直接传 ``report_type`` / ``report_type2``。
    """
    raw = safe_str(code)
    query_code = normalize_code(raw)
    if not query_code:
        return _empty_pack(raw, error="缺少股票代码")
    if not is_sse_code(query_code):
        return _empty_pack(
            query_code,
            error=f"不是上交所代码: {query_code}",
        )

    rt, rt2 = resolve_report_type(
        category, report_type=report_type, report_type2=report_type2
    )
    sec = resolve_security_type(security_type, query_code)
    start_d, end_d = _date_range(start, end, days)

    items: list[dict[str, Any]] = []
    total = 0
    windows = _date_windows(start_d, end_d, chunk_days=chunk_days)
    for i, (win_start, win_end) in enumerate(windows):
        chunk, chunk_total = _collect_bulletin_pages(
            product_id=query_code,
            begin_date=win_start.isoformat(),
            end_date=win_end.isoformat(),
            security_type=sec,
            report_type=rt,
            report_type2=rt2,
            keyword=safe_str(keyword),
            max_pages=max_pages,
            latest=False,
            channel="bulletin",
        )
        items.extend(chunk)
        total += chunk_total
        if i + 1 < len(windows):
            time.sleep(REQUEST_PAUSE_SEC)

    items = _dedupe(items)
    name = items[0]["name"] if items else ""
    return {
        "code": query_code,
        "name": name,
        "security_type": sec,
        "report_type": rt,
        "report_type2": rt2,
        "keyword": safe_str(keyword),
        "begin_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "source": "sse",
        "channel": "bulletin",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": bulletin_page_url(query_code),
    }


def fetch_periodic_reports(
    code: str,
    *,
    kind: str | Sequence[str] = "annual",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365 * 5,
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """定期报告：annual / semi / q1 / q3，可多选。"""
    if isinstance(kind, str):
        kinds = [p.strip() for p in re.split(r"[;,|]", kind) if p.strip()] or ["annual"]
    else:
        kinds = [safe_str(k) for k in kind if safe_str(k)] or ["annual"]

    merged: list[dict[str, Any]] = []
    packs: list[dict[str, Any]] = []
    for item_kind in kinds:
        pack = fetch_announcements(
            code,
            start=start,
            end=end,
            days=days,
            category=item_kind,
            max_pages=max_pages,
        )
        packs.append(pack)
        merged.extend(pack.get("items") or [])
        time.sleep(REQUEST_PAUSE_SEC)

    items = _dedupe(merged)
    head = packs[0] if packs else _empty_pack(code)
    if any(p.get("error") for p in packs) and not items:
        return head
    out = {
        **head,
        "category": ",".join(kinds),
        "count": len(items),
        "total": len(items),
        "items": items,
    }
    out.pop("error", None)
    return out


def search_announcements(
    code: str,
    keyword: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """按标题关键词搜该公司公告（接口 keyWord）。"""
    return fetch_announcements(
        code,
        start=start,
        end=end,
        days=days,
        keyword=keyword,
        max_pages=max_pages,
    )


def fetch_latest_announcements(
    *,
    code: str = "",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 7,
    category: str | None = None,
    keyword: str = "",
    report_type: str | None = None,
    report_type2: str | None = None,
    max_pages: int = 5,
) -> dict[str, Any]:
    """最新公告栏目。不传代码则全市场；可再按代码/分类收窄。"""
    query_code = normalize_code(code)
    if query_code and not is_sse_code(query_code):
        return _empty_pack(
            query_code,
            channel="latest",
            error=f"不是上交所代码: {query_code}",
        )
    rt, rt2 = resolve_report_type(
        category,
        latest=True,
        report_type=report_type,
        report_type2=report_type2,
    )
    start_d, end_d = _date_range(start, end, days)
    items, total = _collect_bulletin_pages(
        product_id=query_code,
        begin_date=start_d.isoformat(),
        end_date=end_d.isoformat(),
        security_type="",
        report_type=rt,
        report_type2=rt2,
        keyword=safe_str(keyword),
        max_pages=max_pages,
        latest=True,
        channel="latest",
    )
    name = ""
    if query_code:
        for row in items:
            if row.get("code") == query_code and row.get("name"):
                name = row["name"]
                break
    return {
        "code": query_code,
        "name": name,
        "report_type": rt,
        "report_type2": rt2,
        "keyword": safe_str(keyword),
        "begin_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "source": "sse",
        "channel": "latest",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": LATEST_PAGE,
    }


# ---------------------------------------------------------------------------
# 监管问询 commonSoaQuery.do
# ---------------------------------------------------------------------------


def query_inquiry_page(
    *,
    stockcode: str,
    page_no: int = 1,
    page_size: int = INQUIRE_PAGE_SIZE,
    letter_type: str = "",
) -> dict[str, Any]:
    """问询函单页原始查询（JSONP）。"""
    params: dict[str, Any] = {
        "jsonCallBack": "jsonpCallback1",
        "isPagination": "true",
        "pageHelp.pageSize": max(1, min(int(page_size), INQUIRE_PAGE_SIZE)),
        "pageHelp.pageNo": max(1, int(page_no)),
        "pageHelp.beginPage": max(1, int(page_no)),
        "pageHelp.cacheSize": 1,
        "pageHelp.endPage": max(1, int(page_no)),
        "sqlId": INQUIRE_SQL_ID,
        "siteId": INQUIRE_SITE_ID,
        "channelId": INQUIRE_CHANNEL_IDS,
        "stockcode": stockcode,
        "extGGLX": letter_type or "",
        "extGGDL": "",
        "order": "createTime|desc,stockcode|asc",
    }
    return _get_payload(INQUIRE_URL, params=params, referer=INQUIRE_PAGE)


def fetch_inquiries(
    code: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    letter_type: str = "",
    max_pages: int = 20,
) -> dict[str, Any]:
    """监管问询函 / 关注函 / 重组问询。日期在客户端过滤（接口按代码查）。"""
    query_code = normalize_code(code)
    if not query_code:
        return _empty_pack(code, channel="inquiry", error="缺少股票代码")
    if not is_sse_code(query_code):
        return _empty_pack(
            query_code,
            channel="inquiry",
            error=f"不是上交所代码: {query_code}",
        )

    start_d = _parse_day(start)
    end_d = _parse_day(end)
    if start_d is None and days is not None:
        end_d = end_d or date.today()
        start_d = end_d - timedelta(days=max(1, int(days)))

    items: list[dict[str, Any]] = []
    total = 0
    total_pages = 1
    page = 1
    limit = max(1, int(max_pages))
    while page <= total_pages and page <= limit:
        try:
            payload = query_inquiry_page(
                stockcode=query_code,
                page_no=page,
                letter_type=letter_type,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("上交所问询查询失败 page=%s: %s", page, exc)
            break
        rows, page_total, page_count = _rows_from_payload(payload)
        if page_total:
            total = page_total
        if page_count:
            total_pages = page_count
        elif total:
            total_pages = max(1, (total + INQUIRE_PAGE_SIZE - 1) // INQUIRE_PAGE_SIZE)
        if not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_code = normalize_code(
                safe_str(row.get("stockcode") or row.get("extSECURITY_CODE"))
            )
            if row_code and row_code != query_code:
                continue
            item = _normalize_inquiry(row, fallback_code=query_code)
            if not item:
                continue
            day = _parse_day(item.get("published_at"))
            if start_d and day and day < start_d:
                continue
            if end_d and day and day > end_d:
                continue
            items.append(item)
        if page >= total_pages:
            break
        page += 1
        if page <= total_pages and page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = _dedupe(items)
    name = items[0]["name"] if items else ""
    return {
        "code": query_code,
        "name": name,
        "letter_type": letter_type,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": "sse",
        "channel": "inquiry",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": INQUIRE_PAGE,
    }


def fetch_all(
    code: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    category: str | None = None,
    keyword: str = "",
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """个股公告 + 监管问询合并去重。"""
    bulletins = fetch_announcements(
        code,
        start=start,
        end=end,
        days=days,
        category=category,
        keyword=keyword,
        max_pages=max_pages,
    )
    inquiries = fetch_inquiries(
        code,
        start=start,
        end=end,
        days=days,
        max_pages=min(20, max_pages),
    )
    items = _dedupe(list(bulletins.get("items") or []) + list(inquiries.get("items") or []))
    error = bulletins.get("error") or inquiries.get("error") or ""
    return {
        "code": bulletins.get("code") or inquiries.get("code") or normalize_code(code),
        "name": bulletins.get("name") or inquiries.get("name") or "",
        "begin_date": bulletins.get("begin_date") or "",
        "end_date": bulletins.get("end_date") or "",
        "source": "sse",
        "channel": "all",
        "count": len(items),
        "total": len(items),
        "items": items,
        "bulletin_count": bulletins.get("count", 0),
        "inquiry_count": inquiries.get("count", 0),
        "error": error,
        "page": bulletin_page_url(code),
    }


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

# static.sse.com.cn 对 PDF 会先返回一段浏览器校验脚本（写 acw_sc__v2 后重载）。
_ACW_POS = (
    15, 35, 29, 24, 33, 16, 1, 38, 10, 9,
    19, 31, 40, 27, 22, 23, 25, 13, 6, 11,
    39, 18, 20, 8, 14, 21, 32, 26, 2, 30,
    7, 4, 17, 5, 3, 28, 34, 37, 12, 36,
)
_ACW_MASK = "3000176000856006061501533003690027800375"
_ARG1_RE = re.compile(r"arg1=['\"]([0-9A-Fa-f]+)['\"]")


def _acw_sc_v2(arg1: str) -> str:
    arg2 = "".join(arg1[p - 1] for p in _ACW_POS)
    out: list[str] = []
    for i in range(0, min(len(arg2), len(_ACW_MASK)), 2):
        xor_char = "%x" % (int(arg2[i : i + 2], 16) ^ int(_ACW_MASK[i : i + 2], 16))
        out.append(xor_char if len(xor_char) == 2 else "0" + xor_char)
    return "".join(out)


def _pdf_session():
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:  # pragma: no cover
        curl_requests = None
    if curl_requests is not None:
        return curl_requests.Session(impersonate="chrome")
    import requests

    sess = requests.Session()
    sess.trust_env = False
    sess.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }
    )
    return sess


def download_pdf(url: str, dest: str | Path) -> Path:
    """下载一条公告 PDF（同一会话完成 CDN 校验后落盘）。"""
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    sess = _pdf_session()
    headers = {"Referer": f"{SITE_PREFIX}/"}
    data: bytes | None = None
    last_hint = ""
    for _ in range(3):
        resp = sess.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        body = resp.content
        ctype = (resp.headers.get("content-type") or "").lower()
        if body.startswith(b"%PDF") or "pdf" in ctype:
            data = body
            break
        text = ""
        try:
            text = resp.text
        except Exception:  # noqa: BLE001
            last_hint = f"content-type={ctype}"
            break
        match = _ARG1_RE.search(text)
        if not match:
            last_hint = f"content-type={ctype} size={len(body)}"
            break
        sess.cookies.set("acw_sc__v2", _acw_sc_v2(match.group(1)), path="/")
    if not data:
        raise RuntimeError(f"下载失败，未拿到 PDF: {url} ({last_hint})")
    dest_path.write_bytes(data)
    return dest_path


def _safe_filename(title: str, code: str, url: str) -> str:
    stem = Path(unquote(urlparse(url).path)).name
    if not stem:
        stem = f"{code or 'sse'}.pdf"
    if not title:
        return stem
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", title).strip(" .")
    cleaned = cleaned[:80] or code or "announcement"
    suffix = Path(stem).suffix or ".pdf"
    return f"{cleaned}{suffix}"


def download_announcements(
    items: Iterable[dict[str, Any]],
    dest_dir: str | Path,
    *,
    limit: int = 0,
) -> list[Path]:
    """批量下载列表里的 PDF。``limit<=0`` 表示全部。"""
    folder = Path(dest_dir)
    folder.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for i, item in enumerate(items):
        if limit > 0 and i >= limit:
            break
        url = safe_str(item.get("url"))
        if not url:
            continue
        name = _safe_filename(
            safe_str(item.get("title")),
            safe_str(item.get("code")),
            url,
        )
        path = download_pdf(url, folder / name)
        saved.append(path)
        time.sleep(REQUEST_PAUSE_SEC)
    return saved


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_items(pack: dict[str, Any], limit: int, as_json: bool) -> None:
    if as_json:
        payload = dict(pack)
        if limit > 0:
            payload["items"] = (pack.get("items") or [])[:limit]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    items = pack.get("items") or []
    shown = items if limit <= 0 else items[:limit]
    extra = []
    if pack.get("code"):
        extra.append(pack["code"])
    if pack.get("name"):
        extra.append(pack["name"])
    bits = " ".join(extra)
    channel = pack.get("channel") or "bulletin"
    print(
        f"{bits}  channel={channel} "
        f"{pack.get('begin_date', '')}~{pack.get('end_date', '')} "
        f"count={pack.get('count')}"
        + (f"/{pack.get('total')}" if pack.get("total") else "")
    )
    if pack.get("error"):
        print(f"  error: {pack['error']}")
        return
    if not shown:
        print("  (empty)")
        return
    for i, row in enumerate(shown, 1):
        day = (row.get("published_at") or "")[:10]
        cat = row.get("category") or ""
        cat_bit = f" [{cat}]" if cat else ""
        print(f"  [{i}] {day}{cat_bit} {row.get('title')}")
        if row.get("url"):
            print(f"       {row['url']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="从上海证券交易所拉取上市公司公告")
    parser.add_argument(
        "code",
        nargs="?",
        default="",
        help="股票代码，如 600519 / 688981；与 --latest 二选一",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="回溯天数；个股公告默认 365，最新公告默认 7，问询函默认不限",
    )
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--category",
        default="",
        help="annual/年报, semi/半年报, q1, q3, periodic/定期, interim/临时",
    )
    parser.add_argument("--keyword", default="", help="标题关键词（keyWord）")
    parser.add_argument(
        "--security-type",
        default="auto",
        help="auto / all / a / star / b / cbond，或原始 0101 编码",
    )
    parser.add_argument("--report-type", default="", help="原始 reportType，如 YEARLY")
    parser.add_argument("--report-type2", default="", help="原始 reportType2，如 DQBG")
    parser.add_argument("--max-pages", type=int, default=5, help="最多翻页，默认 5")
    parser.add_argument("--limit", type=int, default=10, help="打印/下载前 N 条；0 为全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="走最新公告栏目；可不传代码（全市场）",
    )
    parser.add_argument(
        "--inquiries",
        action="store_true",
        help="只查监管问询函",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="公告全文 + 问询函合并",
    )
    parser.add_argument("--download", default="", help="把公告 PDF 存到该目录")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    start = args.start or None
    end = args.end or None
    category = args.category or None
    report_type = args.report_type or None
    report_type2 = args.report_type2 or None

    if args.latest:
        pack = fetch_latest_announcements(
            code=args.code,
            start=start,
            end=end,
            days=7 if args.days is None else args.days,
            category=category,
            keyword=args.keyword,
            report_type=report_type,
            report_type2=report_type2,
            max_pages=args.max_pages,
        )
    elif args.inquiries:
        if not args.code:
            parser.error("--inquiries 需要股票代码")
        pack = fetch_inquiries(
            args.code,
            start=start,
            end=end,
            days=args.days,
            max_pages=args.max_pages,
        )
    elif args.all:
        if not args.code:
            parser.error("--all 需要股票代码")
        pack = fetch_all(
            args.code,
            start=start,
            end=end,
            days=365 if args.days is None else args.days,
            category=category,
            keyword=args.keyword,
            max_pages=args.max_pages,
        )
    else:
        if not args.code:
            parser.error("请提供股票代码，或使用 --latest 查全市场最新公告")
        pack = fetch_announcements(
            args.code,
            start=start,
            end=end,
            days=365 if args.days is None else args.days,
            category=category,
            keyword=args.keyword,
            security_type=args.security_type,
            report_type=report_type,
            report_type2=report_type2,
            max_pages=args.max_pages,
        )

    _print_items(pack, args.limit, args.json)

    if args.download:
        saved = download_announcements(
            pack.get("items") or [],
            args.download,
            limit=args.limit,
        )
        print(f"downloaded {len(saved)} files -> {args.download}")

    return 1 if pack.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
