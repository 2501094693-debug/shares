"""从涨跌停池按交易日收集涨停候选。"""

from __future__ import annotations

from typing import Any

from analysis._path import ensure_backend_path

ensure_backend_path()

from market.steep.service import DEFAULT_DAYS, service as steep_service


def collect_recent_limit_up(days: int = DEFAULT_DAYS, force: bool = False) -> dict[str, Any]:
    """拉取近 N 日涨停池，按天分批；同一只股票可出现在多日。"""
    data = steep_service.recent(days=days, force=force)
    items = list(data.get("items") or [])
    days_out: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for day_idx, day in enumerate(items):
        date = str(day.get("date") or "")
        date_raw = str(day.get("date_raw") or date.replace("-", ""))
        batch: list[dict[str, Any]] = []
        for row in day.get("limit_up") or []:
            code = str(row.get("code") or "").strip()
            if not code:
                continue
            meta = dict(row)
            meta["limit_up_date"] = date
            meta["date_raw"] = date_raw
            meta["days_since_limit_up"] = day_idx + 1
            batch.append(meta)
            candidates.append(meta)
        days_out.append(
            {
                "date": date,
                "date_raw": date_raw,
                "candidate_count": len(batch),
                "candidates": batch,
            }
        )

    return {
        "lookback_days": days,
        "updated_at": data.get("updated_at"),
        "count": len(candidates),
        "candidates": candidates,
        "days": days_out,
        "errors": list(data.get("errors") or []),
    }
