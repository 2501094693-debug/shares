"""东财全市场个股资金流，用来按申万成分股加总到行业。"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from core.fmt import to_float
from core.http import get_json

_UT = "b2884a393a59ad64002292a3e90d46a5"
_FS = (
    "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,"
    "m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2"
)
_FIELDS = (
    "f12,f14,f2,f3,f62,f184,f66,f72,f78,f84,"
    "f115,f23,"
    "f164,f165,f174,f175"
)
_HEADERS = {"Referer": "https://data.eastmoney.com/zjlx/detail.html"}
_PAGE = 200
_HOSTS = (
    "https://push2.eastmoney.com/api/qt/clist/get",
    "https://push2delay.eastmoney.com/api/qt/clist/get",
)


def _page(pn: int) -> dict[str, Any]:
    params = {
        "pn": str(pn),
        "pz": str(_PAGE),
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f62",
        "fs": _FS,
        "fields": _FIELDS,
        "ut": _UT,
    }
    last_error: Exception | None = None
    for url in _HOSTS:
        try:
            return get_json(url, params=params, headers=_HEADERS, timeout=20)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"东财个股资金流失败: {last_error}")


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    diff = data.get("diff") or []
    if isinstance(diff, dict):
        diff = list(diff.values())
    return [item for item in diff if isinstance(item, dict)]


def fetch_stock_flows() -> dict[str, dict[str, Any]]:
    """股票短码 → 今日 / 5 日 / 10 日主力及分档净额。"""
    first = _page(1)
    data = first.get("data") or {}
    total = int(to_float(data.get("total")) or 0)
    first_rows = _rows(first)
    # 东财常把 pz 截成 100，必须按实际页长算页数，否则会漏一半。
    page_size = len(first_rows) or _PAGE
    pages = max(1, math.ceil(total / page_size)) if total else 1
    batches = [first_rows]

    if pages > 1:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = [pool.submit(_page, pn) for pn in range(2, pages + 1)]
            for fut in futs:
                batches.append(_rows(fut.result()))

    out: dict[str, dict[str, Any]] = {}
    for batch in batches:
        for item in batch:
            code = str(item.get("f12") or "").strip()
            if not code:
                continue
            out[code] = {
                "code": code,
                "name": str(item.get("f14") or "").strip(),
                "price": to_float(item.get("f2")),
                "change_pct": to_float(item.get("f3")),
                "main_net": to_float(item.get("f62")),
                "main_net_pct": to_float(item.get("f184")),
                "super_net": to_float(item.get("f66")),
                "big_net": to_float(item.get("f72")),
                "mid_net": to_float(item.get("f78")),
                "small_net": to_float(item.get("f84")),
                "pe_ttm": to_float(item.get("f115")),
                "pb": to_float(item.get("f23")),
                "main_net_5d": to_float(item.get("f164")),
                "main_net_pct_5d": to_float(item.get("f165")),
                "main_net_10d": to_float(item.get("f174")),
                "main_net_pct_10d": to_float(item.get("f175")),
            }
    return out
