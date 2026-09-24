"""趋势分析数据包：仅资金动向 + 分时成交（无日线）。"""

from __future__ import annotations

import logging
import sys
from typing import Any

from agent.config import BACKEND_ROOT

logger = logging.getLogger(__name__)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _empty(kind: str, error: str = "") -> dict[str, Any]:
    return {"kind": kind, "count": 0, "items": [], "error": error}


def _safe(kind: str, fn, *args, **kwargs) -> dict[str, Any]:
    try:
        pack = fn(*args, **kwargs)
        if not isinstance(pack, dict):
            return _empty(kind, "返回非字典")
        out = dict(pack)
        out.setdefault("kind", kind)
        out.setdefault("error", "")
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("趋势数据采集失败 %s: %s", kind, exc)
        return _empty(kind, str(exc))


def fetch_fund_daily(code: str, *, limit: int = 60, force: bool = False) -> dict[str, Any]:
    from company.statistics.fundflow.fetcher import get_fund_flow

    return _safe("fund_daily", get_fund_flow, code, scope="daily", limit=limit, force=force)


def fetch_fund_minute(code: str, *, klt: int = 5, force: bool = False) -> dict[str, Any]:
    from company.statistics.fundflow.fetcher import get_fund_flow

    return _safe(
        "fund_minute",
        get_fund_flow,
        code,
        scope="minute",
        limit=480,
        klt=klt,
        force=force,
    )


def fetch_fund_snapshot(code: str, *, force: bool = False) -> dict[str, Any]:
    from company.statistics.fundflow.fetcher import get_fund_flow

    return _safe("fund_snapshot", get_fund_flow, code, scope="snapshot", force=force)


def fetch_ticks_day(code: str, *, day: str = "", force: bool = False) -> dict[str, Any]:
    from company.line.fetcher import fetch_ticks

    return _safe("ticks", fetch_ticks, code, pos=0, day=day or "", force=force)


def fetch_big_deal(
    code: str,
    *,
    day: str = "",
    force: bool = False,
    min_amount: float = 300_000,
) -> dict[str, Any]:
    from company.statistics.fundflow.fetcher import get_fund_flow

    return _safe(
        "big_deal",
        get_fund_flow,
        code,
        scope="big_deal",
        source="tonghuashun",
        limit=500,
        force=force,
        day=day or "",
        min_amount=min_amount,
    )


def _pack_ok(key: str, pack: dict[str, Any]) -> tuple[bool, int, str]:
    err = str(pack.get("error") or "")
    items = pack.get("items")
    n = len(items) if isinstance(items, list) else int(pack.get("count") or 0)
    if key == "fund_snapshot" and not err and pack.get("main_net") is not None:
        n = max(n, 1)
    return (not err and n > 0), n, err


def build_trend_pack(
    code: str,
    *,
    day: str = "",
    fund_limit: int = 60,
    minute_klt: int = 5,
    min_deal_amount: float = 300_000,
    force: bool = False,
) -> dict[str, Any]:
    """只拉资金动向与分时成交；单源失败不阻断。"""
    fund_daily = fetch_fund_daily(code, limit=fund_limit, force=force)
    fund_minute = fetch_fund_minute(code, klt=minute_klt, force=force)
    fund_snap = fetch_fund_snapshot(code, force=force)
    ticks = fetch_ticks_day(code, day=day, force=force)
    big_deal = fetch_big_deal(code, day=day, force=force, min_amount=min_deal_amount)

    errors: list[str] = []
    sources: list[str] = []
    for key, pack in (
        ("fund_daily", fund_daily),
        ("fund_minute", fund_minute),
        ("fund_snapshot", fund_snap),
        ("ticks", ticks),
        ("big_deal", big_deal),
    ):
        ok, _n, err = _pack_ok(key, pack)
        if err:
            errors.append(f"{key}: {err}")
        elif ok:
            sources.append(key)

    return {
        "code": code,
        "day": day or str(ticks.get("day") or ticks.get("session_day") or ""),
        "fund_daily": fund_daily,
        "fund_minute": fund_minute,
        "fund_snapshot": fund_snap,
        "ticks": ticks,
        "big_deal": big_deal,
        "sources_used": sources,
        "errors": errors,
    }
