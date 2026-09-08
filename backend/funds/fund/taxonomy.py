"""东财场内基金分类树（方案二：clist ``fs`` 板块代码）。

东财行情中心 ETF / LOF 页使用 ``b:MKxxxx`` 板块代码筛选，
与 ``m:1+t:2`` 等市场类型参数不同，后者会混入 A 股。

树形结构对齐申万行业模块：一级（品种）→ 二级（细分类型）。
"""

from __future__ import annotations

from typing import Any

# 二级分类：code → 元数据
CATEGORY_META: dict[str, dict[str, str]] = {
    "stock_etf": {"name": "股票型ETF", "fs": "b:MK0021", "parent": "etf"},
    "bond_etf": {"name": "债券型ETF", "fs": "b:MK0022", "parent": "etf"},
    "cross_etf": {"name": "跨境ETF", "fs": "b:MK0023", "parent": "etf"},
    "commodity_etf": {"name": "商品型ETF", "fs": "b:MK0024", "parent": "etf"},
    "other_etf": {"name": "其他ETF", "fs": "b:MK0827", "parent": "etf"},
    "sh_lof": {"name": "上交所LOF", "fs": "b:MK0404", "parent": "lof"},
    "sz_lof": {"name": "深交所LOF", "fs": "b:MK0405", "parent": "lof"},
    "qdii_lof": {"name": "QDII LOF", "fs": "b:MK0406", "parent": "lof"},
    "commodity_lof": {"name": "商品LOF", "fs": "b:MK0407", "parent": "lof"},
}

# 一级分类
GROUP_META: dict[str, str] = {
    "etf": "ETF",
    "lof": "LOF",
}

ALL_CATEGORY_CODES: tuple[str, ...] = tuple(CATEGORY_META.keys())


def get_category(code: str) -> dict[str, str] | None:
    """按分类代码取元数据；不存在返回 None。"""
    meta = CATEGORY_META.get(code.strip())
    if meta is None:
        return None
    return {"code": code.strip(), **meta}


def get_fs(code: str) -> str:
    """分类代码 → 东财 ``fs`` 参数。"""
    meta = get_category(code)
    if meta is None:
        raise KeyError(f"未知基金分类: {code}")
    return meta["fs"]


def build_tree(counts: dict[str, int] | None = None) -> list[dict[str, Any]]:
    """根据各分类数量构建一级 → 二级树。``counts`` 缺省时 count 为 0。"""
    counts = counts or {}
    groups: dict[str, dict[str, Any]] = {}
    for group_code, group_name in GROUP_META.items():
        groups[group_code] = {
            "code": group_code,
            "name": group_name,
            "count": 0,
            "children": [],
        }

    for code, meta in CATEGORY_META.items():
        parent = groups.get(meta["parent"])
        if parent is None:
            continue
        count = int(counts.get(code, 0))
        parent["children"].append(
            {
                "code": code,
                "name": meta["name"],
                "count": count,
                "fs": meta["fs"],
            }
        )
        parent["count"] += count

    return list(groups.values())


def flat_categories() -> list[dict[str, Any]]:
    """扁平分类列表（含一级归属）。"""
    out: list[dict[str, Any]] = []
    for code, meta in CATEGORY_META.items():
        out.append(
            {
                "code": code,
                "name": meta["name"],
                "fs": meta["fs"],
                "group_code": meta["parent"],
                "group_name": GROUP_META.get(meta["parent"], ""),
            }
        )
    return out
