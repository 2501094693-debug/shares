"""申万一 / 二 / 三级行业总体涨跌。

- 一级、二级：申万宏源官方指数实时点位
- 三级：没有官方指数，用成分股市值加权个股涨跌
"""

from __future__ import annotations

from typing import Any

from .parse import bare_code, parse_pct, parse_yi
from .sw_client import fetch_level_quotes


def attach_sw_quotes(
    nodes: list[dict[str, Any]], level: int
) -> dict[str, dict[str, Any]]:
    """把申万实时行情按代码贴到树上。三级直接返回空映射。"""
    if level not in (1, 2):
        return {}
    by_code = {bare_code(n["code"]): n for n in nodes}
    overlay: dict[str, dict[str, Any]] = {}
    for row in fetch_level_quotes(level):
        node = by_code.get(row["sw_code"])
        if node is None:
            continue
        overlay[node["code"]] = row
    return overlay


def aggregate_from_stocks(
    nodes: list[dict[str, Any]],
    stocks: list[dict[str, Any]],
    level: int,
    *,
    counts_only: bool = False,
    tree: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """成分股 → 行业涨跌。按市值加权；没有市值则等权。"""
    buckets: dict[str, list[tuple[float, float, float]]] = {}
    node_codes = {n["code"] for n in nodes}
    l3_by_code = {
        n["code"]: n
        for n in (tree or nodes)
        if int(n.get("level") or 0) == 3
    }
    parent_key = {1: "l1_code", 2: "l2_code", 3: "code"}[level]

    def industry_code(stock: dict[str, Any]) -> str:
        meta = l3_by_code.get(str(stock.get("l3_code") or "").strip())
        if meta:
            return str(meta.get(parent_key) or "")
        if level == 3:
            return str(stock.get("l3_code") or "").strip()
        return ""

    for stock in stocks:
        code = industry_code(stock)
        if not code or code not in node_codes:
            continue
        chg = parse_pct(stock.get("change_1d"))
        if chg is None:
            continue
        weight = parse_yi(stock.get("market_cap")) or 0.0
        chg5 = parse_pct(stock.get("change_5d")) or 0.0
        buckets.setdefault(code, []).append((chg, chg5, weight))

    out: dict[str, dict[str, Any]] = {}
    for code, items in buckets.items():
        total_w = sum(w for _, _, w in items)
        if total_w > 0:
            chg = sum(c * w for c, _, w in items) / total_w
            chg5 = sum(c5 * w for _, c5, w in items) / total_w
        else:
            chg = sum(c for c, _, _ in items) / len(items)
            chg5 = sum(c5 for _, c5, _ in items) / len(items)
        up = sum(1 for c, _, _ in items if c > 0)
        down = sum(1 for c, _, _ in items if c < 0)
        row = {
            "up_count": up,
            "down_count": down,
            "sample_count": len(items),
            "source": "aggregate",
        }
        if not counts_only:
            row["change_pct"] = chg
            row["change_5d"] = chg5
        out[code] = row
    return out


def merge_quote_row(
    node: dict[str, Any],
    *layers: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """后面的层只填空，不覆盖已有官方点位。"""
    row = {
        "code": node["code"],
        "name": node["name"],
        "level": node["level"],
        "count": node.get("count") or 0,
        "l1_code": node.get("l1_code") or "",
        "l1_name": node.get("l1_name") or "",
        "l2_code": node.get("l2_code") or "",
        "l2_name": node.get("l2_name") or "",
        "parent_code": node.get("parent_code") or "",
        "parent_name": node.get("parent_name") or "",
        "sw_code": bare_code(node["code"]),
        "price": None,
        "last_close": None,
        "open": None,
        "high": None,
        "low": None,
        "change_pct": None,
        "change_5d": None,
        "amount": None,
        "volume": None,
        "up_count": None,
        "down_count": None,
        "sample_count": None,
        "sources": [],
    }
    for layer in layers:
        extra = layer.get(node["code"])
        if not extra:
            continue
        src = extra.get("source")
        if src and src not in row["sources"]:
            row["sources"].append(src)
        for key, value in extra.items():
            if key in {"source", "name"}:
                continue
            if row.get(key) in (None, "", []) and value not in (None, ""):
                row[key] = value
    return row
