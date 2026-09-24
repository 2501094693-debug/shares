"""统一方案 AST：把筛选 / 形态 / 对比收成同一棵谓词树。

叶子：
- ``day``   绝对日或 offset 日区间条件
- ``comp``  跨日 pair / trend

组合节点：
- ``group`` 子节点用 and / or / not / min_hits / 逐段 join 组合

旧三种模式可通过 ``from_screen`` / ``from_pattern`` / ``from_compare`` 转译。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from analysis.shares.common.conditions import (
    LOGIC_AND,
    LOGIC_NOT,
    LOGIC_OR,
    apply_day_not,
    combine_bools,
    describe_spec,
    has_day_joins,
    normalize_day_specs,
    normalize_join,
    normalize_logic,
)
from analysis.shares.common.days import list_trade_days
from analysis.shares.common.metrics import compact_metrics, measure_bar
from analysis.shares.compare.core import describe_comp, evaluate_comp, normalize_comp
from analysis.shares.pattern.scheme import match_day, normalize_day_raw
from core.fmt import to_float

KIND_DAY = "day"
KIND_COMP = "comp"
KIND_GROUP = "group"
KIND_CHOICES = (KIND_DAY, KIND_COMP, KIND_GROUP)


def _trade_dates(n: int = 22) -> list[str]:
    return [str(x["date"]) for x in (list_trade_days(n).get("items") or [])]


def _as_bool(raw: Any, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    return default


def _index_by_date(bars: list[dict[str, Any]]) -> dict[str, int]:
    return {str(bar.get("date") or ""): idx for idx, bar in enumerate(bars) if bar.get("date")}


def _eval_day_leaf(
    bars: list[dict[str, Any]],
    by_date: dict[str, int],
    spec: dict[str, Any],
) -> tuple[bool | None, dict[str, Any] | None]:
    """评估 day 叶子。``ok is None`` 表示缺 K。"""
    date = str(spec.get("date") or "")
    idx = by_date.get(date)
    if idx is None:
        return None, None
    prev_close = bars[idx - 1].get("close") if idx > 0 else None
    metrics = measure_bar(bars[idx], prev_close=prev_close, bars=bars, idx=idx)
    raw = match_day(metrics, spec)
    ok = apply_day_not(raw, spec)
    if metrics is None:
        return ok, None
    extra = " 且下影≥实体" if spec.get("lower_ge_body") else ""
    hit = {
        "kind": KIND_DAY,
        "date": date,
        "spec": {k: v for k, v in spec.items() if k != "date"},
        "spec_text": describe_spec(spec) + extra,
        "metrics": compact_metrics(metrics),
        "negated": bool(spec.get("not")),
        "raw_match": bool(raw),
    }
    return ok, hit


def _normalize_day_node(
    raw: dict[str, Any],
    *,
    trade_dates: list[str] | None,
    index: int = 0,
) -> dict[str, Any] | None:
    spec = normalize_day_raw(raw, trade_dates=trade_dates)
    if spec is None:
        return None
    nid = str(raw.get("id") or raw.get("name") or f"d{index}").strip() or f"d{index}"
    label = str(raw.get("label") or raw.get("name") or "").strip()
    node: dict[str, Any] = {
        "kind": KIND_DAY,
        "id": nid,
        "label": label or spec["date"],
        "date": spec["date"],
        **{k: v for k, v in spec.items() if k != "date"},
    }
    if raw.get("join") is not None:
        node["join"] = normalize_join(raw.get("join"))
    elif spec.get("join") is not None:
        node["join"] = normalize_join(spec.get("join"))
    return node


def _normalize_comp_node(raw: dict[str, Any], *, index: int = 0) -> dict[str, Any] | None:
    comp = normalize_comp(raw, index=index)
    if comp is None:
        return None
    # normalize_comp 的 kind 是 pair/trend；AST 叶子 kind 固定为 comp
    node = {
        "kind": KIND_COMP,
        **{k: v for k, v in comp.items() if k != "kind"},
        "comp_kind": comp.get("kind"),
    }
    if raw.get("join") is not None:
        node["join"] = normalize_join(raw.get("join"))
    return node


def _normalize_node(
    raw: Any,
    *,
    trade_dates: list[str] | None,
    index: int = 0,
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    kind = str(raw.get("kind") or raw.get("type") or "").strip().lower()
    if kind in ("pair", "trend"):
        # 对比子类型，升为 AST 叶子 comp
        raw = {**raw, "comp_kind": kind}
        kind = KIND_COMP
    if not kind:
        if raw.get("field") or raw.get("comps"):
            kind = KIND_COMP
        elif "nodes" in raw or "groups" in raw or "min_hits" in raw:
            kind = KIND_GROUP
        else:
            kind = KIND_DAY

    if kind == KIND_DAY:
        return _normalize_day_node(raw, trade_dates=trade_dates, index=index)
    if kind == KIND_COMP:
        return _normalize_comp_node(raw, index=index)
    if kind != KIND_GROUP:
        return None

    children_raw = raw.get("nodes")
    if not isinstance(children_raw, list):
        # 兼容形态 group：days → day 叶子；或内嵌 comps
        children_raw = []
        for day in raw.get("days") or []:
            if isinstance(day, dict):
                children_raw.append({**day, "kind": KIND_DAY})
        for comp in raw.get("comps") or []:
            if isinstance(comp, dict):
                children_raw.append({**comp, "kind": KIND_COMP})
        nested = raw.get("groups")
        if isinstance(nested, list):
            for g in nested:
                if isinstance(g, dict):
                    children_raw.append({**g, "kind": KIND_GROUP})

    children: list[dict[str, Any]] = []
    for i, item in enumerate(children_raw):
        child = _normalize_node(item, trade_dates=trade_dates, index=i)
        if child:
            children.append(child)
    if not children:
        return None

    min_hits_raw = to_float(raw.get("min_hits") if "min_hits" in raw else raw.get("quiet_min_days"))
    min_hits = int(min_hits_raw) if min_hits_raw is not None else None
    if min_hits is not None:
        min_hits = max(1, min(len(children), min_hits))

    gid = str(raw.get("id") or raw.get("name") or f"g{index}").strip() or f"g{index}"
    label = str(raw.get("label") or raw.get("name") or gid).strip()
    node: dict[str, Any] = {
        "kind": KIND_GROUP,
        "id": gid,
        "label": label,
        "logic": normalize_logic(raw.get("logic")),
        "min_hits": min_hits,
        "nodes": children,
    }
    if has_day_joins(children) or any(c.get("join") is not None for c in children[1:]):
        # 子节点带 join → 组内改为链模式（忽略统一 logic / min_hits）
        node["logic"] = "chain"
        node["min_hits"] = None
    if raw.get("join") is not None:
        node["join"] = normalize_join(raw.get("join"))
    return node


def _needs_offsets(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    if to_float(raw.get("offset")) is not None and not raw.get("date"):
        return True
    for key in ("nodes", "days", "comps", "groups"):
        items = raw.get(key)
        if isinstance(items, list) and any(_needs_offsets(x) for x in items):
            return True
    for key in ("left", "right"):
        if to_float(raw.get(key)) is not None:
            return True
    offs = raw.get("offsets")
    if isinstance(offs, list) and offs:
        return True
    return False


def normalize_tree(
    raw: dict[str, Any] | list[dict[str, Any]] | None,
    *,
    trade_dates: list[str] | None = None,
    logic: Any = None,
) -> dict[str, Any]:
    """收成可缓存 / 可执行的标准树。"""
    if isinstance(raw, list):
        raw = {"nodes": raw, "logic": logic}
    src = raw if isinstance(raw, dict) else {}

    dates = trade_dates
    if dates is None and _needs_offsets(src):
        dates = _trade_dates(22)

    # 顶层已是 nodes，或由旧字段拼装
    nodes_raw = src.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        nodes_raw = []
        # 兼容：groups（形态）
        groups = src.get("groups")
        if isinstance(groups, list) and groups:
            for g in groups:
                if isinstance(g, dict):
                    nodes_raw.append({**g, "kind": KIND_GROUP})
        # 兼容：comps（对比）
        comps = src.get("comps") or src.get("compares") or src.get("comparisons")
        if isinstance(comps, list):
            for c in comps:
                if isinstance(c, dict):
                    nodes_raw.append({**c, "kind": KIND_COMP})
        # 兼容：扁平 days
        days = src.get("days")
        if isinstance(days, list) and not groups:
            for d in days:
                if isinstance(d, dict):
                    nodes_raw.append({**d, "kind": KIND_DAY})

    nodes: list[dict[str, Any]] = []
    for i, item in enumerate(nodes_raw):
        node = _normalize_node(item, trade_dates=dates, index=i)
        if node:
            nodes.append(node)

    top_logic = normalize_logic(logic if logic is not None else src.get("logic"))
    min_hits_raw = to_float(src.get("min_hits"))
    min_hits = int(min_hits_raw) if min_hits_raw is not None else None
    if min_hits is not None and nodes:
        min_hits = max(1, min(len(nodes), min_hits))

    # 顶层若节点带 join → chain
    if nodes and any(n.get("join") is not None for n in nodes[1:]):
        top_logic = "chain"
        min_hits = None
    # 多 group 且未写 logic 时，沿用形态默认 OR
    elif (
        len(nodes) > 1
        and logic is None
        and src.get("logic") is None
        and all(n.get("kind") == KIND_GROUP for n in nodes)
        and not src.get("comps")
        and "nodes" not in src
    ):
        top_logic = LOGIC_OR

    return {
        "id": str(src.get("id") or "").strip(),
        "name": str(src.get("name") or "").strip(),
        "brief": str(src.get("brief") or "").strip(),
        "logic": top_logic,
        "min_hits": min_hits,
        "nodes": nodes,
        "trade_dates": list(dates or []),
    }


def tree_has_rules(tree: dict[str, Any]) -> bool:
    return bool(tree.get("nodes"))


def tree_fingerprint(tree: dict[str, Any]) -> str:
    payload = {
        "logic": tree.get("logic"),
        "min_hits": tree.get("min_hits"),
        "nodes": tree.get("nodes") or [],
        "id": tree.get("id"),
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def describe_node(node: dict[str, Any]) -> str:
    kind = node.get("kind")
    label = node.get("label") or node.get("id") or ""
    if kind == KIND_DAY:
        extra = " 且下影≥实体" if node.get("lower_ge_body") else ""
        return f"[日 {node.get('date')}] {describe_spec(node)}{extra}"
    if kind == KIND_COMP:
        # describe_comp 认 pair/trend
        payload = {**node, "kind": node.get("comp_kind") or "pair"}
        return f"[对比 {label}] {describe_comp(payload)}"
    # group
    children = node.get("nodes") or []
    min_hits = node.get("min_hits")
    if min_hits is not None:
        head = f"[组 {label}] 至少{min_hits}/{len(children)}"
    else:
        logic = node.get("logic") or LOGIC_AND
        tag = str(logic).upper()
        head = f"[组 {label}] {tag}"
    detail = "; ".join(describe_node(c) for c in children)
    return f"{head}: {detail}"


def describe_tree(tree: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if tree.get("name") or tree.get("id"):
        lines.append(str(tree.get("name") or tree.get("id")))
    if tree.get("brief"):
        lines.append(str(tree["brief"]))
    nodes = tree.get("nodes") or []
    logic = tree.get("logic") or LOGIC_AND
    min_hits = tree.get("min_hits")
    if min_hits is not None:
        lines.append(f"顶层至少命中 {min_hits}/{len(nodes)}")
    elif len(nodes) > 1:
        lines.append(f"顶层组合: {str(logic).upper()}")
    for node in nodes:
        lines.append(describe_node(node))
    return lines or ["(空方案)"]


# ---------------------------------------------------------------------------
# 旧模式 → 树
# ---------------------------------------------------------------------------


def from_screen(
    day_specs: list[dict[str, Any]] | None,
    logic: Any = LOGIC_AND,
) -> dict[str, Any]:
    """筛选 days + logic/join → 树。"""
    specs = normalize_day_specs(day_specs)
    nodes = [{"kind": KIND_DAY, **spec} for spec in specs]
    return normalize_tree({"logic": logic, "nodes": nodes, "id": "screen", "name": "筛选"})


def from_pattern(scheme: dict[str, Any] | None) -> dict[str, Any]:
    """形态规范化方案 → 树（保留 groups 为 group 节点）。"""
    src = scheme if isinstance(scheme, dict) else {}
    groups = src.get("groups") or []
    nodes = []
    for g in groups:
        if not isinstance(g, dict):
            continue
        nodes.append(
            {
                "kind": KIND_GROUP,
                "id": g.get("id"),
                "label": g.get("label"),
                "logic": g.get("logic"),
                "min_hits": g.get("min_hits"),
                "nodes": [{"kind": KIND_DAY, **d} for d in (g.get("days") or [])],
            }
        )
    return normalize_tree(
        {
            "id": src.get("id") or "pattern",
            "name": src.get("name") or "形态",
            "brief": src.get("brief"),
            "logic": src.get("logic"),
            "nodes": nodes,
        }
    )


def from_compare(scheme: dict[str, Any] | None) -> dict[str, Any]:
    """对比规范化方案 → 树。"""
    src = scheme if isinstance(scheme, dict) else {}
    nodes: list[dict[str, Any]] = []
    for c in src.get("comps") or []:
        if isinstance(c, dict):
            nodes.append({**c, "kind": KIND_COMP})
    for d in src.get("days") or []:
        if isinstance(d, dict):
            nodes.append({**d, "kind": KIND_DAY})
    return normalize_tree(
        {
            "id": src.get("id") or "compare",
            "name": src.get("name") or "对比",
            "brief": src.get("brief"),
            "logic": src.get("logic"),
            "nodes": nodes,
        }
    )


def normalize_compose_params(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """收成可缓存参数：scheme / nodes / 或旧模式拼装。"""
    src = raw if isinstance(raw, dict) else {}

    if isinstance(src.get("scheme"), dict):
        return {"scheme": src["scheme"]}

    if isinstance(src.get("nodes"), list) and src["nodes"]:
        out: dict[str, Any] = {"nodes": src["nodes"]}
        for key in ("id", "name", "brief", "logic", "min_hits", "top"):
            if key in src and src[key] is not None:
                out[key] = src[key]
        return out

    # 允许把三种旧草稿直接 AND 进组合
    parts: list[dict[str, Any]] = []
    screen_days = src.get("screen") or src.get("screen_days")
    if isinstance(screen_days, dict) and isinstance(screen_days.get("days"), list):
        parts.append(
            {
                "kind": KIND_GROUP,
                "id": "screen",
                "label": "筛选",
                "logic": screen_days.get("logic") or LOGIC_AND,
                "nodes": [{"kind": KIND_DAY, **d} for d in screen_days["days"] if isinstance(d, dict)],
            }
        )
    elif isinstance(screen_days, list) and screen_days:
        parts.append(
            {
                "kind": KIND_GROUP,
                "id": "screen",
                "label": "筛选",
                "logic": src.get("screen_logic") or LOGIC_AND,
                "nodes": [{"kind": KIND_DAY, **d} for d in screen_days if isinstance(d, dict)],
            }
        )

    pattern = src.get("pattern") or src.get("pattern_scheme")
    if isinstance(pattern, dict):
        parts.append({**pattern, "kind": KIND_GROUP, "id": pattern.get("id") or "pattern", "label": pattern.get("label") or pattern.get("name") or "形态"})

    compare = src.get("compare") or src.get("compare_scheme")
    if isinstance(compare, dict):
        # 对比整块收成一组：comps + days
        child_nodes: list[dict[str, Any]] = []
        for c in compare.get("comps") or []:
            if isinstance(c, dict):
                child_nodes.append({**c, "kind": KIND_COMP})
        for d in compare.get("days") or []:
            if isinstance(d, dict):
                child_nodes.append({**d, "kind": KIND_DAY})
        if child_nodes:
            parts.append(
                {
                    "kind": KIND_GROUP,
                    "id": compare.get("id") or "compare",
                    "label": compare.get("name") or "对比",
                    "logic": compare.get("logic") or LOGIC_AND,
                    "nodes": child_nodes,
                }
            )

    if parts:
        out = {
            "id": str(src.get("id") or "compose").strip(),
            "name": str(src.get("name") or "组合方案").strip(),
            "brief": str(src.get("brief") or "").strip(),
            "logic": normalize_logic(src.get("logic") or LOGIC_AND),
            "nodes": parts,
        }
        return out

    raise ValueError(
        "须提供 scheme / nodes，或 screen + pattern + compare 中至少一块非空草稿"
    )


def load_compose_tree(params: dict[str, Any] | None = None) -> dict[str, Any]:
    p = normalize_compose_params(params)
    if "scheme" in p and isinstance(p["scheme"], dict):
        return normalize_tree(p["scheme"])
    return normalize_tree(p)


# ---------------------------------------------------------------------------
# 评估
# ---------------------------------------------------------------------------


def _combine_child_flags(
    flags: list[bool | None],
    nodes: list[dict[str, Any]],
    *,
    logic: Any,
    min_hits: int | None,
) -> bool:
    """组合子节点布尔结果。缺 K（None）在 AND/NOT/chain 视为 False；OR / min_hits 跳过。"""
    if min_hits is not None:
        oks = [f for f in flags if f is True]
        return len(oks) >= int(min_hits)

    mode = normalize_logic(logic) if logic != "chain" else "chain"
    if mode == "chain" or (nodes and any(n.get("join") is not None for n in nodes[1:])):
        if not flags:
            return False
        bits = [False if f is None else bool(f) for f in flags]
        joins = [normalize_join(n.get("join")) for n in nodes[1:]]
        return combine_bools(bits, joins=joins)

    if mode == LOGIC_OR:
        known = [bool(f) for f in flags if f is not None]
        return any(known)
    if mode == LOGIC_NOT:
        if any(f is None for f in flags):
            return False
        return bool(flags) and not any(flags)
    # AND
    if not flags:
        return False
    if any(f is None for f in flags):
        return False
    return all(flags)


def _eval_node(
    bars: list[dict[str, Any]],
    trade_dates: list[str],
    node: dict[str, Any],
    *,
    by_date: dict[str, int],
    cache: dict[int, dict[str, Any] | None],
) -> tuple[bool | None, dict[str, Any] | None]:
    kind = node.get("kind")
    if kind == KIND_DAY:
        return _eval_day_leaf(bars, by_date, node)

    if kind == KIND_COMP:
        payload = {**node, "kind": node.get("comp_kind") or "pair"}
        ok, hit = evaluate_comp(bars, trade_dates, payload, cache)
        if not ok:
            return False, None
        if hit is not None:
            hit = {
                **hit,
                "kind": KIND_COMP,
                "comp_kind": hit.get("kind"),
            }
        return True, hit

    # group
    children = list(node.get("nodes") or [])
    child_flags: list[bool | None] = []
    child_hits: list[dict[str, Any]] = []
    for child in children:
        ok, hit = _eval_node(bars, trade_dates, child, by_date=by_date, cache=cache)
        child_flags.append(ok)
        if ok and hit is not None:
            child_hits.append(hit)

    matched = _combine_child_flags(
        child_flags,
        children,
        logic=node.get("logic"),
        min_hits=node.get("min_hits"),
    )
    if not matched:
        return False, None

    hit_count = sum(1 for f in child_flags if f is True)
    return True, {
        "kind": KIND_GROUP,
        "id": node.get("id"),
        "label": node.get("label"),
        "min_hits": node.get("min_hits"),
        "logic": node.get("logic"),
        "hit_count": hit_count,
        "nodes": child_hits,
        # 兼容形态结果字段
        "days": [h for h in child_hits if h.get("kind") == KIND_DAY],
    }


def evaluate_tree(
    bars: list[dict[str, Any]],
    tree: dict[str, Any],
    *,
    trade_dates: list[str] | None = None,
) -> dict[str, Any] | None:
    """按统一树匹配；未命中返回 None。"""
    nodes = list(tree.get("nodes") or [])
    if not bars or not nodes:
        return None

    dates = trade_dates or list(tree.get("trade_dates") or [])
    if not dates:
        dates = _trade_dates(22)
    if not dates:
        return None

    by_date = _index_by_date(bars)
    cache: dict[int, dict[str, Any] | None] = {}

    flags: list[bool | None] = []
    hits: list[dict[str, Any]] = []
    for node in nodes:
        ok, hit = _eval_node(bars, dates, node, by_date=by_date, cache=cache)
        flags.append(ok)
        if ok and hit is not None:
            hits.append(hit)

    matched = _combine_child_flags(
        flags,
        nodes,
        logic=tree.get("logic"),
        min_hits=tree.get("min_hits"),
    )
    if not matched:
        return None

    # 展平命中细节
    day_hits: list[dict[str, Any]] = []
    comp_hits: list[dict[str, Any]] = []
    group_hits: list[dict[str, Any]] = []
    branch_ids: list[str] = []

    def _collect(hit: dict[str, Any]) -> None:
        kind = hit.get("kind")
        if kind == KIND_DAY:
            day_hits.append(hit)
        elif kind == KIND_COMP:
            comp_hits.append(hit)
        elif kind == KIND_GROUP:
            group_hits.append(hit)
            gid = str(hit.get("id") or "")
            if gid:
                branch_ids.append(gid)
            for child in hit.get("nodes") or []:
                _collect(child)

    for hit in hits:
        _collect(hit)

    # 去重日命中
    seen_dates: set[str] = set()
    uniq_days: list[dict[str, Any]] = []
    for d in sorted(day_hits, key=lambda x: str(x.get("date") or "")):
        date = str(d.get("date") or "")
        if date and date not in seen_dates:
            seen_dates.add(date)
            uniq_days.append(d)

    latest_metrics = None
    as_of = ""
    if bars:
        last = bars[-1]
        idx = len(bars) - 1
        prev_close = bars[idx - 1].get("close") if idx > 0 else None
        latest_metrics = measure_bar(last, prev_close=prev_close, bars=bars, idx=idx)
        as_of = str((latest_metrics or {}).get("date") or last.get("date") or "")

    score = float(len(hits))
    for hit in comp_hits:
        ck = hit.get("comp_kind") or hit.get("kind")
        if ck == "trend" or hit.get("pair_hits") is not None:
            need = max(1, int(hit.get("pair_need") or 1))
            score += 0.1 * (int(hit.get("pair_hits") or 0) / need)
        ratio = to_float(hit.get("ratio"))
        if ratio is not None and 0 < ratio < 1:
            score += 0.05 * (1.0 - ratio)
    for g in group_hits:
        if g.get("min_hits") is not None:
            score += 0.05 * min(5, int(g.get("hit_count") or 0))
    lower_r = to_float((latest_metrics or {}).get("lower_ratio")) or 0.0
    score += min(0.5, lower_r) * 0.4

    return {
        "as_of": as_of,
        "nodes": hits,
        "groups": group_hits,
        "branches": branch_ids,
        "comps": comp_hits,
        "days": uniq_days,
        "matched_nodes": len(hits),
        "matched_comps": len(comp_hits),
        "matched_days": len(uniq_days),
        "latest": compact_metrics(latest_metrics) if latest_metrics else {},
        "score": round(score, 4),
        "logic": tree.get("logic"),
        "scheme_id": tree.get("id") or "",
        "scheme_name": tree.get("name") or "",
    }
