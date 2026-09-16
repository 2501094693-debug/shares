"""同花顺 HQ 大单按交易日落盘。

盘中（09:15–15:31）每次查询覆盖当天文件；盘后 / 周末只读该交易日文件。
文件里存完整 HQ 列表，金额门槛和条数在读取后再切。
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from company.line.session import cn_now, parse_session_day
from core.codes import normalize_code
from core.paths import FUNDFLOW_CACHE_DIR, ensure_cache_dirs

from company.statistics.fundflow.tonghuashun.hq import fetch_hq_big_orders

logger = logging.getLogger(__name__)

_DISK_VERSION = 1
_SESSION_OPEN = 9 * 60 + 15
_SESSION_END = 15 * 60 + 31
_lock = threading.Lock()


def session_day(now: datetime | None = None):
    """当前大单所属交易日：开盘前 / 周末回退到上一交易日。"""
    stamp = cn_now(now)
    weekday = stamp.weekday()
    open_at = stamp.replace(hour=9, minute=15, second=0, microsecond=0)
    if weekday >= 5:
        friday = stamp - timedelta(days=weekday - 4)
        return friday.date()
    if stamp < open_at:
        days_back = 3 if weekday == 0 else 1
        return (stamp - timedelta(days=days_back)).date()
    return stamp.date()


def is_session_open(now: datetime | None = None) -> bool:
    """工作日 09:15 至 15:31（含午休），这段时间覆盖当天缓存。"""
    stamp = cn_now(now)
    if stamp.weekday() >= 5:
        return False
    minutes = stamp.hour * 60 + stamp.minute + stamp.second / 60.0
    return _SESSION_OPEN <= minutes < _SESSION_END


def cache_path(code: str, day=None) -> Path:
    ensure_cache_dirs()
    norm = normalize_code(code)
    parsed = parse_session_day(day)
    iso = (parsed or session_day()).isoformat()
    return FUNDFLOW_CACHE_DIR / f"{norm}_{iso}.json"


def load_session_orders(code: str, day=None) -> dict[str, Any] | None:
    path = cache_path(code, day)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(payload.get("version") or 0) != _DISK_VERSION:
        return None
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    return payload


def save_session_orders(
    code: str,
    items: list[dict[str, Any]],
    *,
    note: str = "",
) -> dict[str, Any]:
    norm = normalize_code(code)
    day = session_day()
    stamp = cn_now()
    payload = {
        "version": _DISK_VERSION,
        "code": norm,
        "session_day": day.isoformat(),
        "cached_at": stamp.isoformat(),
        "note": note,
        "count": len(items),
        "items": items,
    }
    path = cache_path(norm)
    tmp = path.with_suffix(".json.tmp")
    text = json.dumps(payload, ensure_ascii=False)
    with _lock:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return payload


def get_session_orders(code: str, *, force: bool = False, day: str = "") -> dict[str, Any]:
    """返回 ``{items, note, cached, session_day, cached_at}``。

    传入历史 ``day`` 时只读对应缓存，没有则空列表。
    """
    norm = normalize_code(code)
    if not norm:
        raise ValueError("缺少股票代码")
    want_day = parse_session_day(day)
    today = session_day()
    if want_day is not None and want_day != today:
        cached = load_session_orders(norm, want_day)
        iso = want_day.isoformat()
        if cached:
            return {
                "items": [row for row in cached.get("items") or [] if isinstance(row, dict)],
                "note": str(cached.get("note") or "同花顺 HQ 个股大单（主/被）"),
                "cached": True,
                "session_day": str(cached.get("session_day") or iso),
                "cached_at": str(cached.get("cached_at") or ""),
            }
        return {
            "items": [],
            "note": "",
            "cached": False,
            "session_day": iso,
            "cached_at": "",
        }

    live = is_session_open()
    cached = load_session_orders(norm)

    if cached and not force and not live:
        return {
            "items": [row for row in cached.get("items") or [] if isinstance(row, dict)],
            "note": str(cached.get("note") or "同花顺 HQ 个股大单（主/被）"),
            "cached": True,
            "session_day": str(cached.get("session_day") or session_day().isoformat()),
            "cached_at": str(cached.get("cached_at") or ""),
        }

    note = "同花顺 HQ 个股大单（主/被，游客登录）"
    try:
        items = fetch_hq_big_orders(norm)
    except Exception as exc:  # noqa: BLE001
        logger.info("ths hq big_order skip %s: %s", norm, exc)
        if cached:
            return {
                "items": [row for row in cached.get("items") or [] if isinstance(row, dict)],
                "note": f"HQ 个股大单失败，沿用缓存: {exc}",
                "cached": True,
                "session_day": str(cached.get("session_day") or session_day().isoformat()),
                "cached_at": str(cached.get("cached_at") or ""),
            }
        return {
            "items": [],
            "note": f"HQ 个股大单失败: {exc}",
            "cached": False,
            "session_day": session_day().isoformat(),
            "cached_at": "",
        }

    if items:
        saved = save_session_orders(norm, items, note=note)
        cached_at = str(saved.get("cached_at") or "")
    else:
        cached_at = cn_now().isoformat()
        if cached:
            return {
                "items": [row for row in cached.get("items") or [] if isinstance(row, dict)],
                "note": "HQ 返回空列表，沿用缓存",
                "cached": True,
                "session_day": str(cached.get("session_day") or session_day().isoformat()),
                "cached_at": str(cached.get("cached_at") or ""),
            }
    return {
        "items": items,
        "note": note,
        "cached": False,
        "session_day": session_day().isoformat(),
        "cached_at": cached_at,
    }
