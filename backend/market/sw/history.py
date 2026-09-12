"""行业行情历史：优先读每日收盘快照，没有快照再退回申万日报。

快照在盘中随实时树更新，15:31 之后封存，包含一/二/三级、成分股、资金流、涨跌停。
申万日报只覆盖一、二级指数，用来补快照开始之前的日期。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any

from company.line.session import cn_now, last_session_close, today_session_open
from core.cache import TtlCache
from core.paths import MARKET_HISTORY_CACHE_DIR, ensure_cache_dirs
from industry.service import service as industry_service

from .quotes import attach_sw_daily, merge_quote_row
from .sw_client import fetch_daily_analysis
from .taxonomy import filter_level, flatten_tree, nest_rows

logger = logging.getLogger(__name__)

_CACHE_VERSION = 2
_LOOKBACK_DAYS = 20
_LIVE_TTL = 300
_MIN_YEAR = 2014
_MIN_WRITE_SEC = 60
_SNAPSHOT_TICK_SEC = 120
_SOURCE_SNAPSHOT = "snapshot"
_SOURCE_SW_DAILY = "sw_daily"


def parse_query_date(raw: str) -> date:
    text = str(raw or "").strip()[:10]
    try:
        value = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("date 须为 YYYY-MM-DD") from exc
    today = cn_now().date()
    if value > today:
        raise ValueError("不能查询未来日期")
    if value.year < _MIN_YEAR:
        raise ValueError(f"日期不能早于 {_MIN_YEAR}-01-01")
    return value


def snapshot_day(now=None) -> date:
    """当前应写入哪一天的快照：开盘前仍记前一交易日。"""
    stamp = cn_now(now)
    open_at = today_session_open(stamp)
    if open_at is None or stamp < open_at:
        return last_session_close(stamp).date()
    return stamp.date()


def is_seal_time(day: date, now=None) -> bool:
    stamp = cn_now(now)
    if stamp.date() > day:
        return True
    if stamp.date() < day:
        return False
    close = stamp.replace(hour=15, minute=31, second=0, microsecond=0)
    return stamp >= close


def _today() -> date:
    return cn_now().date()


def _disk_path(day: date):
    ensure_cache_dirs()
    return MARKET_HISTORY_CACHE_DIR / f"{day.isoformat()}.json"


def _load_pack(day: date) -> dict[str, Any] | None:
    path = _disk_path(day)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("version") or 0) < 1:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    data = dict(data)
    kind = str(payload.get("kind") or data.get("source") or "")
    if kind == _SOURCE_SNAPSHOT or payload.get("kind") == _SOURCE_SNAPSHOT:
        data["source"] = _SOURCE_SNAPSHOT
    else:
        data.setdefault("source", _SOURCE_SW_DAILY)
    data["history"] = True
    data["live"] = False
    return {
        "kind": data["source"],
        "sealed": bool(payload.get("sealed")),
        "data": data,
    }


def _save_pack(day: date, data: dict[str, Any], *, kind: str, sealed: bool) -> None:
    path = _disk_path(day)
    path.write_text(
        json.dumps(
            {
                "version": _CACHE_VERSION,
                "kind": kind,
                "sealed": sealed,
                "cached_at": time.time(),
                "data": data,
            },
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )


def _pick_trade_date(rows: list[dict[str, Any]], requested: date) -> str | None:
    target = requested.isoformat()
    found = ""
    for row in rows:
        day = str(row.get("date") or "")[:10]
        if day and day <= target and day > found:
            found = day
    return found or None


def _fetch_levels(start: date, end: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(fetch_daily_analysis, 1, start, end)
        f2 = pool.submit(fetch_daily_analysis, 2, start, end)
        return f1.result(), f2.result()


def _build_sw_tree(
    requested: date,
    trade_date: str | None,
    rows1: list[dict[str, Any]],
    rows2: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, Any]:
    nodes = flatten_tree(industry_service.get_tree())
    day_rows1 = [row for row in rows1 if not trade_date or row.get("date") == trade_date]
    day_rows2 = [row for row in rows2 if not trade_date or row.get("date") == trade_date]
    sw1 = attach_sw_daily(filter_level(nodes, 1), day_rows1)
    sw2 = attach_sw_daily(filter_level(nodes, 2), day_rows2)

    rows: list[dict[str, Any]] = []
    for node in nodes:
        if node["level"] == 1:
            quote = merge_quote_row(node, sw1)
        elif node["level"] == 2:
            quote = merge_quote_row(node, sw2)
        else:
            quote = merge_quote_row(node)
        rows.append(quote)

    tree = nest_rows(rows)
    l1 = [row for row in rows if row["level"] == 1]
    return {
        "period": "history",
        "history": True,
        "source": _SOURCE_SW_DAILY,
        "date": requested.isoformat(),
        "trade_date": trade_date,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(rows),
        "up": sum(1 for r in l1 if (r.get("change_pct") or 0) > 0),
        "down": sum(1 for r in l1 if (r.get("change_pct") or 0) < 0),
        "inflow": None,
        "outflow": None,
        "inflow_5d": None,
        "outflow_5d": None,
        "inflow_10d": None,
        "outflow_10d": None,
        "tree": tree,
        "errors": errors,
        "live": False,
        "lite": True,
        "note": "历史涨跌来自申万行业日报，仅覆盖一、二级指数",
    }


def _freeze_snapshot(payload: dict[str, Any], day: date) -> dict[str, Any]:
    frozen = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    frozen["history"] = True
    frozen["live"] = False
    frozen["lite"] = False
    frozen["source"] = _SOURCE_SNAPSHOT
    frozen["date"] = day.isoformat()
    frozen["trade_date"] = day.isoformat()
    frozen["period"] = "history"
    frozen["note"] = "本地收盘快照：涨跌 / 资金流 / 涨跌停 / 成分股"
    return frozen


class HistoryStore:
    def __init__(self) -> None:
        self._live = TtlCache(_LIVE_TTL)
        self._lock = threading.Lock()
        self._sealed: dict[str, dict[str, Any]] = {}
        self._last_write = 0.0
        self._loop_started = False

    def _cached(self, day: date) -> dict[str, Any] | None:
        key = day.isoformat()
        with self._lock:
            hit = self._sealed.get(key)
        if hit is not None:
            return hit
        mem = self._live.get(key)
        if mem is not None:
            return mem
        pack = _load_pack(day)
        if pack is None:
            return None
        data = pack["data"]
        if pack["sealed"]:
            with self._lock:
                self._sealed[key] = data
        else:
            self._live.put(key, data)
        return data

    def _put(self, day: date, payload: dict[str, Any], *, kind: str, sealed: bool) -> None:
        key = day.isoformat()
        if sealed:
            with self._lock:
                self._sealed[key] = payload
            _save_pack(day, payload, kind=kind, sealed=True)
            return
        with self._lock:
            self._sealed.pop(key, None)
        self._live.put(key, payload)
        _save_pack(day, payload, kind=kind, sealed=False)

    def is_sealed(self, day: date) -> bool:
        key = day.isoformat()
        with self._lock:
            hit = self._sealed.get(key)
        if hit is not None and hit.get("source") == _SOURCE_SNAPSHOT:
            return True
        pack = _load_pack(day)
        return bool(pack and pack["kind"] == _SOURCE_SNAPSHOT and pack["sealed"])

    def save_snapshot(self, payload: dict[str, Any], *, force: bool = False) -> bool:
        """把当前实时树写成当日快照。已封存则跳过。"""
        if not isinstance(payload, dict) or payload.get("lite"):
            return False
        if not payload.get("tree"):
            return False
        day = snapshot_day()
        if self.is_sealed(day) and not force:
            return False
        sealing = is_seal_time(day)
        now = time.time()
        if not force and not sealing and now - self._last_write < _MIN_WRITE_SEC:
            return False
        frozen = _freeze_snapshot(payload, day)
        self._put(day, frozen, kind=_SOURCE_SNAPSHOT, sealed=sealing)
        self._last_write = now
        return True

    def load(self, date_text: str, force: bool = False) -> dict[str, Any]:
        requested = parse_query_date(date_text)
        if not force:
            hit = self._cached(requested)
            if hit is not None:
                return hit

        hit = self._cached(requested) if force else None
        if hit is not None and hit.get("source") == _SOURCE_SNAPSHOT:
            return hit

        errors: list[str] = []
        rows1: list[dict[str, Any]] = []
        rows2: list[dict[str, Any]] = []
        try:
            rows1, rows2 = _fetch_levels(requested, requested)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"申万日报: {exc}")

        trade_date = _pick_trade_date(rows1 + rows2, requested)
        if trade_date is None:
            start = requested - timedelta(days=_LOOKBACK_DAYS)
            try:
                rows1, rows2 = _fetch_levels(start, requested)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"申万日报: {exc}")
            trade_date = _pick_trade_date(rows1 + rows2, requested)

        if trade_date is None and not errors:
            errors.append("该日期没有申万行业日报")

        payload = _build_sw_tree(requested, trade_date, rows1, rows2, errors)
        sealed = bool(trade_date) and trade_date < _today().isoformat()
        existing = _load_pack(requested)
        if not existing or existing["kind"] != _SOURCE_SNAPSHOT:
            self._put(requested, payload, kind=_SOURCE_SW_DAILY, sealed=sealed)
        if (
            sealed
            and trade_date
            and trade_date != requested.isoformat()
        ):
            alias_day = date.fromisoformat(trade_date)
            alias_pack = _load_pack(alias_day)
            if not alias_pack or alias_pack["kind"] != _SOURCE_SNAPSHOT:
                alias = dict(payload)
                alias["date"] = trade_date
                self._put(alias_day, alias, kind=_SOURCE_SW_DAILY, sealed=True)
        return payload

    def start_loop(self) -> None:
        if self._loop_started:
            return
        self._loop_started = True
        threading.Thread(
            target=self._loop,
            daemon=True,
            name="market-history-snapshot",
        ).start()

    def _loop(self) -> None:
        time.sleep(8)
        while True:
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001
                logger.warning("industry snapshot tick failed: %s", exc)
            time.sleep(_SNAPSHOT_TICK_SEC)

    def _tick(self) -> None:
        day = snapshot_day()
        if self.is_sealed(day):
            return
        from market.sw.service import service as market_service

        self.save_snapshot(market_service.tree(), force=True)


_store = HistoryStore()


def load_history(date_text: str, force: bool = False) -> dict[str, Any]:
    return _store.load(date_text, force=force)


def load_sealed_snapshot(day: date | None = None) -> dict[str, Any] | None:
    """盘后已封存的完整树；没有则返回 None。"""
    if day is None:
        day = snapshot_day()
    if not _store.is_sealed(day):
        return None
    hit = _store._cached(day)
    if hit is None or hit.get("source") != _SOURCE_SNAPSHOT:
        return None
    return hit


def save_snapshot(payload: dict[str, Any], *, force: bool = False) -> bool:
    return _store.save_snapshot(payload, force=force)


def start_snapshot_loop() -> None:
    _store.start_loop()
