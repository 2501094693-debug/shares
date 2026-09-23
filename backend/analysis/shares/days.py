"""最近交易日列表：供前端按日勾选条件。"""

from __future__ import annotations

from typing import Any

from analysis.decline.bars import normalize_date
from analysis.shares.config import DEFAULT_LOOKBACK_DAYS, FIELD_META, MAX_LOOKBACK_DAYS
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
        "note": "为每个交易日设置振幅/实体/涨跌/影线等区间；未填字段表示不限。多日条件为 AND。",
    }
