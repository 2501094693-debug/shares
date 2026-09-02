"""东财涨停池 / 跌停池。"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from core.fmt import to_float
from core.http import get_json

_UT = "7eea3edcaed734bea9cbfc24409ed989"
_DPT = "wz.ztzt"
_BASE = "https://push2ex.eastmoney.com"
_HEADERS = {"Referer": "https://quote.eastmoney.com/ztb/"}
_PAGE_SIZE = 500


def _trade_date() -> str:
    return datetime.now().strftime("%Y%m%d")


def _pool_payload(endpoint: str, date: str, page: int) -> dict[str, Any]:
    params = {
        "ut": _UT,
        "dpt": _DPT,
        "Pageindex": str(page),
        "pagesize": str(_PAGE_SIZE),
        "sort": "fbt:asc" if endpoint == "getTopicZTPool" else "fund:asc",
        "date": date,
        "_": str(int(time.time() * 1000)),
    }
    payload = get_json(
        f"{_BASE}/{endpoint}",
        params=params,
        headers=_HEADERS,
        timeout=(5, 12),
        retries=2,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("涨跌停池返回非 JSON 对象")
    return payload


def _pool_codes(endpoint: str, date: str | None = None) -> set[str]:
    date = date or _trade_date()
    codes: set[str] = set()
    total = None
    for page in range(0, 20):
        data = (_pool_payload(endpoint, date, page).get("data") or {})
        pool = data.get("pool") or []
        if isinstance(pool, dict):
            pool = list(pool.values())
        for item in pool:
            if not isinstance(item, dict):
                continue
            code = str(item.get("c") or "").strip()
            if code:
                codes.add(code)
        if total is None:
            total = int(to_float(data.get("tc")) or 0)
        if not pool or (total is not None and len(codes) >= total):
            break
    return codes


def _limit_band(code: str, name: str) -> float:
    text = (name or "").upper().replace(" ", "")
    if "ST" in text:
        return 5.0
    if code.startswith(("300", "301", "688", "689")):
        return 20.0
    if code.startswith(("43", "83", "87", "92")):
        return 30.0
    return 10.0


def _at_limit(change_pct: float, band: float, side: int) -> bool:
    slack = 0.12
    if side > 0:
        return change_pct >= band - slack
    return change_pct <= -(band - slack)


def guess_limit_pools(
    quotes: dict[str, dict[str, Any]],
    stocks: list[dict[str, Any]] | None = None,
) -> dict[str, set[str]]:
    """用现价涨跌幅近似涨停 / 跌停，东财池超时后的兜底。"""
    names = {
        str(row.get("code") or "").strip(): str(row.get("name") or "")
        for row in (stocks or [])
    }
    up: set[str] = set()
    down: set[str] = set()
    for code, row in quotes.items():
        code = str(code or "").strip()
        if not code:
            continue
        chg = to_float(row.get("change_pct"))
        if chg is None:
            continue
        name = str(row.get("name") or names.get(code) or "")
        band = _limit_band(code, name)
        if _at_limit(chg, band, 1):
            up.add(code)
        elif _at_limit(chg, band, -1):
            down.add(code)
    return {"limit_up": up, "limit_down": down}


def fetch_limit_pools(date: str | None = None) -> dict[str, set[str]]:
    """今日涨停 / 跌停股票短码集合。"""
    with ThreadPoolExecutor(max_workers=2) as pool:
        up = pool.submit(_pool_codes, "getTopicZTPool", date)
        down = pool.submit(_pool_codes, "getTopicDTPool", date)
        return {"limit_up": up.result(), "limit_down": down.result()}
