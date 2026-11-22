"""把筛选结果写入「我的」分组。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.codes import normalize_code, safe_str
from mine.service import service as mine_service

DEFAULT_GROUP_PREFIX = "MACD金叉"
MAX_STOCKS_PER_GROUP = 1000


def default_group_name(*, prefix: str = DEFAULT_GROUP_PREFIX, day: str = "") -> str:
    """默认分组名：``前缀_YYYY-MM-DD``。"""
    date = str(day or "").strip()[:10]
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    base = safe_str(prefix) or DEFAULT_GROUP_PREFIX
    return f"{base}_{date}"


def _ensure_group(name: str) -> dict[str, Any]:
    listed = mine_service.list_groups().get("groups") or []
    for group in listed:
        if safe_str(group.get("name")) == name:
            return mine_service.get_group(safe_str(group.get("id")))
    return mine_service.create_group(name)


def _clear_group(group_id: str) -> int:
    group = mine_service.get_group(group_id)
    codes = [
        normalize_code(safe_str(s.get("code")))
        for s in (group.get("stocks") or [])
        if isinstance(s, dict)
    ]
    codes = [c for c in codes if c]
    if not codes:
        return 0
    result = mine_service.remove_stocks(group_id, codes)
    return len(result.get("removed") or [])


def write_mine_group(
    rows: list[dict[str, Any]],
    *,
    group_name: str = "",
    replace: bool = True,
    limit: int = 0,
) -> dict[str, Any] | None:
    """按列表顺序写入分组；``limit>0`` 时只取前 N 只。"""
    name = safe_str(group_name) or default_group_name()
    hits = [r for r in rows if normalize_code(safe_str(r.get("code")))]
    if limit and limit > 0:
        hits = hits[: int(limit)]
    if not hits:
        return None
    if len(hits) > MAX_STOCKS_PER_GROUP:
        hits = hits[:MAX_STOCKS_PER_GROUP]

    group = _ensure_group(name)
    gid = safe_str(group.get("id"))
    removed = 0
    if replace:
        removed = _clear_group(gid)

    codes = [normalize_code(safe_str(r.get("code"))) for r in hits]
    codes = [c for c in codes if c]
    names = {
        normalize_code(safe_str(r.get("code"))): safe_str(r.get("name"))
        for r in hits
        if normalize_code(safe_str(r.get("code")))
    }
    result = mine_service.add_stocks(gid, codes, names=names)
    final = result.get("group") or mine_service.get_group(gid)
    return {
        "group_name": safe_str(final.get("name")) or name,
        "group_id": safe_str(final.get("id")) or gid,
        "count": int(final.get("count") or 0),
        "added": len(result.get("added") or []),
        "skipped": len(result.get("skipped") or []),
        "removed": removed,
        "group": final,
    }


__all__ = [
    "DEFAULT_GROUP_PREFIX",
    "MAX_STOCKS_PER_GROUP",
    "default_group_name",
    "write_mine_group",
]
