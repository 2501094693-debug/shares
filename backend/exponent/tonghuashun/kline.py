"""同花顺指数历史 K 线（``thsdk.klines``，需扫码登录）。

指数无复权语义，``adjust`` 固定不复权。对外字段与个股 K 线包对齐。
"""

from __future__ import annotations

import re
from typing import Any

from core.fmt import to_float

from exponent.tonghuashun.codes import resolve

PERIOD_INTERVAL: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "60m": "60m",
    "120m": "120m",
    "day": "day",
    "week": "week",
    "month": "month",
    "quarter": "quarter",
    "year": "year",
}
MINUTE_PERIODS = ("1m", "5m", "15m", "30m", "60m", "120m")

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
    "106": "year", "year": "year", "y": "year",
}


def _period(period: str) -> str:
    key = (period or "day").strip().lower()
    if key in _PERIOD_ALIASES:
        return _PERIOD_ALIASES[key]
    if key in PERIOD_INTERVAL:
        return key
    raise ValueError(
        "period 须为 1m|5m|15m|30m|60m|120m|day|week|month|quarter|year"
    )


def _date(value: str) -> str:
    text = (value or "").replace("-", "").replace("/", "").strip()
    if not text:
        return ""
    if len(text) == 8 and text.isdigit():
        return text
    raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")


def _fmt_time(raw: Any, *, minute: bool) -> str:
    text = re.sub(r"\D", "", str(raw or ""))
    if minute:
        if len(text) >= 12 and text.startswith(("19", "20")):
            return (
                f"{text[0:4]}-{text[4:6]}-{text[6:8]} "
                f"{text[8:10]}:{text[10:12]}"
            )
        if len(text) >= 8 and text.startswith(("19", "20")):
            return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
        return ""
    if len(text) >= 8:
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return str(raw or "").strip()


def _row_get(row: dict[str, Any], *keys: str) -> Any:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        if key in lowered:
            return lowered[key]
    return None


def _parse_row(row: dict[str, Any], *, minute: bool) -> dict[str, Any] | None:
    open_ = to_float(_row_get(row, "open", "openprice", "open_price"))
    close = to_float(_row_get(row, "close", "closeprice", "close_price"))
    high = to_float(_row_get(row, "high", "highprice", "high_price", "max"))
    low = to_float(_row_get(row, "low", "lowprice", "low_price", "min"))
    if close is None and open_ is None:
        return None
    return {
        "time": _fmt_time(_row_get(row, "time", "date", "datetime"), minute=minute),
        "open": open_,
        "close": close,
        "high": high,
        "low": low,
        "volume": to_float(_row_get(row, "volume", "vol")),
        "amount": to_float(_row_get(row, "amount", "turnover", "money")),
        "change": to_float(_row_get(row, "change", "pricechange", "updown")),
        "pct_chg": to_float(
            _row_get(row, "pct_chg", "pctchange", "changepercent", "涨跌幅")
        ),
    }


def _fill_change(items: list[dict[str, Any]]) -> None:
    prev: float | None = None
    for item in items:
        close = to_float(item.get("close"))
        if prev not in (None, 0) and close is not None:
            chg = round(close - prev, 4)
            pct = round((close / prev - 1.0) * 100, 4)
            if item.get("change") in (None, 0) and chg != 0:
                item["change"] = chg
            else:
                item.setdefault("change", chg)
            if item.get("pct_chg") in (None, 0) and pct != 0:
                item["pct_chg"] = pct
            else:
                item.setdefault("pct_chg", pct)
        prev = close if close is not None else prev


def fetch_kline(
    code: str,
    *,
    period: str = "day",
    limit: int = 120,
    beg: str = "",
    end: str = "",
) -> dict[str, Any]:
    """拉取单只指数 K 线。"""
    import thsdk
    from company.line.tonghuashun import auth as _ths_auth

    meta = resolve(code)
    if not _ths_auth.ensure(timeout=3):
        raise RuntimeError("THS_NEED_QRCODE:同花顺需扫码登录，前端打开扫码弹窗后重试")

    canon = _period(period)
    minute = canon in MINUTE_PERIODS
    cap = max(1, min(int(limit) if limit else 120, 10000))
    beg_s = _date(beg)
    end_s = _date(end)
    security = meta["security"]
    interval = PERIOD_INTERVAL[canon]

    if beg_s or end_s:
        if minute:
            raise ValueError("同花顺分钟 K 不支持日期区间，请用 limit")
        frame = thsdk.klines(
            security,
            start_time=beg_s or None,
            end_time=end_s or None,
            adjust="",
            interval=interval,
        )
        query = "range"
    else:
        frame = thsdk.klines(security, adjust="", interval=interval, count=cap)
        query = "last"

    try:
        records = frame.reset_index().to_dict("records")
    except Exception:  # noqa: BLE001
        records = list(frame.to_dict("records")) if hasattr(frame, "to_dict") else []

    items: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        parsed = _parse_row(record, minute=minute)
        if parsed and parsed.get("time"):
            items.append(parsed)
    items.sort(key=lambda r: str(r.get("time") or ""))
    if query == "last" and len(items) > cap:
        items = items[-cap:]
    _fill_change(items)

    return {
        "code": meta.get("code") or "",
        "name": meta.get("name") or "",
        "security": security,
        "market": meta.get("market") or security[:4],
        "period": canon,
        "interval": interval,
        "adjust": "none",
        "query": query,
        "source": "tonghuashun" if items else "",
        "count": len(items),
        "items": items,
    }
