"""申万三级历史主力净流入：东财个股日线按成分股加总。"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from analysis.rotation.config import CACHE_TAG, KLINE_WORKERS
from company.fundflow._common import (
    _DAILY_FIELDS2,
    fetch_datacenter_daily,
    fetch_fflow_klines,
    parse_daily_line,
)
from company.line.eastmoney_kline import resolve_secid
from core.codes import normalize_code
from core.paths import ANALYSIS_CACHE_DIR, ensure_cache_dirs

_FLOW_CACHE_DIR = ANALYSIS_CACHE_DIR / "stock_flow" / CACHE_TAG
_AGG_CACHE_DIR = ANALYSIS_CACHE_DIR / "l3_flow_agg" / CACHE_TAG
_MAX_FETCH_DAYS = 500
_FLOW_WORKERS = max(4, KLINE_WORKERS // 2)


def _cache_path(code: str) -> Path:
    ensure_cache_dirs()
    _FLOW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _FLOW_CACHE_DIR / f"{normalize_code(code)}.json"


def _agg_cache_path(chronological: list[str]) -> Path:
    ensure_cache_dirs()
    _AGG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    start = chronological[0] if chronological else "na"
    end = chronological[-1] if chronological else "na"
    return _AGG_CACHE_DIR / f"{start}_{end}.json"


def _load_disk(code: str) -> dict[str, float]:
    path = _cache_path(code)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("series")
    if not isinstance(rows, dict):
        return {}
    out: dict[str, float] = {}
    for day, val in rows.items():
        iso = str(day or "")[:10]
        if len(iso) != 10:
            continue
        try:
            out[iso] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def _save_disk(code: str, series: dict[str, float]) -> None:
    if not series:
        return
    path = _cache_path(code)
    try:
        path.write_text(
            json.dumps(
                {
                    "code": normalize_code(code),
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "series": {k: series[k] for k in sorted(series)},
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    except OSError:
        return


def _load_agg_daily(chronological: list[str]) -> dict[str, dict[str, float]]:
    path = _agg_cache_path(chronological)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("l3_daily") if isinstance(payload, dict) else None
    if not isinstance(rows, dict):
        return {}
    out: dict[str, dict[str, float]] = {}
    for l3, by_day in rows.items():
        if not isinstance(by_day, dict):
            continue
        dest: dict[str, float] = {}
        for day, val in by_day.items():
            iso = str(day or "")[:10]
            if len(iso) != 10:
                continue
            try:
                dest[iso] = float(val)
            except (TypeError, ValueError):
                continue
        if dest:
            out[str(l3)] = dest
    return out


def _save_agg_daily(chronological: list[str], l3_daily: dict[str, dict[str, float]]) -> None:
    if not chronological or not l3_daily:
        return
    path = _agg_cache_path(chronological)
    try:
        path.write_text(
            json.dumps(
                {
                    "start": chronological[0],
                    "end": chronological[-1],
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "l3_daily": {
                        l3: {k: by_day[k] for k in sorted(by_day)}
                        for l3, by_day in sorted(l3_daily.items())
                    },
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    except OSError:
        return


def _fetch_series(code: str, limit: int) -> dict[str, float]:
    cap = max(1, min(int(limit), _MAX_FETCH_DAYS))
    norm = normalize_code(code)
    sid = resolve_secid(norm)
    if not sid:
        return {}
    items, _meta = fetch_fflow_klines(
        secid=sid,
        klt=101,
        limit=cap,
        fields2=_DAILY_FIELDS2,
        parser=parse_daily_line,
        use_his=True,
        code=norm,
    )
    if len(items) < min(cap, 30):
        try:
            dc_items, _ = fetch_datacenter_daily(norm, limit=cap)
        except Exception:  # noqa: BLE001
            dc_items = []
        if len(dc_items) > len(items):
            items = dc_items
    out: dict[str, float] = {}
    for row in items:
        day = str(row.get("time") or "")[:10]
        net = row.get("main_net")
        if len(day) == 10 and net is not None:
            out[day] = float(net)
    return out


def _stock_series(code: str, needed: set[str], force: bool) -> dict[str, float]:
    norm = normalize_code(code)
    if not norm:
        return {}
    cached = {} if force else _load_disk(norm)
    if cached and needed.issubset(cached.keys()):
        return cached
    limit = max(len(needed) + 12, 60)
    fresh = _fetch_series(norm, limit=limit)
    if not fresh:
        return cached
    merged = dict(cached)
    merged.update(fresh)
    _save_disk(norm, merged)
    return merged


def _bare6(value: Any) -> str:
    text = "".join(ch for ch in str(value or "") if ch.isdigit())
    return text[-6:] if len(text) >= 6 else text


def flow_maps_from_l3_daily(
    l3_daily: dict[str, dict[str, float]],
    chronological: list[str],
) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for idx, iso in enumerate(chronological):
        window5 = chronological[max(0, idx - 4) : idx + 1]
        window10 = chronological[max(0, idx - 9) : idx + 1]
        day_map: dict[str, dict[str, Any]] = {}
        for l3, by_day in l3_daily.items():
            main = by_day.get(iso)
            if main is None:
                continue
            sum5 = sum(by_day.get(d, 0.0) for d in window5 if d in by_day)
            sum10 = sum(by_day.get(d, 0.0) for d in window10 if d in by_day)
            day_map[l3] = {
                "main_net": round(main, 0),
                "main_net_5d": round(sum5, 0),
                "main_net_10d": round(sum10, 0),
            }
        if day_map:
            out[iso] = day_map
    return out


def merge_l3_daily_flows(
    stocks: list[dict[str, Any]],
    chronological: list[str],
    snapshot_daily: dict[str, dict[str, float]],
    *,
    force: bool = False,
    fetch_network: bool = True,
    workers: int = _FLOW_WORKERS,
    errors: list[str] | None = None,
) -> dict[str, dict[str, float]]:
    """三级 × 交易日 → 当日主力净流入。快照优先，其余东财个股日线加总。"""
    if not chronological:
        return {}
    needed = set(chronological)
    l3_daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    if not force:
        cached = _load_agg_daily(chronological)
        for l3, by_day in cached.items():
            l3_daily[l3].update(by_day)
    for l3, by_day in snapshot_daily.items():
        for iso, net in by_day.items():
            if iso in needed:
                l3_daily[l3][iso] = net

    jobs = [s for s in stocks if str(s.get("l3_code") or "").strip() and _bare6(s.get("code"))]
    stock_flows: dict[str, dict[str, float]] = {}
    pending: list[dict[str, Any]] = []
    for stock in jobs:
        code = _bare6(stock.get("code"))
        cached = {} if force else _load_disk(code)
        if cached and needed.issubset(cached.keys()):
            stock_flows[code] = cached
        else:
            pending.append(stock)

    if pending and fetch_network:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futs = {
                pool.submit(_stock_series, _bare6(s.get("code")), needed, force): s
                for s in pending
            }
            for fut in as_completed(futs):
                try:
                    series = fut.result()
                except Exception as exc:  # noqa: BLE001
                    if errors is not None:
                        errors.append(f"历史资金流: {exc}")
                    continue
                code = _bare6(futs[fut].get("code"))
                if code and series:
                    stock_flows[code] = series

    snap_keys = {
        (l3, iso)
        for l3, by_day in snapshot_daily.items()
        for iso in by_day
    }
    for stock in jobs:
        l3 = str(stock.get("l3_code") or "").strip()
        code = _bare6(stock.get("code"))
        if not l3 or not code:
            continue
        for day, net in (stock_flows.get(code) or {}).items():
            if day not in needed or net is None:
                continue
            if (l3, day) in snap_keys:
                continue
            l3_daily[l3][day] += float(net)

    _save_agg_daily(chronological, l3_daily)
    return l3_daily


def build_l3_flow_maps(
    stocks: list[dict[str, Any]],
    chronological: list[str],
    snapshot_daily: dict[str, dict[str, float]] | None = None,
    *,
    force: bool = False,
    fetch_network: bool = True,
    workers: int = _FLOW_WORKERS,
    errors: list[str] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    l3_daily = merge_l3_daily_flows(
        stocks,
        chronological,
        snapshot_daily or {},
        force=force,
        fetch_network=fetch_network,
        workers=workers,
        errors=errors,
    )
    return flow_maps_from_l3_daily(l3_daily, chronological)
