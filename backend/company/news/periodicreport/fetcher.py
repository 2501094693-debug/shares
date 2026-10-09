"""定期报告统一入口（带 TTL 缓存）。

列表按股票缓存；``period`` 只影响 ``selected``，不重复拉网。
"""

from __future__ import annotations

import time
from typing import Any

from core.cache import TtlCache
from core.codes import normalize_code, safe_str

from company.news.periodicreport.fetch import (
    DEFAULT_DAYS,
    fetch_periodic_report,
    pick_period,
)

_TTL = 3600
_cache = TtlCache(_TTL)


def get_periodic_report(
    code: str,
    *,
    days: int | None = DEFAULT_DAYS,
    period: str = "",
    force: bool = False,
) -> dict[str, Any]:
    stock = normalize_code(code) or safe_str(code)
    if not stock:
        raise ValueError("无效股票代码")

    lookback = DEFAULT_DAYS if days is None else max(1, int(days))
    cache_key = f"periodic:v3:{stock}:{lookback}"
    now = time.time()

    data: dict[str, Any] | None = None if force else _cache.get(cache_key)
    if data is None:
        data = fetch_periodic_report(stock, days=lookback, period="")
        if data.get("count", 0) > 0:
            _cache.put(cache_key, data, cached_at=now)

    items = data.get("items") if isinstance(data.get("items"), list) else []
    out = dict(data)
    out["latest"] = items[0] if items else None
    out["selected"] = pick_period(items, period)
    return out
