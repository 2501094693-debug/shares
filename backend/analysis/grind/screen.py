"""阴跌 / 横盘：主筛选逻辑。无硬门槛，只按软评分排序。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from analysis.decline.bars import parse_bars, segment_stats, slice_segment
from analysis.grind.candidates import collect_universe
from analysis.grind.config import (
    CONSOLIDATION_DURATION_SCALE,
    DECLINE_DURATION_SCALE,
    DEFAULT_LOOKBACK_DAYS,
    KLINE_LIMIT,
    SCAN_MAX_DAYS,
)
from analysis.grind.phases import detect_phases, phase_segments
from analysis.grind.scoring import (
    classify,
    combine_scores,
    consolidation_quality_score,
    decline_quality_score,
    duration_score,
    pattern_score,
    persistence_score,
)
from company.line.fetcher import fetch_kline

logger = logging.getLogger(__name__)


def _window_segment(bars: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    if not bars or days <= 0:
        return []
    start = max(0, len(bars) - days)
    return slice_segment(bars, start, len(bars) - 1)


def analyze_one(meta: dict[str, Any], lookback_days: int) -> dict[str, Any] | None:
    code = str(meta.get("code") or "").strip()
    if not code:
        return None

    base = {
        "code": code,
        "name": meta.get("name") or "",
        "l1_name": meta.get("l1_name") or "",
        "l2_name": meta.get("l2_name") or "",
        "l3_name": meta.get("l3_name") or "",
        "kind": "none",
        "kind_label": "不明显",
    }

    try:
        pack = fetch_kline(code, period="day", adjust="qfq", limit=KLINE_LIMIT)
    except Exception as exc:  # noqa: BLE001
        logger.info("kline failed %s: %s", code, exc)
        return {
            **base,
            "error": str(exc),
            "scores": {"total": 0.0, "decline": 0.0, "consolidation": 0.0},
        }

    bars = parse_bars(list(pack.get("items") or []))
    name = str(meta.get("name") or pack.get("name") or "")
    if len(bars) < 8:
        return {
            **base,
            "name": name,
            "error": "日 K 不足",
            "scores": {"total": 0.0, "decline": 0.0, "consolidation": 0.0},
        }

    phases = detect_phases(bars, max_days=max(lookback_days, SCAN_MAX_DAYS))
    cons_seg, dec_seg = phase_segments(bars, phases)
    window = _window_segment(bars, lookback_days)
    cons_scores = list((phases.get("consolidation") or {}).get("daily_scores") or [])
    dec_scores = list((phases.get("decline") or {}).get("daily_scores") or [])

    dec_stats = segment_stats(dec_seg)
    cons_stats = segment_stats(cons_seg)
    win_stats = segment_stats(window)

    if dec_stats.get("total_pct") is not None and dec_stats["total_pct"] > -2:
        dec_seg, dec_scores = [], []
        dec_stats = segment_stats(dec_seg)
        phases["decline"] = {"start": -1, "end": -1, "daily_scores": []}
    if cons_stats.get("range_pct") is not None and cons_stats["range_pct"] > 26:
        cons_seg, cons_scores = [], []
        cons_stats = segment_stats(cons_seg)
        phases["consolidation"] = {"start": -1, "end": -1, "daily_scores": []}

    dec_days = int(dec_stats["days"] or 0)
    cons_days = int(cons_stats["days"] or 0)
    win_pct = win_stats.get("total_pct")
    win_range = win_stats.get("range_pct")
    win_days = int(win_stats.get("days") or 0)
    if win_pct is not None and win_pct <= -6 and win_days > 0:
        span = float(win_range or 40.0)
        clean = max(0.0, min(1.0, (48.0 - max(0.0, span - 12.0)) / 48.0))
        extra = int(win_days * (0.30 + 0.70 * clean) * min(1.0, abs(win_pct) / 12.0))
        dec_days = max(dec_days, extra)
    if (
        win_range is not None
        and win_pct is not None
        and win_days > 0
        and win_range <= 22
        and abs(win_pct) <= 10
    ):
        extra = int(
            win_days
            * max(0.0, 1.0 - max(0.0, win_range - 8.0) / 22.0)
            * max(0.0, 1.0 - abs(win_pct) / 12.0)
        )
        cons_days = max(cons_days, extra)

    dec_duration = duration_score(dec_days, DECLINE_DURATION_SCALE)
    cons_duration = duration_score(cons_days, CONSOLIDATION_DURATION_SCALE)
    dec_quality = decline_quality_score(dec_seg, dec_scores, window, bars)
    cons_quality = consolidation_quality_score(cons_seg, cons_scores, window)
    persist_dec = persistence_score(bars, "decline")
    persist_cons = persistence_score(bars, "consolidation")

    decline = pattern_score(dec_duration, dec_quality, persist_dec)
    consolidation = pattern_score(cons_duration, cons_quality, persist_cons)
    kind, kind_label = classify(decline, consolidation)
    persist = persist_dec if kind == "decline" else persist_cons if kind == "consolidation" else max(
        persist_dec, persist_cons
    )
    total = combine_scores(decline=decline, consolidation=consolidation, name=name)

    as_of = bars[-1]["date"] if bars else ""
    return {
        **base,
        "name": name,
        "as_of": as_of,
        "kind": kind,
        "kind_label": kind_label,
        "detected": {
            "decline": dec_stats,
            "consolidation": cons_stats,
            "window": win_stats,
        },
        "scores": {
            "decline": decline,
            "consolidation": consolidation,
            "decline_duration": dec_duration,
            "decline_quality": dec_quality,
            "consolidation_duration": cons_duration,
            "consolidation_quality": cons_quality,
            "persistence": persist,
            "total": total,
        },
        "kline_source": pack.get("source"),
        "kline_count": len(bars),
    }


def apply_view(data: dict[str, Any], top: int | None, kind: str = "all") -> dict[str, Any]:
    """按形态过滤并截取前 N；不改后台缓存原表。"""
    items = list(data.get("items") or [])
    key = "total"
    if kind == "decline":
        items = [r for r in items if r.get("kind") in ("decline", "mixed")]
        key = "decline"
    elif kind == "consolidation":
        items = [r for r in items if r.get("kind") in ("consolidation", "mixed")]
        key = "consolidation"

    items.sort(
        key=lambda r: float((r.get("scores") or {}).get(key) or 0),
        reverse=True,
    )
    if top is not None and top > 0:
        items = items[:top]
    out = []
    for idx, row in enumerate(items, start=1):
        item = dict(row)
        item.pop("chart", None)
        item["rank"] = idx
        out.append(item)
    return {
        **data,
        "items": out,
        "result_count": len(out),
        "kind": kind,
        "top": top,
    }


def assemble(
    pool: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    lookback_days: int,
) -> dict[str, Any]:
    items = [row for row in results if row and not row.get("error")]
    items.sort(
        key=lambda r: float((r.get("scores") or {}).get("total") or 0),
        reverse=True,
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

    return {
        "lookback_days": lookback_days,
        "updated_at": as_of,
        "candidate_count": int(pool.get("count") or len(pool.get("candidates") or [])),
        "analyzed_count": len(results),
        "result_count": len(items),
        "items": items,
        "errors": errors,
        "note": "无硬门槛：从最近一根向前扫阴跌/横盘，窗口质量作软评分，按总分排序",
    }


def screen_grind(
    days: int = DEFAULT_LOOKBACK_DAYS,
    *,
    code: str = "",
    workers: int = 8,
    top: int | None = None,
    kind: str = "all",
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """全市场或单只：给仍在阴跌 / 横盘的股票打分。"""
    pool = collect_universe(code)
    candidates = list(pool.get("candidates") or [])
    if on_update:
        on_update(assemble(pool, [], lookback_days=days))
    if not candidates:
        payload = assemble(pool, [], lookback_days=days)
        payload["note"] = (pool.get("errors") or ["没有可分析的股票"])[0]
        return apply_view(payload, top, kind)

    results: list[dict[str, Any]] = []
    max_workers = min(max(1, workers), max(1, len(candidates)))
    tick = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {executor.submit(analyze_one, meta, days): meta for meta in candidates}
        for fut in as_completed(futs):
            row = fut.result()
            if not row:
                continue
            results.append(row)
            tick += 1
            if on_update and (tick <= 8 or tick % 20 == 0 or tick == len(candidates)):
                on_update(assemble(pool, results, lookback_days=days))

    payload = assemble(pool, results, lookback_days=days)
    return apply_view(payload, top, kind)
