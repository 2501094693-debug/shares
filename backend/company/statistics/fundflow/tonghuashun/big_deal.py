"""同花顺个股大资金动向：Hexin HQ ``big_order_flow``。"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float

from company.statistics.fundflow.tonghuashun.hq import fetch_hq_big_orders

logger = logging.getLogger(__name__)

_DEFAULT_MIN_AMOUNT = 10_000_000.0


def fetch_big_deals(
    code: str,
    *,
    limit: int = 50,
    order: str = "desc",
    min_amount: float = _DEFAULT_MIN_AMOUNT,
) -> dict[str, Any]:
    """按股票拉取当日 HQ 大单（主/被、手数、金额），默认门槛 1000 万。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("缺少股票代码")
    limit = min(max(int(limit or 50), 1), 200)
    threshold = max(float(min_amount or _DEFAULT_MIN_AMOUNT), 0.0)
    note = "同花顺 HQ 个股大单（主/被）"
    try:
        raw = fetch_hq_big_orders(norm)
    except Exception as exc:  # noqa: BLE001
        logger.info("ths hq big_order skip %s: %s", norm, exc)
        raw = []
        note = f"HQ 个股大单失败: {exc}"
    items = [item for item in raw if (to_float(item.get("amount")) or 0.0) >= threshold]
    reverse = str(order).strip().lower() != "asc"
    items.sort(key=lambda row: to_float(row.get("amount")) or 0.0, reverse=True)
    items.sort(key=lambda row: str(row.get("time") or ""), reverse=reverse)
    items = items[:limit]
    return {
        "code": norm,
        "name": "",
        "period": "big_deal",
        "source": "tonghuashun" if items else "",
        "count": len(items),
        "order": "asc" if str(order).strip().lower() == "asc" else "desc",
        "limit": limit,
        "min_amount": threshold,
        "items": items,
        "note": note,
    }
