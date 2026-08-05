"""公司新闻智能体入口。

流程：
  1. 读缓存（未强制刷新且未过期则直接返回）
  2. 并行思路上采集三类数据：公告 / 媒体新闻 / 机构研报
  3. 去重、按时间窗过滤、分组整理
  4. 写缓存并返回统一结构

对外只暴露 collect_important_news()，供 app.py 的 /api/stocks/news 调用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from news.cache import load_cache, save_cache
from news.constants import LOOKBACK_YEARS
from news.process import (
    dedupe,
    filter_news,
    filter_notices,
    filter_reports,
    span_meta,
)
from news.sources import fetch_media_news, fetch_notices, fetch_research_reports
from news.utils import lookback_start, sort_key, within_lookback


def collect_important_news(
    code: str,
    name: str = "",
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """采集近约 2 年的公告、媒体新闻、研报，按时间从新到旧返回。

    参数
    ----
    code:
        股票代码，必填（如 "600519"）。
    name:
        公司简称，可选。有名称时会额外用公司名搜一遍媒体新闻，覆盖更全。
    force_refresh:
        True 时跳过磁盘缓存，重新拉远端数据。

    返回
    ----
    dict，主要字段：
      code / name / mode / lookback_years
      span_from / span_to          # 实际覆盖的最早、最晚日期
      candidate_count             # 去重前候选条数之和
      counts                      # 三类最终条数
      updated_at
      groups                      # {notices, news, reports}
      items                       # 三类合并后再按时间排序
    """
    code = (code or "").strip()
    name = (name or "").strip()
    if not code:
        raise ValueError("缺少公司代码 code")

    # ---- 1. 缓存命中则直接返回 ----
    if not force_refresh:
        cached = load_cache(code)
        if cached is not None and isinstance(cached.get("groups"), dict):
            return cached

    # ---- 2. 拉取三类原始数据 ----
    start = lookback_start()

    notices_raw = fetch_notices(code)

    # 代码 + 公司名各搜一遍，再合并去重，覆盖更全
    news_raw: list[dict[str, Any]] = []
    news_raw.extend(fetch_media_news(code, start))
    if name and name != code:
        news_raw.extend(fetch_media_news(name, start))

    reports_raw = fetch_research_reports(code, start)

    # ---- 3. 去重 + 时间窗 ----
    notices_raw = [x for x in dedupe(notices_raw) if within_lookback(x, start)]
    news_raw = [x for x in dedupe(news_raw) if within_lookback(x, start)]
    reports_raw = [x for x in dedupe(reports_raw) if within_lookback(x, start)]

    # ---- 4. 分组整理（当前策略：时间窗内尽量全量保留）----
    groups = {
        "notices": filter_notices(notices_raw),
        "news": filter_news(news_raw),
        "reports": filter_reports(reports_raw),
    }

    items = sorted(
        groups["notices"] + groups["news"] + groups["reports"],
        key=sort_key,
    )
    span = span_meta(items)

    data: dict[str, Any] = {
        "code": code,
        "name": name,
        "mode": "full",
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

    # ---- 5. 落盘缓存 ----
    save_cache(code, data)
    return data
