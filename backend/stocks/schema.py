"""股票索引条目的字段约定与规范化。"""

from __future__ import annotations

from typing import Any

# 与成分股表对齐的行情字段
METRIC_KEYS = (
    "price",
    "pe",
    "pe_ttm",
    "pb",
    "roe",
    "dividend_yield",
    "market_cap",
    "change_1d",
    "change_5d",
    "change_ytd",
    "profit_growth",
    "revenue_growth",
)


def stock_key(stock: dict[str, Any]) -> str:
    """去重主键：优先完整代码。"""
    return str(stock.get("full_code") or stock.get("code") or "").strip()


def make_index_entry(
    stock: dict[str, Any], meta: dict[str, Any] | None = None
) -> dict[str, Any]:
    """成分股记录 → 全局索引条目（行业归属 + 行情）。"""
    meta = meta or {}
    entry = {
        "code": stock.get("code", ""),
        "full_code": stock.get("full_code", ""),
        "name": stock.get("name", ""),
        "include_date": stock.get("include_date", ""),
        "l1_name": meta.get("l1_name") or stock.get("l1_name") or stock.get("l1", ""),
        "l2_name": meta.get("l2_name") or stock.get("l2_name") or stock.get("l2", ""),
        "l3_name": meta.get("name") or stock.get("l3_name") or stock.get("l3", ""),
        "l3_code": meta.get("code") or stock.get("l3_code", ""),
    }
    for key in METRIC_KEYS:
        entry[key] = stock.get(key, "")
    return entry
