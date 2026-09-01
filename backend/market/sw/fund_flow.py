"""申万行业资金流向：个股资金流按成分股加总到一 / 二 / 三级。"""

from __future__ import annotations

from typing import Any

from .taxonomy import filter_level

PERIOD_FIELDS = {
    "today": "main_net",
    "5d": "main_net_5d",
    "10d": "main_net_10d",
}
_PERIOD_FIELDS = PERIOD_FIELDS
FLOW_NET_KEYS = tuple(PERIOD_FIELDS.values())

_SUM_KEYS = ("super_net", "big_net", "mid_net", "small_net")


def normalize_period(period: str) -> str:
    key = (period or "today").strip().lower()
    aliases = {
        "today": "today",
        "1": "today",
        "1d": "today",
        "日": "today",
        "今日": "today",
        "5": "5d",
        "5d": "5d",
        "5日": "5d",
        "10": "10d",
        "10d": "10d",
        "10日": "10d",
    }
    if key not in aliases:
        raise ValueError("period 须为 today | 5d | 10d")
    return aliases[key]


def _industry_of(
    stock: dict[str, Any], l3_meta: dict[str, dict[str, Any]]
) -> tuple[str, str, str]:
    l3 = str(stock.get("l3_code") or "").strip()
    meta = l3_meta.get(l3) or {}
    return (
        str(meta.get("l1_code") or ""),
        str(meta.get("l2_code") or ""),
        l3,
    )


def aggregate_stock_flows(
    nodes: list[dict[str, Any]],
    stocks: list[dict[str, Any]],
    flows: dict[str, dict[str, Any]],
    period: str = "today",
) -> dict[str, dict[str, Any]]:
    """把每只成分股的资金流加到它所属的一 / 二 / 三级行业。"""
    period = normalize_period(period)
    net_key = _PERIOD_FIELDS[period]
    l3_meta = {n["code"]: n for n in filter_level(nodes, 3)}

    buckets: dict[str, dict[str, Any]] = {}

    def bucket(code: str) -> dict[str, Any] | None:
        if not code:
            return None
        hit = buckets.get(code)
        if hit is None:
            hit = {
                "main_net": 0.0,
                "super_net": 0.0,
                "big_net": 0.0,
                "mid_net": 0.0,
                "small_net": 0.0,
                "flow_count": 0,
                "leader": "",
                "leader_net": None,
            }
            buckets[code] = hit
        return hit

    def add(code: str, flow: dict[str, Any]) -> None:
        dest = bucket(code)
        if dest is None:
            return
        net = flow.get(net_key)
        if net is None:
            return
        dest["main_net"] += float(net)
        dest["flow_count"] += 1
        if period == "today":
            for key in _SUM_KEYS:
                value = flow.get(key)
                if value is not None:
                    dest[key] += float(value)
        prev = dest.get("leader_net")
        if prev is None or float(net) > float(prev):
            dest["leader"] = str(flow.get("name") or "")
            dest["leader_net"] = float(net)

    for stock in stocks:
        code = str(stock.get("code") or "").strip()
        flow = flows.get(code)
        if not flow:
            continue
        l1, l2, l3 = _industry_of(stock, l3_meta)
        add(l1, flow)
        add(l2, flow)
        add(l3, flow)

    for dest in buckets.values():
        dest["period"] = period
        dest["source"] = "stock_sum"
        if dest["flow_count"] == 0:
            dest["main_net"] = None
        if period != "today":
            for key in _SUM_KEYS:
                dest[key] = None
    return buckets


def aggregate_stock_flows_all(
    nodes: list[dict[str, Any]],
    stocks: list[dict[str, Any]],
    flows: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """一次遍历，汇总今日 / 5 日 / 10 日主力净流入。"""
    l3_meta = {n["code"]: n for n in filter_level(nodes, 3)}
    buckets: dict[str, dict[str, Any]] = {}

    def bucket(code: str) -> dict[str, Any] | None:
        if not code:
            return None
        hit = buckets.get(code)
        if hit is None:
            hit = {
                "main_net": 0.0,
                "main_net_5d": 0.0,
                "main_net_10d": 0.0,
                "super_net": 0.0,
                "big_net": 0.0,
                "mid_net": 0.0,
                "small_net": 0.0,
                "flow_count": 0,
                "leader": "",
                "leader_net": None,
            }
            buckets[code] = hit
        return hit

    def add(code: str, flow: dict[str, Any]) -> None:
        dest = bucket(code)
        if dest is None:
            return
        touched = False
        for key in FLOW_NET_KEYS:
            net = flow.get(key)
            if net is None:
                continue
            dest[key] += float(net)
            touched = True
        if not touched:
            return
        dest["flow_count"] += 1
        for key in _SUM_KEYS:
            value = flow.get(key)
            if value is not None:
                dest[key] += float(value)
        today = flow.get("main_net")
        if today is not None:
            prev = dest.get("leader_net")
            if prev is None or float(today) > float(prev):
                dest["leader"] = str(flow.get("name") or "")
                dest["leader_net"] = float(today)

    for stock in stocks:
        code = str(stock.get("code") or "").strip()
        flow = flows.get(code)
        if not flow:
            continue
        l1, l2, l3 = _industry_of(stock, l3_meta)
        add(l1, flow)
        add(l2, flow)
        add(l3, flow)

    for dest in buckets.values():
        dest["source"] = "stock_sum"
        if dest["flow_count"] == 0:
            for key in FLOW_NET_KEYS:
                dest[key] = None
    return buckets


def flow_rows(
    nodes: list[dict[str, Any]],
    buckets: dict[str, dict[str, Any]],
    level: int,
    period: str,
) -> list[dict[str, Any]]:
    period = normalize_period(period)
    rows: list[dict[str, Any]] = []
    for node in filter_level(nodes, level):
        extra = buckets.get(node["code"]) or {}
        rows.append(
            {
                "code": node["code"],
                "name": node["name"],
                "level": node["level"],
                "l1_code": node.get("l1_code") or "",
                "l1_name": node.get("l1_name") or "",
                "l2_code": node.get("l2_code") or "",
                "l2_name": node.get("l2_name") or "",
                "parent_code": node.get("parent_code") or "",
                "parent_name": node.get("parent_name") or "",
                "period": period,
                "main_net": extra.get("main_net"),
                "super_net": extra.get("super_net"),
                "big_net": extra.get("big_net"),
                "mid_net": extra.get("mid_net"),
                "small_net": extra.get("small_net"),
                "flow_count": extra.get("flow_count") or 0,
                "leader": extra.get("leader") or "",
            }
        )
    rows.sort(key=lambda r: _sort_net(r.get("main_net")), reverse=True)
    return rows


def _sort_net(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")
