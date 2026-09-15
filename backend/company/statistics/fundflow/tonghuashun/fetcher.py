"""同花顺 HQ 大资金动向入口（带 TTL 缓存）。"""

from __future__ import annotations

import time
from typing import Any

from core.cache import TtlCache

from company.statistics.fundflow.tonghuashun.big_deal import fetch_big_deals

_BIG_DEAL_TTL = 180
_big_deal_cache = TtlCache(_BIG_DEAL_TTL)


def _has_items(data: dict[str, Any]) -> bool:
    items = data.get("items") if isinstance(data, dict) else None
    return isinstance(items, list) and bool(items)


def get_fund_flow(
    code: str,
    *,
    scope: str = "big_deal",
    limit: int = 50,
    page: int = 1,
    order: str = "desc",
    force: bool = False,
    **_unused: Any,
) -> dict[str, Any]:
    """仅 ``scope=big_deal``。"""
    key = (scope or "big_deal").strip().lower()
    if key not in {"big_deal", "bigdeal", "ddzz", "tick", ""}:
        raise ValueError("同花顺资金流向仅支持 scope=big_deal")
    deal_limit = min(max(int(limit or 50), 1), 200)
    cache_key = f"ths:big_deal:{code}:{order}:{deal_limit}"
    now = time.time()
    if not force:
        hit = _big_deal_cache.get(cache_key)
        if hit is not None:
            return hit
    data = fetch_big_deals(code, limit=deal_limit, order=order)
    if _has_items(data):
        _big_deal_cache.put(cache_key, data, cached_at=now)
    return data
