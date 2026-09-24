"""结果列表排序与截断（三种筛选共用）。"""

from __future__ import annotations

from typing import Any


def apply_view(data: dict[str, Any], top: int | None) -> dict[str, Any]:
    items = list(data.get("items") or [])
    items.sort(
        key=lambda r: (
            -float(r.get("score") or 0),
            -int(r.get("matched_days") or 0),
            -int(r.get("quiet_count") or 0),
            str(r.get("code") or ""),
        )
    )
    if top is not None and top > 0:
        items = items[:top]
    out = []
    for idx, row in enumerate(items, start=1):
        item = dict(row)
        item.pop("chart", None)
        item["rank"] = idx
        out.append(item)
    return {
        **data,
        "items": out,
        "result_count": len(out),
        "top": top,
    }
