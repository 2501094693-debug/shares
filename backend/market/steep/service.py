"""最近几个交易日的涨停 / 跌停，按天分开。

交易时段只重拉当日池，其余交易日走磁盘缓存；非交易时段全部走缓存。
缓存未命中时仍会拉一次并落盘。
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from company.line.session import cn_now, is_cn_market_live
from core.cache import TtlCache
from core.paths import STEEP_CACHE_DIR, ensure_cache_dirs
from industry.service import service as industry_service

from .calendar import recent_trade_dates
from .em_pool import fetch_day_pools

_LIVE_TTL = 20
_RECENT_TTL = 30
_SW_MAP_TTL = 600
_CACHE_VERSION = 1
_MIN_DAYS = 1
_MAX_DAYS = 30
DEFAULT_DAYS = 15
MAX_DAYS = _MAX_DAYS
_LITE_KEEP_DAYS = 1


def _clamp_days(days: int) -> int:
    try:
        value = int(days)
    except (TypeError, ValueError) as exc:
        raise ValueError("days 须为整数") from exc
    if value < _MIN_DAYS or value > _MAX_DAYS:
        raise ValueError(f"days 须在 {_MIN_DAYS}–{_MAX_DAYS} 之间")
    return value


def _today() -> str:
    return cn_now().strftime("%Y%m%d")


def _is_live_date(date_raw: str) -> bool:
    return date_raw == _today() and is_cn_market_live()


def _empty_day(date: str) -> dict[str, Any]:
    return {
        "date": f"{date[:4]}-{date[4:6]}-{date[6:8]}",
        "date_raw": date,
        "limit_up_count": 0,
        "limit_down_count": 0,
        "limit_up": [],
        "limit_down": [],
    }


def _disk_path(date_raw: str):
    ensure_cache_dirs()
    return STEEP_CACHE_DIR / f"{date_raw}.json"


def _load_disk(date_raw: str) -> dict[str, Any] | None:
    path = _disk_path(date_raw)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(payload.get("version") or 0) != _CACHE_VERSION:
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def _save_disk(date_raw: str, data: dict[str, Any]) -> None:
    path = _disk_path(date_raw)
    path.write_text(
        json.dumps(
            {"version": _CACHE_VERSION, "cached_at": time.time(), "data": data},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class SteepService:
    def __init__(self) -> None:
        self._live = TtlCache(_LIVE_TTL)
        self._recent = TtlCache(_RECENT_TTL)
        self._lock = threading.Lock()
        self._build_lock = threading.Lock()
        self._sealed: dict[str, dict[str, Any]] = {}

    def _sealed_get(self, date_raw: str) -> dict[str, Any] | None:
        with self._lock:
            hit = self._sealed.get(date_raw)
        return hit

    def _sealed_put(self, date_raw: str, row: dict[str, Any]) -> None:
        with self._lock:
            self._sealed[date_raw] = row

    def _cached_day(self, date_raw: str) -> dict[str, Any] | None:
        hit = self._sealed_get(date_raw)
        if hit is not None:
            return hit
        disk = _load_disk(date_raw)
        if disk is not None:
            self._sealed_put(date_raw, disk)
            return disk
        return None

    def _fetch_day(self, date_raw: str) -> tuple[dict[str, Any], str | None]:
        try:
            row = fetch_day_pools(date_raw)
        except Exception as exc:  # noqa: BLE001
            cached = self._cached_day(date_raw)
            if cached is not None:
                return cached, None
            return _empty_day(date_raw), f"{date_raw}: {exc}"
        _save_disk(date_raw, row)
        self._sealed_put(date_raw, row)
        return row, None

    def _one(self, date_raw: str, force: bool) -> tuple[str, dict[str, Any], str | None]:
        live = _is_live_date(date_raw)
        if not force:
            if live:
                hit = self._live.get(date_raw)
                if hit is not None:
                    return date_raw, hit, None
            else:
                cached = self._cached_day(date_raw)
                if cached is not None:
                    return date_raw, cached, None

        row, error = self._fetch_day(date_raw)
        if live and error is None:
            self._live.put(date_raw, row)
        return date_raw, row, error

    def cached_pool(self, date: str) -> dict[str, Any] | None:
        """只读本地涨跌停缓存，没有则 None，不联网。"""
        raw = str(date or "").replace("-", "")[:8]
        if len(raw) != 8 or not raw.isdigit():
            return None
        return self._cached_day(raw)

    def day_pool(self, date: str, force: bool = False) -> dict[str, Any]:
        raw = str(date or "").replace("-", "")[:8]
        if len(raw) != 8 or not raw.isdigit():
            return _empty_day(raw or "00000000")
        _, row, _ = self._one(raw, force)
        return row

    def recent(
        self, days: int = DEFAULT_DAYS, force: bool = False, lite: bool = False
    ) -> dict[str, Any]:
        days = _clamp_days(days)
        cache_key = f"d:{days}"
        if not force:
            hit = self._recent.get(cache_key)
            if hit is not None:
                return _lite_steep(hit) if lite else hit

        with self._build_lock:
            if not force:
                hit = self._recent.get(cache_key)
                if hit is not None:
                    return _lite_steep(hit) if lite else hit
            payload = self._build_recent(days, force=force)
            self._recent.put(cache_key, payload)
        return _lite_steep(payload) if lite else payload

    def _build_recent(self, days: int, force: bool = False) -> dict[str, Any]:
        dates = recent_trade_dates(days)
        errors: list[str] = []

        workers = min(8, max(1, len(dates)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(self._one, date, force) for date in dates]
            fetched = [fut.result() for fut in futs]

        by_date = {date: row for date, row, _ in fetched}
        for _, _, message in fetched:
            if message:
                errors.append(message)

        items = [by_date[date] for date in dates if date in by_date]
        _attach_sw(items)
        return {
            "days": days,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(items),
            "limit_up_total": sum(row["limit_up_count"] for row in items),
            "limit_down_total": sum(row["limit_down_count"] for row in items),
            "items": items,
            "errors": errors,
            "note": "东财涨停池 / 跌停池，行业=申万一/二/三级",
        }


_SW_MAP: tuple[float, dict[str, dict[str, str]]] | None = None


def _sw_map() -> dict[str, dict[str, str]]:
    global _SW_MAP
    now = time.time()
    if _SW_MAP is not None and now - _SW_MAP[0] < _SW_MAP_TTL:
        return _SW_MAP[1]
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
    _SW_MAP = (now, out)
    return out


def _lite_steep(payload: dict[str, Any], keep: int = _LITE_KEEP_DAYS) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for index, day in enumerate(payload.get("items") or []):
        row = dict(day)
        if index >= keep:
            row["limit_up"] = []
            row["limit_down"] = []
        items.append(row)
    lite = dict(payload)
    lite["items"] = items
    lite["lite"] = True
    return lite


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
