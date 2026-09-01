"""东财涨停池 / 跌停池。"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from core.http import get_json

_UT = "7eea3edcaed734bea9cbfc24409ed989"
_DPT = "wz.ztzt"
_BASE = "https://push2ex.eastmoney.com"
_HEADERS = {"Referer": "https://quote.eastmoney.com/ztb/"}
_PAGE_SIZE = 10000


def _trade_date() -> str:
    return datetime.now().strftime("%Y%m%d")


def _pool_codes(endpoint: str, date: str | None = None) -> set[str]:
    date = date or _trade_date()
    params = {
        "ut": _UT,
        "dpt": _DPT,
        "Pageindex": "0",
        "pagesize": str(_PAGE_SIZE),
        "sort": "fbt:asc" if endpoint == "getTopicZTPool" else "fund:asc",
        "date": date,
        "_": str(int(time.time() * 1000)),
    }
    payload = get_json(f"{_BASE}/{endpoint}", params=params, headers=_HEADERS, timeout=20)
    data = payload.get("data") or {}
    pool = data.get("pool") or []
    if isinstance(pool, dict):
        pool = list(pool.values())
    codes: set[str] = set()
    for item in pool:
        if not isinstance(item, dict):
            continue
        code = str(item.get("c") or "").strip()
        if code:
            codes.add(code)
    return codes


def fetch_limit_pools(date: str | None = None) -> dict[str, set[str]]:
    """今日涨停 / 跌停股票短码集合。"""
    return {
        "limit_up": _pool_codes("getTopicZTPool", date=date),
        "limit_down": _pool_codes("getTopicDTPool", date=date),
    }
