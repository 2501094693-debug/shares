"""形态方案：按内联 JSON（groups / scheme）扫描。

方案语义（分组 OR / 至少 M/N）见 ``analysis.shares.pattern.scheme``。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from analysis.decline.bars import parse_bars
from analysis.shares.common.candidates import collect_universe
from analysis.shares.common.config import KLINE_LIMIT
from analysis.shares.common.view import apply_view
from analysis.shares.pattern.scheme import (
    describe_scheme,
    evaluate_scheme,
    scheme_fingerprint,
    scheme_has_rules,
)
from company.line.fetcher import fetch_kline

logger = logging.getLogger(__name__)


def normalize_pattern_params(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """收成可缓存参数：仅支持内联 scheme 或顶层 groups。"""
    src = raw if isinstance(raw, dict) else {}

    if isinstance(src.get("scheme"), dict):
        return {"scheme": src["scheme"]}

    if isinstance(src.get("groups"), list) and src["groups"]:
        out: dict[str, Any] = {"groups": src["groups"]}
        for key in ("id", "name", "brief", "logic", "top"):
            if key in src and src[key] is not None:
                out[key] = src[key]
        return out

    raise ValueError("须提供 scheme 对象或非空 groups 数组")


def pattern_fingerprint(params: dict[str, Any]) -> str:
    scheme = load_pattern_scheme(params)
    return scheme_fingerprint(scheme)


def load_pattern_scheme(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """从内联 JSON 得到规范化方案。"""
    from analysis.shares.pattern.scheme import normalize_scheme

    p = normalize_pattern_params(params)
    if "scheme" in p and isinstance(p["scheme"], dict):
        return normalize_scheme(p["scheme"])
    return normalize_scheme(p)


def analyze_one_pattern(meta: dict[str, Any], scheme: dict[str, Any]) -> dict[str, Any] | None:
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

    hit = evaluate_scheme(bars, scheme)
    if hit is None:
        return None

    return {
        **base,
        "name": name,
        "as_of": hit["as_of"],
        "branches": hit["branches"],
        "hit_lower_shadow": hit["hit_lower_shadow"],
        "hit_quiet_body": hit["hit_quiet_body"],
        "quiet_count": hit["quiet_count"],
        "quiet_days": hit["quiet_days"],
        "latest": hit["latest"],
        "window_days": hit["window_days"],
        "days": hit.get("days") or [],
        "score": hit["score"],
        "matched_days": hit["matched_days"],
        "kline_source": pack.get("source"),
        "kline_count": len(bars),
    }


def assemble_pattern(
    pool: dict[str, Any],
    results: list[dict[str, Any]],
    scheme: dict[str, Any],
    *,
    analyzed: int | None = None,
) -> dict[str, Any]:
    items = [row for row in results if row and not row.get("error")]
    items.sort(
        key=lambda r: (
            -float(r.get("score") or 0),
            -int(r.get("quiet_count") or 0),
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
    summary = describe_scheme(scheme)
    name = scheme.get("name") or scheme.get("id") or "形态方案"
    scheme_id = str(scheme.get("id") or "")
    return {
        "updated_at": as_of,
        "fingerprint": f"pat_{scheme_fingerprint(scheme)}",
        "pattern": scheme_id,
        "scheme": {
            "id": scheme.get("id"),
            "name": scheme.get("name"),
            "brief": scheme.get("brief"),
            "logic": scheme.get("logic"),
            "groups": scheme.get("groups"),
        },
        "params": {"scheme_id": scheme_id} if scheme_id else {},
        "spec_summary": summary,
        "candidate_count": candidate_n,
        "analyzed_count": candidate_n if analyzed is None else analyzed,
        "result_count": len(items),
        "items": items,
        "errors": errors,
        "note": f"{name}（JSON 方案）；分组逻辑见 spec_summary",
    }


def screen_scheme(
    scheme: dict[str, Any],
    *,
    code: str = "",
    workers: int = 8,
    top: int | None = None,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """按已规范化方案全市场/单只扫描。"""
    if not scheme_has_rules(scheme):
        pool = collect_universe(code)
        payload = assemble_pattern(pool, [], scheme, analyzed=0)
        payload["note"] = "方案无有效条件日"
        return apply_view(payload, top)

    pool = collect_universe(code)
    candidates = list(pool.get("candidates") or [])

    if on_update:
        on_update(assemble_pattern(pool, [], scheme, analyzed=0))
    if not candidates:
        payload = assemble_pattern(pool, [], scheme, analyzed=0)
        payload["note"] = (pool.get("errors") or ["没有可分析的股票"])[0]
        return apply_view(payload, top)

    results: list[dict[str, Any]] = []
    max_workers = min(max(1, workers), max(1, len(candidates)))
    tick = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {executor.submit(analyze_one_pattern, meta, scheme): meta for meta in candidates}
        for fut in as_completed(futs):
            row = fut.result()
            tick += 1
            if row:
                results.append(row)
            if on_update and (tick <= 8 or tick % 40 == 0 or tick == len(candidates)):
                on_update(assemble_pattern(pool, results, scheme, analyzed=tick))

    payload = assemble_pattern(pool, results, scheme, analyzed=len(candidates))
    return apply_view(payload, top)
