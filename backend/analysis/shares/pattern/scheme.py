"""筛选方案 JSON：多日 and/or、分组 OR、至少 M/N。

扁平（兼容旧客户端）::

    {"logic": "and", "days": [{"date": "2026-09-23", "pct_chg_min": 1}]}

分组（收下影 OR 近五日缩实体）::

    {
      "logic": "or",
      "groups": [
        {"id": "a", "days": [{"offset": 0, "lower_ratio_min": 0.35, "lower_ge_body": true}]},
        {"id": "b", "min_hits": 3, "days": [{"offset": 0, "body_abs_pct_max": 1.2}, ...]}
      ]
    }
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from analysis.decline.bars import normalize_date
from analysis.shares.common.conditions import (
    LOGIC_AND,
    LOGIC_NOT,
    LOGIC_OR,
    apply_day_not,
    describe_spec,
    match_metrics,
    normalize_day_spec,
    normalize_logic,
)
from analysis.shares.common.days import list_trade_days
from core.fmt import to_float


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


def normalize_day_raw(
    raw: dict[str, Any] | None,
    *,
    trade_dates: list[str] | None = None,
) -> dict[str, Any] | None:
    """单日条件；可用 date 或 offset（0=最新交易日）。支持 body_abs_pct_max、lower_ge_body。"""
    if not isinstance(raw, dict):
        return None

    item = dict(raw)
    date = normalize_date(item.get("date") or item.get("day") or "")
    if not date:
        offset = to_float(item.get("offset"))
        if offset is None or trade_dates is None:
            return None
        idx = int(offset)
        if idx < 0 or idx >= len(trade_dates):
            return None
        date = trade_dates[idx]
    item["date"] = date

    # |实体幅度| 上限 → body_pct 双边
    abs_max = to_float(item.get("body_abs_pct_max"))
    if abs_max is not None:
        abs_max = abs(float(abs_max))
        if item.get("body_pct_min") is None and item.get("min_body_pct") is None:
            item["body_pct_min"] = -abs_max
        if item.get("body_pct_max") is None and item.get("max_body_pct") is None:
            item["body_pct_max"] = abs_max

    spec = normalize_day_spec(item)
    lower_ge = item.get("lower_ge_body")
    if lower_ge is not None:
        flag = _as_bool(lower_ge, False)
        if spec is None:
            if not date:
                return None
            spec = {"date": date}
            # 无区间字段时仍保留单日逻辑 / 取反
            field_logic = normalize_logic(item.get("logic"))
            if field_logic != LOGIC_AND:
                spec["logic"] = field_logic
            if _as_bool(item.get("not"), False):
                spec["not"] = True
        if flag:
            spec["lower_ge_body"] = True
        elif "lower_ge_body" in spec:
            del spec["lower_ge_body"]

    if spec is None:
        return None
    # 仅有 lower_ge_body、无区间字段也算有效规则
    if not any(k.endswith("_min") or k.endswith("_max") for k in spec) and not spec.get(
        "lower_ge_body"
    ):
        return None
    return spec


def normalize_day_list(
    raw_days: Any,
    *,
    trade_dates: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(raw_days, list):
        return []
    by_date: dict[str, dict[str, Any]] = {}
    for item in raw_days:
        spec = normalize_day_raw(item, trade_dates=trade_dates)
        if spec is None:
            continue
        by_date[spec["date"]] = spec
    return sorted(by_date.values(), key=lambda s: s["date"])


def _normalize_group(
    raw: dict[str, Any],
    *,
    trade_dates: list[str] | None = None,
    index: int = 0,
) -> dict[str, Any] | None:
    days = normalize_day_list(raw.get("days"), trade_dates=trade_dates)
    if not days:
        return None
    min_hits_raw = to_float(raw.get("min_hits") if "min_hits" in raw else raw.get("quiet_min_days"))
    min_hits = int(min_hits_raw) if min_hits_raw is not None else None
    if min_hits is not None:
        min_hits = max(1, min(len(days), min_hits))
    gid = str(raw.get("id") or raw.get("name") or f"g{index}").strip() or f"g{index}"
    label = str(raw.get("label") or raw.get("name") or gid).strip()
    return {
        "id": gid,
        "label": label,
        "logic": normalize_logic(raw.get("logic")),
        "min_hits": min_hits,
        "days": days,
    }


def normalize_scheme(
    raw: dict[str, Any] | list[dict[str, Any]] | None,
    *,
    trade_dates: list[str] | None = None,
    logic: Any = None,
) -> dict[str, Any]:
    """收成可缓存/可执行的标准方案。"""
    if isinstance(raw, list):
        raw = {"days": raw, "logic": logic}
    src = raw if isinstance(raw, dict) else {}

    dates = trade_dates
    if dates is None and _needs_offsets(src):
        dates = [str(x["date"]) for x in (list_trade_days(22).get("items") or [])]

    groups_raw = src.get("groups")
    groups: list[dict[str, Any]] = []
    if isinstance(groups_raw, list) and groups_raw:
        for idx, item in enumerate(groups_raw):
            if not isinstance(item, dict):
                continue
            group = _normalize_group(item, trade_dates=dates, index=idx)
            if group:
                groups.append(group)
    else:
        days = normalize_day_list(src.get("days"), trade_dates=dates)
        if days:
            min_hits_raw = to_float(src.get("min_hits"))
            min_hits = int(min_hits_raw) if min_hits_raw is not None else None
            if min_hits is not None:
                min_hits = max(1, min(len(days), min_hits))
            groups.append(
                {
                    "id": "main",
                    "label": "条件",
                    "logic": normalize_logic(logic if logic is not None else src.get("logic")),
                    "min_hits": min_hits,
                    "days": days,
                }
            )

    top_logic = normalize_logic(logic if logic is not None else src.get("logic"))
    # 多组时默认 OR（形态方案语义）；单组沿用组内 / 显式 logic
    if len(groups) > 1 and logic is None and src.get("logic") is None:
        top_logic = LOGIC_OR

    flat_days: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for day in group["days"]:
            if day["date"] not in seen:
                seen.add(day["date"])
                flat_days.append(day)
    flat_days.sort(key=lambda s: s["date"])

    return {
        "id": str(src.get("id") or "").strip(),
        "name": str(src.get("name") or "").strip(),
        "brief": str(src.get("brief") or "").strip(),
        "logic": top_logic,
        "groups": groups,
        "days": flat_days,
    }


def _needs_offsets(src: dict[str, Any]) -> bool:
    def _list_needs(days: Any) -> bool:
        if not isinstance(days, list):
            return False
        for item in days:
            if not isinstance(item, dict):
                continue
            if not normalize_date(item.get("date") or item.get("day") or ""):
                if to_float(item.get("offset")) is not None:
                    return True
        return False

    if _list_needs(src.get("days")):
        return True
    groups = src.get("groups")
    if isinstance(groups, list):
        for g in groups:
            if isinstance(g, dict) and _list_needs(g.get("days")):
                return True
    return False


def scheme_fingerprint(scheme: dict[str, Any]) -> str:
    payload = {
        "logic": scheme.get("logic"),
        "groups": [
            {
                "id": g.get("id"),
                "logic": g.get("logic"),
                "min_hits": g.get("min_hits"),
                "days": g.get("days"),
            }
            for g in (scheme.get("groups") or [])
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def describe_scheme(scheme: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    groups = scheme.get("groups") or []
    top = normalize_logic(scheme.get("logic"))
    if len(groups) <= 1:
        g = groups[0] if groups else None
        if not g:
            return ["(空方案)"]
        days = g.get("days") or []
        min_hits = g.get("min_hits")
        if min_hits is not None:
            lines.append(f"近{len(days)}日至少{min_hits}日命中")
        else:
            logic = normalize_logic(g.get("logic"))
            if logic == LOGIC_OR:
                lines.append("多日 OR")
            elif logic == LOGIC_NOT:
                lines.append("多日 NOT（全部不满足）")
            else:
                lines.append("多日 AND")
        for day in days:
            extra = " 且下影≥实体" if day.get("lower_ge_body") else ""
            lines.append(f"{day['date']}: {describe_spec(day)}{extra}")
        return lines

    if top == LOGIC_OR:
        joiner = " OR "
    elif top == LOGIC_NOT:
        joiner = " NOR "
    else:
        joiner = " AND "
    lines.append("分组" + joiner.join(str(g.get("label") or g.get("id")) for g in groups))
    for g in groups:
        days = g.get("days") or []
        min_hits = g.get("min_hits")
        if min_hits is not None:
            head = f"[{g.get('label') or g.get('id')}] 至少{min_hits}/{len(days)}日"
        else:
            gl = normalize_logic(g.get("logic"))
            tag = "OR" if gl == LOGIC_OR else ("NOT" if gl == LOGIC_NOT else "AND")
            head = f"[{g.get('label') or g.get('id')}] {tag}"
        detail = "; ".join(
            f"{d['date']} {describe_spec(d)}"
            + (" 下影≥实体" if d.get("lower_ge_body") else "")
            for d in days
        )
        lines.append(f"{head}: {detail}")
    return lines


def scheme_has_rules(scheme: dict[str, Any]) -> bool:
    return any(g.get("days") for g in (scheme.get("groups") or []))


def match_day(metrics: dict[str, Any] | None, spec: dict[str, Any]) -> bool:
    """单日匹配（含 lower_ge_body；不含本日 ``not`` 取反）。"""
    if not match_metrics(metrics, spec):
        return False
    if not spec.get("lower_ge_body"):
        return True
    if metrics is None:
        return False
    lower = to_float(metrics.get("lower_ratio"))
    body = to_float(metrics.get("body_ratio"))
    if lower is None or body is None:
        return False
    return lower >= body



def _body_abs_pct(metrics: dict[str, Any]) -> float | None:
    raw = metrics.get("body_pct")
    if raw is None:
        return None
    try:
        return abs(float(raw))
    except (TypeError, ValueError):
        return None


def evaluate_scheme(
    bars: list[dict[str, Any]],
    scheme: dict[str, Any],
) -> dict[str, Any] | None:
    """按规范化方案匹配一根股票的日 K；未命中返回 None。"""
    from analysis.shares.common.metrics import compact_metrics, measure_bar

    groups = list(scheme.get("groups") or [])
    if not bars or not groups:
        return None

    by_date = {str(bar.get("date") or ""): idx for idx, bar in enumerate(bars) if bar.get("date")}

    def try_day(spec: dict[str, Any]) -> tuple[bool | None, dict[str, Any] | None]:
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
            "body_abs_pct": _body_abs_pct(metrics),
            "negated": bool(spec.get("not")),
            "raw_match": bool(raw),
        }
        return ok, hit

    def eval_group(group: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
        days = list(group.get("days") or [])
        day_hits: list[dict[str, Any]] = []
        day_oks: list[bool] = []
        missing = False
        for spec in days:
            ok, hit = try_day(spec)
            if ok is None:
                missing = True
                continue
            day_oks.append(ok)
            if ok and hit is not None:
                day_hits.append(hit)

        min_hits = group.get("min_hits")
        if min_hits is not None:
            hit_n = sum(1 for x in day_oks if x)
            ok = hit_n >= int(min_hits)
            hit_count = hit_n
        else:
            g_logic = normalize_logic(group.get("logic"))
            if g_logic == LOGIC_OR:
                ok = any(day_oks)
            elif g_logic == LOGIC_NOT:
                ok = (not missing) and bool(days) and (not any(day_oks))
                if ok:
                    day_hits = []
                    for spec in days:
                        _, hit = try_day(spec)
                        if hit is not None:
                            day_hits.append(hit)
            else:
                ok = (not missing) and len(day_oks) == len(days) and all(day_oks) and bool(days)
            hit_count = len(day_hits)

        if not ok:
            return False, None
        return True, {
            "id": group.get("id"),
            "label": group.get("label"),
            "min_hits": min_hits,
            "hit_count": hit_count,
            "days": day_hits,
        }

    evaluated: list[tuple[bool, dict[str, Any] | None]] = [eval_group(g) for g in groups]
    matched = [payload for ok, payload in evaluated if ok and payload is not None]
    top = normalize_logic(scheme.get("logic"))

    if top == LOGIC_AND:
        if len(matched) < len(groups):
            return None
        group_hits = matched
    elif top == LOGIC_NOT:
        if len(groups) <= 1:
            # 单组：not 已在组内 days 逻辑处理，组间不再二次取反
            if not matched:
                return None
            group_hits = matched
        else:
            # 多组 NOR：全部组都不命中才入选
            if any(ok for ok, _ in evaluated):
                return None
            group_hits = []
    else:
        if not matched:
            return None
        group_hits = matched

    all_day_hits: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    for ghit in group_hits:
        for hit in ghit.get("days") or []:
            date = str(hit.get("date") or "")
            if date and date not in seen_dates:
                seen_dates.add(date)
                all_day_hits.append(hit)
    all_day_hits.sort(key=lambda d: str(d.get("date") or ""))
    branch_ids = [str(g.get("id") or "") for g in group_hits]
    latest_metrics = None
    as_of = ""
    if bars:
        last = bars[-1]
        idx = len(bars) - 1
        prev_close = bars[idx - 1].get("close") if idx > 0 else None
        latest_metrics = measure_bar(last, prev_close=prev_close, bars=bars, idx=idx)
        as_of = str((latest_metrics or {}).get("date") or last.get("date") or "")

    score = float(len(group_hits))
    quiet_group = next((g for g in group_hits if g.get("id") == "quiet_body"), None)
    if quiet_group is None:
        quiet_group = next((g for g in group_hits if g.get("min_hits") is not None), None)
    quiet_count = int(quiet_group["hit_count"]) if quiet_group else 0
    lower_r = to_float((latest_metrics or {}).get("lower_ratio")) or 0.0
    score += min(0.5, lower_r) * 0.4
    score += min(5, quiet_count) * 0.05

    quiet_src = next((g for g in groups if g.get("id") == "quiet_body"), None)
    if quiet_src is None:
        quiet_src = next((g for g in groups if g.get("min_hits") is not None), None)
    if quiet_src:
        window_specs: list[dict[str, Any]] = list(quiet_src.get("days") or [])
    else:
        window_specs = []
        for g in groups:
            window_specs.extend(g.get("days") or [])

    quiet_hit_dates = {str(d.get("date") or "") for d in (quiet_group or {}).get("days") or []}
    shadow_hit = "lower_shadow" in branch_ids

    window_days: list[dict[str, Any]] = []
    for spec in window_specs:
        date = spec["date"]
        idx = by_date.get(date)
        if idx is None:
            continue
        prev_close = bars[idx - 1].get("close") if idx > 0 else None
        metrics = measure_bar(bars[idx], prev_close=prev_close, bars=bars, idx=idx)
        if metrics is None:
            continue
        window_days.append(
            {
                "date": date,
                "body_abs_pct": _body_abs_pct(metrics),
                "lower_ratio": metrics.get("lower_ratio"),
                "body_ratio": metrics.get("body_ratio"),
                "body_pct": metrics.get("body_pct"),
                "pct_chg": metrics.get("pct_chg"),
                "is_lower_shadow": shadow_hit and date == as_of,
                "is_quiet_body": date in quiet_hit_dates,
                "metrics": compact_metrics(metrics),
            }
        )

    quiet_days = []
    if quiet_group:
        quiet_days = [
            {
                "date": d.get("date"),
                "body_abs_pct": d.get("body_abs_pct"),
                "metrics": d.get("metrics"),
            }
            for d in quiet_group.get("days") or []
        ]

    return {
        "as_of": as_of,
        "branches": branch_ids,
        "groups": group_hits,
        "hit_lower_shadow": shadow_hit,
        "hit_quiet_body": quiet_group is not None,
        "quiet_count": quiet_count,
        "quiet_min_days": (quiet_src or {}).get("min_hits"),
        "quiet_window": len((quiet_src or {}).get("days") or []),
        "quiet_days": quiet_days,
        "latest": compact_metrics(latest_metrics) if latest_metrics else {},
        "window_days": window_days,
        "days": all_day_hits,
        "matched_days": len(all_day_hits),
        "score": round(score, 4),
        "logic": top,
        "scheme_id": scheme.get("id") or "",
        "scheme_name": scheme.get("name") or "",
    }
