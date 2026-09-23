"""按多日日线条件筛选股票。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from analysis.decline.bars import parse_bars
from analysis.shares.candidates import collect_universe
from analysis.shares.conditions import (
    describe_spec,
    match_metrics,
    normalize_day_specs,
    specs_fingerprint,
)
from analysis.shares.config import KLINE_LIMIT
from analysis.shares.metrics import compact_metrics, measure_bar
from company.line.fetcher import fetch_kline

logger = logging.getLogger(__name__)


def _index_by_date(bars: list[dict[str, Any]]) -> dict[str, int]:
    return {str(bar.get("date") or ""): idx for idx, bar in enumerate(bars) if bar.get("date")}


def evaluate_stock(bars: list[dict[str, Any]], specs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """对一只股票的日 K 逐日匹配；全部满足才返回明细。"""
    if not bars or not specs:
        return None

    by_date = _index_by_date(bars)
    day_hits: list[dict[str, Any]] = []

    for spec in specs:
        date = spec["date"]
        idx = by_date.get(date)
        if idx is None:
            return None
        prev_close = bars[idx - 1].get("close") if idx > 0 else None
        metrics = measure_bar(bars[idx], prev_close=prev_close, bars=bars, idx=idx)
        if not match_metrics(metrics, spec):
            return None
        assert metrics is not None
        day_hits.append(
            {
                "date": date,
                "spec": {k: v for k, v in spec.items() if k != "date"},
                "spec_text": describe_spec(spec),
                "metrics": compact_metrics(metrics),
            }
        )

    return {
        "matched_days": len(day_hits),
        "days": day_hits,
        "as_of": day_hits[-1]["date"] if day_hits else "",
    }


def analyze_one(meta: dict[str, Any], specs: list[dict[str, Any]]) -> dict[str, Any] | None:
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

    hit = evaluate_stock(bars, specs)
    if hit is None:
        return None

    return {
        **base,
        "name": name,
        "as_of": hit["as_of"],
        "matched_days": hit["matched_days"],
        "days": hit["days"],
        "kline_source": pack.get("source"),
        "kline_count": len(bars),
    }


def apply_view(data: dict[str, Any], top: int | None) -> dict[str, Any]:
    items = list(data.get("items") or [])
    items.sort(
        key=lambda r: (
            -int(r.get("matched_days") or 0),
            str(r.get("code") or ""),
        )
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
        "top": top,
    }


def assemble(
    pool: dict[str, Any],
    results: list[dict[str, Any]],
    specs: list[dict[str, Any]],
    *,
    analyzed: int | None = None,
) -> dict[str, Any]:
    items = [row for row in results if row and not row.get("error")]
    items.sort(key=lambda r: (-int(r.get("matched_days") or 0), str(r.get("code") or "")))
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
    return {
        "updated_at": as_of,
        "fingerprint": specs_fingerprint(specs),
        "specs": specs,
        "spec_summary": [f"{s['date']}: {describe_spec(s)}" for s in specs],
        "candidate_count": candidate_n,
        "analyzed_count": candidate_n if analyzed is None else analyzed,
        "result_count": len(items),
        "items": items,
        "errors": errors,
        "note": "多日日线条件为 AND；未设规则的交易日不参与筛选",
    }


def screen_shares(
    *,
    day_specs: list[dict[str, Any]] | None = None,
    code: str = "",
    workers: int = 8,
    top: int | None = None,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """全市场或单只：按给定交易日条件筛选。"""
    specs = normalize_day_specs(day_specs)
    pool = collect_universe(code)

    if not specs:
        payload = assemble(pool, [], [], analyzed=0)
        payload["note"] = "请至少为一天设置有效条件（涨跌/最大涨跌幅/实体/影线占比）"
        return apply_view(payload, top)

    candidates = list(pool.get("candidates") or [])
    if on_update:
        on_update(assemble(pool, [], specs, analyzed=0))
    if not candidates:
        payload = assemble(pool, [], specs, analyzed=0)
        payload["note"] = (pool.get("errors") or ["没有可分析的股票"])[0]
        return apply_view(payload, top)

    results: list[dict[str, Any]] = []
    max_workers = min(max(1, workers), max(1, len(candidates)))
    tick = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {executor.submit(analyze_one, meta, specs): meta for meta in candidates}
        for fut in as_completed(futs):
            row = fut.result()
            tick += 1
            if row:
                results.append(row)
            if on_update and (tick <= 8 or tick % 40 == 0 or tick == len(candidates)):
                on_update(assemble(pool, results, specs, analyzed=tick))

    payload = assemble(pool, results, specs, analyzed=len(candidates))
    return apply_view(payload, top)
