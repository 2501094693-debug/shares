"""财务报表统一入口（带 TTL 缓存）。"""

from __future__ import annotations

import time
from typing import Any

from company.news.financialreport._common import STATEMENT_REPORTS
from company.news.financialreport.statements import fetch_all_statements, fetch_statement
from core.cache import TtlCache

_TTL = 3600
_cache = TtlCache(_TTL)

_VALID_SCOPES = frozenset({"all", "merged", *STATEMENT_REPORTS})


def _has_payload(data: dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("count", 0) > 0:
        return True
    statements = data.get("statements")
    if isinstance(statements, dict):
        return any(bool(v) for v in statements.values())
    items = data.get("items")
    return isinstance(items, list) and bool(items)


def get_financial_report(
    code: str,
    *,
    scope: str = "merged",
    limit: int = 24,
    force: bool = False,
) -> dict[str, Any]:
    """``scope=all|merged|main|income|balance|cashflow|lico``。"""
    key = (scope or "merged").strip().lower()
    if key not in _VALID_SCOPES:
        raise ValueError(f"scope 须为 {' | '.join(sorted(_VALID_SCOPES))}")

    page_size = min(max(int(limit or 24), 1), 60)
    cache_key = f"{key}:{code}:{page_size}"
    now = time.time()
    if not force:
        hit = _cache.get(cache_key)
        if hit is not None:
            return hit

    if key == "all":
        data = fetch_all_statements(code, page_size=page_size)
    elif key == "merged":
        pack = fetch_all_statements(code, page_size=page_size)
        data = {
            "code": pack.get("code") or "",
            "source": pack.get("source") or "",
            "scope": "merged",
            "count": pack.get("count") or 0,
            "items": pack.get("merged") or [],
            "annual": pack.get("annual") or [],
            "recent": pack.get("recent") or [],
        }
    else:
        rows = fetch_statement(code, key, page_size=page_size)
        data = {
            "code": code.strip(),
            "source": "eastmoney" if rows else "",
            "scope": key,
            "count": len(rows),
            "items": rows,
        }

    if _has_payload(data):
        _cache.put(cache_key, data, cached_at=now)
    return data
