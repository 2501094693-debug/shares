"""从涨跌停池收集近期涨停候选。"""

from __future__ import annotations

from typing import Any

from analysis._path import ensure_backend_path

ensure_backend_path()

from market.steep.service import DEFAULT_DAYS, service as steep_service


def collect_recent_limit_up(days: int = DEFAULT_DAYS, force: bool = False) -> dict[str, Any]:
    """拉取近 N 日涨停池，按代码去重，保留最近一次涨停记录。"""
    data = steep_service.recent(days=days, force=force)
    items = list(data.get("items") or [])
    # items 新 → 旧
    by_code: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for day_idx, day in enumerate(items):
        date = str(day.get("date") or "")
        for row in day.get("limit_up") or []:
            code = str(row.get("code") or "").strip()
            if not code:
                continue
            meta = dict(row)
            meta["limit_up_date"] = date
            meta["days_since_limit_up"] = day_idx + 1
            if code not in by_code:
                order.append(code)
            by_code[code] = meta

    candidates = [by_code[code] for code in order]
    return {
        "lookback_days": days,
        "updated_at": data.get("updated_at"),
        "count": len(candidates),
        "candidates": candidates,
        "errors": list(data.get("errors") or []),
    }
