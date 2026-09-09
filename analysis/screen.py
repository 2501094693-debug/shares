"""阴跌→横盘→涨停：主筛选逻辑。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from analysis._path import ensure_backend_path

ensure_backend_path()

from company.line.fetcher import fetch_kline

from analysis.bars import build_sparkline, find_bar_index, parse_bars, segment_stats
from analysis.candidates import collect_recent_limit_up
from analysis.config import (
    CHART_MAX_BARS,
    CHART_MA_WARMUP,
    CHART_PAD_AFTER,
    CHART_PAD_BEFORE,
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

    limit_date = str(meta.get("limit_up_date") or "")
    base = {
        "code": code,
        "name": meta.get("name"),
        "limit_up_date": limit_date,
        "date_raw": meta.get("date_raw") or limit_date.replace("-", ""),
        "days_since_limit_up": meta.get("days_since_limit_up"),
        "board_count": meta.get("board_count"),
        "change_pct": meta.get("change_pct"),
        "l1_name": meta.get("l1_name"),
        "l2_name": meta.get("l2_name"),
        "l3_name": meta.get("l3_name"),
    }

    try:
        pack = fetch_kline(code, period="day", adjust="qfq", limit=KLINE_LIMIT)
    except Exception as exc:  # noqa: BLE001
        logger.info("kline failed %s: %s", code, exc)
        return {
            **base,
            "error": str(exc),
            "scores": {"total": 0.0},
            "chart": {"bars": [], "warmup": 0, "decline": [None, None], "consolidation": [None, None], "limit_up": None},
        }

    bars = parse_bars(list(pack.get("items") or []))
    limit_idx = find_bar_index(bars, limit_date)
    if limit_idx is None:
        return {
            **base,
            "name": meta.get("name") or pack.get("name"),
            "error": "涨停日未在日 K 中找到",
            "scores": {"total": 0.0},
            "chart": {"bars": [], "warmup": 0, "decline": [None, None], "consolidation": [None, None], "limit_up": None},
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
        **base,
        "name": meta.get("name") or pack.get("name"),
        "detected": {
            "decline": dec_stats,
            "consolidation": cons_stats,
        },
        "scores": parts,
        "weights": WEIGHTS,
        "chart": build_sparkline(
            bars,
            limit_idx,
            phases,
            pad_before=CHART_PAD_BEFORE,
            pad_after=CHART_PAD_AFTER,
            max_bars=CHART_MAX_BARS,
            ma_warmup=CHART_MA_WARMUP,
        ),
        "kline_source": pack.get("source"),
        "kline_count": len(bars),
    }


def apply_day_top(data: dict[str, Any], top: int | None) -> dict[str, Any]:
    """每个交易日只保留前 N 名；top<=0 或 None 表示全量。"""
    analyzed = data.get("analyzed_count")
    if analyzed is None:
        analyzed = data.get("result_count")
    if top is None or top <= 0:
        return {**data, "analyzed_count": analyzed}

    days_out: list[dict[str, Any]] = []
    flat: list[dict[str, Any]] = []
    for day in data.get("days") or []:
        items = list(day.get("items") or [])[:top]
        days_out.append({**day, "items": items, "result_count": len(items)})
        flat.extend(items)
    return {
        **data,
        "days": days_out,
        "items": flat,
        "result_count": len(flat),
        "analyzed_count": analyzed,
    }


def assemble_ranked_days(
    pool: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    lookback_days: int,
) -> dict[str, Any]:
    """用当前已完成的结果按日重新排名。"""
    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for row in results:
        key = (str(row.get("code") or ""), str(row.get("limit_up_date") or ""))
        if key[0]:
            by_pair[key] = row

    days_out: list[dict[str, Any]] = []
    flat: list[dict[str, Any]] = []
    for day in pool.get("days") or []:
        date = str(day.get("date") or "")
        ranked: list[dict[str, Any]] = []
        for meta in day.get("candidates") or []:
            key = (str(meta.get("code") or ""), date)
            hit = by_pair.get(key)
            if hit:
                ranked.append(hit)
        ranked.sort(
            key=lambda r: float((r.get("scores") or {}).get("total") or 0),
            reverse=True,
        )
        for idx, row in enumerate(ranked, start=1):
            row["rank"] = idx
        days_out.append(
            {
                "date": date,
                "date_raw": day.get("date_raw") or date.replace("-", ""),
                "candidate_count": int(day.get("candidate_count") or len(ranked)),
                "analyzed_count": len(ranked),
                "result_count": len(ranked),
                "items": ranked,
            }
        )
        flat.extend(ranked)

    candidate_count = int(pool.get("count") or len(pool.get("candidates") or []))
    return {
        "lookback_days": lookback_days,
        "updated_at": pool.get("updated_at"),
        "candidate_count": candidate_count,
        "analyzed_count": len(flat),
        "result_count": len(flat),
        "items": flat,
        "days": days_out,
        "errors": pool.get("errors") or [],
        "note": "硬条件：当日涨停；按交易日分批排名；其余维度均为软评分",
    }


def _empty_payload(days: int, pool: dict[str, Any], note: str) -> dict[str, Any]:
    payload = assemble_ranked_days(pool, [], lookback_days=days)
    payload["note"] = note
    return payload


def screen_yindie(
    days: int = DEFAULT_LOOKBACK_DAYS,
    *,
    force: bool = False,
    workers: int = 8,
    top: int | None = None,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """按日筛选涨停池中「阴跌→横盘→突破」得分较高的股票。"""
    pool = collect_recent_limit_up(days=days, force=force)
    candidates = list(pool.get("candidates") or [])
    if on_update:
        on_update(assemble_ranked_days(pool, [], lookback_days=days))
    if not candidates:
        return _empty_payload(days, pool, "近 N 日涨停池为空")

    results: list[dict[str, Any]] = []
    max_workers = min(max(1, workers), max(1, len(candidates)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {
            executor.submit(_analyze_one, meta, days): meta
            for meta in candidates
        }
        for fut in as_completed(futs):
            row = fut.result()
            if row:
                results.append(row)
                if on_update:
                    on_update(assemble_ranked_days(pool, results, lookback_days=days))

    payload = assemble_ranked_days(pool, results, lookback_days=days)
    return apply_day_top(payload, top)
