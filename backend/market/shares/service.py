"""个股行情：把行业树里按行业挂着的成分股摊成涨跌排序表。"""

from __future__ import annotations

import threading
import time
from collections import Counter
from typing import Any

from core.cache import TtlCache
from market.sw.parse import parse_num, parse_pct, parse_yi
from market.sw.service import service as market_service

_LIST_TTL = 90
_LITE_LIMIT = 80


def _sort_num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _valuation(stock: dict[str, Any], flow: dict[str, Any]) -> tuple[float | None, float | None]:
    pe = flow.get("pe_ttm")
    pb = flow.get("pb")
    if pe is None:
        pe = parse_num(stock.get("pe_ttm")) or parse_num(stock.get("pe"))
    if pb is None:
        pb = parse_num(stock.get("pb"))
    return pe, pb


def _row(stock: dict[str, Any], flow: dict[str, Any]) -> dict[str, Any] | None:
    code = str(stock.get("code") or "").strip()
    if not code:
        return None
    live_chg = flow.get("change_pct")
    live_px = flow.get("price")
    pe_ttm, pb = _valuation(stock, flow)
    return {
        "code": code,
        "name": str(stock.get("name") or flow.get("name") or "").strip(),
        "l1_name": str(stock.get("l1_name") or "").strip(),
        "l2_name": str(stock.get("l2_name") or "").strip(),
        "l3_name": str(stock.get("l3_name") or "").strip(),
        "l3_code": str(stock.get("l3_code") or "").strip(),
        "change_pct": live_chg if live_chg is not None else parse_pct(stock.get("change_1d")),
        "price": live_px if live_px is not None else parse_num(stock.get("price")),
        "market_cap": parse_yi(stock.get("market_cap")),
        "pe_ttm": pe_ttm,
        "pb": pb,
        "main_net": flow.get("main_net"),
        "main_net_5d": flow.get("main_net_5d"),
        "main_net_10d": flow.get("main_net_10d"),
    }


def _apply_live(row: dict[str, Any], flow: dict[str, Any]) -> None:
    if not row.get("name") and flow.get("name"):
        row["name"] = str(flow.get("name") or "").strip()
    if flow.get("change_pct") is not None:
        row["change_pct"] = flow["change_pct"]
    if flow.get("price") is not None:
        row["price"] = flow["price"]
    if flow.get("pe_ttm") is not None:
        row["pe_ttm"] = flow["pe_ttm"]
    if flow.get("pb") is not None:
        row["pb"] = flow["pb"]
    for key in ("main_net", "main_net_5d", "main_net_10d"):
        if flow.get(key) is not None:
            row[key] = flow[key]


def _rank(items: list[dict[str, Any]]) -> None:
    items.sort(key=lambda row: _sort_num(row.get("change_pct")), reverse=True)
    for i, row in enumerate(items, start=1):
        row["rank"] = i


def _summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    up = down = flat = 0
    for row in items:
        chg = row.get("change_pct")
        try:
            n = float(chg) if chg is not None else None
        except (TypeError, ValueError):
            n = None
        if n is None:
            continue
        if n > 0:
            up += 1
        elif n < 0:
            down += 1
        else:
            flat += 1
    counts = Counter(row.get("l1_name") or "" for row in items)
    industries = [
        {"name": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if name
    ]
    return {"up": up, "down": down, "flat": flat, "industries": industries}


def _lite_list(payload: dict[str, Any], limit: int = _LITE_LIMIT) -> dict[str, Any]:
    items = payload.get("items") or []
    lite = dict(payload)
    lite["items"] = items[:limit]
    lite["lite"] = True
    return lite


def _lite_from_market_tree() -> dict[str, Any] | None:
    """行业树已热时，直接抽出涨幅前 N，避免再拼整张个股表。"""
    cached = market_service._tree.get("t:all")
    if not cached:
        return None
    items: list[dict[str, Any]] = []

    def walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            if int(node.get("level") or 0) == 4:
                code = str(node.get("code") or "").strip()
                if not code:
                    continue
                items.append(
                    {
                        "code": code,
                        "name": str(node.get("name") or "").strip(),
                        "l1_name": str(node.get("l1_name") or "").strip(),
                        "l2_name": str(node.get("l2_name") or "").strip(),
                        "l3_name": str(node.get("parent_name") or "").strip(),
                        "l3_code": str(node.get("parent_code") or "").strip(),
                        "change_pct": node.get("change_pct"),
                        "price": node.get("price"),
                        "market_cap": node.get("market_cap"),
                        "pe_ttm": node.get("pe_ttm"),
                        "pb": node.get("pb"),
                        "main_net": node.get("main_net"),
                        "main_net_5d": node.get("main_net_5d"),
                        "main_net_10d": node.get("main_net_10d"),
                    }
                )
            else:
                walk(node.get("children") or [])

    walk(cached.get("tree") or [])
    if not items:
        return None
    _rank(items)
    summary = _summarize(items)
    return {
        "updated_at": cached.get("updated_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(items),
        "live": bool(cached.get("live")),
        **summary,
        "items": items[:_LITE_LIMIT],
        "errors": [],
        "lite": True,
        "note": "来自行业树缓存的个股首屏",
    }


class ShareQuoteService:
    def __init__(self) -> None:
        self._list = TtlCache(_LIST_TTL)
        self._lock = threading.Lock()

    def list(
        self, force: bool = False, live: bool = False, lite: bool = False
    ) -> dict[str, Any]:
        """申万成分股一张表，涨跌从高到低。"""
        cache_key = "all"
        if not force:
            hit = self._list.get(cache_key)
            if hit is not None:
                if live:
                    hit = self._refresh_quotes(hit)
                return _lite_list(hit) if lite else hit
        if lite and not force:
            quick = _lite_from_market_tree()
            if quick is not None:
                return quick

        with self._lock:
            if not force:
                hit = self._list.get(cache_key)
                if hit is not None:
                    if live:
                        hit = self._refresh_quotes(hit)
                    return _lite_list(hit) if lite else hit
            payload = self._build_list(force=force)
        return _lite_list(payload) if lite else payload

    def _build_list(self, force: bool = False) -> dict[str, Any]:
        errors: list[str] = []
        stocks = market_service._stocks()
        try:
            flows = market_service._raw_stock_flows(force=force)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"个股行情: {exc}")
            flows = {}

        seen: set[str] = set()
        items: list[dict[str, Any]] = []
        for stock in stocks:
            row = _row(stock, flows.get(str(stock.get("code") or "").strip()) or {})
            if row is None or row["code"] in seen:
                continue
            seen.add(row["code"])
            items.append(row)
        _rank(items)

        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(items),
            "live": False,
            **_summarize(items),
            "items": items,
            "errors": errors,
            "note": "申万行业成分股摊平，按涨跌从高到低",
        }
        self._list.put("all", payload)
        return payload

    def _refresh_quotes(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("items") or []
        try:
            flows = market_service._raw_stock_flows(force=False)
        except Exception as exc:  # noqa: BLE001
            errors = list(payload.get("errors") or [])
            errors.append(f"实时行情: {exc}")
            payload["errors"] = errors
            return payload
        for row in items:
            flow = flows.get(row.get("code") or "") or {}
            if flow:
                _apply_live(row, flow)
        _rank(items)
        payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        payload["live"] = True
        payload.update(_summarize(items))
        return payload


service = ShareQuoteService()
