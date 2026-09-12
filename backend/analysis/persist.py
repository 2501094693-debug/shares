"""研判结果落盘：按窗口复用，盘中用当日结果，收盘后沿用到下一交易日开盘。"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from company.line.session import last_session_close, market_phase, today_session_open
from core.paths import ANALYSIS_CACHE_DIR, ensure_cache_dirs

CACHE_VERSION = 1
KIND_DECLINE = "decline"
KIND_GRIND = "grind"

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class JobSlot:
    status: str = "idle"
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: float = 0.0
    finished_at: float = 0.0
    run_id: int = 0


def is_fresh(cached_at: float) -> bool:
    """当日开盘后算过的结果，盘中一直可用；收盘后沿用到下次开盘。"""
    if cached_at <= 0:
        return False
    phase = market_phase()
    if phase in ("live", "lunch"):
        opened = today_session_open()
        if opened is None:
            return True
        return cached_at >= opened.timestamp()
    return cached_at >= last_session_close().timestamp()


def strip_charts(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """去掉走势切片。前端自己拉日 K，接口里带 K 线会把页面打满。"""
    if not isinstance(data, dict):
        return data

    def row_without_chart(row: Any) -> Any:
        if not isinstance(row, dict) or "chart" not in row:
            return row
        item = dict(row)
        item.pop("chart", None)
        return item

    out = dict(data)
    items = out.get("items")
    if isinstance(items, list):
        out["items"] = [row_without_chart(row) for row in items]
    days = out.get("days")
    if isinstance(days, list):
        cleaned = []
        for day in days:
            if not isinstance(day, dict):
                cleaned.append(day)
                continue
            item = dict(day)
            nested = item.get("items")
            if isinstance(nested, list):
                item["items"] = [row_without_chart(row) for row in nested]
            cleaned.append(item)
        out["days"] = cleaned
    return out


def load_disk(kind: str, key: str) -> tuple[float, dict[str, Any]] | None:
    path = _disk_path(kind, key)
    if not path.exists():
        return None
    try:
        packed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(packed.get("version") or 0) != CACHE_VERSION:
        return None
    data = packed.get("data")
    if not isinstance(data, dict):
        return None
    return float(packed.get("cached_at") or 0), strip_charts(data)


def save_disk(kind: str, key: str, data: dict[str, Any]) -> None:
    path = _disk_path(kind, key)
    try:
        path.write_text(
            json.dumps(
                {"version": CACHE_VERSION, "cached_at": time.time(), "data": strip_charts(data)},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    except OSError:
        return


def _disk_path(kind: str, key: str):
    ensure_cache_dirs()
    safe = _SAFE.sub("_", key).strip("_")[:80] or "default"
    return ANALYSIS_CACHE_DIR / f"{kind}_{safe}.json"
