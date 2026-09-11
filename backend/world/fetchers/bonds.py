"""新浪全球国债收益率日线。"""

from __future__ import annotations

from typing import Any

from core.http import get_json

from world.catalog import BONDS

_BOND_URL = "https://bond.finance.sina.com.cn/hq/gb/daily"


def _num(raw: Any) -> float | None:
    if raw is None or raw == "" or raw == "-":
        return None
    try:
        return round(float(raw), 4)
    except (TypeError, ValueError):
        return None


def _fetch_symbol(symbol: str, *, limit: int) -> list[dict[str, Any]]:
    payload = get_json(_BOND_URL, params={"symbol": symbol}, timeout=15)
    rows = (payload.get("result") or {}).get("data") or []
    out: list[dict[str, Any]] = []
    for row in rows[-limit:]:
        out.append(
            {
                "date": str(row.get("d") or ""),
                "open": _num(row.get("o")),
                "high": _num(row.get("h")),
                "low": _num(row.get("l")),
                "close": _num(row.get("c")),
            }
        )
    out.reverse()
    return out


def fetch_bond_region(region: str, *, limit: int = 120) -> dict[str, Any]:
    cfg = BONDS[region]
    series: list[dict[str, Any]] = []
    for tenor in cfg["tenors"]:
        history = _fetch_symbol(tenor["symbol"], limit=limit)
        latest = history[0] if history else {}
        series.append(
            {
                "id": tenor["id"],
                "name": tenor["name"],
                "symbol": tenor["symbol"],
                "latest": latest,
                "history": history,
            }
        )
    return {
        "region": region,
        "name": cfg["name"],
        "series": series,
    }


def fetch_bonds(*, limit: int = 120, regions: list[str] | None = None) -> dict[str, Any]:
    keys = regions or list(BONDS.keys())
    return {"items": [fetch_bond_region(region, limit=limit) for region in keys]}
