"""东财 A 股指数目录（宽基为主）。

对外统一 6 位 ``code``，查询映射到东财 ``secid``（``市场号.代码``）：
上证 / 多数中证 ``1.xxxxxx``，深证 / 北证 ``0.xxxxxx``，部分中证 ``2.xxxxxx``。
"""

from __future__ import annotations

from typing import Any

# 东财 clist 分类 → fs 筛选
CATEGORIES: dict[str, dict[str, str]] = {
    "important": {"name": "沪深重要指数", "fs": "b:MK0010"},
    "sse": {"name": "上证系列指数", "fs": "m:1+t:1"},
    "szse": {"name": "深证系列指数", "fs": "m:0+t:5"},
    "csi": {"name": "中证系列指数", "fs": "m:2"},
}

GROUPS: dict[str, dict[str, Any]] = {
    "broad": {
        "name": "宽基",
        "items": [
            {"code": "000001", "name": "上证指数", "secid": "1.000001"},
            {"code": "399001", "name": "深证成指", "secid": "0.399001"},
            {"code": "399006", "name": "创业板指", "secid": "0.399006"},
            {"code": "000688", "name": "科创50", "secid": "1.000688"},
            {"code": "899050", "name": "北证50", "secid": "0.899050"},
        ],
    },
    "scale": {
        "name": "规模",
        "items": [
            {"code": "000016", "name": "上证50", "secid": "1.000016"},
            {"code": "000010", "name": "上证180", "secid": "1.000010"},
            {"code": "000300", "name": "沪深300", "secid": "1.000300"},
            {"code": "000905", "name": "中证500", "secid": "1.000905"},
            {"code": "000852", "name": "中证1000", "secid": "1.000852"},
            {"code": "932000", "name": "中证2000", "secid": "2.932000"},
            {"code": "000903", "name": "中证A100", "secid": "1.000903"},
            {"code": "399330", "name": "深证100", "secid": "0.399330"},
        ],
    },
    "other": {
        "name": "其他",
        "items": [
            {"code": "000015", "name": "红利指数", "secid": "1.000015"},
            {"code": "000985", "name": "中证全指", "secid": "1.000985"},
            {"code": "399317", "name": "国证A指", "secid": "0.399317"},
        ],
    },
}


def all_items() -> list[dict[str, Any]]:
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
    return {item["code"]: item for item in all_items()}


def catalog() -> dict[str, Any]:
    return {
        "source": "eastmoney",
        "categories": CATEGORIES,
        "groups": list(GROUPS.keys()),
        "indices": GROUPS,
        "items": all_items(),
    }
