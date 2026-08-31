"""北京证券交易所公告：个股检索、分类/关键词、全市场最新、问询相关公告、PDF 下载。

官网公告检索：
  https://www.bse.cn/disclosure/announcement.html

公开查询（JSONP POST，需带官网 Referer）：
  /disclosureInfoController/companyAnnouncement.do
  - disclosureType[]=5     全部
  - disclosureType[]=9503  定期报告（1001 年报 / 1002 半年报 / 1003 一季报 / 1004 三季报）
  - disclosureType[]=9504  临时公告
  - xxfcbj[]=2 北交所（92 开头）；xxfcbj[]=3 新三板历史（43/83 旧码）
  - 问询函没有独立栏目，用 keyword=问询函 查公司公告

    python company/news/exchange/bse.py 920185
    python company/news/exchange/bse.py 920185 --days 90
    python company/news/exchange/bse.py 920185 --category annual
    python company/news/exchange/bse.py 920185 --keyword 减持
    python company/news/exchange/bse.py 920047 --inquiries
    python company/news/exchange/bse.py 430047 --layer neeq
    python company/news/exchange/bse.py --latest --days 3 --limit 20
    python company/news/exchange/bse.py 920185 --download ./pdfs --limit 3
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

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import detect_market, normalize_code, safe_str
from core.http import browser_post

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))

ANN_URL = "https://www.bse.cn/disclosureInfoController/companyAnnouncement.do"
SITE_PREFIX = "https://www.bse.cn"
NOTICE_PAGE = "https://www.bse.cn/disclosure/announcement.html"

PAGE_SIZE = 20
REQUEST_PAUSE_SEC = 0.25
MAX_PAGES = 50
DEFAULT_CHUNK_DAYS = 366

TYPE_ALL = "5"
TYPE_PERIODIC = "9503"
TYPE_INTERIM = "9504"

# 请求 disclosureType[]；年报等细类在返回的 disclosureSubType 上过滤。
SUBTYPE_LABELS: dict[str, str] = {
    "9503-1001": "年报",
    "9503-1005": "年报摘要",
    "9503-1002": "半年报",
    "9503-1006": "半年报摘要",
    "9503-1003": "一季报",
    "9503-1007": "一季报摘要",
    "9503-1004": "三季报",
    "9503-1008": "三季报摘要",
}
_TITLE_HEADING_RE = re.compile(r"^\[(定期报告|临时公告)\]")

DISCLOSURE_TYPES: dict[str, str] = {
    "all": TYPE_ALL,
    "全部": TYPE_ALL,
    "5": TYPE_ALL,
    "periodic": TYPE_PERIODIC,
    "定期": TYPE_PERIODIC,
    "定期报告": TYPE_PERIODIC,
    "9503": TYPE_PERIODIC,
    "interim": TYPE_INTERIM,
    "临时": TYPE_INTERIM,
    "临时公告": TYPE_INTERIM,
    "9504": TYPE_INTERIM,
    "annual": TYPE_PERIODIC,
    "yearly": TYPE_PERIODIC,
    "year": TYPE_PERIODIC,
    "年报": TYPE_PERIODIC,
    "semi": TYPE_PERIODIC,
    "半年报": TYPE_PERIODIC,
    "中报": TYPE_PERIODIC,
    "q2": TYPE_PERIODIC,
    "q1": TYPE_PERIODIC,
    "一季报": TYPE_PERIODIC,
    "q3": TYPE_PERIODIC,
    "三季报": TYPE_PERIODIC,
}

SUBTYPES: dict[str, frozenset[str]] = {
    "annual": frozenset({"9503-1001", "9503-1005"}),
    "yearly": frozenset({"9503-1001", "9503-1005"}),
    "year": frozenset({"9503-1001", "9503-1005"}),
    "年报": frozenset({"9503-1001", "9503-1005"}),
    "semi": frozenset({"9503-1002", "9503-1006"}),
    "半年报": frozenset({"9503-1002", "9503-1006"}),
    "中报": frozenset({"9503-1002", "9503-1006"}),
    "q2": frozenset({"9503-1002", "9503-1006"}),
    "q1": frozenset({"9503-1003", "9503-1007"}),
    "一季报": frozenset({"9503-1003", "9503-1007"}),
    "q3": frozenset({"9503-1004", "9503-1008"}),
    "三季报": frozenset({"9503-1004", "9503-1008"}),
}

LAYER_LISTED = "2"
LAYER_NEEQ = "3"
LAYERS: dict[str, str] = {
    "auto": LAYER_LISTED,
    "listed": LAYER_LISTED,
    "bse": LAYER_LISTED,
    "北交所": LAYER_LISTED,
    "2": LAYER_LISTED,
    "neeq": LAYER_NEEQ,
    "三板": LAYER_NEEQ,
    "新三板": LAYER_NEEQ,
    "3": LAYER_NEEQ,
    "all": "all",
    "全部": "all",
}

_JSONP_RE = re.compile(r"^[^(]+\((.*)\)\s*;?\s*$", re.DOTALL)
_ACW_POS = (
    15, 35, 29, 24, 33, 16, 1, 38, 10, 9,
    19, 31, 40, 27, 22, 23, 25, 13, 6, 11,
    39, 18, 20, 8, 14, 21, 32, 26, 2, 30,
    7, 4, 17, 5, 3, 28, 34, 37, 12, 36,
)
_ACW_MASK = "3000176000856006061501533003690027800375"
_ARG1_RE = re.compile(r"arg1=['\"]([0-9A-Fa-f]+)['\"]")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _headers(referer: str) -> dict[str, str]:
    return {
        "Referer": referer,
        "Origin": SITE_PREFIX,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
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


def _form_pairs(mapping: dict[str, Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for key, value in mapping.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            for one in value:
                pairs.append((key, str(one)))
        else:
            pairs.append((key, str(value)))
    return pairs


def _post_jsonp(
    url: str,
    *,
    form: dict[str, Any],
    referer: str,
    timeout: int = 30,
) -> Any:
    cb = f"jQuery{int(time.time() * 1000)}"
    resp = browser_post(
        f"{url}?callback={cb}",
        data=_form_pairs(form),
        headers=_headers(referer),
        timeout=timeout,
    )
    resp.raise_for_status()
    return _parse_jsonp(resp.text)


def bulletin_page_url(code: str = "") -> str:
    c = normalize_code(code)
    if c:
        return f"{NOTICE_PAGE}?companyCd={c}"
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
    if isinstance(value, dict):
        ts = value.get("time")
        if isinstance(ts, (int, float)):
            if ts > 1e12:
                ts /= 1000.0
            try:
                return datetime.fromtimestamp(ts, tz=TZ_CN).strftime("%Y-%m-%d %H:%M:%S")
            except (OverflowError, OSError, ValueError):
                return ""
        return _fmt_dt(value.get("date") or value.get("publishDate"))
    text = safe_str(value)
    if not text:
        return ""
    parsed = _parse_day(text)
    if parsed and len(text) <= 10:
        return f"{parsed.isoformat()} 00:00:00"
    return text[:19]


def pdf_url(path: str) -> str:
    """把 destFilePath 拼成 www.bse.cn 下载地址。"""
    raw = safe_str(path).strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        return f"https:{raw}"
    if raw.lower().startswith("http://") or raw.lower().startswith("https://"):
        return raw
    if raw.startswith("www."):
        return f"https://{raw}"
    return f"{SITE_PREFIX.rstrip('/')}/{raw.lstrip('/')}"


def is_bse_code(code: str) -> bool:
    """北交所 92xxxx / 原新三板 43/83/87 开头。"""
    c = normalize_code(code)
    if not c:
        return False
    if c.startswith(("92", "43", "83", "87")):
        return True
    return detect_market(c) == "bse"


# ---------------------------------------------------------------------------
# 参数规范化
# ---------------------------------------------------------------------------


def resolve_disclosure_type(category: str | None) -> str:
    key = safe_str(category).strip()
    if not key:
        return TYPE_ALL
    mapped = DISCLOSURE_TYPES.get(key) or DISCLOSURE_TYPES.get(key.lower())
    if mapped:
        return mapped
    raise ValueError(
        f"未知 category: {category}；可用 {', '.join(sorted(set(DISCLOSURE_TYPES)))}"
    )


def resolve_subtypes(category: str | None) -> frozenset[str]:
    key = safe_str(category).strip()
    if not key:
        return frozenset()
    return SUBTYPES.get(key) or SUBTYPES.get(key.lower()) or frozenset()


def resolve_layer(layer: str | None, code: str = "") -> str:
    """auto / listed 走北交所层（xxfcbj=2）；43/83 旧码在该层会映射到现 92 代码。"""
    _ = code
    key = safe_str(layer).strip() or "auto"
    mapped = LAYERS.get(key) or LAYERS.get(key.lower())
    if mapped:
        return mapped
    raise ValueError(f"未知 layer: {layer}；可用 listed / neeq / all")


# ---------------------------------------------------------------------------
# 列表解析
# ---------------------------------------------------------------------------


def _normalize_bulletin(
    row: dict[str, Any],
    *,
    fallback_code: str = "",
    channel: str = "bulletin",
) -> dict[str, Any] | None:
    title = safe_str(row.get("disclosureTitle") or row.get("disclosurePostTitle"))
    if not title:
        return None
    title = _TITLE_HEADING_RE.sub("", title).lstrip(" :：")
    path = safe_str(row.get("destFilePath") or row.get("filePath"))
    code = normalize_code(safe_str(row.get("companyCd")))
    subtype = safe_str(row.get("disclosureSubType"))
    dtype = safe_str(row.get("disclosureType"))
    heading = SUBTYPE_LABELS.get(subtype) or (
        "定期报告" if dtype == TYPE_PERIODIC else "临时公告" if dtype == TYPE_INTERIM else ""
    )
    return {
        "code": code or fallback_code,
        "name": safe_str(row.get("companyName") or row.get("issuerName")),
        "title": title,
        "published_at": _fmt_dt(row.get("publishDate") or row.get("pubDate") or row.get("upDate")),
        "url": pdf_url(path),
        "adjunct_url": path,
        "adjunct_type": safe_str(row.get("fileExt")) or "pdf",
        "info_id": safe_str(row.get("infoId") or row.get("dKey")),
        "disclosure_type": dtype,
        "disclosure_subtype": subtype,
        "layer": safe_str(row.get("xxfcbj")),
        "category": heading or subtype or dtype,
        "heading": heading,
        "channel": channel,
        "source": "北京证券交易所",
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


def _list_info(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list) and payload:
        block = payload[0]
    else:
        block = payload
    if not isinstance(block, dict):
        return {}
    info = block.get("listInfo")
    return info if isinstance(info, dict) else {}


# ---------------------------------------------------------------------------
# 个股 / 全市场公告 companyAnnouncement.do
# ---------------------------------------------------------------------------


def query_bulletin_page(
    *,
    company_cd: str = "",
    page: int = 0,
    page_size: int = PAGE_SIZE,
    begin_date: str = "",
    end_date: str = "",
    disclosure_type: str = TYPE_ALL,
    layer: str = LAYER_LISTED,
    keyword: str = "",
) -> dict[str, Any]:
    """公告单页原始查询。``company_cd`` 为空时做全市场切片。页码从 0 起。"""
    form: dict[str, Any] = {
        "page": max(0, int(page)),
        "pageSize": max(1, min(int(page_size), 50)),
        "companyCd": company_cd or "",
        "disclosureType[]": disclosure_type or TYPE_ALL,
        "xxfcbj[]": layer or LAYER_LISTED,
        "isNewThree": "1",
        "siteId": "1",
        "keyword": keyword or "",
    }
    if begin_date:
        form["startTime"] = begin_date
    if end_date:
        form["endTime"] = end_date
    payload = _post_jsonp(ANN_URL, form=form, referer=bulletin_page_url(company_cd))
    return _list_info(payload)


def _collect_bulletin_pages(
    *,
    company_cd: str,
    begin_date: str,
    end_date: str,
    disclosure_type: str,
    layer: str,
    keyword: str,
    subtypes: frozenset[str],
    max_pages: int,
    channel: str,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    total = 0
    total_pages = 1
    page = 0
    limit = max(1, int(max_pages))
    while page < total_pages and page < limit:
        try:
            info = query_bulletin_page(
                company_cd=company_cd,
                page=page,
                begin_date=begin_date,
                end_date=end_date,
                disclosure_type=disclosure_type,
                layer=layer,
                keyword=keyword,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("北交所公告查询失败 page=%s: %s", page, exc)
            break
        rows = info.get("content") or []
        if not isinstance(rows, list):
            rows = []
        total = int(info.get("totalElements") or 0)
        total_pages = int(info.get("totalPages") or 0)
        if total_pages <= 0 and total:
            size = int(info.get("size") or PAGE_SIZE) or PAGE_SIZE
            total_pages = max(1, (total + size - 1) // size)
        if not total_pages:
            total_pages = 1
        if not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            if subtypes:
                sub = safe_str(row.get("disclosureSubType"))
                if sub not in subtypes:
                    continue
            item = _normalize_bulletin(
                row, fallback_code=company_cd, channel=channel
            )
            if item:
                items.append(item)
        page += 1
        if page < total_pages and page < limit:
            time.sleep(REQUEST_PAUSE_SEC)
    return _dedupe(items), total


def _empty_pack(code: str, *, error: str = "", **extra: Any) -> dict[str, Any]:
    pack = {
        "code": normalize_code(code) or safe_str(code),
        "name": "",
        "source": "bse",
        "count": 0,
        "total": 0,
        "items": [],
    }
    pack.update(extra)
    if error:
        pack["error"] = error
    return pack


def _layers_to_query(layer: str) -> list[str]:
    if layer == "all":
        return [LAYER_LISTED, LAYER_NEEQ]
    return [layer or LAYER_LISTED]


def fetch_announcements(
    code: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    category: str | None = None,
    keyword: str = "",
    layer: str | None = "auto",
    max_pages: int = MAX_PAGES,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
) -> dict[str, Any]:
    """按股票拉取北交所公告（主入口）。

    ``category`` 可用 ``annual`` / ``年报`` / ``semi`` / ``q1`` / ``q3`` /
    ``periodic`` / ``interim``。``layer`` 可用 ``listed`` / ``neeq`` / ``all``。
    """
    raw = safe_str(code)
    query_code = normalize_code(raw)
    if not query_code:
        return _empty_pack(raw, error="缺少股票代码")
    if not is_bse_code(query_code):
        return _empty_pack(query_code, error=f"不是北交所代码: {query_code}")

    dtype = resolve_disclosure_type(category)
    subs = resolve_subtypes(category)
    xxfcbj = resolve_layer(layer, query_code)
    start_d, end_d = _date_range(start, end, days)

    items: list[dict[str, Any]] = []
    total = 0
    windows = _date_windows(start_d, end_d, chunk_days=chunk_days)
    layers = _layers_to_query(xxfcbj)
    for layer_i, one_layer in enumerate(layers):
        for i, (win_start, win_end) in enumerate(windows):
            chunk, chunk_total = _collect_bulletin_pages(
                company_cd=query_code,
                begin_date=win_start.isoformat(),
                end_date=win_end.isoformat(),
                disclosure_type=dtype,
                layer=one_layer,
                keyword=safe_str(keyword),
                subtypes=subs,
                max_pages=max_pages,
                channel="bulletin",
            )
            items.extend(chunk)
            total += chunk_total
            if i + 1 < len(windows):
                time.sleep(REQUEST_PAUSE_SEC)
        if layer_i + 1 < len(layers):
            time.sleep(REQUEST_PAUSE_SEC)

    items = _dedupe(items)
    name = items[0]["name"] if items else ""
    return {
        "code": query_code,
        "query_code": query_code,
        "name": name,
        "disclosure_type": dtype,
        "layer": xxfcbj,
        "keyword": safe_str(keyword),
        "begin_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "source": "bse",
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
    """按标题关键词搜该公司公告（接口 keyword）。"""
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
    layer: str | None = "listed",
    max_pages: int = 5,
) -> dict[str, Any]:
    """最新 / 全市场公告。不传代码则全市场。"""
    query_code = normalize_code(code)
    if query_code and not is_bse_code(query_code):
        return _empty_pack(
            query_code,
            channel="latest",
            error=f"不是北交所代码: {query_code}",
        )
    dtype = resolve_disclosure_type(category)
    subs = resolve_subtypes(category)
    xxfcbj = resolve_layer(layer, query_code)
    start_d, end_d = _date_range(start, end, days)
    items: list[dict[str, Any]] = []
    total = 0
    for one_layer in _layers_to_query(xxfcbj):
        chunk, chunk_total = _collect_bulletin_pages(
            company_cd=query_code,
            begin_date=start_d.isoformat(),
            end_date=end_d.isoformat(),
            disclosure_type=dtype,
            layer=one_layer,
            keyword=safe_str(keyword),
            subtypes=subs,
            max_pages=max_pages,
            channel="latest",
        )
        items.extend(chunk)
        total += chunk_total
    items = _dedupe(items)
    name = ""
    if query_code:
        for row in items:
            if row.get("name"):
                name = row["name"]
                break
    return {
        "code": query_code,
        "name": name,
        "disclosure_type": dtype,
        "layer": xxfcbj,
        "keyword": safe_str(keyword),
        "begin_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "source": "bse",
        "channel": "latest",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": bulletin_page_url(query_code),
    }


def fetch_inquiries(
    code: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = None,
    keyword: str = "问询函",
    max_pages: int = 20,
) -> dict[str, Any]:
    """问询相关公司公告（官网无独立问询栏目，走 keyword）。"""
    lookback = days
    start_d = _parse_day(start)
    end_d = _parse_day(end)
    begin = ""
    finish = ""
    if start_d is None and lookback is not None:
        end_d = end_d or date.today()
        start_d = end_d - timedelta(days=max(1, int(lookback)))
    if start_d and end_d:
        begin, finish = start_d.isoformat(), end_d.isoformat()
    elif start_d:
        begin = start_d.isoformat()
    elif end_d:
        finish = end_d.isoformat()

    raw = safe_str(code)
    query_code = normalize_code(raw)
    if not query_code:
        return _empty_pack(raw, channel="inquiry", error="缺少股票代码")
    if not is_bse_code(query_code):
        return _empty_pack(
            query_code, channel="inquiry", error=f"不是北交所代码: {query_code}"
        )

    xxfcbj = resolve_layer("auto", query_code)
    items: list[dict[str, Any]] = []
    total = 0
    for one_layer in _layers_to_query(xxfcbj):
        chunk, chunk_total = _collect_bulletin_pages(
            company_cd=query_code,
            begin_date=begin,
            end_date=finish,
            disclosure_type=TYPE_ALL,
            layer=one_layer,
            keyword=keyword or "问询函",
            subtypes=frozenset(),
            max_pages=max_pages,
            channel="inquiry",
        )
        items.extend(chunk)
        total += chunk_total
    items = _dedupe(items)
    name = items[0]["name"] if items else ""
    pack = {
        "code": query_code,
        "query_code": query_code,
        "name": name,
        "keyword": keyword or "问询函",
        "begin_date": begin,
        "end_date": finish,
        "source": "bse",
        "channel": "inquiry",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": bulletin_page_url(query_code),
    }
    for item in pack["items"]:
        item["channel"] = "inquiry"
        item["category"] = item.get("category") or "问询函"
    return pack


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
    """个股公告 + 问询相关公告合并去重。"""
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
        "code": normalize_code(code) or bulletins.get("code") or inquiries.get("code"),
        "name": bulletins.get("name") or inquiries.get("name") or "",
        "begin_date": bulletins.get("begin_date") or "",
        "end_date": bulletins.get("end_date") or "",
        "source": "bse",
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
        stem = f"{code or 'bse'}.pdf"
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
    parser = argparse.ArgumentParser(description="从北京证券交易所拉取上市公司公告")
    parser.add_argument(
        "code",
        nargs="?",
        default="",
        help="股票代码，如 920185 / 430047；与 --latest 二选一",
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
    parser.add_argument("--keyword", default="", help="标题关键词")
    parser.add_argument(
        "--layer",
        default="auto",
        help="listed 北交所(xxfcbj=2) / neeq 新三板历史 / all",
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
        help="只查问询相关公司公告",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="公告全文 + 问询相关合并",
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
            layer=args.layer,
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
            keyword=args.keyword or "问询函",
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
            layer=args.layer,
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
