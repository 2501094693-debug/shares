"""同花顺 HQ 个股大资金动向（``scope=big_deal``）。

从磁盘缓存 / HQ 拉取当日大单，按金额门槛过滤后分页返回。
"""

from __future__ import annotations

from typing import Any

from core.codes import normalize_code

from company.statistics.fundflow.tonghuashun.store import get_session_orders


def _sort_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("time") or ""), str(row.get("event_id") or ""))


def fetch_big_deals(
    code: str,
    *,
    limit: int = 50,
    page: int = 1,
    order: str = "desc",
    min_amount: float = 10_000_000,
    force: bool = False,
) -> dict[str, Any]:
    """个股 HQ 大单：门槛过滤 + 时间排序 + 分页。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    page = max(int(page or 1), 1)
    limit = max(int(limit or 0), 0)
    min_amount = max(float(min_amount or 0), 0.0)
    reverse = str(order or "desc").strip().lower() != "asc"

    session = get_session_orders(norm, force=force)
    items = [row for row in session.get("items") or [] if isinstance(row, dict)]
    filtered = [
        row for row in items if float(row.get("amount") or 0) >= min_amount
    ]
    filtered.sort(key=_sort_key, reverse=reverse)

    total = len(filtered)
    if limit == 0:
        page_items = filtered
        pages = 1
        page = 1
        page_limit = total
    else:
        pages = max(1, (total + limit - 1) // limit)
        page = min(page, pages)
        start = (page - 1) * limit
        page_items = filtered[start : start + limit]
        page_limit = limit

    return {
        "code": norm,
        "name": "",
        "period": "big_deal",
        "source": "tonghuashun" if page_items else "",
        "count": len(page_items),
        "total": total,
        "page": page,
        "pages": pages,
        "order": "asc" if not reverse else "desc",
        "limit": page_limit,
        "min_amount": min_amount,
        "cached": bool(session.get("cached")),
        "session_day": str(session.get("session_day") or ""),
        "cached_at": str(session.get("cached_at") or ""),
        "items": page_items,
        "note": str(session.get("note") or "同花顺 HQ 个股大单（主/被）"),
    }
