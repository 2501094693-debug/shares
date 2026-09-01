"""最近几个交易日的涨停 / 跌停，按天分开。"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from core.cache import TtlCache
from industry.service import service as industry_service

from .calendar import recent_trade_dates
from .em_pool import fetch_day_pools

_TTL = 90
_MIN_DAYS = 1
_MAX_DAYS = 30
DEFAULT_DAYS = 15
MAX_DAYS = _MAX_DAYS


def _clamp_days(days: int) -> int:
    try:
        value = int(days)
    except (TypeError, ValueError) as exc:
        raise ValueError("days 须为整数") from exc
    if value < _MIN_DAYS or value > _MAX_DAYS:
        raise ValueError(f"days 须在 {_MIN_DAYS}–{_MAX_DAYS} 之间")
    return value


class SteepService:
    def __init__(self) -> None:
        self._cache = TtlCache(_TTL)

    def recent(self, days: int = DEFAULT_DAYS, force: bool = False) -> dict[str, Any]:
        days = _clamp_days(days)
        cache_key = f"d:{days}"
        if not force:
            hit = self._cache.get(cache_key)
            if hit is not None:
                return hit

        dates = recent_trade_dates(days)
        errors: list[str] = []

        def _one(date: str) -> tuple[str, dict[str, Any], str | None]:
            try:
                return date, fetch_day_pools(date), None
            except Exception as exc:  # noqa: BLE001
                empty = {
                    "date": f"{date[:4]}-{date[4:6]}-{date[6:8]}",
                    "date_raw": date,
                    "limit_up_count": 0,
                    "limit_down_count": 0,
                    "limit_up": [],
                    "limit_down": [],
                }
                return date, empty, f"{date}: {exc}"

        with ThreadPoolExecutor(max_workers=min(8, max(1, len(dates)))) as pool:
            futs = [pool.submit(_one, date) for date in dates]
            fetched = [fut.result() for fut in futs]

        by_date = {date: row for date, row, _ in fetched}
        for _, _, message in fetched:
            if message:
                errors.append(message)

        items = [by_date[date] for date in dates if date in by_date]
        _attach_sw(items)
        payload = {
            "days": days,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(items),
            "limit_up_total": sum(row["limit_up_count"] for row in items),
            "limit_down_total": sum(row["limit_down_count"] for row in items),
            "items": items,
            "errors": errors,
            "note": "东财涨停池 / 跌停池，行业=申万一/二/三级",
        }
        self._cache.put(cache_key, payload)
        return payload


def _sw_map() -> dict[str, dict[str, str]]:
    industry_service.stocks.ensure_populated()
    out: dict[str, dict[str, str]] = {}
    for stock in industry_service.stocks.all_stocks():
        code = str(stock.get("code") or "").strip()
        if not code or code in out:
            continue
        out[code] = {
            "l1_name": str(stock.get("l1_name") or "").strip(),
            "l2_name": str(stock.get("l2_name") or "").strip(),
            "l3_name": str(stock.get("l3_name") or "").strip(),
            "l3_code": str(stock.get("l3_code") or "").strip(),
        }
    return out


def _attach_sw(items: list[dict[str, Any]]) -> None:
    mapping = _sw_map()
    empty = {"l1_name": "", "l2_name": "", "l3_name": "", "l3_code": ""}
    for day in items:
        for key in ("limit_up", "limit_down"):
            for row in day.get(key) or []:
                meta = mapping.get(str(row.get("code") or "").strip()) or empty
                row["l1_name"] = meta["l1_name"]
                row["l2_name"] = meta["l2_name"]
                row["l3_name"] = meta["l3_name"]
                row["l3_code"] = meta["l3_code"]


service = SteepService()
