"""巨潮资讯网公告：orgId 解析、列表检索、分类/关键词/调研/督导、PDF 下载。

官网查询页：https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/search

两步协议（不能只传 6 位代码）：
  1. topSearch 用代码或简称换 orgId
  2. hisAnnouncement/query 用 ``代码,orgId`` 分页拉列表

    python company/news/cninfo.py 600519
    python company/news/cninfo.py 600519 --days 90
    python company/news/cninfo.py 600519 --category annual
    python company/news/cninfo.py 600519 --keyword 问询函
    python company/news/cninfo.py 600519 --tab relation
    python company/news/cninfo.py 600519 --org-only
    python company/news/cninfo.py 000001 --download ./pdfs --limit 3
    python company/news/cninfo.py --market szse --category annual --days 30 --limit 20
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
from core.http import browser_post, get_bytes, get_json

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))

SEARCH_URL = "https://www.cninfo.com.cn/new/information/topSearch/query"
QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_PREFIX = "https://static.cninfo.com.cn/"
PAGE_SIZE = 30
REQUEST_PAUSE_SEC = 0.25
MAX_PAGES = 50

# 静态股票表（含 orgId）。sse_stock.json 当前 404，深市这份可用作缓存。
STOCK_LIST_URLS = (
    "https://www.cninfo.com.cn/new/data/szse_stock.json",
)

_SEARCH_PAGE = "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/search"
_HEADERS = {
    "Referer": _SEARCH_PAGE,
    "Origin": "https://www.cninfo.com.cn",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
_FORM_HEADERS = {
    **_HEADERS,
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

# 市场栏目：上交所 sse / 深交所 szse / 北交所 bj
COLUMNS: dict[str, str] = {
    "sse": "sse",
    "sh": "sse",
    "szse": "szse",
    "sz": "szse",
    "bj": "bj",
    "bse": "bj",
    "auto": "auto",
}
_COLUMN_BY_MARKET = {"sse": "sse", "szse": "szse", "bse": "bj"}

# fulltext 公告正文；relation 调研；supervise 持续督导
TABS: dict[str, str] = {
    "fulltext": "fulltext",
    "announcement": "fulltext",
    "notice": "fulltext",
    "公告": "fulltext",
    "relation": "relation",
    "ir": "relation",
    "调研": "relation",
    "supervise": "supervise",
    "督导": "supervise",
    "持续督导": "supervise",
}

# 板块过滤；查单股通常留空
PLATES: dict[str, str] = {
    "szmb": "深圳主板",
    "szcy": "创业板",
    "shmb": "上海主板",
    "shkcp": "科创板",
    "bj": "北交所",
}

# 沪深京公告分类。值是接口 category 字段；键是别名（可中英混用）。
CATEGORIES: dict[str, str] = {
    "annual": "category_ndbg_szsh",
    "年报": "category_ndbg_szsh",
    "ndbg": "category_ndbg_szsh",
    "semi": "category_bndbg_szsh",
    "半年报": "category_bndbg_szsh",
    "bndbg": "category_bndbg_szsh",
    "q1": "category_yjdbg_szsh",
    "一季报": "category_yjdbg_szsh",
    "yjdbg": "category_yjdbg_szsh",
    "q3": "category_sjdbg_szsh",
    "三季报": "category_sjdbg_szsh",
    "sjdbg": "category_sjdbg_szsh",
    "forecast": "category_yjygjxz_szsh",
    "业绩预告": "category_yjygjxz_szsh",
    "yjyg": "category_yjygjxz_szsh",
    "dividend": "category_qyfpxzcs_szsh",
    "权益分派": "category_qyfpxzcs_szsh",
    "board": "category_dshgg_szsh",
    "董事会": "category_dshgg_szsh",
    "supervisory": "category_jshgg_szsh",
    "监事会": "category_jshgg_szsh",
    "shareholder": "category_gddh_szsh",
    "股东大会": "category_gddh_szsh",
    "operation": "category_rcjy_szsh",
    "日常经营": "category_rcjy_szsh",
    "governance": "category_gszl_szsh",
    "公司治理": "category_gszl_szsh",
    "intermediary": "category_zj_szsh",
    "中介报告": "category_zj_szsh",
    "ipo": "category_sf_szsh",
    "首发": "category_sf_szsh",
    "seo": "category_zf_szsh",
    "增发": "category_zf_szsh",
    "equity": "category_gqbd_szsh",
    "股权变动": "category_gqbd_szsh",
    "unlock": "category_jj_szsh",
    "解禁": "category_jj_szsh",
    "cbond": "category_kzzq_szsh",
    "可转债": "category_kzzq_szsh",
    "rights": "category_pg_szsh",
    "配股": "category_pg_szsh",
    "other_financing": "category_qtrz_szsh",
    "其他融资": "category_qtrz_szsh",
    "incentive": "category_gqjl_szsh",
    "股权激励": "category_gqjl_szsh",
    "st": "category_tbclts_szsh",
    "特别处理": "category_tbclts_szsh",
    "delist": "category_tszlq_szsh",
    "退市整理": "category_tszlq_szsh",
    "amend": "category_bcgz_szsh",
    "补充更正": "category_bcgz_szsh",
}

_ORG_CACHE: dict[str, dict[str, str]] = {}
_STOCK_MAP: dict[str, dict[str, str]] | None = None


# ---------------------------------------------------------------------------
# HTTP / 文本
# ---------------------------------------------------------------------------


def _post_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> Any:
    resp = browser_post(
        url,
        params=params,
        data=data,
        headers=headers or _HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def strip_em(text: str) -> str:
    """去掉 isHLtitle=true 时标题里的 <em> 高亮标签。"""
    return re.sub(r"</?em[^>]*>", "", safe_str(text), flags=re.IGNORECASE)


def parse_announcement_time(value: Any) -> datetime | None:
    """announcementTime 是毫秒时间戳，按北京时间换算。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=TZ_CN)
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts > 1e12:
        ts /= 1000.0
    if ts <= 0:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=TZ_CN)
    except (OverflowError, OSError, ValueError):
        return None


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(TZ_CN)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _parse_day(value: str | date | datetime | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = safe_str(value).replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text[:8], fmt).date()
        except ValueError:
            continue
    return None


def _se_date(
    start: str | date | datetime | None,
    end: str | date | datetime | None,
    days: int | None,
) -> str:
    end_d = _parse_day(end) or date.today()
    start_d = _parse_day(start)
    if start_d is None:
        lookback = 365 if days is None else max(1, int(days))
        start_d = end_d - timedelta(days=lookback)
    if start_d > end_d:
        start_d, end_d = end_d, start_d
    return f"{start_d.isoformat()}~{end_d.isoformat()}"


def pdf_url(adjunct_url: str) -> str:
    """把 adjunctUrl 拼成可下载的 PDF 地址。"""
    path = safe_str(adjunct_url).lstrip("/")
    if not path:
        return ""
    if path.lower().startswith("http://") or path.lower().startswith("https://"):
        return path
    return PDF_PREFIX + path


# ---------------------------------------------------------------------------
# 参数规范化
# ---------------------------------------------------------------------------


def resolve_column(column: str | None, code: str = "") -> str:
    key = safe_str(column).lower()
    if key in COLUMNS and COLUMNS[key] != "auto":
        return COLUMNS[key]
    market = detect_market(code)
    return _COLUMN_BY_MARKET.get(market, "szse")


def resolve_tab(tab: str | None) -> str:
    key = safe_str(tab).lower() or "fulltext"
    if key in TABS:
        return TABS[key]
    if safe_str(tab) in TABS:
        return TABS[safe_str(tab)]
    return "fulltext"


def resolve_category(category: str | Sequence[str] | None) -> str:
    """别名或原始 category_xxx 都接受；多个用分号拼接。"""
    if category is None or category == "":
        return ""
    if isinstance(category, str):
        parts = [p.strip() for p in re.split(r"[;,|]", category) if p.strip()]
    else:
        parts = [safe_str(p) for p in category if safe_str(p)]
    codes: list[str] = []
    for part in parts:
        raw = part.strip().rstrip(";")
        if not raw:
            continue
        if raw.startswith("category_"):
            codes.append(raw)
            continue
        mapped = CATEGORIES.get(raw) or CATEGORIES.get(raw.lower())
        if mapped:
            codes.append(mapped)
        else:
            raise ValueError(
                f"未知 category: {raw}；可用 {', '.join(sorted(set(CATEGORIES)))}"
            )
    return ";".join(codes)


def a_share_code(code: str, org_id: str = "") -> str:
    """B 股代码转对应 A 股。巨潮 stock 参数不接受 200/900 开头。"""
    c = normalize_code(code)
    if not c:
        return ""
    if c.startswith("200"):
        return "000" + c[3:]
    if c.startswith("900"):
        oid = safe_str(org_id)
        if oid.startswith("gssh") and len(oid) >= 11:
            digits = re.sub(r"\D", "", oid)
            if len(digits) >= 6:
                return digits[-6:]
        return c
    return c


# ---------------------------------------------------------------------------
# orgId
# ---------------------------------------------------------------------------


def search_orgs(keyword: str, *, max_num: int = 10) -> list[dict[str, str]]:
    """topSearch 联想：代码或简称。"""
    text = safe_str(keyword)
    if not text:
        return []
    try:
        rows = _post_json(
            SEARCH_URL,
            params={"keyWord": text, "maxNum": max(1, min(int(max_num), 50))},
            headers=_HEADERS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("topSearch 失败 keyword=%s: %s", text, exc)
        return []
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        org_id = safe_str(row.get("orgId"))
        if not org_id:
            continue
        out.append(
            {
                "code": normalize_code(safe_str(row.get("code")))
                or safe_str(row.get("code")),
                "org_id": org_id,
                "name": safe_str(row.get("zwjc")),
                "pinyin": safe_str(row.get("pinyin")),
                "category": safe_str(row.get("category") or row.get("type")),
            }
        )
    return out


def load_org_map(*, force: bool = False) -> dict[str, dict[str, str]]:
    """加载巨潮静态股票表（代码 → orgId）。失败的 URL 会跳过。"""
    global _STOCK_MAP
    if _STOCK_MAP is not None and not force:
        return _STOCK_MAP
    mapping: dict[str, dict[str, str]] = {}
    for url in STOCK_LIST_URLS:
        try:
            payload = get_json(url, timeout=30)
        except Exception as exc:  # noqa: BLE001
            logger.info("股票表不可用 %s: %s", url, exc)
            continue
        rows = payload.get("stockList") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = normalize_code(safe_str(row.get("code")))
            org_id = safe_str(row.get("orgId"))
            if not code or not org_id:
                continue
            mapping[code] = {
                "code": code,
                "org_id": org_id,
                "name": safe_str(row.get("zwjc")),
                "category": safe_str(row.get("category")),
                "pinyin": safe_str(row.get("pinyin")),
            }
    _STOCK_MAP = mapping
    return mapping


def resolve_org(code_or_name: str) -> dict[str, str] | None:
    """解析 orgId / 简称。优先 topSearch，静态表兜底。B 股自动转到 A 股代码。"""
    raw = safe_str(code_or_name)
    if not raw:
        return None
    code = normalize_code(raw)
    cache_key = code or raw
    cached = _ORG_CACHE.get(cache_key)
    if cached:
        return dict(cached)

    keyword = code or raw
    rows = search_orgs(keyword, max_num=10)
    picked: dict[str, str] | None = None
    if code:
        for row in rows:
            if normalize_code(row.get("code", "")) == code:
                picked = row
                break
    if picked is None and rows:
        picked = rows[0]

    if picked is None and code:
        mapping = load_org_map()
        picked = mapping.get(code)

    if not picked or not picked.get("org_id"):
        return None

    query_code = a_share_code(picked.get("code") or code, picked["org_id"])
    if query_code and query_code != normalize_code(picked.get("code", "")):
        # B 股：再用 A 股代码确认一次，保证 stock= 用的是可查代码
        a_rows = search_orgs(query_code, max_num=10)
        for row in a_rows:
            if normalize_code(row.get("code", "")) == query_code:
                picked = row
                break
        else:
            picked = {
                **picked,
                "code": query_code,
                "input_code": code or raw,
            }
    elif query_code:
        picked = {**picked, "code": query_code}

    _ORG_CACHE[cache_key] = picked
    if picked.get("code"):
        _ORG_CACHE[picked["code"]] = picked
    return dict(picked)


# ---------------------------------------------------------------------------
# 列表查询
# ---------------------------------------------------------------------------


def _normalize_item(
    row: dict[str, Any],
    *,
    column: str,
    tab: str,
    fallback_code: str = "",
    fallback_name: str = "",
    fallback_org: str = "",
) -> dict[str, Any] | None:
    title = strip_em(row.get("announcementTitle"))
    if not title:
        return None
    adjunct = safe_str(row.get("adjunctUrl"))
    published = parse_announcement_time(row.get("announcementTime"))
    return {
        "code": safe_str(row.get("secCode")) or fallback_code,
        "name": safe_str(row.get("secName")) or fallback_name,
        "org_id": safe_str(row.get("orgId")) or fallback_org,
        "announcement_id": safe_str(row.get("announcementId")),
        "title": title,
        "published_at": _fmt_dt(published),
        "published_ms": int(row["announcementTime"])
        if isinstance(row.get("announcementTime"), (int, float))
        else None,
        "url": pdf_url(adjunct),
        "adjunct_url": adjunct,
        "adjunct_type": safe_str(row.get("adjunctType")) or "PDF",
        "adjunct_size": row.get("adjunctSize"),
        "category": safe_str(row.get("announcementTypeName")),
        "category_code": safe_str(row.get("announcementType")),
        "column": column,
        "tab": tab,
        "source": "巨潮资讯",
    }


def query_page(
    *,
    stock: str = "",
    page_num: int = 1,
    page_size: int = PAGE_SIZE,
    column: str = "szse",
    tab: str = "fulltext",
    se_date: str = "",
    category: str = "",
    search_key: str = "",
    plate: str = "",
    trade: str = "",
    sort_name: str = "",
    sort_type: str = "",
    highlight_title: bool = True,
) -> dict[str, Any]:
    """单页原始查询。``stock`` 为空时做全市场切片（需配合 plate/category/日期）。"""
    form = {
        "pageNum": max(1, int(page_num)),
        "pageSize": max(1, min(int(page_size), PAGE_SIZE)),
        "column": column or "szse",
        "tabName": tab or "fulltext",
        "plate": plate or "",
        "searchkey": search_key or "",
        "secid": "",
        "category": category or "",
        "trade": trade or "",
        "seDate": se_date or "",
        "sortName": sort_name or "",
        "sortType": sort_type or "",
        "isHLtitle": "true" if highlight_title else "false",
        "stock": stock or "",
    }
    payload = _post_json(QUERY_URL, data=form, headers=_FORM_HEADERS)
    if not isinstance(payload, dict):
        return {
            "announcements": [],
            "totalAnnouncement": 0,
            "totalpages": 0,
            "hasMore": False,
        }
    return payload


def _collect_pages(
    *,
    stock: str,
    column: str,
    tab: str,
    se_date: str,
    category: str,
    search_key: str,
    plate: str,
    max_pages: int,
    fallback_code: str,
    fallback_name: str,
    fallback_org: str,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    total = 0
    total_pages = 1
    page = 1
    limit = max(1, int(max_pages))
    while page <= total_pages and page <= limit:
        try:
            payload = query_page(
                stock=stock,
                page_num=page,
                column=column,
                tab=tab,
                se_date=se_date,
                category=category,
                search_key=search_key,
                plate=plate,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("hisAnnouncement 失败 page=%s: %s", page, exc)
            break
        rows = payload.get("announcements") or []
        total = int(payload.get("totalAnnouncement") or payload.get("totalRecordNum") or 0)
        total_pages = int(payload.get("totalpages") or 1)
        has_more = bool(payload.get("hasMore"))
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _normalize_item(
                row,
                column=column,
                tab=tab,
                fallback_code=fallback_code,
                fallback_name=fallback_name,
                fallback_org=fallback_org,
            )
            if not item:
                continue
            key = item["announcement_id"] or f"{item['title']}|{item['published_at'][:10]}"
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
        if page >= total_pages and not has_more:
            break
        page += 1
        if page <= total_pages and page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)
    return items, total


def fetch_announcements(
    code: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    column: str | None = None,
    tab: str = "fulltext",
    category: str | Sequence[str] | None = None,
    keyword: str = "",
    plate: str = "",
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """按股票拉取巨潮公告（主入口）。

    ``category`` 可用 ``annual`` / ``年报`` / ``category_ndbg_szsh``。
    ``tab`` 可用 ``fulltext`` / ``relation`` / ``supervise``。
    """
    org = resolve_org(code)
    if not org:
        return {
            "code": normalize_code(code) or safe_str(code),
            "name": "",
            "org_id": "",
            "column": "",
            "tab": resolve_tab(tab),
            "se_date": "",
            "source": "cninfo",
            "count": 0,
            "total": 0,
            "items": [],
            "error": f"找不到 orgId: {code}",
        }

    query_code = org["code"]
    col = resolve_column(column, query_code)
    tab_name = resolve_tab(tab)
    cat = resolve_category(category)
    se_date = _se_date(start, end, days)
    stock = f"{query_code},{org['org_id']}"

    items, total = _collect_pages(
        stock=stock,
        column=col,
        tab=tab_name,
        se_date=se_date,
        category=cat,
        search_key=safe_str(keyword),
        plate=safe_str(plate),
        max_pages=max_pages,
        fallback_code=query_code,
        fallback_name=org.get("name", ""),
        fallback_org=org["org_id"],
    )
    return {
        "code": query_code,
        "name": org.get("name", ""),
        "org_id": org["org_id"],
        "column": col,
        "tab": tab_name,
        "category": cat,
        "keyword": safe_str(keyword),
        "se_date": se_date,
        "source": "cninfo",
        "count": len(items),
        "total": total,
        "items": items,
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
    return fetch_announcements(
        code,
        start=start,
        end=end,
        days=days,
        category=kind,
        max_pages=max_pages,
    )


def search_announcements(
    code: str,
    keyword: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """按标题关键词搜该公司公告。"""
    return fetch_announcements(
        code,
        start=start,
        end=end,
        days=days,
        keyword=keyword,
        max_pages=max_pages,
    )


def fetch_surveys(
    code: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """投资者关系 / 调研记录（tabName=relation）。"""
    return fetch_announcements(
        code,
        start=start,
        end=end,
        days=days,
        tab="relation",
        max_pages=max_pages,
    )


def fetch_supervise(
    code: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """持续督导（tabName=supervise）。"""
    return fetch_announcements(
        code,
        start=start,
        end=end,
        days=days,
        tab="supervise",
        max_pages=max_pages,
    )


def fetch_market_announcements(
    *,
    column: str = "szse",
    category: str | Sequence[str] | None = None,
    keyword: str = "",
    plate: str = "",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 7,
    max_pages: int = 5,
) -> dict[str, Any]:
    """不指定个股的全市场切片（例如近一周年报）。"""
    col = resolve_column(column)
    cat = resolve_category(category)
    se_date = _se_date(start, end, days)
    items, total = _collect_pages(
        stock="",
        column=col,
        tab="fulltext",
        se_date=se_date,
        category=cat,
        search_key=safe_str(keyword),
        plate=safe_str(plate),
        max_pages=max_pages,
        fallback_code="",
        fallback_name="",
        fallback_org="",
    )
    return {
        "code": "",
        "name": "",
        "org_id": "",
        "column": col,
        "tab": "fulltext",
        "category": cat,
        "keyword": safe_str(keyword),
        "plate": safe_str(plate),
        "se_date": se_date,
        "source": "cninfo",
        "count": len(items),
        "total": total,
        "items": items,
    }


def download_pdf(url: str, dest: str | Path) -> Path:
    """下载一条公告 PDF。"""
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    data = get_bytes(
        url,
        headers={"Referer": "https://www.cninfo.com.cn/"},
        timeout=60,
    )
    dest_path.write_bytes(data)
    return dest_path


def _safe_filename(title: str, announcement_id: str, url: str) -> str:
    stem = Path(unquote(urlparse(url).path)).name or f"{announcement_id}.PDF"
    if not title:
        return stem
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", title).strip(" .")
    cleaned = cleaned[:80] or announcement_id or "announcement"
    suffix = Path(stem).suffix or ".PDF"
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
            safe_str(item.get("announcement_id")),
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
    if pack.get("org_id"):
        extra.append(pack["org_id"])
    print(
        " ".join(extra)
        + f"  column={pack.get('column')} tab={pack.get('tab')} "
        + f"seDate={pack.get('se_date')} count={pack.get('count')}"
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
    parser = argparse.ArgumentParser(description="从巨潮资讯网拉取上市公司公告")
    parser.add_argument(
        "code",
        nargs="?",
        default="",
        help="股票代码或简称，如 600519 / 贵州茅台；与 --market 二选一",
    )
    parser.add_argument("--days", type=int, default=365, help="回溯天数，默认 365")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--column",
        default="auto",
        help="sse / szse / bj / auto，默认按代码判断",
    )
    parser.add_argument(
        "--tab",
        default="fulltext",
        help="fulltext 公告 | relation 调研 | supervise 持续督导",
    )
    parser.add_argument(
        "--category",
        default="",
        help="分类别名，如 annual / 年报 / q1；多个用逗号分隔",
    )
    parser.add_argument("--keyword", default="", help="标题关键词")
    parser.add_argument("--plate", default="", help="板块，如 szmb / shkcp")
    parser.add_argument("--max-pages", type=int, default=5, help="最多翻页，默认 5")
    parser.add_argument("--limit", type=int, default=10, help="打印/下载前 N 条；0 为全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--org-only", action="store_true", help="只解析 orgId，不查公告")
    parser.add_argument(
        "--market",
        default="",
        help="不指定个股时的全市场栏目：sse / szse / bj",
    )
    parser.add_argument("--download", default="", help="把公告 PDF 存到该目录")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.org_only:
        if not args.code:
            parser.error("--org-only 需要股票代码或简称")
        org = resolve_org(args.code)
        if args.json:
            print(json.dumps(org or {}, ensure_ascii=False, indent=2))
        elif org:
            print(
                f"{org.get('code')} {org.get('name') or ''}  "
                f"orgId={org.get('org_id')}  {org.get('category') or ''}"
            )
        else:
            print(f"找不到 orgId: {args.code}")
            return 1
        return 0

    start = args.start or None
    end = args.end or None
    category = args.category or None

    if args.market and not args.code:
        pack = fetch_market_announcements(
            column=args.market,
            category=category,
            keyword=args.keyword,
            plate=args.plate,
            start=start,
            end=end,
            days=args.days,
            max_pages=args.max_pages,
        )
    else:
        if not args.code:
            parser.error("请提供股票代码，或使用 --market 做全市场查询")
        pack = fetch_announcements(
            args.code,
            start=start,
            end=end,
            days=args.days,
            column=args.column,
            tab=args.tab,
            category=category,
            keyword=args.keyword,
            plate=args.plate,
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
