"""全市场扫描：先走纸带，再叠加大盘、行业、相对强度。"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from analysis.livermore.config import ACTIONS, DEFAULT_LOOKBACK_DAYS, RS_DAYS
from analysis.livermore.engine import analyze_index, apply_context, tape_from_meta
from core.codes import normalize_code
from industry.service import service as industry_service

logger = logging.getLogger(__name__)

_ACTION_RANK = {name: idx for idx, name in enumerate(ACTIONS)}


def _as_meta(row: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code(str(row.get("code") or ""))
    return {
        "code": code,
        "name": row.get("name") or "",
        "l1_name": row.get("l1_name") or "",
        "l2_name": row.get("l2_name") or "",
        "l3_name": row.get("l3_name") or "",
        "l3_code": row.get("l3_code") or "",
    }


def collect_universe(code: str = "") -> dict[str, Any]:
    industry_service.stocks.ensure_populated()
    target = normalize_code(code)
    errors: list[str] = []
    if target:
        hit = industry_service.stocks.get_by_code(target)
        items = [_as_meta(hit)] if hit else [_as_meta({"code": target})]
        return {"count": len(items), "candidates": items, "errors": errors}

    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for row in industry_service.stocks.all_stocks():
        meta = _as_meta(row)
        if not meta["code"] or meta["code"] in seen:
            continue
        seen.add(meta["code"])
        items.append(meta)
    if not items:
        errors.append("股票索引为空，请先打开行业树或个股页让成分股索引建立")
    return {"count": len(items), "candidates": items, "errors": errors}


def peek_rotation(days: int = 20) -> dict[str, Any] | None:
    """只读轮动缓存，不触发重算。"""
    try:
        from analysis.persist import KIND_ROTATION, load_disk
        from analysis.rotation.config import CACHE_TAG
    except Exception:  # noqa: BLE001
        return None
    packed = load_disk(KIND_ROTATION, f"d{days}_{CACHE_TAG}")
    if not packed:
        return None
    _, data = packed
    return data if isinstance(data, dict) else None


def _leading_l3(rotation: dict[str, Any] | None) -> tuple[set[str], str]:
    if not rotation:
        return set(), "proxy"
    days = list(rotation.get("days") or [])
    if not days:
        return set(), "proxy"
    latest = days[0]
    codes: set[str] = set()
    for row in list(latest.get("first") or []) + list(latest.get("again") or []):
        code = str(row.get("code") or "").strip()
        if code:
            codes.add(code)
    return codes, "rotation"


def apply_view(data: dict[str, Any], top: int | None, kind: str = "all") -> dict[str, Any]:
    items = list(data.get("items") or [])
    if kind and kind != "all":
        items = [r for r in items if r.get("action") == kind]
    items.sort(
        key=lambda r: (
            _ACTION_RANK.get(str(r.get("action") or "cash"), 99),
            int((r.get("rs") or {}).get("rank") or 9999),
            -float(r.get("change_20d") or -999),
        )
    )
    if top is not None and top > 0:
        items = items[:top]
    out = []
    for idx, row in enumerate(items, start=1):
        item = dict(row)
        item["rank"] = idx
        out.append(item)
    counts = {name: 0 for name in ACTIONS}
    for row in data.get("items") or []:
        act = str(row.get("action") or "")
        if act in counts:
            counts[act] += 1
    return {
        **data,
        "items": out,
        "result_count": len(out),
        "kind": kind,
        "top": top,
        "action_counts": counts,
    }


def assemble(
    pool: dict[str, Any],
    tapes: list[dict[str, Any]],
    *,
    index_snap: dict[str, Any] | None,
    rotation: dict[str, Any] | None,
) -> dict[str, Any]:
    leading, tag = _leading_l3(rotation)
    by_l3: dict[str, list[float]] = defaultdict(list)
    for row in tapes:
        if row.get("error"):
            continue
        chg = row.get("change_20d")
        l3 = str(row.get("l3_code") or "")
        if chg is not None and l3:
            by_l3[l3].append(float(chg))

    results: list[dict[str, Any]] = []
    for row in tapes:
        if row.get("error"):
            results.append(row)
            continue
        l3 = str(row.get("l3_code") or "")
        if tag == "rotation":
            industry_leading = bool(l3 and l3 in leading)
            industry_tag = "again" if industry_leading else "untouched"
        elif l3 and by_l3.get(l3):
            peers = by_l3.get(l3) or []
            ordered = sorted(peers)
            med = ordered[len(ordered) // 2]
            index_chg = (index_snap or {}).get("change_20d")
            industry_leading = bool(index_chg is None or med >= float(index_chg))
            industry_tag = "proxy"
        else:
            industry_leading = True
            industry_tag = "unknown"
        results.append(
            apply_context(
                row,
                index_snap=index_snap,
                peer_changes=by_l3.get(l3) or [],
                industry_leading=industry_leading,
                industry_tag=industry_tag,
            )
        )

    ok_rows = [r for r in results if not r.get("error")]
    errors = list(pool.get("errors") or [])
    for row in results:
        if row.get("error"):
            errors.append(f"{row.get('code') or ''} {row['error']}".strip())
    errors = errors[:30]

    as_of = ""
    for row in ok_rows:
        as_of = str(row.get("as_of") or "")
        if as_of:
            break
    gate = (index_snap or {}).get("gate") or {}
    return {
        "lookback_days": RS_DAYS,
        "updated_at": as_of,
        "candidate_count": int(pool.get("count") or len(pool.get("candidates") or [])),
        "analyzed_count": len(tapes),
        "result_count": len(ok_rows),
        "items": ok_rows,
        "errors": errors,
        "gate": gate,
        "rotation_used": tag == "rotation",
        "note": (
            "由上而下：大盘六栏 → 领头行业 → 组内相对强度 → 关键点与量能 → 动作。"
            "probe/pyramid/hold 才是可交易集合；wait 是靠近关键点但未穿过。"
            + (" 行业来自轮动缓存。" if tag == "rotation" else " 未读到轮动缓存，行业用三级相对大盘代理。")
        ),
        "ruleset": "livermore-v1",
    }


def screen_livermore(
    days: int = DEFAULT_LOOKBACK_DAYS,
    *,
    code: str = "",
    workers: int = 8,
    top: int | None = None,
    kind: str = "all",
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    _ = days
    pool = collect_universe(code)
    candidates = list(pool.get("candidates") or [])
    fetch_raw = bool(code)
    try:
        index_snap = analyze_index()
    except Exception as exc:  # noqa: BLE001
        logger.info("index failed: %s", exc)
        index_snap = {"gate": {"allow": False, "column": "unclear", "reason": "gate.blocked"}}
    rotation = None if code else peek_rotation(20)

    if on_update:
        on_update(assemble(pool, [], index_snap=index_snap, rotation=rotation))
    if not candidates:
        payload = assemble(pool, [], index_snap=index_snap, rotation=rotation)
        payload["note"] = (pool.get("errors") or ["没有可分析的股票"])[0]
        return apply_view(payload, top, kind)

    tapes: list[dict[str, Any]] = []
    max_workers = min(max(1, workers), max(1, len(candidates)))
    tick = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {
            executor.submit(tape_from_meta, meta, fetch_raw=fetch_raw): meta
            for meta in candidates
        }
        for fut in as_completed(futs):
            row = fut.result()
            if not row:
                continue
            tapes.append(row)
            tick += 1
            if on_update and (tick <= 8 or tick % 20 == 0 or tick == len(candidates)):
                on_update(
                    assemble(pool, tapes, index_snap=index_snap, rotation=rotation)
                )

    payload = assemble(pool, tapes, index_snap=index_snap, rotation=rotation)
    return apply_view(payload, top, kind)
