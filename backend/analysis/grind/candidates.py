"""全市场 / 单只股票候选。"""

from __future__ import annotations

from typing import Any

from core.codes import normalize_code
from industry.service import service as industry_service


def _as_meta(row: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code(str(row.get("code") or ""))
    return {
        "code": code,
        "name": row.get("name") or "",
        "l1_name": row.get("l1_name") or "",
        "l2_name": row.get("l2_name") or "",
        "l3_name": row.get("l3_name") or "",
    }


def collect_universe(code: str = "") -> dict[str, Any]:
    """申万成分股全市场；指定 code 则只分析这一只。"""
    industry_service.stocks.ensure_populated()
    target = normalize_code(code)
    errors: list[str] = []

    if target:
        hit = industry_service.stocks.get_by_code(target)
        items = [_as_meta(hit)] if hit else [_as_meta({"code": target})]
        return {
            "count": len(items),
            "candidates": items,
            "errors": errors,
        }

    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for row in industry_service.stocks.all_stocks():
        meta = _as_meta(row)
        if not meta["code"] or meta["code"] in seen:
            continue
        seen.add(meta["code"])
        items.append(meta)

    if not items:
        errors.append("股票索引为空，请先打开行业树或个股页让成分股索引建立")

    return {
        "count": len(items),
        "candidates": items,
        "errors": errors,
    }
