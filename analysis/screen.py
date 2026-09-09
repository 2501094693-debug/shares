"""阴跌→横盘→涨停：主筛选逻辑。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from analysis._path import ensure_backend_path

ensure_backend_path()

from company.line.fetcher import fetch_kline

from analysis.bars import find_bar_index, parse_bars, segment_stats
from analysis.candidates import collect_recent_limit_up
from analysis.config import (
    CONSOLIDATION_DURATION_SCALE,
    DECLINE_DURATION_SCALE,
    DEFAULT_LOOKBACK_DAYS,
    KLINE_LIMIT,
    WEIGHTS,
)
from analysis.phases import detect_phases, phase_segments
from analysis.scoring import (
    breakout_score,
    consolidation_quality_score,
    decline_quality_score,
    duration_score,
    structure_score,
    total_score,
)

logger = logging.getLogger(__name__)


def _analyze_one(meta: dict[str, Any], lookback_days: int) -> dict[str, Any] | None:
    code = str(meta.get("code") or "").strip()
    if not code:
        return None

    try:
        pack = fetch_kline(code, period="day", adjust="qfq", limit=KLINE_LIMIT)
    except Exception as exc:  # noqa: BLE001
        logger.info("kline failed %s: %s", code, exc)
        return {
            "code": code,
            "name": meta.get("name"),
            "limit_up_date": meta.get("limit_up_date"),
            "error": str(exc),
            "scores": {"total": 0.0},
        }

    bars = parse_bars(list(pack.get("items") or []))
    limit_date = str(meta.get("limit_up_date") or "")
    limit_idx = find_bar_index(bars, limit_date)
    if limit_idx is None:
        return {
            "code": code,
            "name": meta.get("name") or pack.get("name"),
            "limit_up_date": limit_date,
            "error": "涨停日未在日 K 中找到",
            "scores": {"total": 0.0},
        }

    phases = detect_phases(bars, limit_idx)
    cons_seg, dec_seg = phase_segments(bars, phases)
    cons_scores = list((phases.get("consolidation") or {}).get("daily_scores") or [])
    dec_scores = list((phases.get("decline") or {}).get("daily_scores") or [])

    limit_bar = bars[limit_idx]
    dec_stats = segment_stats(dec_seg)
    cons_stats = segment_stats(cons_seg)

    parts = {
        "decline_duration": duration_score(dec_stats["days"], DECLINE_DURATION_SCALE),
        "decline_quality": decline_quality_score(dec_seg, dec_scores),
        "consolidation_duration": duration_score(cons_stats["days"], CONSOLIDATION_DURATION_SCALE),
        "consolidation_quality": consolidation_quality_score(cons_seg, cons_scores),
        "breakout": breakout_score(limit_bar, meta, cons_seg, lookback_days),
        "structure": structure_score(dec_seg, cons_seg, limit_bar),
    }
    parts["total"] = total_score(parts)

    return {
        "code": code,
        "name": meta.get("name") or pack.get("name"),
        "limit_up_date": limit_date,
        "days_since_limit_up": meta.get("days_since_limit_up"),
        "board_count": meta.get("board_count"),
        "change_pct": meta.get("change_pct"),
        "l1_name": meta.get("l1_name"),
        "l2_name": meta.get("l2_name"),
        "l3_name": meta.get("l3_name"),
        "detected": {
            "decline": dec_stats,
            "consolidation": cons_stats,
        },
        "scores": parts,
        "weights": WEIGHTS,
        "kline_source": pack.get("source"),
        "kline_count": len(bars),
    }


def screen_yindie(
    days: int = DEFAULT_LOOKBACK_DAYS,
    *,
    force: bool = False,
    workers: int = 8,
    top: int | None = None,
) -> dict[str, Any]:
    """筛选近期涨停且「阴跌→横盘→突破」得分较高的股票。"""
    pool = collect_recent_limit_up(days=days, force=force)
    candidates = list(pool.get("candidates") or [])
    results: list[dict[str, Any]] = []

    max_workers = min(max(1, workers), max(1, len(candidates)))
    if not candidates:
        return {
            "lookback_days": days,
            "updated_at": pool.get("updated_at"),
            "candidate_count": 0,
            "result_count": 0,
            "items": [],
            "errors": pool.get("errors") or [],
            "note": "近 N 日涨停池为空",
        }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {
            executor.submit(_analyze_one, meta, days): meta
            for meta in candidates
        }
        for fut in as_completed(futs):
            row = fut.result()
            if row:
                results.append(row)

    results.sort(key=lambda r: float((r.get("scores") or {}).get("total") or 0), reverse=True)
    if top is not None and top > 0:
        results = results[:top]

    return {
        "lookback_days": days,
        "updated_at": pool.get("updated_at"),
        "candidate_count": len(candidates),
        "result_count": len(results),
        "items": results,
        "errors": pool.get("errors") or [],
        "note": "硬条件：近 N 日涨停；其余维度均为软评分",
    }
