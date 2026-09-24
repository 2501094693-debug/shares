"""组合方案：统一 AST 一次扫盘。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from analysis.decline.bars import parse_bars
from analysis.shares.common.ast import (
    describe_tree,
    evaluate_tree,
    load_compose_tree,
    normalize_compose_params,
    tree_fingerprint,
    tree_has_rules,
)
from analysis.shares.common.candidates import collect_universe
from analysis.shares.common.config import COMPARE_FIELD_META, KLINE_LIMIT
from analysis.shares.common.view import apply_view
from company.line.fetcher import fetch_kline

logger = logging.getLogger(__name__)


def analyze_one_compose(meta: dict[str, Any], tree: dict[str, Any]) -> dict[str, Any] | None:
    code = str(meta.get("code") or "").strip()
    if not code:
        return None

    base = {
        "code": code,
        "name": meta.get("name") or "",
        "l1_name": meta.get("l1_name") or "",
        "l2_name": meta.get("l2_name") or "",
        "l3_name": meta.get("l3_name") or "",
    }

    try:
        pack = fetch_kline(code, period="day", adjust="qfq", limit=KLINE_LIMIT)
    except Exception as exc:  # noqa: BLE001
        logger.info("kline failed %s: %s", code, exc)
        return {**base, "error": str(exc)}

    bars = parse_bars(list(pack.get("items") or []))
    name = str(meta.get("name") or pack.get("name") or "")
    if not bars:
        return {**base, "name": name, "error": "日 K 为空"}

    hit = evaluate_tree(bars, tree)
    if hit is None:
        return None

    return {
        **base,
        "name": name,
        "as_of": hit["as_of"],
        "nodes": hit["nodes"],
        "groups": hit.get("groups") or [],
        "branches": hit.get("branches") or [],
        "comps": hit.get("comps") or [],
        "days": hit.get("days") or [],
        "matched_nodes": hit.get("matched_nodes") or 0,
        "matched_comps": hit.get("matched_comps") or 0,
        "matched_days": hit.get("matched_days") or 0,
        "latest": hit.get("latest") or {},
        "score": hit["score"],
        "scheme_id": hit.get("scheme_id") or "",
        "scheme_name": hit.get("scheme_name") or "",
        "kline_source": pack.get("source"),
        "kline_count": len(bars),
    }


def assemble_compose(
    pool: dict[str, Any],
    results: list[dict[str, Any]],
    tree: dict[str, Any],
    *,
    analyzed: int | None = None,
) -> dict[str, Any]:
    items = [row for row in results if row and not row.get("error")]
    items.sort(
        key=lambda r: (
            -float(r.get("score") or 0),
            -int(r.get("matched_nodes") or 0),
            -int(r.get("matched_days") or 0),
            str(r.get("code") or ""),
        )
    )
    for idx, row in enumerate(items, start=1):
        row["rank"] = idx

    errors = list(pool.get("errors") or [])
    for row in results:
        if row and row.get("error"):
            code = row.get("code") or ""
            errors.append(f"{code} {row['error']}".strip())
    errors = errors[:30]

    as_of = ""
    for row in items:
        as_of = str(row.get("as_of") or "")
        if as_of:
            break

    candidate_n = int(pool.get("count") or len(pool.get("candidates") or []))
    summary = describe_tree(tree)
    name = tree.get("name") or tree.get("id") or "组合方案"
    scheme_id = str(tree.get("id") or "")
    return {
        "updated_at": as_of,
        "fingerprint": f"ast_{tree_fingerprint(tree)}",
        "pattern": scheme_id,
        "mode": "compose",
        "scheme": {
            "id": tree.get("id"),
            "name": tree.get("name"),
            "brief": tree.get("brief"),
            "logic": tree.get("logic"),
            "min_hits": tree.get("min_hits"),
            "nodes": tree.get("nodes"),
        },
        "params": {"scheme_id": scheme_id} if scheme_id else {},
        "spec_summary": summary,
        "candidate_count": candidate_n,
        "analyzed_count": candidate_n if analyzed is None else analyzed,
        "result_count": len(items),
        "items": items,
        "errors": errors,
        "note": f"{name}（统一 AST）；规则见 spec_summary",
        "compare_fields": COMPARE_FIELD_META,
    }


def screen_compose(
    tree: dict[str, Any],
    *,
    code: str = "",
    workers: int = 8,
    top: int | None = None,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """按统一树全市场 / 单只扫描。"""
    if not tree_has_rules(tree):
        pool = collect_universe(code)
        payload = assemble_compose(pool, [], tree, analyzed=0)
        payload["note"] = "方案无有效节点"
        return apply_view(payload, top)

    pool = collect_universe(code)
    candidates = list(pool.get("candidates") or [])

    if on_update:
        on_update(assemble_compose(pool, [], tree, analyzed=0))
    if not candidates:
        payload = assemble_compose(pool, [], tree, analyzed=0)
        payload["note"] = (pool.get("errors") or ["没有可分析的股票"])[0]
        return apply_view(payload, top)

    results: list[dict[str, Any]] = []
    max_workers = min(max(1, workers), max(1, len(candidates)))
    tick = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {executor.submit(analyze_one_compose, meta, tree): meta for meta in candidates}
        for fut in as_completed(futs):
            row = fut.result()
            tick += 1
            if row:
                results.append(row)
            if on_update and (tick <= 8 or tick % 40 == 0 or tick == len(candidates)):
                on_update(assemble_compose(pool, results, tree, analyzed=tick))

    payload = assemble_compose(pool, results, tree, analyzed=len(candidates))
    return apply_view(payload, top)


__all__ = [
    "analyze_one_compose",
    "assemble_compose",
    "load_compose_tree",
    "normalize_compose_params",
    "screen_compose",
    "tree_fingerprint",
    "tree_has_rules",
]
