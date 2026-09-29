"""趋势分析数据包：仅资金动向列表 + 分时成交列表。"""

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
        limit=0,
        force=force,
        day=day or "",
        min_amount=min_amount,
    )


def _pack_ok(pack: dict[str, Any]) -> tuple[bool, int, str]:
    err = str(pack.get("error") or "")
    items = pack.get("items")
    n = len(items) if isinstance(items, list) else int(pack.get("count") or 0)
    return (not err and n > 0), n, err


def build_trend_pack(
    code: str,
    *,
    day: str = "",
    min_deal_amount: float = 300_000,
    force: bool = False,
) -> dict[str, Any]:
    """只拉同花顺资金动向列表与东财分时成交列表；单源失败不阻断。"""
    ticks = fetch_ticks_day(code, day=day, force=force)
    big_deal = fetch_big_deal(code, day=day, force=force, min_amount=min_deal_amount)

    errors: list[str] = []
    sources: list[str] = []
    for key, pack in (("big_deal", big_deal), ("ticks", ticks)):
        ok, _n, err = _pack_ok(pack)
        if err:
            errors.append(f"{key}: {err}")
        elif ok:
            sources.append(key)

    return {
        "code": code,
        "day": day
        or str(ticks.get("day") or ticks.get("session_day") or big_deal.get("session_day") or ""),
        "ticks": ticks,
        "big_deal": big_deal,
        "sources_used": sources,
        "errors": errors,
    }
