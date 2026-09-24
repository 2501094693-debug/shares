"""跨日对比筛选：比较前后若干交易日的日线指标。

相对形态（绝对阈值）多出两类条件：

1. **两两对比** ``left`` / ``right``（offset）+ ``op`` / ``ratio_*`` / ``delta_*``
2. **序列趋势** ``offsets`` + ``trend``（down / up / flat）+ 可选 ``min_pairs``

可与绝对日条件 ``days`` 并用，由顶层 ``logic`` 组合。

示例::

    {
      "id": "settle_compare",
      "name": "对比趋稳",
      "logic": "and",
      "days": [{"offset": 0, "pct_chg_min": -1.2, "pct_chg_max": 1.2}],
      "comps": [
        {
          "field": "body_abs_pct",
          "offsets": [4, 3, 2, 1, 0],
          "trend": "down",
          "min_pairs": 3
        },
        {"field": "vol_ratio", "left": 0, "right": 3, "op": "lt"}
      ]
    }
"""

from __future__ import annotations

import hashlib
import json
import logging
import operator
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from analysis.decline.bars import parse_bars
from analysis.shares.common.candidates import collect_universe
from analysis.shares.common.conditions import (
    LOGIC_NOT,
    LOGIC_OR,
    apply_day_not,
    describe_spec,
    normalize_logic,
)
from analysis.shares.common.config import (
    COMPARE_FIELD_META,
    COMPARE_FIELDS,
    COMPARE_OPS,
    COMPARE_TRENDS,
    KLINE_LIMIT,
)
from analysis.shares.common.days import list_trade_days
from analysis.shares.common.metrics import compact_metrics, measure_bar
from analysis.shares.common.view import apply_view
from analysis.shares.pattern.scheme import match_day, normalize_day_list, normalize_day_raw
from company.line.fetcher import fetch_kline
from core.fmt import to_float

logger = logging.getLogger(__name__)

_OP_FN: dict[str, Callable[[float, float], bool]] = {
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
    "eq": lambda a, b: abs(a - b) <= 1e-6,
}

_OP_SYM = {"lt": "<", "le": "≤", "gt": ">", "ge": "≥", "eq": "="}
_TREND_LABEL = {"down": "递减", "up": "递增", "flat": "持平"}


def _offset_label(offset: int) -> str:
    return "T0" if offset == 0 else f"T-{offset}"


def _field_label(field: str) -> str:
    meta = COMPARE_FIELD_META.get(field) or {}
    return str(meta.get("label") or field)


def metric_value(metrics: dict[str, Any] | None, field: str) -> float | None:
    """从单日指标取出可对比数值（含派生字段）。"""
    if not metrics or not field:
        return None
    if field == "body_abs_pct":
        raw = to_float(metrics.get("body_pct"))
        return abs(raw) if raw is not None else None
    if field == "abs_pct_chg":
        raw = to_float(metrics.get("pct_chg"))
        return abs(raw) if raw is not None else None
    if field == "range_pct":
        gain = to_float(metrics.get("max_gain"))
        drop = to_float(metrics.get("max_drop"))
        if gain is None or drop is None:
            return None
        return float(gain) - float(drop)
    return to_float(metrics.get(field))


def _normalize_op(raw: Any) -> str | None:
    text = str(raw or "").strip().lower()
    aliases = {
        "<": "lt",
        "<=": "le",
        "≤": "le",
        ">": "gt",
        ">=": "ge",
        "≥": "ge",
        "==": "eq",
        "=": "eq",
        "less": "lt",
        "greater": "gt",
    }
    text = aliases.get(text, text)
    return text if text in COMPARE_OPS else None


def _normalize_trend(raw: Any) -> str | None:
    text = str(raw or "").strip().lower()
    aliases = {
        "dec": "down",
        "decreasing": "down",
        "desc": "down",
        "shrink": "down",
        "inc": "up",
        "increasing": "up",
        "asc": "up",
        "stable": "flat",
        "same": "flat",
    }
    text = aliases.get(text, text)
    return text if text in COMPARE_TRENDS else None


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


def _parse_offset(raw: Any) -> int | None:
    if isinstance(raw, dict):
        raw = raw.get("offset", raw.get("day"))
    val = to_float(raw)
    if val is None:
        return None
    idx = int(val)
    return idx if idx >= 0 else None


def normalize_comp(
    raw: dict[str, Any] | None,
    *,
    index: int = 0,
) -> dict[str, Any] | None:
    """规范化单条对比条件。"""
    if not isinstance(raw, dict):
        return None

    field = str(raw.get("field") or raw.get("metric") or "").strip()
    if field not in COMPARE_FIELDS:
        return None

    cid = str(raw.get("id") or raw.get("name") or f"c{index}").strip() or f"c{index}"
    label = str(raw.get("label") or raw.get("name") or "").strip()

    offsets_raw = raw.get("offsets") or raw.get("chain") or raw.get("days")
    if isinstance(offsets_raw, list) and offsets_raw:
        offsets: list[int] = []
        for item in offsets_raw:
            off = _parse_offset(item)
            if off is None:
                continue
            if off not in offsets:
                offsets.append(off)
        if len(offsets) < 2:
            return None
        trend = _normalize_trend(raw.get("trend") or raw.get("dir") or "down")
        if trend is None:
            return None
        strict = _as_bool(raw.get("strict"), True)
        min_pairs_raw = to_float(raw.get("min_pairs") if "min_pairs" in raw else raw.get("min_hits"))
        min_pairs = int(min_pairs_raw) if min_pairs_raw is not None else len(offsets) - 1
        min_pairs = max(1, min(len(offsets) - 1, min_pairs))
        out: dict[str, Any] = {
            "id": cid,
            "label": label or f"{_field_label(field)}{_TREND_LABEL.get(trend, trend)}",
            "kind": "trend",
            "field": field,
            "offsets": offsets,
            "trend": trend,
            "strict": strict,
            "min_pairs": min_pairs,
        }
        return out

    left = _parse_offset(raw.get("left") if "left" in raw else raw.get("a"))
    right = _parse_offset(raw.get("right") if "right" in raw else raw.get("b"))
    if left is None or right is None or left == right:
        return None

    op = _normalize_op(raw.get("op") or raw.get("cmp"))
    ratio_min = to_float(raw.get("ratio_min"))
    ratio_max = to_float(raw.get("ratio_max"))
    delta_min = to_float(raw.get("delta_min"))
    delta_max = to_float(raw.get("delta_max"))
    if op is None and ratio_min is None and ratio_max is None and delta_min is None and delta_max is None:
        op = "lt"

    parts = [f"{_offset_label(left)} {_OP_SYM.get(op or 'lt', op)} {_offset_label(right)}"]
    if ratio_max is not None:
        parts.append(f"比值≤{ratio_max}")
    if ratio_min is not None:
        parts.append(f"比值≥{ratio_min}")
    if delta_max is not None:
        parts.append(f"差≤{delta_max}")
    if delta_min is not None:
        parts.append(f"差≥{delta_min}")

    out = {
        "id": cid,
        "label": label or f"{_field_label(field)} {parts[0]}",
        "kind": "pair",
        "field": field,
        "left": left,
        "right": right,
        "op": op,
        "ratio_min": ratio_min,
        "ratio_max": ratio_max,
        "delta_min": delta_min,
        "delta_max": delta_max,
    }
    return out


def normalize_compare_scheme(
    raw: dict[str, Any] | None,
    *,
    trade_dates: list[str] | None = None,
) -> dict[str, Any]:
    """收成可缓存/可执行的对比方案。"""
    src = raw if isinstance(raw, dict) else {}
    dates = trade_dates
    if dates is None:
        dates = [str(x["date"]) for x in (list_trade_days(22).get("items") or [])]

    comps_raw = src.get("comps") or src.get("compares") or src.get("comparisons") or []
    comps: list[dict[str, Any]] = []
    if isinstance(comps_raw, list):
        for idx, item in enumerate(comps_raw):
            if not isinstance(item, dict):
                continue
            comp = normalize_comp(item, index=idx)
            if comp:
                comps.append(comp)

    days = normalize_day_list(src.get("days"), trade_dates=dates)

    top_logic = normalize_logic(src.get("logic"))

    return {
        "id": str(src.get("id") or "").strip(),
        "name": str(src.get("name") or "").strip(),
        "brief": str(src.get("brief") or "").strip(),
        "logic": top_logic,
        "comps": comps,
        "days": days,
    }


def compare_has_rules(scheme: dict[str, Any]) -> bool:
    return bool(scheme.get("comps") or scheme.get("days"))


def compare_fingerprint(scheme: dict[str, Any]) -> str:
    payload = {
        "logic": scheme.get("logic"),
        "comps": scheme.get("comps") or [],
        "days": scheme.get("days") or [],
        "id": scheme.get("id"),
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def describe_comp(comp: dict[str, Any]) -> str:
    field = _field_label(str(comp.get("field") or ""))
    if comp.get("kind") == "trend":
        offsets = comp.get("offsets") or []
        chain = "→".join(_offset_label(int(o)) for o in offsets)
        trend = _TREND_LABEL.get(str(comp.get("trend")), str(comp.get("trend")))
        strict = "严格" if comp.get("strict") else "非严格"
        min_pairs = comp.get("min_pairs")
        total = max(0, len(offsets) - 1)
        return f"{field} {chain} {strict}{trend}（≥{min_pairs}/{total} 段）"
    left = _offset_label(int(comp.get("left") or 0))
    right = _offset_label(int(comp.get("right") or 0))
    op = _OP_SYM.get(str(comp.get("op") or "lt"), comp.get("op"))
    bits = [f"{field} {left} {op} {right}"]
    if comp.get("ratio_max") is not None:
        bits.append(f"比值≤{comp['ratio_max']}")
    if comp.get("ratio_min") is not None:
        bits.append(f"比值≥{comp['ratio_min']}")
    if comp.get("delta_max") is not None:
        bits.append(f"差≤{comp['delta_max']}")
    if comp.get("delta_min") is not None:
        bits.append(f"差≥{comp['delta_min']}")
    return " · ".join(bits)


def describe_compare_scheme(scheme: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    logic = normalize_logic(scheme.get("logic"))
    if scheme.get("name") or scheme.get("id"):
        lines.append(str(scheme.get("name") or scheme.get("id")))
    if scheme.get("brief"):
        lines.append(str(scheme["brief"]))
    for comp in scheme.get("comps") or []:
        label = comp.get("label") or comp.get("id")
        lines.append(f"[{label}] {describe_comp(comp)}")
    for spec in scheme.get("days") or []:
        lines.append(f"[绝对] {spec.get('date')}: {describe_spec(spec)}")
    if len((scheme.get("comps") or []) + (scheme.get("days") or [])) > 1:
        lines.append(f"组合: {logic.upper()}")
    return lines


def normalize_compare_params(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """收成可缓存参数：scheme 或顶层 comps/days。"""
    src = raw if isinstance(raw, dict) else {}
    if isinstance(src.get("scheme"), dict):
        return {"scheme": src["scheme"]}

    has_comps = isinstance(src.get("comps"), list) and bool(src.get("comps"))
    has_days = isinstance(src.get("days"), list) and bool(src.get("days"))
    if has_comps or has_days:
        out: dict[str, Any] = {}
        if has_comps:
            out["comps"] = src["comps"]
        if has_days:
            out["days"] = src["days"]
        for key in ("id", "name", "brief", "logic", "top"):
            if key in src and src[key] is not None:
                out[key] = src[key]
        return out

    raise ValueError("须提供 scheme 对象，或非空 comps / days")


def load_compare_scheme(params: dict[str, Any] | None = None) -> dict[str, Any]:
    p = normalize_compare_params(params)
    if "scheme" in p and isinstance(p["scheme"], dict):
        return normalize_compare_scheme(p["scheme"])
    return normalize_compare_scheme(p)


def _metrics_at_offset(
    bars: list[dict[str, Any]],
    trade_dates: list[str],
    offset: int,
    cache: dict[int, dict[str, Any] | None],
) -> dict[str, Any] | None:
    if offset in cache:
        return cache[offset]
    if offset < 0 or offset >= len(trade_dates):
        cache[offset] = None
        return None
    date = trade_dates[offset]
    by_date = {str(bar.get("date") or ""): idx for idx, bar in enumerate(bars) if bar.get("date")}
    idx = by_date.get(date)
    if idx is None:
        cache[offset] = None
        return None
    prev_close = bars[idx - 1].get("close") if idx > 0 else None
    metrics = measure_bar(bars[idx], prev_close=prev_close, bars=bars, idx=idx)
    cache[offset] = metrics
    return metrics


def _pair_ok(left_v: float, right_v: float, comp: dict[str, Any]) -> bool:
    op = comp.get("op")
    if op:
        fn = _OP_FN.get(str(op))
        if fn is None or not fn(left_v, right_v):
            return False
    ratio_min = comp.get("ratio_min")
    ratio_max = comp.get("ratio_max")
    if ratio_min is not None or ratio_max is not None:
        if right_v == 0:
            return False
        ratio = left_v / right_v
        if ratio_min is not None and ratio < float(ratio_min):
            return False
        if ratio_max is not None and ratio > float(ratio_max):
            return False
    delta = left_v - right_v
    delta_min = comp.get("delta_min")
    delta_max = comp.get("delta_max")
    if delta_min is not None and delta < float(delta_min):
        return False
    if delta_max is not None and delta > float(delta_max):
        return False
    return True


def _trend_pair_ok(prev_v: float, next_v: float, trend: str, strict: bool) -> bool:
    if trend == "down":
        return next_v < prev_v if strict else next_v <= prev_v
    if trend == "up":
        return next_v > prev_v if strict else next_v >= prev_v
    # flat：相对变化不超过 15% 或绝对值差 ≤ 0.15（取较宽的一边）
    if prev_v == 0:
        return abs(next_v) <= 0.15
    return abs(next_v - prev_v) / abs(prev_v) <= 0.15 or abs(next_v - prev_v) <= 0.15


def evaluate_comp(
    bars: list[dict[str, Any]],
    trade_dates: list[str],
    comp: dict[str, Any],
    cache: dict[int, dict[str, Any] | None],
) -> tuple[bool, dict[str, Any] | None]:
    field = str(comp.get("field") or "")
    if comp.get("kind") == "trend":
        offsets = [int(o) for o in (comp.get("offsets") or [])]
        values: list[tuple[int, float, str]] = []
        for off in offsets:
            metrics = _metrics_at_offset(bars, trade_dates, off, cache)
            val = metric_value(metrics, field)
            if metrics is None or val is None:
                return False, None
            values.append((off, float(val), str(metrics.get("date") or "")))

        trend = str(comp.get("trend") or "down")
        strict = bool(comp.get("strict", True))
        pair_hits = 0
        pair_details: list[dict[str, Any]] = []
        for i in range(len(values) - 1):
            off_a, va, date_a = values[i]
            off_b, vb, date_b = values[i + 1]
            ok = _trend_pair_ok(va, vb, trend, strict)
            if ok:
                pair_hits += 1
            pair_details.append(
                {
                    "from_offset": off_a,
                    "to_offset": off_b,
                    "from_date": date_a,
                    "to_date": date_b,
                    "from": va,
                    "to": vb,
                    "ok": ok,
                }
            )
        need = int(comp.get("min_pairs") or (len(values) - 1))
        matched = pair_hits >= need
        return matched, {
            "id": comp.get("id"),
            "label": comp.get("label"),
            "kind": "trend",
            "field": field,
            "trend": trend,
            "pair_hits": pair_hits,
            "pair_need": need,
            "values": [{"offset": o, "value": v, "date": d} for o, v, d in values],
            "pairs": pair_details,
            "spec_text": describe_comp(comp),
        }

    left = int(comp.get("left") or 0)
    right = int(comp.get("right") or 0)
    left_m = _metrics_at_offset(bars, trade_dates, left, cache)
    right_m = _metrics_at_offset(bars, trade_dates, right, cache)
    left_v = metric_value(left_m, field)
    right_v = metric_value(right_m, field)
    if left_v is None or right_v is None:
        return False, None
    ok = _pair_ok(float(left_v), float(right_v), comp)
    return ok, {
        "id": comp.get("id"),
        "label": comp.get("label"),
        "kind": "pair",
        "field": field,
        "left": {
            "offset": left,
            "date": (left_m or {}).get("date"),
            "value": left_v,
        },
        "right": {
            "offset": right,
            "date": (right_m or {}).get("date"),
            "value": right_v,
        },
        "ratio": (float(left_v) / float(right_v)) if right_v else None,
        "delta": float(left_v) - float(right_v),
        "spec_text": describe_comp(comp),
    }


def evaluate_compare(
    bars: list[dict[str, Any]],
    scheme: dict[str, Any],
    *,
    trade_dates: list[str] | None = None,
) -> dict[str, Any] | None:
    """按对比方案匹配；未命中返回 None。"""
    comps = list(scheme.get("comps") or [])
    days = list(scheme.get("days") or [])
    if not bars or (not comps and not days):
        return None

    dates = trade_dates
    if dates is None:
        dates = [str(x["date"]) for x in (list_trade_days(22).get("items") or [])]
    if not dates:
        return None

    cache: dict[int, dict[str, Any] | None] = {}
    by_date = {str(bar.get("date") or ""): idx for idx, bar in enumerate(bars) if bar.get("date")}

    flags: list[bool] = []
    comp_hits: list[dict[str, Any]] = []
    for comp in comps:
        ok, hit = evaluate_comp(bars, dates, comp, cache)
        flags.append(bool(ok))
        if ok and hit is not None:
            comp_hits.append(hit)

    day_hits: list[dict[str, Any]] = []
    for spec in days:
        # 规范化方案里 days 已是绝对 date；若仍带 offset 再解析
        resolved = spec
        if "date" not in spec and "offset" in spec:
            resolved = normalize_day_raw(spec, trade_dates=dates) or spec
        date = str(resolved.get("date") or "")
        idx = by_date.get(date)
        if idx is None:
            flags.append(False)
            continue
        prev_close = bars[idx - 1].get("close") if idx > 0 else None
        metrics = measure_bar(bars[idx], prev_close=prev_close, bars=bars, idx=idx)
        raw = match_day(metrics, resolved)
        ok = apply_day_not(raw, resolved)
        flags.append(bool(ok))
        if ok and metrics is not None:
            day_hits.append(
                {
                    "date": date,
                    "spec": {k: v for k, v in resolved.items() if k != "date"},
                    "spec_text": describe_spec(resolved),
                    "metrics": compact_metrics(metrics),
                }
            )

    if not flags:
        return None

    mode = normalize_logic(scheme.get("logic"))
    if mode == LOGIC_OR:
        matched = any(flags)
    elif mode == LOGIC_NOT:
        matched = not any(flags)
    else:
        matched = all(flags)

    if not matched:
        return None

    latest_metrics = None
    as_of = ""
    if bars:
        last = bars[-1]
        idx = len(bars) - 1
        prev_close = bars[idx - 1].get("close") if idx > 0 else None
        latest_metrics = measure_bar(last, prev_close=prev_close, bars=bars, idx=idx)
        as_of = str((latest_metrics or {}).get("date") or last.get("date") or "")

    score = float(len(comp_hits) + len(day_hits))
    for hit in comp_hits:
        if hit.get("kind") == "trend":
            need = max(1, int(hit.get("pair_need") or 1))
            score += 0.1 * (int(hit.get("pair_hits") or 0) / need)
        elif hit.get("kind") == "pair":
            ratio = to_float(hit.get("ratio"))
            if ratio is not None and 0 < ratio < 1:
                score += 0.05 * (1.0 - ratio)

    return {
        "as_of": as_of,
        "comps": comp_hits,
        "days": day_hits,
        "matched_comps": len(comp_hits),
        "matched_days": len(day_hits),
        "latest": compact_metrics(latest_metrics) if latest_metrics else {},
        "score": round(score, 4),
        "scheme_id": scheme.get("id") or "",
        "scheme_name": scheme.get("name") or "",
    }


def analyze_one_compare(meta: dict[str, Any], scheme: dict[str, Any]) -> dict[str, Any] | None:
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

    hit = evaluate_compare(bars, scheme)
    if hit is None:
        return None

    return {
        **base,
        "name": name,
        "as_of": hit["as_of"],
        "comps": hit["comps"],
        "days": hit["days"],
        "matched_comps": hit["matched_comps"],
        "matched_days": hit["matched_days"],
        "latest": hit["latest"],
        "score": hit["score"],
        "scheme_id": hit.get("scheme_id") or "",
        "scheme_name": hit.get("scheme_name") or "",
        "kline_source": pack.get("source"),
        "kline_count": len(bars),
    }


def assemble_compare(
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
            -int(r.get("matched_comps") or 0),
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
    summary = describe_compare_scheme(scheme)
    name = scheme.get("name") or scheme.get("id") or "对比方案"
    scheme_id = str(scheme.get("id") or "")
    return {
        "updated_at": as_of,
        "fingerprint": f"cmp_{compare_fingerprint(scheme)}",
        "pattern": scheme_id,
        "mode": "compare",
        "scheme": {
            "id": scheme.get("id"),
            "name": scheme.get("name"),
            "brief": scheme.get("brief"),
            "logic": scheme.get("logic"),
            "comps": scheme.get("comps"),
            "days": scheme.get("days"),
        },
        "params": {"scheme_id": scheme_id} if scheme_id else {},
        "spec_summary": summary,
        "candidate_count": candidate_n,
        "analyzed_count": candidate_n if analyzed is None else analyzed,
        "result_count": len(items),
        "items": items,
        "errors": errors,
        "note": f"{name}（跨日对比）；规则见 spec_summary",
        "compare_fields": COMPARE_FIELD_META,
    }


def screen_compare(
    scheme: dict[str, Any],
    *,
    code: str = "",
    workers: int = 8,
    top: int | None = None,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """按已规范化对比方案全市场/单只扫描。"""
    if not compare_has_rules(scheme):
        pool = collect_universe(code)
        payload = assemble_compare(pool, [], scheme, analyzed=0)
        payload["note"] = "方案无有效对比或绝对条件"
        return apply_view(payload, top)

    pool = collect_universe(code)
    candidates = list(pool.get("candidates") or [])

    if on_update:
        on_update(assemble_compare(pool, [], scheme, analyzed=0))
    if not candidates:
        payload = assemble_compare(pool, [], scheme, analyzed=0)
        payload["note"] = (pool.get("errors") or ["没有可分析的股票"])[0]
        return apply_view(payload, top)

    results: list[dict[str, Any]] = []
    max_workers = min(max(1, workers), max(1, len(candidates)))
    tick = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {executor.submit(analyze_one_compare, meta, scheme): meta for meta in candidates}
        for fut in as_completed(futs):
            row = fut.result()
            tick += 1
            if row:
                results.append(row)
            if on_update and (tick <= 8 or tick % 40 == 0 or tick == len(candidates)):
                on_update(assemble_compare(pool, results, scheme, analyzed=tick))

    payload = assemble_compare(pool, results, scheme, analyzed=len(candidates))
    return apply_view(payload, top)
