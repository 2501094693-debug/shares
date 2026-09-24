"""最近交易日列表：供前端按日勾选条件。"""

from __future__ import annotations

from typing import Any

from analysis.decline.bars import normalize_date
from analysis.shares.common.config import (
    COMPARE_FIELD_META,
    COMPARE_OPS,
    COMPARE_TRENDS,
    DEFAULT_LOOKBACK_DAYS,
    FIELD_META,
    MAX_LOOKBACK_DAYS,
)
from market.steep.calendar import recent_trade_dates


def list_trade_days(days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, Any]:
    """返回近 N 个交易日（新→旧），附可选条件字段说明。"""
    n = max(1, min(int(days or DEFAULT_LOOKBACK_DAYS), MAX_LOOKBACK_DAYS))
    raw = recent_trade_dates(n)
    items: list[dict[str, Any]] = []
    for offset, compact in enumerate(raw):
        date = normalize_date(compact)
        items.append(
            {
                "date": date,
                "offset": offset,  # 0=最近一个交易日
                "label": "最新" if offset == 0 else f"T-{offset}",
            }
        )
    return {
        "days": n,
        "count": len(items),
        "items": items,
        "fields": FIELD_META,
        "compare_fields": COMPARE_FIELD_META,
        "compare_ops": list(COMPARE_OPS),
        "compare_trends": list(COMPARE_TRENDS),
        "note": (
            "筛选式：为每个交易日设区间；形态：groups 绝对阈值；"
            "对比：comps 比较前后交易日指标（可兼 days 绝对条件）。"
        ),
    }
