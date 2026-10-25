"""东财指数历史 K 线：``push2his`` ``/api/qt/stock/kline/get``。

指数无复权语义，``adjust`` 固定不复权。对外字段与个股 / 同花顺指数 K 线包对齐。
"""

from __future__ import annotations

from typing import Any

from core.fmt import to_float
from core.http import get_json

from exponent.eastmoney.codes import resolve

PERIOD_KLT: dict[str, str] = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
    "120m": "120",
    "day": "101",
    "week": "102",
    "month": "103",
    "quarter": "104",
    "halfyear": "105",
    "year": "106",
}

_PERIOD_ALIASES: dict[str, str] = {
    "1": "1m", "1m": "1m",
    "5": "5m", "5m": "5m",
    "15": "15m", "15m": "15m",
    "30": "30m", "30m": "30m",
    "60": "60m", "60m": "60m", "1h": "60m",
    "120": "120m", "120m": "120m", "2h": "120m",
    "101": "day", "day": "day", "d": "day", "daily": "day",
    "102": "week", "week": "week", "w": "week",
    "103": "month", "month": "month", "m": "month",
    "104": "quarter", "quarter": "quarter", "q": "quarter",
    "105": "halfyear", "halfyear": "halfyear", "half": "halfyear",
    "106": "year", "year": "year", "y": "year",
}

# 历史 K 以 his 为主；delay / push2 偶发空数组，作兜底
_HOSTS = (
    "https://push2his.eastmoney.com",
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
    "https://92.push2his.eastmoney.com",
)
_HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}
_UT = "fa5fd1943c7b386f172d6893dbfba10b"
_FIELDS1 = "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
_END_OPEN = "20500101"
_MAX_LMT = 10000


def _period(period: str) -> str:
    key = (period or "day").strip().lower()
    if key in _PERIOD_ALIASES:
        return _PERIOD_ALIASES[key]
    if key in PERIOD_KLT:
        return key
    raise ValueError(
        "period 须为 1m|5m|15m|30m|60m|120m|day|week|month|quarter|halfyear|year"
    )


def _date(value: str) -> str:
    text = (value or "").replace("-", "").replace("/", "").strip()
    if not text:
        return ""
    if len(text) == 8 and text.isdigit():
        return text
    raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")


def _parse_row(line: str) -> dict[str, Any] | None:
    parts = str(line).split(",")
    if len(parts) < 5:
        return None
    open_ = to_float(parts[1])
    close = to_float(parts[2])
    high = to_float(parts[3])
    low = to_float(parts[4])
    if close is None and open_ is None:
        return None
    item: dict[str, Any] = {
        "time": str(parts[0]).strip(),
        "open": open_,
        "close": close,
        "high": high,
        "low": low,
        "volume": to_float(parts[5]) if len(parts) > 5 else None,
        "amount": to_float(parts[6]) if len(parts) > 6 else None,
    }
    if len(parts) > 7:
        item["amplitude"] = to_float(parts[7])
    if len(parts) > 8:
        item["pct_chg"] = to_float(parts[8])
    if len(parts) > 9:
        item["change"] = to_float(parts[9])
    if len(parts) > 10:
        item["turnover"] = to_float(parts[10])
    return item


def fetch_kline(
    code: str,
    *,
    period: str = "day",
    limit: int = 120,
    beg: str = "",
    end: str = "",
) -> dict[str, Any]:
    """拉取单只指数 K 线（不复权）。"""
    meta = resolve(code)
    secid = meta["secid"]
    canon = _period(period)
    klt = PERIOD_KLT[canon]
    cap = max(1, min(int(limit) if limit else 120, _MAX_LMT))
    beg_s = _date(beg)
    end_s = _date(end) or _END_OPEN

    params: dict[str, str] = {
        "secid": secid,
        "fields1": _FIELDS1,
        "fields2": _FIELDS2,
        "klt": klt,
        "fqt": "0",
        "ut": _UT,
        "end": end_s,
    }
    if beg_s:
        params["beg"] = beg_s
        params["lmt"] = str(_MAX_LMT)
        query = "range"
    else:
        params["lmt"] = str(cap)
        query = "last"

    name = meta.get("name") or ""
    out_code = meta.get("code") or ""
    items: list[dict[str, Any]] = []
    last_exc: Exception | None = None

    for host in _HOSTS:
        try:
            payload = get_json(
                f"{host}/api/qt/stock/kline/get",
                params=params,
                headers=_HEADERS,
                timeout=12,
                retries=2,
            )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            continue
        rows = data.get("klines") or []
        if not rows:
            continue
        parsed: list[dict[str, Any]] = []
        for line in rows:
            row = _parse_row(str(line))
            if row and row.get("time"):
                parsed.append(row)
        if not parsed:
            continue
        if query == "last" and len(parsed) > cap:
            parsed = parsed[-cap:]
        items = parsed
        name = str(data.get("name") or name).strip()
        out_code = str(data.get("code") or out_code).strip()
        break

    if not items and last_exc:
        raise last_exc

    return {
        "code": out_code,
        "name": name,
        "secid": secid,
        "period": canon,
        "klt": klt,
        "adjust": "none",
        "query": query,
        "source": "eastmoney" if items else "",
        "count": len(items),
        "items": items,
    }
