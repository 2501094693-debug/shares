"""详情页资讯入口。

对外暴露 collect_company_messages()，供 /api/stocks/news 使用。
分组键：exchange / cninfo / designated_press / official_news / other_news / reports。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable

from core.codes import detect_market, normalize_code, safe_str

from company.news._items import (
    as_news,
    as_notice,
    as_report,
    dedupe,
    full_lookback_days,
    lookback_start,
    sort_key,
    span_meta,
    unpack,
    within_lookback,
)
from company.news.cache import load_cache, save_cache
from company.news.cninfo import fetch_announcements as fetch_cninfo_announcements
from company.news.eastmoney.search import fetch_news as fetch_eastmoney_news
from company.news.exchange import (
    fetch_bse_announcements,
    fetch_sse_announcements,
    fetch_szse_announcements,
)
from company.news.query import query_press
from company.news.taxonomy.constants import TIER_DESIGNATED_PRESS, TIER_OFFICIAL_MEDIA
from company.news.taxonomy.media_tiers import resolve_media_tier
from company.news.tonghuashun.news import fetch_news as fetch_ths_news
from company.news.tonghuashun.reports import fetch_reports as fetch_ths_reports
from company.news.xueqiu.news import fetch_news as fetch_xq_news
from company.news.xueqiu.reports import fetch_reports as fetch_xq_reports

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
_EXCHANGE_FETCH = {
    "sse": fetch_sse_announcements,
    "szse": fetch_szse_announcements,
    "bse": fetch_bse_announcements,
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
    if market in {"sse", "szse", "bse"}:
        return market
    return None


def _safe_unpack(
    fetcher: Callable[..., dict[str, Any]],
    target: str,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    try:
        return unpack(fetcher(target, **kwargs))
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s 失败 %s: %s", getattr(fetcher, "__name__", fetcher), target, exc)
        return []


def _fetch_notices(
    code: str,
    *,
    channel: str,
    start: datetime,
    require_time: bool,
    max_pages: int,
) -> list[dict[str, Any]]:
    if channel == "cninfo":
        fetcher = fetch_cninfo_announcements
    else:
        fetcher = _EXCHANGE_FETCH.get(channel)
        if fetcher is None:
            return []
    raw = _safe_unpack(
        fetcher,
        code,
        start=start,
        days=None,
        max_pages=max_pages,
    )
    name = raw[0].get("name", "") if raw else ""
    tagged = [as_notice(x, channel=channel, code=code, name=name) for x in raw]
    tagged = [
        x
        for x in dedupe(tagged)
        if within_lookback(x, start, require_time=require_time)
    ]
    return sorted(tagged, key=sort_key)[:MAX_NOTICES]


def _media_bucket(item: dict[str, Any]) -> str:
    media = item.get("media_name") or item.get("source") or ""
    tier = resolve_media_tier(str(media))
    if tier == TIER_DESIGNATED_PRESS:
        return "designated_press"
    if tier == TIER_OFFICIAL_MEDIA:
        return "official_news"
    return "other_news"


def _collect_market_news(
    code: str,
    name: str,
    start: datetime,
    *,
    days: int,
    max_pages: int,
    require_time: bool,
) -> dict[str, list[dict[str, Any]]]:
    em_kind = "all" if days > 180 else "old"
    em_pages = max_pages
    side_pages = min(max_pages, 8)
    jobs: list[tuple[str, Callable[[], list[dict[str, Any]]]]] = [
        (
            "em_code",
            lambda: _safe_unpack(
                fetch_eastmoney_news,
                code,
                start=start,
                days=None,
                max_pages=em_pages,
                kind=em_kind,
            ),
        ),
        (
            "ths",
            lambda: _safe_unpack(
                fetch_ths_news,
                code,
                start=start,
                days=None,
                max_pages=side_pages,
            ),
        ),
        (
            "xq",
            lambda: _safe_unpack(
                fetch_xq_news,
                code,
                start=start,
                days=None,
                max_pages=side_pages,
            ),
        ),
    ]
    if name and name != code:
        jobs.append(
            (
                "em_name",
                lambda: _safe_unpack(
                    fetch_eastmoney_news,
                    name,
                    start=start,
                    days=None,
                    max_pages=em_pages,
                    kind=em_kind,
                ),
            )
        )

    collected: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as pool:
        futs = [pool.submit(fn) for _, fn in jobs]
        for fut in as_completed(futs):
            collected.extend(fut.result())

    tagged = [as_news(x, code=code, name=name) for x in collected]
    tagged = [
        x
        for x in dedupe(tagged)
        if within_lookback(x, start, require_time=require_time)
    ]
    buckets: dict[str, list[dict[str, Any]]] = {
        "designated_press": [],
        "official_news": [],
        "other_news": [],
    }
    for item in tagged:
        buckets[_media_bucket(item)].append(item)
    for key, rows in buckets.items():
        buckets[key] = sorted(rows, key=sort_key)[:MAX_NEWS]
    return buckets


def _collect_press(
    code: str,
    name: str,
    start: datetime,
    *,
    max_pages: int,
    require_time: bool,
) -> list[dict[str, Any]]:
    pack = query_press(
        code or name,
        outlet="all",
        start=start,
        days=None,
        max_pages=max(2, min(max_pages, 4)),
    )
    rows = list(pack.get("items") or [])
    for row in rows:
        row.setdefault("code", code)
        row.setdefault("name", name)
    rows = [
        x
        for x in dedupe(rows)
        if within_lookback(x, start, require_time=require_time)
    ]
    return sorted(rows, key=sort_key)[:MAX_NEWS]


def _collect_reports(
    code: str,
    name: str,
    start: datetime,
    *,
    max_pages: int,
    require_time: bool,
) -> list[dict[str, Any]]:
    side_pages = min(max_pages, 8)
    collected: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [
            pool.submit(
                _safe_unpack,
                fetch_ths_reports,
                code,
                start=start,
                days=None,
            ),
            pool.submit(
                _safe_unpack,
                fetch_xq_reports,
                code,
                start=start,
                days=None,
                max_pages=side_pages,
            ),
        ]
        for fut in as_completed(futs):
            collected.extend(fut.result())
    tagged = [as_report(x, code=code, name=name) for x in collected]
    tagged = [
        x
        for x in dedupe(tagged)
        if within_lookback(x, start, require_time=require_time)
    ]
    return sorted(tagged, key=sort_key)[:MAX_REPORTS]


def _resolve_kinds(kind: str) -> list[str]:
    if kind == "notices":
        return ["exchange", "cninfo"]
    if kind == "news":
        return list(_NEWS_KINDS)
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
    code = normalize_code(code) or safe_str(code)
    name = safe_str(name)
    if not code:
        raise ValueError("缺少公司代码 code")

    if days is None:
        days = DEFAULT_FEED_DAYS
    days = max(1, int(days))
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
    candidate_count = 0
    news_buckets: dict[str, list[dict[str, Any]]] = {
        "designated_press": [],
        "official_news": [],
        "other_news": [],
    }

    if "exchange" in kinds:
        ch = _exchange_channel(code)
        if ch:
            rows = _fetch_notices(
                code,
                channel=ch,
                start=start,
                require_time=require_time,
                max_pages=max_pages,
            )
            groups["exchange"] = rows
            candidate_count += len(rows)

    if "cninfo" in kinds:
        rows = _fetch_notices(
            code,
            channel="cninfo",
            start=start,
            require_time=require_time,
            max_pages=max_pages,
        )
        groups["cninfo"] = rows
        candidate_count += len(rows)

    need_market = any(k in kinds for k in ("official_news", "other_news"))
    need_press = "designated_press" in kinds
    if need_market:
        news_buckets = _collect_market_news(
            code,
            name,
            start,
            days=days,
            max_pages=max_pages,
            require_time=require_time,
        )
    if need_press:
        press_rows = _collect_press(
            code,
            name,
            start,
            max_pages=max_pages,
            require_time=require_time,
        )
        merged = dedupe(press_rows + news_buckets.get("designated_press", []))
        news_buckets["designated_press"] = sorted(merged, key=sort_key)[:MAX_NEWS]

    for nk in _NEWS_KINDS:
        if nk in kinds:
            groups[nk] = news_buckets.get(nk, [])
            candidate_count += len(groups[nk])

    if "reports" in kinds:
        groups["reports"] = _collect_reports(
            code,
            name,
            start,
            max_pages=max_pages,
            require_time=require_time,
        )
        candidate_count += len(groups["reports"])

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
        "source": "company.news",
    }

    save_cache(code, data, days, kind)

    if kind in ("official_news", "other_news"):
        for sibling_kind in ("official_news", "other_news"):
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


collect_important_news = collect_company_messages
