"""详情页资讯：采集后按通道分组，供 /api/stocks/news 使用。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from core.codes import detect_market, normalize_code, safe_str

from company.news._items import (
    dedupe,
    full_lookback_days,
    lookback_start,
    sort_key,
    span_meta,
    within_lookback,
)
from company.news.cache import load_cache, save_cache
from company.news.query import (
    query_announcements,
    query_market_news,
    query_press,
    query_reports,
)
from company.news.taxonomy.constants import TIER_DESIGNATED_PRESS, TIER_OFFICIAL_MEDIA
from company.news.taxonomy.media_tiers import resolve_media_tier

logger = logging.getLogger(__name__)

VALID_KINDS = (
    "exchange",
    "cninfo",
    "designated_press",
    "official_news",
    "other_news",
    "reports",
)
_NEWS_KINDS = ("designated_press", "official_news", "other_news")
_KIND_ALIASES = {
    "notices": ("exchange", "cninfo"),
    "news": _NEWS_KINDS,
    "official": ("designated_press", "official_news"),
}

LOOKBACK_YEARS = 50
DEFAULT_FEED_DAYS = 3
MAX_NOTICES = 5000
MAX_NEWS = 8000
MAX_REPORTS = 5000


def pages_for_days(days: int) -> int:
    d = max(1, int(days))
    if d <= 30:
        return 3
    if d <= 365:
        return 20
    if d <= 365 * 5:
        return 60
    if d <= 365 * 15:
        return 120
    return 200


def _empty_groups() -> dict[str, list[dict[str, Any]]]:
    return {k: [] for k in VALID_KINDS}


def _exchange_channel(code: str) -> str | None:
    market = detect_market(code)
    return market if market in {"sse", "szse", "bse"} else None


def _safe(label: str, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s 失败: %s", label, exc)
        return []


def _take(
    rows: list[dict[str, Any]],
    start: datetime,
    *,
    require_time: bool,
    limit: int,
) -> list[dict[str, Any]]:
    kept = [x for x in rows if within_lookback(x, start, require_time=require_time)]
    return sorted(kept, key=sort_key)[:limit]


def _media_bucket(item: dict[str, Any]) -> str:
    media = item.get("media_name") or item.get("source") or ""
    tier = resolve_media_tier(str(media))
    if tier == TIER_DESIGNATED_PRESS:
        return "designated_press"
    if tier == TIER_OFFICIAL_MEDIA:
        return "official_news"
    return "other_news"


def _bucket_news(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets = {k: [] for k in _NEWS_KINDS}
    for item in rows:
        buckets[_media_bucket(item)].append(item)
    return buckets


def _resolve_kinds(kind: str) -> list[str]:
    if kind in _KIND_ALIASES:
        return list(_KIND_ALIASES[kind])
    if kind and kind not in VALID_KINDS:
        raise ValueError(f"kind 无效，可选: {', '.join(VALID_KINDS)}")
    return [kind] if kind else list(VALID_KINDS)


def _news_only_payload(
    base: dict[str, Any],
    *,
    kind: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    groups = _empty_groups()
    groups[kind] = rows
    span = span_meta(rows)
    payload = dict(base)
    payload.update(
        {
            "kind": kind,
            "groups": groups,
            "counts": {k: len(groups[k]) for k in VALID_KINDS},
            "items": rows,
            "candidate_count": len(rows),
            "span_from": span["from"],
            "span_to": span["to"],
        }
    )
    return payload


def collect_company_messages(
    code: str,
    name: str = "",
    *,
    force_refresh: bool = False,
    days: int | None = None,
    kind: str = "",
) -> dict[str, Any]:
    """采集交易所/巨潮公告、七报七网、官方新闻、其他新闻、机构研报。"""
    code = normalize_code(code) or safe_str(code)
    name = safe_str(name)
    if not code:
        raise ValueError("缺少公司代码 code")

    days = DEFAULT_FEED_DAYS if days is None else max(1, int(days))
    days = min(days, full_lookback_days(years=LOOKBACK_YEARS))
    kind = (kind or "").strip().lower()
    kinds = _resolve_kinds(kind)

    if not force_refresh:
        cached = load_cache(code, days, kind)
        if cached is not None and isinstance(cached.get("groups"), dict):
            return cached

    start = lookback_start(days, years=LOOKBACK_YEARS)
    require_time = days <= 30
    max_pages = pages_for_days(days)
    groups = _empty_groups()
    news_buckets = {k: [] for k in _NEWS_KINDS}

    if "exchange" in kinds:
        ch = _exchange_channel(code)
        if ch:
            groups["exchange"] = _take(
                _safe("exchange", query_announcements, code, channel=ch, start=start, days=None, max_pages=max_pages),
                start,
                require_time=require_time,
                limit=MAX_NOTICES,
            )

    if "cninfo" in kinds:
        groups["cninfo"] = _take(
            _safe("cninfo", query_announcements, code, channel="cninfo", start=start, days=None, max_pages=max_pages),
            start,
            require_time=require_time,
            limit=MAX_NOTICES,
        )

    need_market = any(k in kinds for k in ("official_news", "other_news"))
    if need_market:
        news_buckets = _bucket_news(
            _take(
                _safe(
                    "market_news",
                    query_market_news,
                    code,
                    name,
                    start=start,
                    days=days,
                    max_pages=max_pages,
                    em_kind="all" if days > 180 else "old",
                ),
                start,
                require_time=require_time,
                limit=MAX_NEWS,
            )
        )

    if "designated_press" in kinds:
        press = _safe(
            "press",
            query_press,
            code or name,
            outlet="all",
            start=start,
            days=None,
            max_pages=max(2, min(max_pages, 4)),
        )
        rows = list((press or {}).get("items") or []) if isinstance(press, dict) else []
        for row in rows:
            row.setdefault("code", code)
            row.setdefault("name", name)
        merged = dedupe(_take(rows, start, require_time=require_time, limit=MAX_NEWS) + news_buckets["designated_press"])
        news_buckets["designated_press"] = sorted(merged, key=sort_key)[:MAX_NEWS]

    for nk in _NEWS_KINDS:
        if nk in kinds:
            groups[nk] = news_buckets.get(nk, [])

    if "reports" in kinds:
        groups["reports"] = _take(
            _safe("reports", query_reports, code, name, start=start, days=None, max_pages=max_pages),
            start,
            require_time=require_time,
            limit=MAX_REPORTS,
        )

    items = sorted((row for key in VALID_KINDS for row in groups[key]), key=sort_key)
    span = span_meta(items)
    data: dict[str, Any] = {
        "code": code,
        "name": name,
        "mode": "window",
        "days": days,
        "kind": kind or "all",
        "lookback_years": LOOKBACK_YEARS,
        "full_days": full_lookback_days(years=LOOKBACK_YEARS),
        "span_from": span["from"],
        "span_to": span["to"],
        "candidate_count": sum(len(groups[k]) for k in VALID_KINDS),
        "counts": {k: len(groups[k]) for k in VALID_KINDS},
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "groups": groups,
        "items": items,
        "source": "company.news",
    }
    save_cache(code, data, days, kind)

    if kind in ("official_news", "other_news"):
        sibling = "other_news" if kind == "official_news" else "official_news"
        save_cache(
            code,
            _news_only_payload(data, kind=sibling, rows=news_buckets[sibling]),
            days,
            sibling,
        )
    return data
