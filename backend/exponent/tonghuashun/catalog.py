"""同花顺 A 股指数目录（宽基为主）。

同花顺内部证券码与交易所公开代码不同：上证系多用 ``USHI1Axxxx`` / ``USHI1Bxxxx``，
深证系为 ``USZIxxxxxx``，中证/北证另有 ``UZZI`` / ``USTI``。对外统一用 6 位
``code``（如 ``000001`` / ``000300``），查询时映射到 ``security``。
"""

from __future__ import annotations

from typing import Any

# 市场：同花顺 4 位前缀
MARKETS: dict[str, str] = {
    "USHI": "上证指数",
    "USZI": "深证指数",
    "UZZI": "中证指数",
    "USTI": "北证指数",
}

# 分组目录：常用宽基 / 规模 / 主题
GROUPS: dict[str, dict[str, Any]] = {
    "broad": {
        "name": "宽基",
        "items": [
            {"code": "000001", "name": "上证指数", "security": "USHI1A0001", "market": "USHI"},
            {"code": "399001", "name": "深证成指", "security": "USZI399001", "market": "USZI"},
            {"code": "399006", "name": "创业板指", "security": "USZI399006", "market": "USZI"},
            {"code": "000688", "name": "科创50", "security": "USHI1B0688", "market": "USHI"},
            {"code": "899050", "name": "北证50", "security": "USTI899050", "market": "USTI"},
        ],
    },
    "scale": {
        "name": "规模",
        "items": [
            {"code": "000016", "name": "上证50", "security": "USHI1B0016", "market": "USHI"},
            {"code": "000010", "name": "上证180", "security": "USHI1B0007", "market": "USHI"},
            {"code": "000300", "name": "沪深300", "security": "USHI1B0300", "market": "USHI"},
            {"code": "000905", "name": "中证500", "security": "USHI1B0905", "market": "USHI"},
            {"code": "000852", "name": "中证1000", "security": "USHI1B0852", "market": "USHI"},
            {"code": "932000", "name": "中证2000", "security": "UZZI932000", "market": "UZZI"},
            {"code": "000903", "name": "中证A100", "security": "USHI1B0903", "market": "USHI"},
            {"code": "399330", "name": "深证100", "security": "USZI399330", "market": "USZI"},
        ],
    },
    "other": {
        "name": "其他",
        "items": [
            {"code": "000015", "name": "红利指数", "security": "USHI1B0015", "market": "USHI"},
            {"code": "000985", "name": "中证全指", "security": "UZZI000985", "market": "UZZI"},
            {"code": "399317", "name": "国证A指", "security": "USZI399317", "market": "USZI"},
        ],
    },
}


def all_items() -> list[dict[str, Any]]:
    """扁平化目录条目（按分组顺序）。"""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group_id, block in GROUPS.items():
        for item in block["items"]:
            code = str(item["code"])
            if code in seen:
                continue
            seen.add(code)
            out.append(
                {
                    "group": group_id,
                    "group_name": block["name"],
                    **item,
                }
            )
    return out


def by_code() -> dict[str, dict[str, Any]]:
    """``code`` → 目录条目。"""
    return {item["code"]: item for item in all_items()}


def catalog() -> dict[str, Any]:
    return {
        "markets": MARKETS,
        "groups": list(GROUPS.keys()),
        "indices": GROUPS,
        "items": all_items(),
    }
