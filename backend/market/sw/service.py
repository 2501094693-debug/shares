"""行业行情门面：涨跌 + 成分股资金流加总，输出申万树。"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from core.cache import TtlCache
from industry.service import service as industry_service
from .em_limit_pool import fetch_limit_pools
from .em_stock_flow import fetch_stock_flows
from .fund_flow import (
    FLOW_NET_KEYS,
    aggregate_stock_flows,
    aggregate_stock_flows_all,
    flow_rows,
    normalize_period,
)
from .parse import parse_num, parse_pct, parse_yi
from .quotes import aggregate_from_stocks, attach_sw_quotes, merge_quote_row
from .taxonomy import filter_level, flatten_tree, nest_rows

_QUOTE_TTL = 90
_FLOW_TTL = 120
_TREE_TTL = 90


class MarketService:
    def __init__(self) -> None:
        self._quotes = TtlCache(_QUOTE_TTL)
        self._flows = TtlCache(_FLOW_TTL)
        self._stock_flows = TtlCache(_FLOW_TTL)
        self._limit_pools = TtlCache(_FLOW_TTL)
        self._tree = TtlCache(_TREE_TTL)

    def _nodes(self) -> list[dict[str, Any]]:
        return flatten_tree(industry_service.get_tree())

    def _stocks(self) -> list[dict[str, Any]]:
        industry_service.stocks.ensure_populated()
        return industry_service.stocks.all_stocks()

    def _raw_stock_flows(self, force: bool = False) -> dict[str, dict[str, Any]]:
        if not force:
            hit = self._stock_flows.get("all")
            if hit is not None:
                return hit
        rows = fetch_stock_flows()
        self._stock_flows.put("all", rows)
        return rows

    def _raw_limit_pools(self, force: bool = False) -> dict[str, set[str]]:
        if not force:
            hit = self._limit_pools.get("today")
            if hit is not None:
                return hit
        pools = fetch_limit_pools()
        self._limit_pools.put("today", pools)
        return pools

    def quotes(self, level: int, force: bool = False) -> dict[str, Any]:
        level = _check_level(level)
        cache_key = f"q:{level}"
        if not force:
            hit = self._quotes.get(cache_key)
            if hit is not None:
                return hit

        nodes = self._nodes()
        level_nodes = filter_level(nodes, level)
        sw_map: dict[str, dict[str, Any]] = {}
        agg_map: dict[str, dict[str, Any]] = {}
        errors: list[str] = []

        def _sw() -> None:
            nonlocal sw_map
            if level in (1, 2):
                try:
                    sw_map = attach_sw_quotes(level_nodes, level)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"申万行情: {exc}")

        def _agg() -> None:
            nonlocal agg_map
            try:
                agg_map = aggregate_from_stocks(
                    level_nodes,
                    self._stocks(),
                    level,
                    counts_only=level in (1, 2),
                    tree=nodes,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"成分股汇总: {exc}")

        with ThreadPoolExecutor(max_workers=2) as pool:
            for fut in (pool.submit(_sw), pool.submit(_agg)):
                fut.result()

        items = [merge_quote_row(node, sw_map, agg_map) for node in level_nodes]
        items.sort(key=lambda r: _sort_num(r.get("change_pct")), reverse=True)
        payload = {
            "level": level,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(items),
            "up": sum(1 for r in items if (r.get("change_pct") or 0) > 0),
            "down": sum(1 for r in items if (r.get("change_pct") or 0) < 0),
            "items": items,
            "errors": errors,
        }
        self._quotes.put(cache_key, payload)
        return payload

    def fund_flow(
        self, level: int, period: str = "today", force: bool = False
    ) -> dict[str, Any]:
        level = _check_level(level)
        period = normalize_period(period)
        cache_key = f"f:{level}:{period}"
        if not force:
            hit = self._flows.get(cache_key)
            if hit is not None:
                return hit

        nodes = self._nodes()
        errors: list[str] = []
        try:
            buckets = aggregate_stock_flows(
                nodes, self._stocks(), self._raw_stock_flows(force=force), period
            )
            items = flow_rows(nodes, buckets, level, period)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"资金流: {exc}")
            items = flow_rows(nodes, {}, level, period)

        inflow = sum(r["main_net"] for r in items if r.get("main_net") and r["main_net"] > 0)
        outflow = sum(r["main_net"] for r in items if r.get("main_net") and r["main_net"] < 0)
        payload = {
            "level": level,
            "period": period,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(items),
            "inflow": inflow or None,
            "outflow": outflow or None,
            "items": items,
            "errors": errors,
            "note": "资金流 = 东财个股资金流按申万成分股加总",
        }
        self._flows.put(cache_key, payload)
        return payload

    def tree(
        self, period: str = "today", force: bool = False, live: bool = False
    ) -> dict[str, Any]:
        """一棵申万树：一级/二级官方涨跌，三级市值加权，资金流成分股加总。

        ``live=True`` 且已有缓存时，只重拉申万一/二级实时点位，树结构不动。
        ``period`` 参数保留兼容，树内同时含今日 / 5 日 / 10 日资金。
        """
        _ = normalize_period(period)
        cache_key = "t:all"
        if not force:
            hit = self._tree.get(cache_key)
            if hit is not None:
                if live:
                    return self._refresh_index_quotes(hit)
                return hit

        nodes = self._nodes()
        stocks = self._stocks()
        errors: list[str] = []
        sw1: dict[str, dict[str, Any]] = {}
        sw2: dict[str, dict[str, Any]] = {}
        agg3: dict[str, dict[str, Any]] = {}
        counts12: dict[str, dict[str, Any]] = {}
        buckets: dict[str, dict[str, Any]] = {}
        limit_pools: dict[str, set[str]] = {"limit_up": set(), "limit_down": set()}

        def _sw1() -> None:
            nonlocal sw1
            try:
                sw1 = attach_sw_quotes(filter_level(nodes, 1), 1)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"申万一级: {exc}")

        def _sw2() -> None:
            nonlocal sw2
            try:
                sw2 = attach_sw_quotes(filter_level(nodes, 2), 2)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"申万二级: {exc}")

        def _agg() -> None:
            nonlocal agg3, counts12
            try:
                agg3 = aggregate_from_stocks(
                    filter_level(nodes, 3), stocks, 3, tree=nodes
                )
                counts12 = {
                    **aggregate_from_stocks(
                        filter_level(nodes, 1), stocks, 1, counts_only=True, tree=nodes
                    ),
                    **aggregate_from_stocks(
                        filter_level(nodes, 2), stocks, 2, counts_only=True, tree=nodes
                    ),
                }
            except Exception as exc:  # noqa: BLE001
                errors.append(f"成分股涨跌: {exc}")

        def _flow() -> None:
            nonlocal buckets
            try:
                buckets = aggregate_stock_flows_all(
                    nodes, stocks, self._raw_stock_flows(force=force)
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"资金流: {exc}")

        def _limits() -> None:
            nonlocal limit_pools
            try:
                limit_pools = self._raw_limit_pools(force=force)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"涨跌停池: {exc}")

        with ThreadPoolExecutor(max_workers=5) as pool:
            futs = [pool.submit(fn) for fn in (_sw1, _sw2, _agg, _flow, _limits)]
            for fut in futs:
                fut.result()

        rows: list[dict[str, Any]] = []
        for node in nodes:
            if node["level"] == 1:
                quote = merge_quote_row(node, sw1, counts12)
            elif node["level"] == 2:
                quote = merge_quote_row(node, sw2, counts12)
            else:
                quote = merge_quote_row(node, agg3)
            flow = buckets.get(node["code"]) or {}
            rows.append(
                {
                    **quote,
                    "main_net": flow.get("main_net"),
                    "main_net_5d": flow.get("main_net_5d"),
                    "main_net_10d": flow.get("main_net_10d"),
                    "super_net": flow.get("super_net"),
                    "big_net": flow.get("big_net"),
                    "mid_net": flow.get("mid_net"),
                    "small_net": flow.get("small_net"),
                    "flow_count": flow.get("flow_count") or 0,
                    "leader": flow.get("leader") or "",
                }
            )

        tree = nest_rows(rows)
        stock_nodes = 0
        try:
            stock_nodes = _attach_stocks(
                tree, stocks, self._raw_stock_flows(force=False)
            )
            _roll_up_l3(tree)
            _roll_up_stock_counts(tree, limit_pools)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"成分股挂树: {exc}")
        l1 = [row for row in rows if row["level"] == 1]
        flow_totals = _flow_totals(l1)
        payload = {
            "period": "all",
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(rows),
            "up": sum(1 for r in l1 if (r.get("change_pct") or 0) > 0),
            "down": sum(1 for r in l1 if (r.get("change_pct") or 0) < 0),
            **flow_totals,
            "stock_flow_count": len(self._stock_flows.get("all") or {}),
            "stock_node_count": stock_nodes,
            "tree": tree,
            "errors": errors,
            "note": "一级列表按涨跌排序；树为二级/三级/成分股；涨跌一二级=申万指数，三级与个股=行情，资金流=成分股加总",
        }
        self._tree.put(cache_key, payload)
        return payload

    def _refresh_index_quotes(self, payload: dict[str, Any]) -> dict[str, Any]:
        """在已有树上更新申万一/二级点位，并用东财盘口覆盖个股涨跌。"""
        tree = payload.get("tree") or []
        l1_nodes = _nodes_at(tree, 1)
        l2_nodes = _nodes_at(tree, 2)
        try:
            sw1 = attach_sw_quotes(l1_nodes, 1)
            sw2 = attach_sw_quotes(l2_nodes, 2)
        except Exception as exc:  # noqa: BLE001
            errors = list(payload.get("errors") or [])
            errors.append(f"实时点位: {exc}")
            payload["errors"] = errors
            return payload

        quotes = self._raw_stock_flows(force=False)
        _QUOTE_KEYS = (
            "change_pct",
            "price",
            "last_close",
            "open",
            "high",
            "low",
            "amount",
            "volume",
        )

        def apply(node: dict[str, Any]) -> None:
            extra = sw1.get(node["code"]) or sw2.get(node["code"])
            if extra:
                for key in _QUOTE_KEYS:
                    if extra.get(key) is not None:
                        node[key] = extra[key]
            if int(node.get("level") or 0) == 4:
                live = quotes.get(node["code"]) or {}
                if live.get("change_pct") is not None:
                    node["change_pct"] = live["change_pct"]
                if live.get("price") is not None:
                    node["price"] = live["price"]
                if live.get("pe_ttm") is not None:
                    node["pe_ttm"] = live["pe_ttm"]
                if live.get("pb") is not None:
                    node["pb"] = live["pb"]
            for child in node.get("children") or []:
                apply(child)

        for root in tree:
            apply(root)
        _roll_up_l3(tree)
        _roll_up_stock_counts(tree, self._raw_limit_pools(force=False))

        payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        payload["live"] = True
        payload["up"] = sum(1 for n in l1_nodes if (n.get("change_pct") or 0) > 0)
        payload["down"] = sum(1 for n in l1_nodes if (n.get("change_pct") or 0) < 0)
        return payload


def _flow_totals(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for key, inflow_key, outflow_key in (
        ("main_net", "inflow", "outflow"),
        ("main_net_5d", "inflow_5d", "outflow_5d"),
        ("main_net_10d", "inflow_10d", "outflow_10d"),
    ):
        inflow = sum(r[key] for r in rows if r.get(key) and r[key] > 0)
        outflow = sum(r[key] for r in rows if r.get(key) and r[key] < 0)
        out[inflow_key] = inflow or None
        out[outflow_key] = outflow or None
    return out


def _valuation_from_flow(flow: dict[str, Any]) -> tuple[float | None, float | None]:
    pe = flow.get("pe_ttm")
    pb = flow.get("pb")
    if pe is None and pb is None:
        return None, None
    return pe, pb


def _attach_stocks(
    tree: list[dict[str, Any]],
    stocks: list[dict[str, Any]],
    flows: dict[str, dict[str, Any]],
) -> int:
    """把成分股挂到三级节点下，按个股涨跌排序。返回挂上的只数。"""
    by_l3: dict[str, list[dict[str, Any]]] = {}
    for stock in stocks:
        l3 = str(stock.get("l3_code") or "").strip()
        if not l3:
            continue
        by_l3.setdefault(l3, []).append(stock)

    attached = 0

    def walk(nodes: list[dict[str, Any]]) -> None:
        nonlocal attached
        for node in nodes:
            if int(node.get("level") or 0) == 3:
                kids: list[dict[str, Any]] = []
                for stock in by_l3.get(node["code"], []):
                    code = str(stock.get("code") or "").strip()
                    flow = flows.get(code) or {}
                    live_chg = flow.get("change_pct")
                    live_px = flow.get("price")
                    pe_ttm, pb = _valuation_from_flow(flow)
                    if pe_ttm is None:
                        pe_ttm = parse_num(stock.get("pe_ttm")) or parse_num(
                            stock.get("pe")
                        )
                    if pb is None:
                        pb = parse_num(stock.get("pb"))
                    kids.append(
                        {
                            "code": code,
                            "name": str(stock.get("name") or "").strip(),
                            "level": 4,
                            "count": 0,
                            "l1_code": node.get("l1_code") or "",
                            "l1_name": node.get("l1_name") or "",
                            "l2_code": node.get("l2_code") or "",
                            "l2_name": node.get("l2_name") or "",
                            "parent_code": node["code"],
                            "parent_name": node.get("name") or "",
                            "change_pct": live_chg
                            if live_chg is not None
                            else parse_pct(stock.get("change_1d")),
                            "price": live_px
                            if live_px is not None
                            else parse_num(stock.get("price")),
                            "market_cap": parse_yi(stock.get("market_cap")),
                            "pe_ttm": pe_ttm,
                            "pb": pb,
                            "main_net": flow.get("main_net"),
                            "main_net_5d": flow.get("main_net_5d"),
                            "main_net_10d": flow.get("main_net_10d"),
                            "flow_count": 1
                            if any(flow.get(key) is not None for key in FLOW_NET_KEYS)
                            else 0,
                            "children": [],
                        }
                    )
                kids.sort(key=lambda row: _sort_num(row.get("change_pct")), reverse=True)
                node["children"] = kids
                attached += len(kids)
            else:
                walk(node.get("children") or [])

    walk(tree)
    return attached


def _roll_up_stock_counts(
    tree: list[dict[str, Any]], limit_pools: dict[str, set[str]]
) -> None:
    """成分股上涨 / 下跌家数 + 东财涨跌停池按行业汇总。"""
    limit_up_codes = set(limit_pools.get("limit_up") or ())
    limit_down_codes = set(limit_pools.get("limit_down") or ())

    def from_stocks(stocks: list[dict[str, Any]]) -> dict[str, int]:
        up = down = 0
        limit_up = limit_down = 0
        for stock in stocks:
            code = str(stock.get("code") or "").strip()
            chg = stock.get("change_pct")
            try:
                chg_n = float(chg) if chg is not None else None
            except (TypeError, ValueError):
                chg_n = None
            if chg_n is not None:
                if chg_n > 0:
                    up += 1
                elif chg_n < 0:
                    down += 1
            if code in limit_up_codes:
                limit_up += 1
            if code in limit_down_codes:
                limit_down += 1
        return {
            "up_count": up,
            "down_count": down,
            "limit_up_count": limit_up,
            "limit_down_count": limit_down,
        }

    def sum_children(nodes: list[dict[str, Any]]) -> dict[str, int]:
        up = down = limit_up = limit_down = 0
        for node in nodes:
            up += int(node.get("up_count") or 0)
            down += int(node.get("down_count") or 0)
            limit_up += int(node.get("limit_up_count") or 0)
            limit_down += int(node.get("limit_down_count") or 0)
        return {
            "up_count": up,
            "down_count": down,
            "limit_up_count": limit_up,
            "limit_down_count": limit_down,
        }

    def walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            children = node.get("children") or []
            for child in children:
                walk([child])
            level = int(node.get("level") or 0)
            if level == 3:
                stats = from_stocks(children)
            elif level in (1, 2):
                stats = sum_children(children)
            else:
                continue
            node.update(stats)

    walk(tree)


def _roll_up_l3(tree: list[dict[str, Any]]) -> None:
    """三级涨跌改用当前成分股盘口按市值加权，避免乐咕日更和实时对不上。"""
    for node in _nodes_at(tree, 3):
        weighted: list[tuple[float, float]] = []
        for child in node.get("children") or []:
            chg = child.get("change_pct")
            if chg is None:
                continue
            try:
                chg_n = float(chg)
            except (TypeError, ValueError):
                continue
            cap = child.get("market_cap")
            try:
                weight = float(cap) if cap is not None else 0.0
            except (TypeError, ValueError):
                weight = 0.0
            weighted.append((chg_n, weight))
        if not weighted:
            continue
        total_w = sum(w for _, w in weighted)
        if total_w > 0:
            node["change_pct"] = sum(c * w for c, w in weighted) / total_w
        else:
            node["change_pct"] = sum(c for c, _ in weighted) / len(weighted)
        node["sample_count"] = len(weighted)
        node["up_count"] = sum(1 for c, _ in weighted if c > 0)
        node["down_count"] = sum(1 for c, _ in weighted if c < 0)


def _nodes_at(tree: list[dict[str, Any]], level: int) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            if int(node.get("level") or 0) == level:
                found.append(node)
            walk(node.get("children") or [])

    walk(tree)
    return found


def _check_level(level: int) -> int:
    try:
        value = int(level)
    except (TypeError, ValueError) as exc:
        raise ValueError("level 须为 1 / 2 / 3") from exc
    if value not in (1, 2, 3):
        raise ValueError("level 须为 1 / 2 / 3")
    return value


def _sort_num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


service = MarketService()
