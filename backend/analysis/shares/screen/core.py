"""按多日日线条件筛选股票。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from analysis.decline.bars import parse_bars
from analysis.shares.common.candidates import collect_universe
from analysis.shares.common.conditions import (
    LOGIC_AND,
    LOGIC_NOT,
    LOGIC_OR,
    apply_day_not,
    describe_day_chain,
    describe_spec,
    has_day_joins,
    normalize_day_specs,
    normalize_join,
    normalize_logic,
    specs_fingerprint,
)
from analysis.shares.common.config import KLINE_LIMIT
from analysis.shares.common.metrics import compact_metrics, measure_bar
from analysis.shares.common.view import apply_view
from analysis.shares.pattern.scheme import match_day
from company.line.fetcher import fetch_kline

logger = logging.getLogger(__name__)


def _index_by_date(bars: list[dict[str, Any]]) -> dict[str, int]:
    return {str(bar.get("date") or ""): idx for idx, bar in enumerate(bars) if bar.get("date")}


def _day_eval(
    bars: list[dict[str, Any]],
    by_date: dict[str, int],
    spec: dict[str, Any],
) -> tuple[bool | None, dict[str, Any] | None]:
    """评估单日。

    返回 ``(ok, hit)``：
    - ``ok is None``：缺 K，无法判定（AND/NOT 视为失败；OR 跳过）
    - ``ok``：已含本日 ``not`` 取反
    - ``hit``：原始字段命中时的详情（取反成功时也可能带 metrics）
    """
    date = spec["date"]
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
        "date": date,
        "spec": {k: v for k, v in spec.items() if k != "date"},
        "spec_text": describe_spec(spec) + extra,
        "metrics": compact_metrics(metrics),
        "negated": bool(spec.get("not")),
        "raw_match": bool(raw),
    }
    return ok, hit


def evaluate_stock(
    bars: list[dict[str, Any]],
    specs: list[dict[str, Any]],
    logic: str = LOGIC_AND,
) -> dict[str, Any] | None:
    """对一只股票的日 K 逐日匹配。

    - 若条件日带 ``join``：按日期顺序左结合连接（and / or）；缺 K 视为该日 False
    - 否则统一 ``logic``：
      - ``and``：所有条件日全部满足
      - ``or``：任一条件日满足（缺 K 跳过）
      - ``not``：全部不满足（缺 K 视为失败）
    """
    if not bars or not specs:
        return None

    mode = normalize_logic(logic)
    by_date = _index_by_date(bars)
    evaluated: list[tuple[bool | None, dict[str, Any] | None]] = [
        _day_eval(bars, by_date, spec) for spec in specs
    ]

    if has_day_joins(specs):
        day_hits: list[dict[str, Any]] = []
        first_ok, first_hit = evaluated[0]
        if first_ok is None:
            return None
        acc = bool(first_ok)
        if first_hit is not None:
            day_hits.append(first_hit)
        for spec, (ok, hit) in zip(specs[1:], evaluated[1:]):
            bit = False if ok is None else bool(ok)
            if normalize_join(spec.get("join")) == LOGIC_OR:
                acc = acc or bit
            else:
                acc = acc and bit
            if hit is not None:
                day_hits.append(hit)
        if not acc:
            return None
        matched = sum(1 for ok, _ in evaluated if ok is True)
        return {
            "matched_days": matched,
            "days": day_hits,
            "as_of": day_hits[-1]["date"] if day_hits else "",
            "logic": "chain",
        }

    day_hits = []
    if mode == LOGIC_OR:
        for ok, hit in evaluated:
            if ok is None:
                continue
            if ok and hit is not None:
                day_hits.append(hit)
        if not day_hits:
            return None
    elif mode == LOGIC_NOT:
        for ok, hit in evaluated:
            if ok is None:
                return None
            if ok:
                return None
            if hit is not None:
                day_hits.append(hit)
        if not day_hits and not specs:
            return None
    else:
        for ok, hit in evaluated:
            if ok is None or not ok:
                return None
            if hit is not None:
                day_hits.append(hit)

    return {
        "matched_days": len(day_hits),
        "days": day_hits,
        "as_of": day_hits[-1]["date"] if day_hits else "",
        "logic": mode,
    }


def analyze_one(
    meta: dict[str, Any],
    specs: list[dict[str, Any]],
    logic: str = LOGIC_AND,
) -> dict[str, Any] | None:
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

    hit = evaluate_stock(bars, specs, logic=logic)
    if hit is None:
        return None

    return {
        **base,
        "name": name,
        "as_of": hit["as_of"],
        "matched_days": hit["matched_days"],
        "days": hit["days"],
        "logic": hit.get("logic") or normalize_logic(logic),
        "kline_source": pack.get("source"),
        "kline_count": len(bars),
    }


def assemble(
    pool: dict[str, Any],
    results: list[dict[str, Any]],
    specs: list[dict[str, Any]],
    *,
    logic: str = LOGIC_AND,
    analyzed: int | None = None,
) -> dict[str, Any]:
    mode = normalize_logic(logic)
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
    if mode == LOGIC_OR:
        logic_label = "OR（任一满足）"
    elif mode == LOGIC_NOT:
        logic_label = "NOT（全部不满足）"
    else:
        logic_label = "AND（全部满足）"
    if has_day_joins(specs):
        logic_label = "逐日连接（左结合）"
        note = f"多日条件为逐段与/或：{describe_day_chain(specs, mode)}；未设规则的交易日不参与筛选"
    else:
        note = f"多日日线条件为 {logic_label}；未设规则的交易日不参与筛选"
    return {
        "updated_at": as_of,
        "fingerprint": specs_fingerprint(specs, mode),
        "logic": "chain" if has_day_joins(specs) else mode,
        "specs": specs,
        "spec_summary": [f"{s['date']}: {describe_spec(s)}" for s in specs],
        "chain_summary": describe_day_chain(specs, mode),
        "candidate_count": candidate_n,
        "analyzed_count": candidate_n if analyzed is None else analyzed,
        "result_count": len(items),
        "items": items,
        "errors": errors,
        "note": note,
    }


def screen_shares(
    *,
    day_specs: list[dict[str, Any]] | None = None,
    logic: str = LOGIC_AND,
    code: str = "",
    workers: int = 8,
    top: int | None = None,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """全市场或单只：按给定交易日条件筛选。"""
    specs = normalize_day_specs(day_specs)
    mode = normalize_logic(logic)
    pool = collect_universe(code)

    if not specs:
        payload = assemble(pool, [], [], logic=mode, analyzed=0)
        payload["note"] = "请至少为一天设置有效条件（涨跌/最大涨跌幅/实体/影线占比）"
        return apply_view(payload, top)

    candidates = list(pool.get("candidates") or [])
    if on_update:
        on_update(assemble(pool, [], specs, logic=mode, analyzed=0))
    if not candidates:
        payload = assemble(pool, [], specs, logic=mode, analyzed=0)
        payload["note"] = (pool.get("errors") or ["没有可分析的股票"])[0]
        return apply_view(payload, top)

    results: list[dict[str, Any]] = []
    max_workers = min(max(1, workers), max(1, len(candidates)))
    tick = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {
            executor.submit(analyze_one, meta, specs, mode): meta for meta in candidates
        }
        for fut in as_completed(futs):
            row = fut.result()
            tick += 1
            if row:
                results.append(row)
            if on_update and (tick <= 8 or tick % 40 == 0 or tick == len(candidates)):
                on_update(assemble(pool, results, specs, logic=mode, analyzed=tick))

    payload = assemble(pool, results, specs, logic=mode, analyzed=len(candidates))
    return apply_view(payload, top)
