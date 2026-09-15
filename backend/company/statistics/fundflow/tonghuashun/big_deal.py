"""同花顺个股大资金动向：Hexin HQ ``big_order_flow``。"""

from __future__ import annotations

from typing import Any

from core.codes import normalize_code
from core.fmt import to_float

from company.statistics.fundflow.tonghuashun.store import get_session_orders

_DEFAULT_MIN_AMOUNT = 10_000_000.0
_MAX_PAGE_SIZE = 20_000


def fetch_big_deals(
    code: str,
    *,
    limit: int = 50,
    page: int = 1,
    order: str = "desc",
    min_amount: float = _DEFAULT_MIN_AMOUNT,
    force: bool = False,
) -> dict[str, Any]:
    """按股票拉取当日 HQ 大单。盘中覆盖落盘，盘后读交易日缓存。

    ``limit=0`` 返回门槛筛选后的全部记录；否则按 ``page`` / ``limit`` 分页。
    """
    norm = normalize_code(code)
    if not norm:
        raise ValueError("缺少股票代码")
    requested = int(limit or 0)
    threshold = max(float(_DEFAULT_MIN_AMOUNT if min_amount is None else min_amount), 0.0)
    pack = get_session_orders(norm, force=force)
    items = [
        item
        for item in pack.get("items") or []
        if (to_float(item.get("amount")) or 0.0) >= threshold
    ]
    reverse = str(order).strip().lower() != "asc"
    items.sort(key=lambda row: to_float(row.get("amount")) or 0.0, reverse=True)
    items.sort(key=lambda row: str(row.get("time") or ""), reverse=reverse)
    total = len(items)
    if requested <= 0:
        page_size = total
        page_no = 1
        pages = 1
        page_items = items
    else:
        page_size = min(max(requested, 1), _MAX_PAGE_SIZE)
        pages = max(1, (total + page_size - 1) // page_size) if total else 1
        page_no = min(max(int(page or 1), 1), pages)
        start = (page_no - 1) * page_size
        page_items = items[start : start + page_size]
    return {
        "code": norm,
        "name": "",
        "period": "big_deal",
        "source": "tonghuashun" if page_items else "",
        "count": len(page_items),
        "total": total,
        "page": page_no,
        "pages": pages,
        "page_size": page_size or total,
        "order": "asc" if str(order).strip().lower() == "asc" else "desc",
        "limit": 0 if requested <= 0 else page_size,
        "min_amount": threshold,
        "session_day": pack.get("session_day") or "",
        "cached": bool(pack.get("cached")),
        "cached_at": pack.get("cached_at") or "",
        "items": page_items,
        "note": pack.get("note") or "",
    }
