"""申万行业树摊平 + 按代码 / 名称对齐外部行情。"""

from __future__ import annotations

from typing import Any, Iterable

from .parse import bare_code, norm_name


def flatten_tree(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """一级 → 二级 → 三级，每行带上下级代码和名称。"""
    rows: list[dict[str, Any]] = []
    for l1 in tree:
        l1_code = str(l1.get("code") or "").strip()
        l1_name = str(l1.get("name") or "").strip()
        rows.append(
            {
                "level": 1,
                "code": l1_code,
                "name": l1_name,
                "count": int(l1.get("count") or 0),
                "l1_code": l1_code,
                "l1_name": l1_name,
                "l2_code": "",
                "l2_name": "",
                "parent_code": "",
                "parent_name": "",
            }
        )
        for l2 in l1.get("children") or []:
            l2_code = str(l2.get("code") or "").strip()
            l2_name = str(l2.get("name") or "").strip()
            rows.append(
                {
                    "level": 2,
                    "code": l2_code,
                    "name": l2_name,
                    "count": int(l2.get("count") or 0),
                    "l1_code": l1_code,
                    "l1_name": l1_name,
                    "l2_code": l2_code,
                    "l2_name": l2_name,
                    "parent_code": l1_code,
                    "parent_name": l1_name,
                }
            )
            for l3 in l2.get("children") or []:
                l3_code = str(l3.get("code") or "").strip()
                l3_name = str(l3.get("name") or "").strip()
                rows.append(
                    {
                        "level": 3,
                        "code": l3_code,
                        "name": l3_name,
                        "count": int(l3.get("count") or 0),
                        "l1_code": l1_code,
                        "l1_name": l1_name,
                        "l2_code": l2_code,
                        "l2_name": l2_name,
                        "parent_code": l2_code,
                        "parent_name": l2_name,
                    }
                )
    return rows


def filter_level(rows: Iterable[dict[str, Any]], level: int) -> list[dict[str, Any]]:
    return [row for row in rows if int(row.get("level") or 0) == level]


def nest_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """扁平行业行 → 一级.children.二级.children.三级，保持申万官方顺序。"""
    by_code = {row["code"]: {**row, "children": []} for row in rows}
    roots: list[dict[str, Any]] = []
    for row in rows:
        node = by_code[row["code"]]
        parent = by_code.get(str(row.get("parent_code") or ""))
        if parent is not None:
            parent["children"].append(node)
        elif int(row.get("level") or 0) == 1:
            roots.append(node)
    return roots


def index_by_code(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = bare_code(str(row.get("code") or ""))
        if key:
            out[key] = row
    return out


def index_by_name(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """同名时保留更细的级别（三级优先），避免一级「银行」盖住二级。"""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = norm_name(str(row.get("name") or ""))
        if not key:
            continue
        prev = out.get(key)
        if prev is None or int(row.get("level") or 0) >= int(prev.get("level") or 0):
            out[key] = row
    return out


def index_by_name_level(
    rows: Iterable[dict[str, Any]], level: int
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if int(row.get("level") or 0) != level:
            continue
        key = norm_name(str(row.get("name") or ""))
        if key:
            out[key] = row
    return out
