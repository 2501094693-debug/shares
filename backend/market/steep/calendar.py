"""最近交易日：优先本地日 K，其次上证指数。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from company.line.eastmoney_kline import fetch_line
from company.line.session import is_cn_market_live
from core.paths import KLINE_CACHE_DIR

# 本地日 K 只在开市日有 bar，用来当交易日历，避免节假日被算进去。
_DISK_ANCHORS = ("600519_day_qfq.json", "000858_day_qfq.json")


def _dates_from_items(items: list | None) -> list[str]:
    dates: list[str] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("time") or item.get("date") or "").strip().replace("-", "")[:8]
        if len(text) == 8 and text.isdigit():
            dates.append(text)
    return dates


def _from_disk() -> list[str]:
    best: list[str] = []
    for name in _DISK_ANCHORS:
        path = KLINE_CACHE_DIR / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data = payload.get("data") if isinstance(payload, dict) else None
        items = data.get("items") if isinstance(data, dict) else None
        dates = _dates_from_items(items if isinstance(items, list) else None)
        if len(dates) > len(best):
            best = dates
    return best


def _from_index(limit: int) -> list[str]:
    cap = max(limit, 1)
    try:
        from company.line.tencent_kline import fetch_line as fetch_tx

        dates = _dates_from_items(
            fetch_tx("sh000001", period="day", adjust="none", limit=cap).get("items")
        )
        if len(dates) >= cap:
            return dates
    except Exception:  # noqa: BLE001
        dates = []
    try:
        em = _dates_from_items(
            fetch_line("1.000001", period="day", adjust="none", limit=cap).get("items")
        )
        if len(em) > len(dates):
            dates = em
    except Exception:  # noqa: BLE001
        pass
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
    """最近 ``days`` 个交易日，新 → 旧。只认有日 K 的开市日。"""
    limit = max(int(days), 1)
    dates = _from_disk()
    if len(dates) < limit:
        extra = _from_index(max(limit + 32, 500))
        if len(extra) > len(dates):
            dates = extra

    if is_cn_market_live():
        today = datetime.now().strftime("%Y%m%d")
        if today not in dates:
            dates.append(today)

    if not dates:
        dates = _weekdays(limit)

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
