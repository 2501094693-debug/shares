"""详情页资讯入口。

对外暴露 collect_company_messages()，供 /api/stocks/news 使用。
分组键：exchange / cninfo / designated_press / official_news / other_news / reports。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from message.disclosure.http_util import (
    detect_market,
    full_lookback_days,
    lookback_start,
    normalize_code,
    sort_key,
    within_lookback,
)
from message.disclosure.query import query_announcements
from message.market import fetch_media_news, fetch_research_reports
from message.taxonomy.constants import TIER_DESIGNATED_PRESS, TIER_OFFICIAL_MEDIA
from message.taxonomy.media_tiers import resolve_media_tier

from .cache import load_cache, save_cache
from .constants import DEFAULT_FEED_DAYS, LOOKBACK_YEARS, pages_for_days
from .process import (
    dedupe,
    filter_news,
    filter_notices,
    filter_reports,
    span_meta,
)

VALID_KINDS = (
    "exchange",
    "cninfo",
    "designated_press",
    "official_news",
    "other_news",
    "reports",
)
_NEWS_KINDS = ("designated_press", "official_news", "other_news")


def _empty_groups() -> dict[str, list[dict[str, Any]]]:
    return {k: [] for k in VALID_KINDS}


def _exchange_channel(code: str) -> str | None:
    market = detect_market(code)
    if market in {"sse", "szse", "bse"}:
        return market
    return None


def _fetch_kind_notices(
    code: str,
    *,
    channel: str,
    start: datetime,
    require_time: bool,
    max_pages: int,
) -> list[dict[str, Any]]:
    raw = query_announcements(
        code,
        channel=channel,
        start=start,
        end=None,
        days=None,
        max_pages=max_pages,
    )
    raw = [
        x
        for x in dedupe(raw)
        if within_lookback(x, start, require_time=require_time)
    ]
    return filter_notices(raw)


def _media_bucket(item: dict[str, Any]) -> str:
    media = item.get("media_name") or item.get("source") or ""
    tier = resolve_media_tier(str(media))
    if tier == TIER_DESIGNATED_PRESS:
        return "designated_press"
    if tier == TIER_OFFICIAL_MEDIA:
        return "official_news"
    return "other_news"


def _split_media_news(
    code: str,
    name: str,
    start: datetime,
    *,
    require_time: bool,
) -> dict[str, list[dict[str, Any]]]:
    news_raw: list[dict[str, Any]] = []
    news_raw.extend(fetch_media_news(code, start))
    if name and name != code:
        news_raw.extend(fetch_media_news(name, start))
    news_raw = [
        x
        for x in dedupe(news_raw)
        if within_lookback(x, start, require_time=require_time)
    ]
    buckets: dict[str, list[dict[str, Any]]] = {
        "designated_press": [],
        "official_news": [],
        "other_news": [],
    }
    for item in news_raw:
        buckets[_media_bucket(item)].append(item)
    return {k: filter_news(v) for k, v in buckets.items()}


def _resolve_kinds(kind: str) -> list[str]:
    if kind == "notices":
        return ["exchange", "cninfo"]
    if kind == "news":
        return list(_NEWS_KINDS)
    # 旧整包别名：七报七网 + 官方新闻
    if kind == "official":
        return ["designated_press", "official_news"]
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
    payload["kind"] = kind
    payload["groups"] = groups
    payload["counts"] = {k: len(groups[k]) for k in VALID_KINDS}
    payload["items"] = rows
    payload["candidate_count"] = len(rows)
    payload["span_from"] = span["from"]
    payload["span_to"] = span["to"]
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
    code = normalize_code(code) or (code or "").strip()
    name = (name or "").strip()
    if not code:
        raise ValueError("缺少公司代码 code")

    if days is None:
        days = DEFAULT_FEED_DAYS
    days = max(1, int(days))
    days = min(days, full_lookback_days(years=LOOKBACK_YEARS))

    kind = (kind or "").strip().lower()
    kinds = _resolve_kinds(kind)

    cache_kind = kind
    if not force_refresh:
        cached = load_cache(code, days, cache_kind)
        if cached is not None and isinstance(cached.get("groups"), dict):
            return cached

    start = lookback_start(days, years=LOOKBACK_YEARS)
    require_time = days <= 30
    max_pages = pages_for_days(days)

    groups = _empty_groups()
    candidate_count = 0
    news_buckets: dict[str, list[dict[str, Any]]] = {
        "designated_press": [],
        "official_news": [],
        "other_news": [],
    }

    if "exchange" in kinds:
        ch = _exchange_channel(code)
        if ch:
            rows = _fetch_kind_notices(
                code,
                channel=ch,
                start=start,
                require_time=require_time,
                max_pages=max_pages,
            )
            groups["exchange"] = rows
            candidate_count += len(rows)

    if "cninfo" in kinds:
        rows = _fetch_kind_notices(
            code,
            channel="cninfo",
            start=start,
            require_time=require_time,
            max_pages=max_pages,
        )
        groups["cninfo"] = rows
        candidate_count += len(rows)

    need_news = any(k in kinds for k in _NEWS_KINDS)
    if need_news:
        news_buckets = _split_media_news(
            code, name, start, require_time=require_time
        )
        for nk in _NEWS_KINDS:
            if nk in kinds:
                groups[nk] = news_buckets[nk]
                candidate_count += len(news_buckets[nk])

    if "reports" in kinds:
        reports_raw = fetch_research_reports(code, start)
        reports_raw = [
            x
            for x in dedupe(reports_raw)
            if within_lookback(x, start, require_time=require_time)
        ]
        groups["reports"] = filter_reports(reports_raw)
        candidate_count += len(reports_raw)

    items = sorted(
        [row for key in VALID_KINDS for row in groups[key]],
        key=sort_key,
    )
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
        "candidate_count": candidate_count,
        "counts": {k: len(groups[k]) for k in VALID_KINDS},
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "groups": groups,
        "items": items,
        "source": "message",
    }

    save_cache(code, data, days, cache_kind)

    # 任一新闻分栏请求时，顺带写另外两栏缓存，避免重复打东财
    if kind in _NEWS_KINDS:
        for sibling_kind in _NEWS_KINDS:
            if sibling_kind == kind:
                continue
            save_cache(
                code,
                _news_only_payload(
                    data,
                    kind=sibling_kind,
                    rows=news_buckets[sibling_kind],
                ),
                days,
                sibling_kind,
            )

    return data


# 兼容旧名
collect_important_news = collect_company_messages
