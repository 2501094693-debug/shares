"""东财国内期货分类树（clist ``fs`` 市场代码）。

树形结构对齐场内基金模块：一级（商品 / 金融）→ 二级（交易所）。
"""

from __future__ import annotations

from typing import Any

# 二级分类：code → 元数据
CATEGORY_META: dict[str, dict[str, str]] = {
    "shfe": {"name": "上期所", "fs": "m:113", "parent": "commodity", "venue": "SHFE"},
    "dce": {"name": "大商所", "fs": "m:114", "parent": "commodity", "venue": "DCE"},
    "czce": {"name": "郑商所", "fs": "m:115", "parent": "commodity", "venue": "CZCE"},
    "ine": {"name": "上期能源", "fs": "m:142", "parent": "commodity", "venue": "INE"},
    "gfex": {"name": "广期所", "fs": "m:225", "parent": "commodity", "venue": "GFEX"},
    "cffex": {"name": "中金所", "fs": "m:8", "parent": "financial", "venue": "CFFEX"},
}

# 一级分类
GROUP_META: dict[str, str] = {
    "commodity": "商品期货",
    "financial": "金融期货",
}

ALL_CATEGORY_CODES: tuple[str, ...] = tuple(CATEGORY_META.keys())

# 东财 f13 市场号 → 分类代码
MARKET_ID_TO_CATEGORY: dict[int, str] = {
    113: "shfe",
    114: "dce",
    115: "czce",
    142: "ine",
    225: "gfex",
    8: "cffex",
}


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
        raise KeyError(f"未知期货分类: {code}")
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
                "venue": meta["venue"],
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
                "venue": meta["venue"],
                "group_code": meta["parent"],
                "group_name": GROUP_META.get(meta["parent"], ""),
            }
        )
    return out
