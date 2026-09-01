"""最近交易日：用上证指数日 K 当日历。"""

from __future__ import annotations

from datetime import datetime, timedelta

from company.line.eastmoney_kline import fetch_line


def _from_kline(limit: int) -> list[str]:
    data = fetch_line("1.000001", period="day", adjust="none", limit=max(limit, 1))
    dates: list[str] = []
    for item in data.get("items") or []:
        text = str(item.get("time") or "").strip().replace("-", "")[:8]
        if len(text) == 8 and text.isdigit():
            dates.append(text)
    return dates


def _weekdays(limit: int) -> list[str]:
    dates: list[str] = []
    day = datetime.now().date()
    while len(dates) < limit:
        if day.weekday() < 5:
            dates.append(day.strftime("%Y%m%d"))
        day -= timedelta(days=1)
    dates.reverse()
    return dates


def recent_trade_dates(days: int = 5) -> list[str]:
    """最近 ``days`` 个交易日，新 → 旧。"""
    limit = max(int(days), 1)
    try:
        dates = _from_kline(limit + 2)
    except Exception:  # noqa: BLE001
        dates = []
    if len(dates) < limit:
        dates = _weekdays(limit)

    today = datetime.now().strftime("%Y%m%d")
    if today not in dates and datetime.now().weekday() < 5:
        dates.append(today)

    uniq: list[str] = []
    seen: set[str] = set()
    for date in reversed(dates):
        if date in seen:
            continue
        seen.add(date)
        uniq.append(date)
        if len(uniq) >= limit:
            break
    return uniq
