"""个股历史换手率：当日成交量 ÷ 自由流通股。"""

from __future__ import annotations

import logging
import time
from typing import Any

from company.line.fetcher import fetch_kline
from company.statistics.free_float import calc as calc_free_float
from core.cache import TtlCache
from core.codes import normalize_code
from core.fmt import to_float

logger = logging.getLogger(__name__)

TURNOVER_TTL = 600
_cache = TtlCache(TURNOVER_TTL)


def _turnover_from_volume(volume_hands: float | None, free_float_shares: float) -> float | None:
    """成交量（手）÷ 自由流通股（股）→ 百分比数值，如 1.25 表示 1.25%。"""
    if volume_hands is None or not free_float_shares or free_float_shares <= 0:
        return None
    shares = volume_hands * 100.0
    return round(shares / free_float_shares * 100.0, 4)


def _fetch_day_kline(code: str, cap: int) -> dict[str, Any]:
    """按 limit 拉日 K；大 limit 偶发失败时逐级降级重试。"""
    tries = [cap]
    for fallback in (1500, 750, 250):
        if fallback < cap:
            tries.append(fallback)
    for try_limit in tries:
        try:
            pack = fetch_kline(code, period="day", adjust="none", limit=try_limit)
        except Exception as exc:  # noqa: BLE001
            logger.info("turnover kline skip %s limit=%s: %s", code, try_limit, exc)
            continue
        if pack.get("items"):
            return pack
    return {}


def fetch_turnover_history(
    code: str,
    *,
    limit: int = 2500,
    force: bool = False,
) -> dict[str, Any]:
    """拉取按日的换手率序列（成交量 / 自由流通股），时间升序。"""
    code = normalize_code(code)
    if not code:
        raise ValueError("无效股票代码")

    cap = max(1, min(int(limit or 2500), 5000))
    cache_key = f"{code}:{cap}:turnover:v6"
    now = time.time()
    if not force:
        hit = _cache.get(cache_key)
        if hit is not None:
            return hit

    ff: dict[str, Any] = {}
    try:
        ff = calc_free_float(code) or {}
    except Exception as exc:  # noqa: BLE001
        logger.info("turnover free float skip %s: %s", code, exc)

    free_float_shares = to_float(ff.get("free_float_shares"))
    if not free_float_shares or free_float_shares <= 0:
        free_float_shares = to_float(ff.get("listed_a_shares") or ff.get("float_shares"))
        if free_float_shares:
            logger.info("turnover use listed A shares %s: %s", code, free_float_shares)

    if not free_float_shares or free_float_shares <= 0:
        return {
            "code": code,
            "name": str(ff.get("name") or ""),
            "source": "",
            "free_float_shares": None,
            "count": 0,
            "items": [],
        }

    pack = _fetch_day_kline(code, cap)
    kline_source = str(pack.get("source") or "").strip()

    items: list[dict[str, Any]] = []
    for row in pack.get("items") or []:
        if not isinstance(row, dict):
            continue
        time_s = str(row.get("time") or "").strip()
        if not time_s:
            continue
        volume = to_float(row.get("volume"))
        turnover = _turnover_from_volume(volume, free_float_shares)
        items.append(
            {
                "time": time_s,
                "turnover": turnover,
                "close": to_float(row.get("close")),
                "volume": volume,
            }
        )

    result = {
        "code": pack.get("code") or code,
        "name": pack.get("name") or "",
        "source": kline_source if items else "",
        "free_float_shares": free_float_shares,
        "count": len(items),
        "items": items,
    }
    if items:
        _cache.put(cache_key, result, cached_at=now)
    return result
