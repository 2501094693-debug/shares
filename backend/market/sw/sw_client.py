"""申万宏源研究指数接口。

官方只发布到二级行业；三级没有对应指数。
站点证书经常不完整，与 akshare 一样关闭校验。
二级约 124 条，``page_size=200`` 一页拿完，避免连打 3 页时盘中读超时。
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from core.fmt import to_float
from core.http import get_json
from .parse import bare_code, change_from_close

_LEVEL_TYPE = {1: "一级行业", 2: "二级行业"}
_PAGE_SIZE = 200
_HEADERS = {
    "Referer": "https://www.swsresearch.com/institute_sw/allIndex/releasedIndex",
    "Accept": "application/json, text/plain, */*",
}


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    payload = get_json(
        url,
        params=params,
        headers=_HEADERS,
        timeout=(5, 15),
        retries=2,
        verify=False,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("申万接口返回非 JSON 对象")
    return payload


def fetch_level_quotes(level: int) -> list[dict[str, Any]]:
    """一级 / 二级行业实时点位。``level`` 只能是 1 或 2。"""
    indextype = _LEVEL_TYPE.get(level)
    if not indextype:
        raise ValueError("申万实时行情只覆盖一级、二级行业")

    url = "https://www.swsresearch.com/institute-sw/api/index_publish/current/"
    first = _get_json(
        url, {"page": "1", "page_size": str(_PAGE_SIZE), "indextype": indextype}
    )
    data = first.get("data") or {}
    total = int(data.get("count") or 0)
    pages = max(1, math.ceil(total / _PAGE_SIZE)) if total else 1
    batches = [data.get("results") or []]
    for page in range(2, pages + 1):
        payload = _get_json(
            url,
            {"page": str(page), "page_size": str(_PAGE_SIZE), "indextype": indextype},
        )
        batches.append((payload.get("data") or {}).get("results") or [])

    rows: list[dict[str, Any]] = []
    for raw in batches:
        for item in raw:
            if not isinstance(item, dict):
                continue
            last_close = to_float(item.get("l3"))
            open_px = to_float(item.get("l4"))
            amount = to_float(item.get("l5"))
            high = to_float(item.get("l6"))
            low = to_float(item.get("l7"))
            price = to_float(item.get("l8"))
            volume = to_float(item.get("l11"))
            code = bare_code(str(item.get("swindexcode") or ""))
            name = str(item.get("swindexname") or "").strip()
            if not code:
                continue
            rows.append(
                {
                    "sw_code": code,
                    "name": name,
                    "last_close": last_close,
                    "open": open_px,
                    "price": price,
                    "high": high,
                    "low": low,
                    "amount": amount,
                    "volume": volume,
                    "change_pct": change_from_close(price, last_close),
                    "source": "sw",
                }
            )
    return rows


def fetch_daily_analysis(
    level: int,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """一级 / 二级行业区间日报（涨跌幅、换手、估值）。"""
    index_type = _LEVEL_TYPE.get(level)
    if not index_type:
        raise ValueError("申万日报只覆盖一级、二级行业")

    url = "https://www.swsresearch.com/institute-sw/api/index_analysis/index_analysis_report/"
    params = {
        "page": "1",
        "page_size": str(_PAGE_SIZE),
        "index_type": index_type,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "type": "DAY",
        "swindexcode": "all",
    }
    first = _get_json(url, params)
    data = first.get("data") or {}
    total = int(data.get("count") or 0)
    pages = max(1, math.ceil(total / _PAGE_SIZE)) if total else 1
    batches = [data.get("results") or []]
    for page in range(2, pages + 1):
        params["page"] = str(page)
        payload = _get_json(url, params)
        batches.append((payload.get("data") or {}).get("results") or [])

    rows: list[dict[str, Any]] = []
    for raw in batches:
        for item in raw:
            if not isinstance(item, dict):
                continue
            code = bare_code(str(item.get("swindexcode") or ""))
            if not code:
                continue
            rows.append(
                {
                    "sw_code": code,
                    "name": str(item.get("swindexname") or "").strip(),
                    "date": str(item.get("bargaindate") or "")[:10],
                    "close": to_float(item.get("closeindex")),
                    "change_pct": to_float(item.get("markup")),
                    "turnover": to_float(item.get("turnoverrate")),
                    "pe": to_float(item.get("pe")),
                    "pb": to_float(item.get("pb")),
                    "amount_share": to_float(item.get("bargainsumrate")),
                    "float_mv": to_float(item.get("negotiablessharesum1")),
                }
            )
    rows.sort(key=lambda x: (x["sw_code"], x["date"]))
    return rows


def recent_window(days: int = 16) -> tuple[date, date]:
    """含今天的日历窗口，用来覆盖约 10 个交易日。"""
    end = date.today()
    start = end - timedelta(days=max(days, 7))
    return start, end
