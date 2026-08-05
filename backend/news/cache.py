"""按股票代码读写新闻结果的磁盘缓存。"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from core.paths import ensure_cache_dirs
from .constants import CACHE_DIR, CACHE_TTL_SEC, CACHE_VERSION


def cache_path(code: str, days: int, kind: str = "") -> Path:
    """股票代码 → 缓存文件路径（含天数窗口与可选类型）。"""
    safe = re.sub(r"[^\w.-]+", "_", code.strip()) or "unknown"
    kind_part = f"_{kind}" if kind else ""
    return CACHE_DIR / f"{safe}_d{int(days)}{kind_part}.json"


def load_cache(code: str, days: int, kind: str = "") -> dict[str, Any] | None:
    """读取有效缓存；版本不对或过期则返回 None。"""
    path = cache_path(code, days, kind)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    # 结构升级后旧文件直接作废
    if int(payload.get("version") or 0) != CACHE_VERSION:
        return None

    cached_at = float(payload.get("cached_at") or 0)
    if time.time() - cached_at > CACHE_TTL_SEC:
        return None

    data = payload.get("data")
    return data if isinstance(data, dict) else None


def save_cache(code: str, data: dict[str, Any], days: int, kind: str = "") -> None:
    """把采集结果写入磁盘（含版本号与写入时间）。"""
    ensure_cache_dirs()
    path = cache_path(code, days, kind)
    path.write_text(
        json.dumps(
            {
                "version": CACHE_VERSION,
                "cached_at": time.time(),
                "data": data,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
