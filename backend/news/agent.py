"""公司新闻智能体入口。

流程：
  1. 读缓存（未强制刷新且未过期则直接返回）
  2. 按需采集：公告 / 媒体新闻 / 机构研报（可只采一类）
  3. 去重、按时间窗过滤、分组整理
  4. 写缓存并返回统一结构

对外暴露 collect_important_news()，供 app.py 的 /api/stocks/news 调用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .cache import load_cache, save_cache
from .constants import DEFAULT_NEWS_DAYS, LOOKBACK_YEARS
from .process import (
    dedupe,
    filter_news,
    filter_notices,
    filter_reports,
    span_meta,
)
from .sources import fetch_media_news, fetch_notices, fetch_research_reports
from .utils import full_lookback_days, lookback_start, sort_key, within_lookback

VALID_KINDS = ("notices", "news", "reports")


def collect_important_news(
    code: str,
    name: str = "",
    *,
    force_refresh: bool = False,
    days: int | None = None,
    kind: str = "",
) -> dict[str, Any]:
    """采集公告、媒体新闻、研报。

    参数
    ----
    code:
        股票代码，必填（如 "600519"）。
    name:
        公司简称，可选。有名称时会额外用公司名搜一遍媒体新闻。
    force_refresh:
        True 时跳过磁盘缓存，重新拉远端数据。
    days:
        回溯天数。默认 DEFAULT_NEWS_DAYS（3）。传更大值可查更早数据。
    kind:
        空字符串 = 三类都采；或 notices / news / reports 只采一类。
    """
    code = (code or "").strip()
    name = (name or "").strip()
    if not code:
        raise ValueError("缺少公司代码 code")

    if days is None:
        days = DEFAULT_NEWS_DAYS
    days = max(1, int(days))
    # 超过全量窗口时钳制到全量天数，便于缓存键稳定
    days = min(days, full_lookback_days())

    kind = (kind or "").strip().lower()
    if kind and kind not in VALID_KINDS:
        raise ValueError(f"kind 无效，可选: {', '.join(VALID_KINDS)}")
    kinds = [kind] if kind else list(VALID_KINDS)

    cache_kind = kind  # 整包缓存用空 kind；单类用对应 kind
    if not force_refresh:
        cached = load_cache(code, days, cache_kind)
        if cached is not None and isinstance(cached.get("groups"), dict):
            return cached

    start = lookback_start(days)
    # 短窗口要求有发布时间，避免无日期条目冲进「近 3 天」
    require_time = days <= 30

    groups: dict[str, list[dict[str, Any]]] = {
        "notices": [],
        "news": [],
        "reports": [],
    }
    candidate_count = 0

    if "notices" in kinds:
        notices_raw = fetch_notices(code, start=start)
        notices_raw = [
            x
            for x in dedupe(notices_raw)
            if within_lookback(x, start, require_time=require_time)
        ]
        groups["notices"] = filter_notices(notices_raw)
        candidate_count += len(notices_raw)

    if "news" in kinds:
        news_raw: list[dict[str, Any]] = []
        news_raw.extend(fetch_media_news(code, start))
        if name and name != code:
            news_raw.extend(fetch_media_news(name, start))
        news_raw = [
            x
            for x in dedupe(news_raw)
            if within_lookback(x, start, require_time=require_time)
        ]
        groups["news"] = filter_news(news_raw)
        candidate_count += len(news_raw)

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
        groups["notices"] + groups["news"] + groups["reports"],
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
        "full_days": full_lookback_days(),
        "span_from": span["from"],
        "span_to": span["to"],
        "candidate_count": candidate_count,
        "counts": {
            "notices": len(groups["notices"]),
            "news": len(groups["news"]),
            "reports": len(groups["reports"]),
        },
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "groups": groups,
        "items": items,
    }

    save_cache(code, data, days, cache_kind)
    return data
