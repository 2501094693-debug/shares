"""个股资金流向统一入口（带 TTL 缓存）。"""

from __future__ import annotations

import time
from typing import Any

from core.cache import TtlCache

from company.fundflow.stock import fetch_daily, fetch_minute, fetch_snapshot

_DAILY_TTL = 600
_LIVE_TTL = 60

_daily_cache = TtlCache(_DAILY_TTL)
_live_cache = TtlCache(_LIVE_TTL)


def _has_flow_payload(data: dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    items = data.get("items")
    if isinstance(items, list) and items:
        return True
    count = data.get("count")
    return isinstance(count, int) and count > 0


def _cached(
    cache: TtlCache,
    key: str,
    *,
    force: bool,
    loader,
) -> dict[str, Any]:
    now = time.time()
    if not force:
        hit = cache.get(key)
        if hit is not None:
            return hit
    data = loader()
    if _has_flow_payload(data):
        cache.put(key, data, cached_at=now)
    return data


def get_fund_flow(
    code: str,
    *,
    scope: str = "daily",
    limit: int = 120,
    klt: int = 1,
    force: bool = False,
) -> dict[str, Any]:
    """``scope=daily|minute|snapshot``。"""
    key = (scope or "daily").strip().lower()
    if key == "minute":
        return _cached(
            _live_cache,
            f"minute:{code}:{klt}:{limit}",
            force=force,
            loader=lambda: fetch_minute(code, limit=limit, klt=klt),
        )
    if key == "snapshot":
        return _cached(
            _live_cache,
            f"snapshot:{code}",
            force=force,
            loader=lambda: fetch_snapshot(code),
        )
    daily_limit = min(max(int(limit or 120), 1), 120)
    return _cached(
        _daily_cache,
        f"daily:{code}:{daily_limit}",
        force=force,
        loader=lambda: fetch_daily(code, limit=daily_limit),
    )
