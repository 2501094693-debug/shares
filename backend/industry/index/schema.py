"""股票索引条目的字段约定。

``StockStore`` 把各行业成分股摊成一张扁平表（``stocks_index.json``），
搜索、公司详情都读这张表。本模块规定：

- 一行怎么去重（``stock_key``）
- 一行有哪些字段（行业归属 + ``METRIC_KEYS`` 行情）
- 表格空值哪些字符串该当成「没有」（``EMPTY_CELLS``）
"""

from __future__ import annotations

from typing import Any

# 与乐咕成分股表对齐的行情字段。公司详情页会再用东财盘口覆盖同名键。
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

# pandas / 乐咕表格里常见的「空格子」。收成字符串后若落在这里，一律当 ""。
EMPTY_CELLS = frozenset({"nan", "None", "—", "-", "<NA>", "NaT"})


def stock_key(stock: dict[str, Any]) -> str:
    """去重主键：优先完整代码（如 ``600519.SH``），没有再用短码。"""
    return str(stock.get("full_code") or stock.get("code") or "").strip()


def make_index_entry(
    stock: dict[str, Any], meta: dict[str, Any] | None = None
) -> dict[str, Any]:
    """成分股记录 → 全局索引条目。

    ``meta`` 是三级行业信息（``IndustryTree.get_l3_meta`` 的返回值）：
    - ``meta["name"]`` / ``meta["code"]`` 是 **行业** 名称和代码，不是股票
    - 成分股自身的 ``name`` 才是股票简称
    """
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
