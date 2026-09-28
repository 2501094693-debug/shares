"""自选分组磁盘持久化。

文件：``backend/cache/mine/groups.json``
"""

from __future__ import annotations

import json
import threading
from typing import Any

from core.paths import MINE_GROUPS_CACHE, ensure_cache_dirs

_DISK_VERSION = 1
_lock = threading.RLock()


def _empty_payload() -> dict[str, Any]:
    return {"version": _DISK_VERSION, "groups": []}


def load() -> dict[str, Any]:
    """读取全部分组；文件不存在或损坏时返回空结构。"""
    ensure_cache_dirs()
    path = MINE_GROUPS_CACHE
    if not path.is_file():
        return _empty_payload()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_payload()
    if not isinstance(raw, dict):
        return _empty_payload()
    groups = raw.get("groups")
    if not isinstance(groups, list):
        groups = []
    return {"version": _DISK_VERSION, "groups": [g for g in groups if isinstance(g, dict)]}


def save(payload: dict[str, Any]) -> None:
    """原子写入分组文件（调用方须已持有 ``_lock``）。"""
    ensure_cache_dirs()
    path = MINE_GROUPS_CACHE
    data = {
        "version": _DISK_VERSION,
        "groups": list(payload.get("groups") or []),
    }
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
