"""大盘总闸：上证六栏处于上升家族才允许新开多。"""

from __future__ import annotations

from typing import Any

from analysis.livermore.config import INDEX_ALLOW_COLUMNS, INDEX_CODE, INDEX_NAME


def market_gate(index_key: dict[str, Any] | None) -> dict[str, Any]:
    column = str((index_key or {}).get("column") or "unclear")
    allow = column in INDEX_ALLOW_COLUMNS
    return {
        "code": INDEX_CODE,
        "name": INDEX_NAME,
        "column": column,
        "column_label": (index_key or {}).get("column_label") or "",
        "family": (index_key or {}).get("family") or "unclear",
        "allow": allow,
        "as_of": (index_key or {}).get("as_of") or "",
        "reason": "" if allow else "gate.blocked",
    }
