"""深圳证券交易所公告：个股检索、分类/关键词、全市场最新、监管问询、PDF 下载。

官网公告检索：
  https://www.szse.cn/disclosure/listed/notice/index.html
定期报告：
  https://www.szse.cn/disclosure/listed/fixed/index.html
监管问询：
  https://www.szse.cn/disclosure/supervision/inquire/index.html

两套公开查询（JSON，需带官网 Referer）：
  1. /api/disc/announcement/annList     上市公司公告 / 定期报告
  2. /api/report/ShowReport/data        问询函 / 关注函（CATALOGID=main_wxhj）

    python company/news/szse.py 000001
    python company/news/szse.py 000001 --days 90
    python company/news/szse.py 000001 --category annual
    python company/news/szse.py 000001 --keyword 董事
    python company/news/szse.py 002731 --inquiries
    python company/news/szse.py 300750 --days 60
    python company/news/szse.py --latest --days 3 --limit 20
    python company/news/szse.py --latest --category annual --days 30
    python company/news/szse.py 000001 --download ./pdfs --limit 3
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import unquote, urljoin, urlparse

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import detect_market, normalize_code, safe_str
from core.http import browser_get, browser_post

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))

ANN_URL = "https://www.szse.cn/api/disc/announcement/annList"
INQUIRE_URL = "https://www.szse.cn/api/report/ShowReport/data"
PDF_PREFIX = "https://disc.static.szse.cn/download"
INQUIRE_FILE_PREFIX = "https://reportdocs.static.szse.cn"
SITE_PREFIX = "https://www.szse.cn"

NOTICE_PAGE = "https://www.szse.cn/disclosure/listed/notice/index.html"
FIXED_PAGE = "https://www.szse.cn/disclosure/listed/fixed/index.html"
INQUIRE_PAGE = "https://www.szse.cn/disclosure/supervision/inquire/index.html"
DETAIL_PAGE = "https://www.szse.cn/disclosure/listed/bulletinDetail/index.html"

PAGE_SIZE = 50
INQUIRE_PAGE_SIZE = 20
REQUEST_PAUSE_SEC = 0.25
MAX_PAGES = 50
DEFAULT_CHUNK_DAYS = 366

CHANNEL_NOTICE = "listedNotice_disc"
CHANNEL_FIXED = "fixed_disc"
CHANNELS: dict[str, str] = {
    "auto": "auto",
    "notice": CHANNEL_NOTICE,
    "listed": CHANNEL_NOTICE,
    "公告": CHANNEL_NOTICE,
    "listedNotice_disc": CHANNEL_NOTICE,
    "fixed": CHANNEL_FIXED,
    "periodic": CHANNEL_FIXED,
    "定期": CHANNEL_FIXED,
    "fixed_disc": CHANNEL_FIXED,
}

# 官网 bigCategoryId。定期报告栏目改走 channelCode=fixed_disc。
CATEGORIES: dict[str, str] = {
    "all": "",
    "全部": "",
    "annual": "010301",
    "yearly": "010301",
    "year": "010301",
    "年报": "010301",
    "semi": "010303",
    "半年报": "010303",
    "中报": "010303",
    "q2": "010303",
    "q1": "010305",
    "一季报": "010305",
    "q3": "010307",
    "三季报": "010307",
    "periodic": "FIXED",
    "定期": "FIXED",
    "定期报告": "FIXED",
    "interim": "",
    "临时": "",
    "临时公告": "",
}

INQUIRE_CATALOG = "main_wxhj"
# tab1 主板 / tab2 原中小板 / tab3 创业板；按代码优先，再扫其余以免漏
INQUIRE_TABS: dict[str, tuple[str, ...]] = {
    "main": ("tab1", "tab2", "tab3"),
    "sme": ("tab2", "tab1", "tab3"),
    "chinext": ("tab3", "tab1", "tab2"),
}

_ACW_POS = (
    15, 35, 29, 24, 33, 16, 1, 38, 10, 9,
    19, 31, 40, 27, 22, 23, 25, 13, 6, 11,
    39, 18, 20, 8, 14, 21, 32, 26, 2, 30,
    7, 4, 17, 5, 3, 28, 34, 37, 12, 36,
)
_ACW_MASK = "3000176000856006061501533003690027800375"
_ARG1_RE = re.compile(r"arg1=['\"]([0-9A-Fa-f]+)['\"]")
_ENCODE_OPEN_RE = re.compile(r"encode-open='([^']+)'")
_HREF_RE = re.compile(r"""href=['"]([^'"]+)['"]""")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _ann_headers(referer: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Referer": referer,
        "Origin": SITE_PREFIX,
        "X-Requested-With": "XMLHttpRequest",
        "X-Request-Type": "ajax",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def _get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    referer: str,
    timeout: int = 30,
) -> Any:
    resp = browser_get(
        url,
        params=params,
        headers={
            "Referer": referer,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def _post_json(
    url: str,
    *,
    payload: dict[str, Any],
    referer: str,
    timeout: int = 30,
) -> dict[str, Any]:
    resp = browser_post(
        f"{url}?random={random.random()}",
        data=json.dumps(payload, ensure_ascii=False),
        headers=_ann_headers(referer),
        timeout=timeout,
    )
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


def bulletin_page_url(code: str = "", *, channel: str = CHANNEL_NOTICE) -> str:
    if channel == CHANNEL_FIXED:
        return FIXED_PAGE
    c = normalize_code(code)
    if c:
        return f"{NOTICE_PAGE}?stock={c}"
    return NOTICE_PAGE


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


def _first(value: Any) -> str:
    if isinstance(value, list):
        return safe_str(value[0]) if value else ""
    return safe_str(value)


def pdf_url(path: str) -> str:
    """把 attachPath 拼成 disc.static.szse.cn/download 地址。"""
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


def extract_href(html: str) -> str:
    """从问询函 ck / hfck 字段抽出 encode-open 或 href 路径。"""
    text = safe_str(html)
    if not text:
        return ""
    match = _ENCODE_OPEN_RE.search(text)
    if match:
        return match.group(1)
    match = _HREF_RE.search(text)
    return match.group(1) if match else ""


def inquiry_file_url(path: str) -> str:
    raw = safe_str(path).strip()
    if not raw or raw.startswith("javascript:"):
        return ""
    if raw.startswith("//"):
        return f"https:{raw}"
    if raw.lower().startswith("http://") or raw.lower().startswith("https://"):
        parsed = urlparse(raw)
        if parsed.path.startswith("/UpFiles/"):
            return f"{INQUIRE_FILE_PREFIX}{parsed.path}"
        return raw
    if raw.startswith("www."):
        return inquiry_file_url(f"https://{raw}")
    if "UpFiles/" in raw.replace("\\", "/"):
        return f"{INQUIRE_FILE_PREFIX.rstrip('/')}/{raw.lstrip('/')}"
    return urljoin(f"{SITE_PREFIX}/", raw)


def is_szse_code(code: str) -> bool:
    """深市主板 / 创业板 / B 股 / 深市可转债。"""
    c = normalize_code(code)
    if not c:
        return False
    if c.startswith(("00", "30", "20", "12")):
        return True
    return detect_market(c) == "szse"


# ---------------------------------------------------------------------------
# 参数规范化
# ---------------------------------------------------------------------------


def resolve_channel(channel: str | None, *, category: str | None = None) -> str:
    key = safe_str(channel).lower() or "auto"
    if key in CHANNELS and CHANNELS[key] != "auto":
        return CHANNELS[key]
    cat = safe_str(category)
    mapped = CATEGORIES.get(cat) or CATEGORIES.get(cat.lower())
    if mapped == "FIXED":
        return CHANNEL_FIXED
    return CHANNEL_NOTICE


def resolve_category(category: str | None) -> str:
    """返回 bigCategoryId；定期报告栏目返回 ``FIXED``；全部返回空串。"""
    key = safe_str(category).strip()
    if not key:
        return ""
    if key.startswith("01") and key.isdigit():
        return key
    mapped = CATEGORIES.get(key) or CATEGORIES.get(key.lower())
    if mapped is not None:
        return mapped
    raise ValueError(
        f"未知 category: {category}；可用 {', '.join(sorted(set(CATEGORIES)))}"
    )


def resolve_inquire_tabs(code: str) -> tuple[str, ...]:
    c = normalize_code(code)
    if c.startswith("30"):
        return INQUIRE_TABS["chinext"]
    if c.startswith(("002", "003")):
        return INQUIRE_TABS["sme"]
    return INQUIRE_TABS["main"]


# ---------------------------------------------------------------------------
# 列表解析
# ---------------------------------------------------------------------------


def _normalize_bulletin(
    row: dict[str, Any],
    *,
    fallback_code: str = "",
    channel: str = "bulletin",
    category_label: str = "",
) -> dict[str, Any] | None:
    title = safe_str(row.get("title"))
    if not title:
        return None
    path = safe_str(row.get("attachPath"))
    ann_id = safe_str(row.get("annId") or row.get("id"))
    code = normalize_code(_first(row.get("secCode")))
    return {
        "code": code or fallback_code,
        "name": _first(row.get("secName")),
        "title": title,
        "published_at": _fmt_dt(row.get("publishTime")),
        "url": pdf_url(path),
        "adjunct_url": path,
        "adjunct_type": safe_str(row.get("attachFormat")) or "PDF",
        "adjunct_size": row.get("attachSize"),
        "ann_id": ann_id,
        "detail_url": f"{DETAIL_PAGE}?annId={ann_id}" if ann_id else "",
        "category": category_label or _first(row.get("bigCategoryId")),
        "category_code": _first(row.get("bigCategoryId") or row.get("smallCategoryId")),
        "channel": channel,
        "source": "深圳证券交易所",
    }


def _normalize_inquiry(
    row: dict[str, Any],
    *,
    fallback_code: str = "",
    tab: str = "",
) -> dict[str, Any] | None:
    code = normalize_code(safe_str(row.get("gsdm")))
    name = safe_str(row.get("gsjc"))
    letter_type = safe_str(row.get("hjlb")) or "问询函"
    path = extract_href(safe_str(row.get("ck")))
    url = inquiry_file_url(path)
    if not url and not letter_type:
        return None
    title = f"{name or code or fallback_code}：收到深交所{letter_type}"
    reply = inquiry_file_url(extract_href(safe_str(row.get("hfck"))))
    return {
        "code": code or fallback_code,
        "name": name,
        "title": title,
        "published_at": _fmt_dt(row.get("fhrq")),
        "url": url,
        "adjunct_url": path,
        "adjunct_type": "PDF",
        "reply_url": reply,
        "category": letter_type,
        "heading": letter_type,
        "channel": "inquiry",
        "source": "深圳证券交易所",
        "tab": tab,
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
# 个股 / 全市场公告 annList
# ---------------------------------------------------------------------------


def query_bulletin_page(
    *,
    stock: str = "",
    page_num: int = 1,
    page_size: int = PAGE_SIZE,
    begin_date: str = "",
    end_date: str = "",
    channel_code: str = CHANNEL_NOTICE,
    big_category_id: str = "",
    keyword: str = "",
) -> dict[str, Any]:
    """公告单页原始查询。``stock`` 为空时做全市场切片。"""
    payload: dict[str, Any] = {
        "seDate": [begin_date or "", end_date or ""],
        "channelCode": [channel_code or CHANNEL_NOTICE],
        "pageSize": max(1, min(int(page_size), PAGE_SIZE)),
        "pageNum": max(1, int(page_num)),
    }
    if stock:
        payload["stock"] = [stock]
    if keyword:
        payload["searchKey"] = [keyword]
    if big_category_id:
        payload["bigCategoryId"] = [big_category_id]
    referer = bulletin_page_url(stock, channel=channel_code or CHANNEL_NOTICE)
    return _post_json(ANN_URL, payload=payload, referer=referer)


def _collect_bulletin_pages(
    *,
    stock: str,
    begin_date: str,
    end_date: str,
    channel_code: str,
    big_category_id: str,
    keyword: str,
    max_pages: int,
    channel: str,
    category_label: str,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    total = 0
    total_pages = 1
    page = 1
    limit = max(1, int(max_pages))
    while page <= total_pages and page <= limit:
        try:
            payload = query_bulletin_page(
                stock=stock,
                page_num=page,
                begin_date=begin_date,
                end_date=end_date,
                channel_code=channel_code,
                big_category_id=big_category_id,
                keyword=keyword,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("深交所公告查询失败 page=%s: %s", page, exc)
            break
        rows = payload.get("data") or []
        if not isinstance(rows, list):
            rows = []
        count = int(payload.get("announceCount") or 0)
        if count:
            total = count
            total_pages = max(1, (count + PAGE_SIZE - 1) // PAGE_SIZE)
        if not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _normalize_bulletin(
                row,
                fallback_code=stock,
                channel=channel,
                category_label=category_label,
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
        "source": "szse",
        "count": 0,
        "total": 0,
        "items": [],
    }
    pack.update(extra)
    if error:
        pack["error"] = error
    return pack


def _category_label(category: str | None, big_category_id: str) -> str:
    key = safe_str(category)
    if key:
        return key
    for alias, code in CATEGORIES.items():
        if code and code == big_category_id and alias.isascii() and alias.isalpha():
            return alias
    return big_category_id


def fetch_announcements(
    code: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    category: str | None = None,
    keyword: str = "",
    channel: str | None = "auto",
    max_pages: int = MAX_PAGES,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
) -> dict[str, Any]:
    """按股票拉取深交所公告（主入口）。

    ``category`` 可用 ``annual`` / ``年报`` / ``semi`` / ``q1`` / ``q3`` /
    ``periodic``。也可传原始 ``010301``。
    """
    raw = safe_str(code)
    query_code = normalize_code(raw)
    if not query_code:
        return _empty_pack(raw, error="缺少股票代码")
    if not is_szse_code(query_code):
        return _empty_pack(query_code, error=f"不是深交所代码: {query_code}")

    cat = resolve_category(category)
    channel_code = resolve_channel(channel, category=category)
    big_id = "" if cat == "FIXED" else cat
    if cat == "FIXED":
        channel_code = CHANNEL_FIXED
    start_d, end_d = _date_range(start, end, days)
    label = _category_label(category, big_id)

    items: list[dict[str, Any]] = []
    total = 0
    windows = _date_windows(start_d, end_d, chunk_days=chunk_days)
    for i, (win_start, win_end) in enumerate(windows):
        chunk, chunk_total = _collect_bulletin_pages(
            stock=query_code,
            begin_date=win_start.isoformat(),
            end_date=win_end.isoformat(),
            channel_code=channel_code,
            big_category_id=big_id,
            keyword=safe_str(keyword),
            max_pages=max_pages,
            channel="bulletin",
            category_label=label,
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
        "channel_code": channel_code,
        "big_category_id": big_id,
        "keyword": safe_str(keyword),
        "begin_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "source": "szse",
        "channel": "bulletin",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": bulletin_page_url(query_code, channel=channel_code),
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
    """定期报告：annual / semi / q1 / q3，可多选；也可用 ``periodic`` 走定期栏目。"""
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
    """按标题关键词搜该公司公告（接口 searchKey）。"""
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
    channel: str | None = "auto",
    max_pages: int = 5,
) -> dict[str, Any]:
    """最新 / 全市场公告。不传代码则全市场；可再按代码/分类/关键词收窄。"""
    query_code = normalize_code(code)
    if query_code and not is_szse_code(query_code):
        return _empty_pack(
            query_code,
            channel="latest",
            error=f"不是深交所代码: {query_code}",
        )
    cat = resolve_category(category)
    channel_code = resolve_channel(channel, category=category)
    big_id = "" if cat == "FIXED" else cat
    if cat == "FIXED":
        channel_code = CHANNEL_FIXED
    start_d, end_d = _date_range(start, end, days)
    label = _category_label(category, big_id)
    items, total = _collect_bulletin_pages(
        stock=query_code,
        begin_date=start_d.isoformat(),
        end_date=end_d.isoformat(),
        channel_code=channel_code,
        big_category_id=big_id,
        keyword=safe_str(keyword),
        max_pages=max_pages,
        channel="latest",
        category_label=label,
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
        "channel_code": channel_code,
        "big_category_id": big_id,
        "keyword": safe_str(keyword),
        "begin_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "source": "szse",
        "channel": "latest",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": bulletin_page_url(query_code, channel=channel_code),
    }


# ---------------------------------------------------------------------------
# 监管问询 ShowReport / main_wxhj
# ---------------------------------------------------------------------------


def query_inquiry_page(
    *,
    stockcode: str = "",
    page_no: int = 1,
    tab: str = "tab1",
) -> dict[str, Any]:
    """问询函单页原始查询。``stockcode`` 可空（该 tab 全市场）。"""
    params: dict[str, Any] = {
        "SHOWTYPE": "JSON",
        "CATALOGID": INQUIRE_CATALOG,
        "TABKEY": tab,
        "PAGENO": max(1, int(page_no)),
        "random": random.random(),
    }
    if stockcode:
        params["txtZqdm"] = stockcode
    payload = _get_json(INQUIRE_URL, params=params, referer=INQUIRE_PAGE)
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return payload if isinstance(payload, dict) else {}


def fetch_inquiries(
    code: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    max_pages: int = 20,
) -> dict[str, Any]:
    """监管问询函 / 关注函。日期在客户端过滤；按主板/中小/创业板 tab 依次查。"""
    query_code = normalize_code(code)
    if not query_code:
        return _empty_pack(code, channel="inquiry", error="缺少股票代码")
    if not is_szse_code(query_code):
        return _empty_pack(
            query_code,
            channel="inquiry",
            error=f"不是深交所代码: {query_code}",
        )

    start_d = _parse_day(start)
    end_d = _parse_day(end)
    if start_d is None and days is not None:
        end_d = end_d or date.today()
        start_d = end_d - timedelta(days=max(1, int(days)))

    items: list[dict[str, Any]] = []
    total = 0
    tabs = resolve_inquire_tabs(query_code)
    for tab_i, tab in enumerate(tabs):
        page = 1
        total_pages = 1
        limit = max(1, int(max_pages))
        tab_hit = False
        while page <= total_pages and page <= limit:
            try:
                block = query_inquiry_page(
                    stockcode=query_code, page_no=page, tab=tab
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("深交所问询查询失败 tab=%s page=%s: %s", tab, page, exc)
                break
            meta = block.get("metadata") if isinstance(block.get("metadata"), dict) else {}
            rows = block.get("data") or []
            if not isinstance(rows, list) or not rows:
                break
            tab_hit = True
            record_count = int(meta.get("recordcount") or 0)
            page_size = int(meta.get("pagesize") or INQUIRE_PAGE_SIZE) or INQUIRE_PAGE_SIZE
            if record_count:
                if page == 1:
                    total = max(total, record_count)
                total_pages = max(1, (record_count + page_size - 1) // page_size)
            else:
                total_pages = int(meta.get("pagecount") or 1)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_code = normalize_code(safe_str(row.get("gsdm")))
                if row_code and row_code != query_code:
                    continue
                item = _normalize_inquiry(row, fallback_code=query_code, tab=tab)
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
        if tab_hit and tab_i + 1 < len(tabs):
            time.sleep(REQUEST_PAUSE_SEC)

    items = _dedupe(items)
    name = items[0]["name"] if items else ""
    return {
        "code": query_code,
        "name": name,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": "szse",
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
        "source": "szse",
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
    """下载一条公告 PDF。CDN 偶发校验页时按浏览器同样写 cookie 再取。"""
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
        stem = f"{code or 'szse'}.pdf"
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
    parser = argparse.ArgumentParser(description="从深圳证券交易所拉取上市公司公告")
    parser.add_argument(
        "code",
        nargs="?",
        default="",
        help="股票代码，如 000001 / 300750；与 --latest 二选一",
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
        help="annual/年报, semi/半年报, q1, q3, periodic/定期",
    )
    parser.add_argument("--keyword", default="", help="标题关键词（searchKey）")
    parser.add_argument(
        "--channel",
        default="auto",
        help="auto / notice 上市公司公告 / fixed 定期报告栏目",
    )
    parser.add_argument("--max-pages", type=int, default=5, help="最多翻页，默认 5")
    parser.add_argument("--limit", type=int, default=10, help="打印/下载前 N 条；0 为全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="走全市场最新公告；可不传代码",
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

    if args.latest:
        pack = fetch_latest_announcements(
            code=args.code,
            start=start,
            end=end,
            days=7 if args.days is None else args.days,
            category=category,
            keyword=args.keyword,
            channel=args.channel,
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
            channel=args.channel,
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
