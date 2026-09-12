"""三级每日事实缓存：收盘后冻结，再算时不再回放快照/日 K。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from analysis.rotation.config import CACHE_TAG
from company.line.session import cn_now, market_phase
from core.paths import ANALYSIS_CACHE_DIR, ensure_cache_dirs

_SAFE = re.compile(r"[^0-9-]+")
_FACT_KEYS = (
    "code",
    "name",
    "l1_code",
    "l1_name",
    "l2_code",
    "l2_name",
    "change_1d",
    "up_1d",
    "down_1d",
    "limit_up_1d",
    "limit_down_1d",
    "strong_1d",
    "cap_median",
    "cap_tier",
    "sample_count",
    "leader",
)


def day_frozen(iso: str) -> bool:
    """已收盘的交易日可以复用日面板。盘中的今天不算冻结。"""
    today = cn_now().date().isoformat()
    if iso < today:
        return True
    if iso > today:
        return False
    return market_phase() == "closed"


def _dir() -> Path:
    ensure_cache_dirs()
    path = ANALYSIS_CACHE_DIR / "l3_day" / CACHE_TAG
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path(iso: str) -> Path:
    safe = _SAFE.sub("", iso)[:10]
    return _dir() / f"{safe}.json"


def _fact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in _FACT_KEYS if key in row}


def load_l3_day(iso: str) -> tuple[list[dict[str, Any]], str] | None:
    path = _path(iso)
    if not path.exists():
        return None
    try:
        packed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(packed, dict):
        return None
    rows = packed.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    source = str(packed.get("source") or "cache")
    out = [row for row in rows if isinstance(row, dict) and row.get("code")]
    if not out:
        return None
    return out, source


def save_l3_day(iso: str, rows: list[dict[str, Any]], source: str) -> None:
    facts = [_fact_row(row) for row in rows if isinstance(row, dict) and row.get("code")]
    if not facts:
        return
    path = _path(iso)
    try:
        path.write_text(
            json.dumps(
                {"date": iso, "source": source, "rows": facts},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    except OSError:
        return
