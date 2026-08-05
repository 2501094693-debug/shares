"""公司新闻智能体：近 1–2 年公告 + 媒体新闻 -> 筛选 -> 按时间从新到旧。"""

from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd
import requests

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover
    curl_requests = None

from core.paths import NEWS_CACHE_DIR, ensure_cache_dirs

CACHE_DIR = NEWS_CACHE_DIR
CACHE_TTL_SEC = 30 * 60
CACHE_VERSION = 6  # bump: keep all related media news
LOOKBACK_YEARS = 2
MAX_CANDIDATES = 160
MAX_RESULT = 80
MAX_PER_GROUP = 60
MAX_NOTICES = 500  # full announcement list within lookback
MAX_REPORTS = 2000  # full research-report list within lookback
MAX_NEWS = 2000  # keep all fetched media news within lookback
NEWS_PAGE_SIZE = 100
NEWS_MAX_PAGES = 10  # East Money hard-stops around 1000 hits
REQUEST_PAUSE_SEC = 0.25
EM_REPORT_URL = "https://reportapi.eastmoney.com/report/list"

EM_NEWS_URL = "https://search-api-web.eastmoney.com/search/jsonp"
EM_NEWS_CB = "jQuery35101792940631092459_1700000000000"

IMPORTANT_KEYWORDS = [
    "\u516c\u544a",
    "\u4e1a\u7ee9",
    "\u9884\u544a",
    "\u5feb\u62a5",
    "\u5e74\u62a5",
    "\u534a\u5e74\u62a5",
    "\u5b63\u62a5",
    "\u4e2d\u6807",
    "\u5408\u540c",
    "\u8ba2\u5355",
    "\u5e76\u8d2d",
    "\u91cd\u7ec4",
    "\u6536\u8d2d",
    "\u8d2d\u4e70",
    "\u589e\u6301",
    "\u51cf\u6301",
    "\u56de\u8d2d",
    "\u5904\u7f5a",
    "\u7acb\u6848",
    "\u76d1\u7ba1",
    "\u95ee\u8be2",
    "\u8bc9\u8bbc",
    "\u589e\u53d1",
    "\u914d\u80a1",
    "\u505c\u724c",
    "\u590d\u724c",
    "\u80a1\u6743\u6fc0\u52b1",
    "\u91cd\u5927",
    "\u7a81\u7834",
    "\u83b7\u6279",
    "\u6838\u51c6",
    "\u80a1\u4e1c\u5927\u4f1a",
    "\u51b3\u8bae",
    "\u5206\u7ea2",
    "\u5229\u6da6",
    "\u4e8f\u635f",
    "\u98ce\u9669\u63d0\u793a",
    "\u8d44\u4ea7\u91cd\u7ec4",
    "\u878d\u8d44",
]

WEAK_KEYWORDS = [
    "\u6da8\u8dcc\u5e45",
    "\u9f99\u864e\u699c",
    "\u8d44\u91d1\u6d41\u5411",
    "\u5f02\u52a8\u80a1",
    "\u677f\u5757\u6da8\u5e45",
    "\u5348\u8bc4",
    "\u5c3e\u76d8",
    "\u590d\u76d8",
    "\u76d8\u4e2d\u5feb\u8baf",
]

# Prefer these announcement categories when present in title/type.
NOTICE_KEEP_KEYWORDS = [
    "\u4e1a\u7ee9",
    "\u5e74\u62a5",
    "\u534a\u5e74\u62a5",
    "\u5b63\u62a5",
    "\u9884\u544a",
    "\u5feb\u62a5",
    "\u91cd\u5927",
    "\u91cd\u7ec4",
    "\u6536\u8d2d",
    "\u878d\u8d44",
    "\u98ce\u9669",
    "\u95ee\u8be2",
    "\u5904\u7f5a",
    "\u7acb\u6848",
    "\u589e\u6301",
    "\u51cf\u6301",
    "\u56de\u8d2d",
    "\u80a1\u6743\u6fc0\u52b1",
    "\u5206\u7ea2",
    "\u5229\u6da6",
    "\u4e8f\u635f",
    "\u505c\u724c",
    "\u590d\u724c",
    "\u80a1\u4e1c\u5927\u4f1a",
    "\u51b3\u8bae",
    "\u62db\u80a1",
    "\u914d\u80a1",
    "\u53ef\u8f6c\u503a",
    "\u5408\u540c",
    "\u4e2d\u6807",
]


def _safe_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = _safe_str(value)
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _sort_key(item: dict[str, Any]) -> tuple[int, float]:
    dt = _parse_time(item.get("published_at", ""))
    if dt is None:
        return (1, 0.0)
    return (0, -dt.timestamp())


def _lookback_start() -> datetime:
    return datetime.now() - timedelta(days=365 * LOOKBACK_YEARS + 5)


def _within_lookback(item: dict[str, Any], start: datetime) -> bool:
    dt = _parse_time(item.get("published_at", ""))
    if dt is None:
        return True
    return dt >= start


def _cache_path(code: str) -> Path:
    safe = re.sub(r"[^\w.-]+", "_", code.strip()) or "unknown"
    return CACHE_DIR / f"{safe}.json"


def _load_cache(code: str) -> dict[str, Any] | None:
    path = _cache_path(code)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(payload.get("version") or 0) != CACHE_VERSION:
        return None
    cached_at = float(payload.get("cached_at") or 0)
    if time.time() - cached_at > CACHE_TTL_SEC:
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def _save_cache(code: str, data: dict[str, Any]) -> None:
    ensure_cache_dirs()
    path = _cache_path(code)
    path.write_text(
        json.dumps(
            {
                "version": CACHE_VERSION,
                "cached_at": time.time(),
                "data": data,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _strip_em_tags(text: str) -> str:
    return re.sub(r"</?em>", "", text or "")


def _fetch_notices(code: str) -> list[dict[str, Any]]:
    """Fetch company announcements for the lookback window (covers 1–2 years)."""
    end = date.today()
    begin = (datetime.now() - timedelta(days=365 * LOOKBACK_YEARS)).date()
    # akshare expects YYYYMMDD for this endpoint.
    begin_s = begin.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")
    try:
        df = ak.stock_individual_notice_report(
            security=code,
            symbol="\u5168\u90e8",
            begin_date=begin_s,
            end_date=end_s,
        )
    except Exception:  # noqa: BLE001
        return []
    if df is None or df.empty:
        return []

    items: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        title = _safe_str(row.get("\u516c\u544a\u6807\u9898"))
        if not title:
            continue
        notice_type = _safe_str(row.get("\u516c\u544a\u7c7b\u578b"))
        published = row.get("\u516c\u544a\u65e5\u671f")
        items.append(
            {
                "title": title,
                "summary": notice_type,
                "source": "\u516c\u53f8\u516c\u544a",
                "url": _safe_str(row.get("\u7f51\u5740")),
                "published_at": _safe_str(published),
                "kind": "notice",
                "why": notice_type or "\u516c\u544a",
            }
        )
    return items


def _http_get(url: str, *, params: dict[str, Any], headers: dict[str, str], timeout: int = 25):
    """Prefer curl_cffi (required by East Money search); fall back to requests."""
    if curl_requests is not None:
        return curl_requests.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            impersonate="chrome",
        )
    return requests.get(url, params=params, headers=headers, timeout=timeout)


def _fetch_em_news_page(keyword: str, page_index: int) -> tuple[int, list[dict[str, Any]]]:
    from urllib.parse import quote

    inner = {
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "time",
                "pageIndex": page_index,
                "pageSize": NEWS_PAGE_SIZE,
                "preTag": "<em>",
                "postTag": "</em>",
            }
        },
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": f"https://so.eastmoney.com/news/s?keyword={quote(keyword)}",
        "Accept": "*/*",
    }
    try:
        resp = _http_get(
            EM_NEWS_URL,
            params={
                "cb": EM_NEWS_CB,
                "param": json.dumps(inner, ensure_ascii=False),
                "_": str(int(time.time() * 1000)),
            },
            headers=headers,
            timeout=25,
        )
        resp.raise_for_status()
        text = resp.text
        start = text.find("(")
        end = text.rfind(")")
        if start < 0 or end <= start:
            return 0, []
        payload = json.loads(text[start + 1 : end])
    except Exception:  # noqa: BLE001
        return 0, []

    hits = int(payload.get("hitsTotal") or 0)
    rows = ((payload.get("result") or {}).get("cmsArticleWebOld")) or []
    if isinstance(rows, dict):
        rows = rows.get("list") or rows.get("data") or []
    if not isinstance(rows, list):
        rows = []

    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _strip_em_tags(_safe_str(row.get("title")))
        if not title:
            continue
        code_id = _safe_str(row.get("code"))
        url = _safe_str(row.get("url"))
        if not url and code_id:
            url = f"http://finance.eastmoney.com/a/{code_id}.html"
        items.append(
            {
                "title": title,
                "summary": _strip_em_tags(_safe_str(row.get("content"))),
                "source": _safe_str(row.get("mediaName")) or "\u4e1c\u65b9\u8d22\u5bcc",
                "url": url,
                "published_at": _safe_str(row.get("date")),
                "kind": "news",
                "why": "",
            }
        )
    return hits, items


def _fetch_media_news(keyword: str, lookback_start: datetime) -> list[dict[str, Any]]:
    """Paginate East Money media search by time; supplement notices with recent media."""
    keyword = (keyword or "").strip()
    if not keyword:
        return []

    hits, first = _fetch_em_news_page(keyword, 1)
    collected = list(first)
    total_pages = min(NEWS_MAX_PAGES, max(1, math.ceil(hits / NEWS_PAGE_SIZE))) if hits else NEWS_MAX_PAGES

    for page in range(2, total_pages + 1):
        if collected:
            dated = [_parse_time(x.get("published_at")) for x in collected]
            dated = [d for d in dated if d is not None]
            if dated and min(dated) < lookback_start:
                break
        time.sleep(REQUEST_PAUSE_SEC)
        _, rows = _fetch_em_news_page(keyword, page)
        if not rows:
            break
        collected.extend(rows)
        page_dates = [_parse_time(x.get("published_at")) for x in rows]
        page_dates = [d for d in page_dates if d is not None]
        if page_dates and min(page_dates) < lookback_start:
            break

    return [x for x in collected if _within_lookback(x, lookback_start)]


def _fetch_research_reports(code: str, lookback_start: datetime) -> list[dict[str, Any]]:
    """Fetch all institutional research reports in the lookback window."""
    code = (code or "").strip()
    if not code:
        return []

    begin = lookback_start.date().strftime("%Y-%m-%d")
    end = (date.today().replace(year=date.today().year + 1)).strftime("%Y-01-01")
    page_size = 100
    page_no = 1
    total_pages = 1
    items: list[dict[str, Any]] = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://data.eastmoney.com/report/stock.jshtml",
        "Accept": "application/json, text/plain, */*",
    }

    while page_no <= total_pages and page_no <= 50:
        params = {
            "industryCode": "*",
            "pageSize": str(page_size),
            "industry": "*",
            "rating": "*",
            "ratingChange": "*",
            "beginTime": begin,
            "endTime": end,
            "pageNo": str(page_no),
            "fields": "",
            "qType": "0",
            "orgCode": "",
            "code": code,
            "rcode": "",
            "p": str(page_no),
            "pageNum": str(page_no),
            "pageNumber": str(page_no),
        }
        try:
            resp = _http_get(EM_REPORT_URL, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:  # noqa: BLE001
            break

        rows = payload.get("data") or []
        if not isinstance(rows, list) or not rows:
            break

        hits = int(payload.get("hits") or 0)
        total_pages = int(payload.get("TotalPage") or math.ceil(hits / page_size) or 1)

        for row in rows:
            if not isinstance(row, dict):
                continue
            title = _safe_str(row.get("title"))
            if not title:
                continue
            org = _safe_str(row.get("orgSName") or row.get("orgName"))
            rating = _safe_str(row.get("emRatingName") or row.get("sRatingName"))
            info_code = _safe_str(row.get("infoCode"))
            url = ""
            if info_code:
                url = f"https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"
            published = _safe_str(row.get("publishDate"))
            # publishDate sometimes like "2026-07-23 00:00:00"
            why_parts = [p for p in (org, rating) if p]
            items.append(
                {
                    "title": title,
                    "summary": " · ".join(why_parts) if why_parts else "\u673a\u6784\u7814\u62a5",
                    "source": org or "\u673a\u6784\u7814\u62a5",
                    "url": url,
                    "published_at": published,
                    "kind": "report",
                    "why": rating or "\u7814\u62a5",
                    "org": org,
                    "rating": rating,
                }
            )

        page_no += 1
        if page_no <= total_pages:
            time.sleep(REQUEST_PAUSE_SEC)

    if items:
        return [x for x in items if _within_lookback(x, lookback_start)]

    # Fallback to akshare if direct API returned nothing.
    try:
        df = ak.stock_research_report_em(symbol=code)
    except Exception:  # noqa: BLE001
        return []
    if df is None or df.empty:
        return []

    fallback: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        title = _safe_str(row.get("\u62a5\u544a\u540d\u79f0"))
        if not title:
            continue
        org = _safe_str(row.get("\u673a\u6784"))
        rating = _safe_str(row.get("\u4e1c\u8d22\u8bc4\u7ea7"))
        published = row.get("\u65e5\u671f")
        why_parts = [p for p in (org, rating) if p]
        fallback.append(
            {
                "title": title,
                "summary": " · ".join(why_parts) if why_parts else "\u673a\u6784\u7814\u62a5",
                "source": org or "\u673a\u6784\u7814\u62a5",
                "url": _safe_str(row.get("\u62a5\u544aPDF\u94fe\u63a5")),
                "published_at": _safe_str(published),
                "kind": "report",
                "why": rating or "\u7814\u62a5",
                "org": org,
                "rating": rating,
            }
        )
    return [x for x in fallback if _within_lookback(x, lookback_start)]


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    # Prefer notices when colliding with news.
    ordered = sorted(
        items,
        key=lambda x: {"notice": 0, "report": 1, "news": 2}.get(x.get("kind") or "news", 2),
    )
    for item in ordered:
        key = item.get("url") or item.get("title") or ""
        key = key.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _is_important_notice(item: dict[str, Any]) -> bool:
    text = f"{item.get('title', '')} {item.get('summary', '')} {item.get('why', '')}"
    return any(k in text for k in NOTICE_KEEP_KEYWORDS)


def _heuristic_filter(items: list[dict[str, Any]], company_name: str) -> list[dict[str, Any]]:
    name = (company_name or "").strip()
    kept: list[dict[str, Any]] = []
    for item in items:
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        if item.get("kind") == "notice":
            if _is_important_notice(item):
                row = dict(item)
                if not row.get("why"):
                    row["why"] = "\u516c\u544a"
                kept.append(row)
            continue

        if any(w in text for w in WEAK_KEYWORDS) and not any(k in text for k in IMPORTANT_KEYWORDS):
            continue
        hit = next((k for k in IMPORTANT_KEYWORDS if k in text), "")
        name_hit = bool(name) and name in text
        if hit or name_hit:
            row = dict(item)
            row["why"] = hit or "\u63d0\u53ca\u516c\u53f8"
            kept.append(row)

    if kept:
        return sorted(kept, key=_sort_key)[:MAX_RESULT]

    # Fallback: newest notices + news so the panel is never empty.
    fallback = sorted(items, key=_sort_key)[: min(30, MAX_RESULT)]
    return [dict(x, why=x.get("why") or "\u8fd1\u671f\u76f8\u5173") for x in fallback]


def _filter_notices(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep all announcements in the lookback window (no keyword culling)."""
    kept = []
    for item in items:
        row = dict(item)
        row["kind"] = "notice"
        if not row.get("why"):
            row["why"] = row.get("summary") or "\u516c\u544a"
        kept.append(row)
    return sorted(kept, key=_sort_key)[:MAX_NOTICES]


def _filter_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep all media news in the lookback window (no keyword culling)."""
    kept = []
    for item in items:
        row = dict(item)
        row["kind"] = "news"
        if not row.get("why"):
            row["why"] = "\u65b0\u95fb"
        kept.append(row)
    return sorted(kept, key=_sort_key)[:MAX_NEWS]


def _filter_reports(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep all research reports in the lookback window (no 60-item cap)."""
    kept = []
    for item in items:
        row = dict(item)
        row["kind"] = "report"
        if not row.get("why"):
            row["why"] = row.get("rating") or "\u7814\u62a5"
        kept.append(row)
    return sorted(kept, key=_sort_key)[:MAX_REPORTS]


def _split_groups(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    notices: list[dict[str, Any]] = []
    news: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for item in items:
        kind = item.get("kind") or "news"
        if kind == "notice":
            notices.append(item)
        elif kind == "report":
            reports.append(item)
        else:
            news.append(item)
    return {
        "notices": sorted(notices, key=_sort_key)[:MAX_PER_GROUP],
        "news": sorted(news, key=_sort_key)[:MAX_PER_GROUP],
        "reports": sorted(reports, key=_sort_key)[:MAX_PER_GROUP],
    }


def _llm_enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _extract_json(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty llm response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
    if not match:
        raise ValueError("no json in llm response")
    return json.loads(match.group(0))


def _llm_filter(
    items: list[dict[str, Any]],
    *,
    code: str,
    name: str,
) -> list[dict[str, Any]] | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    # Keep important notices first, then fill with recent media for LLM ranking.
    notices = [x for x in items if x.get("kind") == "notice" and _is_important_notice(x)]
    news = [x for x in items if x.get("kind") != "notice"]
    mixed = sorted(notices + news, key=_sort_key)[:MAX_CANDIDATES]

    payload_items = [
        {
            "index": i,
            "title": c.get("title", ""),
            "summary": (c.get("summary") or "")[:280],
            "published_at": c.get("published_at", ""),
            "source": c.get("source", ""),
            "kind": c.get("kind", "news"),
        }
        for i, c in enumerate(mixed)
    ]

    system = (
        "You filter A-share company news/announcements for importance over a 1-2 year horizon. "
        "Keep material events (earnings, M&A, contracts, regulation, buybacks, incentives, etc.). "
        "Drop routine market chatter. Return JSON only."
    )
    user = {
        "company": {"code": code, "name": name},
        "candidates": payload_items,
        "instruction": (
            f'Return {{"items":[{{"index":0,"why":"short reason"}},...]}} with at most {MAX_RESULT} items. '
            "Cover the full time span when possible, not only the last few days. "
            "Prefer notices for historical coverage."
        ),
    }

    try:
        resp = requests.post(
            f"{base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": json.dumps(user, ensure_ascii=False),
                    },
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
    except Exception:  # noqa: BLE001
        return None

    raw_items = parsed.get("items") if isinstance(parsed, dict) else parsed
    if not isinstance(raw_items, list):
        return None

    kept: list[dict[str, Any]] = []
    seen_idx: set[int] = set()
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry.get("index"))
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(mixed) or idx in seen_idx:
            continue
        seen_idx.add(idx)
        item = dict(mixed[idx])
        why = _safe_str(entry.get("why")) or item.get("why") or "\u91cd\u8981"
        item["why"] = why[:80]
        kept.append(item)
        if len(kept) >= MAX_RESULT:
            break

    return kept if kept else None


def _span_meta(items: list[dict[str, Any]]) -> dict[str, str]:
    dates = [_parse_time(x.get("published_at")) for x in items]
    dates = [d for d in dates if d is not None]
    if not dates:
        return {"from": "", "to": ""}
    return {
        "from": min(dates).strftime("%Y-%m-%d"),
        "to": max(dates).strftime("%Y-%m-%d"),
    }


def collect_important_news(
    code: str,
    name: str = "",
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Collect notices / media news / research reports for ~2 years, newest first."""
    code = (code or "").strip()
    name = (name or "").strip()
    if not code:
        raise ValueError("\u7f3a\u5c11\u516c\u53f8\u4ee3\u7801 code")

    if not force_refresh:
        cached = _load_cache(code)
        if cached is not None and isinstance(cached.get("groups"), dict):
            return cached

    lookback_start = _lookback_start()
    notices_raw = _fetch_notices(code)
    # Always search by code and company name, then merge/dedupe for fuller coverage.
    news_raw: list[dict[str, Any]] = []
    news_raw.extend(_fetch_media_news(code, lookback_start))
    if name and name != code:
        news_raw.extend(_fetch_media_news(name, lookback_start))
    reports_raw = _fetch_research_reports(code, lookback_start)

    notices_raw = [x for x in _dedupe(notices_raw) if _within_lookback(x, lookback_start)]
    news_raw = [x for x in _dedupe(news_raw) if _within_lookback(x, lookback_start)]
    reports_raw = [x for x in _dedupe(reports_raw) if _within_lookback(x, lookback_start)]

    # Keep full lists for all three groups (sorted newest-first).
    notices = _filter_notices(notices_raw)
    news_only = _filter_news(news_raw)
    reports = _filter_reports(reports_raw)
    mode = "full"

    groups = {
        "notices": notices,
        "news": news_only,
        "reports": reports,
    }

    items = sorted(
        groups["notices"] + groups["news"] + groups["reports"],
        key=_sort_key,
    )
    span = _span_meta(items)
    data = {
        "code": code,
        "name": name,
        "mode": mode,
        "lookback_years": LOOKBACK_YEARS,
        "span_from": span["from"],
        "span_to": span["to"],
        "candidate_count": len(notices_raw) + len(news_raw) + len(reports_raw),
        "counts": {
            "notices": len(groups["notices"]),
            "news": len(groups["news"]),
            "reports": len(groups["reports"]),
        },
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "groups": groups,
        "items": items,
    }
    _save_cache(code, data)
    return data
