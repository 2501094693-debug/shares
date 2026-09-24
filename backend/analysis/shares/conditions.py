"""日线条件：规范化与匹配（单日/多日 与或非）。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from analysis.decline.bars import normalize_date
from analysis.shares.config import RANGE_FIELDS
from core.fmt import to_float

LOGIC_AND = "and"
LOGIC_OR = "or"
LOGIC_NOT = "not"
LOGIC_CHOICES = (LOGIC_AND, LOGIC_OR, LOGIC_NOT)


def _bound(raw: Any) -> float | None:
    return to_float(raw)


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


def normalize_logic(raw: Any = None) -> str:
    """组合逻辑：and（与）/ or（或）/ not（非，即全部不满足 / NOR）。"""
    value = str(raw or LOGIC_AND).strip().lower()
    if value in ("or", "any", "|", "||"):
        return LOGIC_OR
    if value in ("not", "nor", "none", "!", "~", "no"):
        return LOGIC_NOT
    return LOGIC_AND


def normalize_join(raw: Any = None) -> str:
    """二元连接：and（与）/ or（或）。非（¬）是一元取反，不用作连接符。"""
    value = str(raw or LOGIC_AND).strip().lower()
    if value in ("or", "any", "|", "||"):
        return LOGIC_OR
    return LOGIC_AND


def _active_fields(spec: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for field in RANGE_FIELDS:
        if spec.get(f"{field}_min") is not None or spec.get(f"{field}_max") is not None:
            fields.append(field)
    return fields


def _field_join_of(spec: dict[str, Any], field: str) -> str | None:
    raw = spec.get(f"{field}_join")
    if raw is None:
        raw = spec.get(f"{field}_op")
    if raw is None:
        return None
    return normalize_join(raw)


def has_field_joins(spec: dict[str, Any]) -> bool:
    fields = _active_fields(spec)
    return any(_field_join_of(spec, field) is not None for field in fields[1:])


def has_day_joins(specs: list[dict[str, Any]]) -> bool:
    return any(spec.get("join") is not None for spec in (specs or [])[1:])


def combine_bools(values: list[bool], joins: list[str] | None = None, logic: Any = None) -> bool:
    """按逐段 join（左结合）或统一 logic 组合布尔值。"""
    if not values:
        return True
    if joins is not None and len(joins) == len(values) - 1:
        acc = bool(values[0])
        for flag, join in zip(values[1:], joins):
            if normalize_join(join) == LOGIC_OR:
                acc = acc or bool(flag)
            else:
                acc = acc and bool(flag)
        return acc
    mode = normalize_logic(logic)
    if mode == LOGIC_OR:
        return any(values)
    if mode == LOGIC_NOT:
        return not any(values)
    return all(values)


def normalize_day_spec(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """把前端/CLI 传来的单日条件收成标准结构；无有效约束则返回 None。

    额外字段：
    - ``logic``：本日字段统一组合 and / or / not（无逐字段 join 时）
    - ``{field}_join``：该字段与「上一已填字段」的连接 and / or
    - ``join``：本条件日与「上一条件日」的连接 and / or
    - ``not``：本日结果取反（多日组合前）
    - ``{field}_not``：该字段区间判定取反
    """
    if not isinstance(raw, dict):
        return None

    date = normalize_date(raw.get("date") or raw.get("day") or "")
    if not date:
        return None

    spec: dict[str, Any] = {"date": date}
    has_rule = False

    for field in RANGE_FIELDS:
        lo = _bound(raw.get(f"{field}_min") if f"{field}_min" in raw else raw.get(f"min_{field}"))
        hi = _bound(raw.get(f"{field}_max") if f"{field}_max" in raw else raw.get(f"max_{field}"))
        # 也支持 {"amplitude": {"min": 1, "max": 5}} 简写
        nested = raw.get(field)
        if isinstance(nested, dict):
            if lo is None:
                lo = _bound(nested.get("min"))
            if hi is None:
                hi = _bound(nested.get("max"))
            if nested.get("not") is not None and f"{field}_not" not in raw:
                if _as_bool(nested.get("not"), False):
                    spec[f"{field}_not"] = True
            if nested.get("join") is not None and f"{field}_join" not in raw:
                spec[f"{field}_join"] = normalize_join(nested.get("join"))
        if lo is not None:
            spec[f"{field}_min"] = lo
            has_rule = True
        if hi is not None:
            spec[f"{field}_max"] = hi
            has_rule = True
        if lo is not None or hi is not None:
            if _as_bool(raw.get(f"{field}_not"), False):
                spec[f"{field}_not"] = True
            join_raw = raw.get(f"{field}_join")
            if join_raw is None:
                join_raw = raw.get(f"{field}_op")
            if join_raw is not None:
                spec[f"{field}_join"] = normalize_join(join_raw)

    if not has_rule:
        return None

    if not has_field_joins(spec):
        field_logic = normalize_logic(raw.get("logic"))
        if field_logic != LOGIC_AND:
            spec["logic"] = field_logic
    if raw.get("join") is not None:
        spec["join"] = normalize_join(raw.get("join"))
    if _as_bool(raw.get("not"), False):
        spec["not"] = True
    return spec


def normalize_day_specs(raw_days: Any) -> list[dict[str, Any]]:
    """多日条件列表；同一日期后写覆盖先写；无规则日丢弃。"""
    if not isinstance(raw_days, list):
        return []
    by_date: dict[str, dict[str, Any]] = {}
    for item in raw_days:
        spec = normalize_day_spec(item)
        if spec is None:
            continue
        by_date[spec["date"]] = spec
    specs = sorted(by_date.values(), key=lambda s: s["date"])
    if specs and "join" in specs[0]:
        # 按日期排序后的首日不参与「与前日连接」
        specs[0] = {k: v for k, v in specs[0].items() if k != "join"}
    return specs


def has_active_rules(spec: dict[str, Any]) -> bool:
    for field in RANGE_FIELDS:
        if spec.get(f"{field}_min") is not None or spec.get(f"{field}_max") is not None:
            return True
    return False


def _field_in_range(value: Any, lo: Any, hi: Any) -> bool:
    if value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if lo is not None and number < float(lo):
        return False
    if hi is not None and number > float(hi):
        return False
    return True


def match_metrics(metrics: dict[str, Any] | None, spec: dict[str, Any]) -> bool:
    """单日指标是否满足该日字段约束（含逐字段连接 / 统一与或非；不含本日 ``not``）。"""
    if metrics is None:
        return False

    fields = _active_fields(spec)
    checks: list[bool] = []
    for field in fields:
        lo = spec.get(f"{field}_min")
        hi = spec.get(f"{field}_max")
        ok = _field_in_range(metrics.get(field), lo, hi)
        if spec.get(f"{field}_not"):
            ok = not ok
        checks.append(ok)

    if not checks:
        return True

    if has_field_joins(spec):
        joins = [_field_join_of(spec, field) or LOGIC_AND for field in fields[1:]]
        return combine_bools(checks, joins=joins)

    return combine_bools(checks, logic=spec.get("logic"))


def apply_day_not(matched: bool, spec: dict[str, Any]) -> bool:
    """应用本日结果取反。"""
    if spec.get("not"):
        return not matched
    return matched


def specs_fingerprint(specs: list[dict[str, Any]], logic: Any = None) -> str:
    """条件指纹，用作任务 / 缓存 key（含多日与或非 / 逐段连接）。"""
    payload = json.dumps(
        {"logic": normalize_logic(logic), "days": specs},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def describe_spec(spec: dict[str, Any]) -> str:
    """人类可读的单日条件摘要。"""
    parts: list[tuple[str, str]] = []
    for field in RANGE_FIELDS:
        lo = spec.get(f"{field}_min")
        hi = spec.get(f"{field}_max")
        if lo is None and hi is None:
            continue
        if lo is not None and hi is not None:
            text = f"{field}[{lo},{hi}]"
        elif lo is not None:
            text = f"{field}>={lo}"
        else:
            text = f"{field}<={hi}"
        if spec.get(f"{field}_not"):
            text = f"¬{text}"
        parts.append((field, text))
    if not parts:
        body = "(空)"
    elif has_field_joins(spec):
        body = parts[0][1]
        for field, text in parts[1:]:
            join = _field_join_of(spec, field) or LOGIC_AND
            body += (" ∨ " if join == LOGIC_OR else " ∧ ") + text
    else:
        texts = [text for _, text in parts]
        mode = normalize_logic(spec.get("logic"))
        if mode == LOGIC_OR:
            body = " ∨ ".join(texts)
        elif mode == LOGIC_NOT:
            body = "¬(" + " ∨ ".join(texts) + ")"
            if spec.get("not"):
                return "¬" + body
            return body
        else:
            body = " ∧ ".join(texts)
    if spec.get("not"):
        return f"¬({body})"
    return body


def describe_day_chain(specs: list[dict[str, Any]], logic: Any = None) -> str:
    """多日连接摘要：逐段 join 或统一 logic。"""
    if not specs:
        return "(空)"
    labels = [f"{s['date']}:{describe_spec(s)}" for s in specs]
    if has_day_joins(specs):
        body = labels[0]
        for spec, label in zip(specs[1:], labels[1:]):
            join = normalize_join(spec.get("join"))
            body += (" ∨ " if join == LOGIC_OR else " ∧ ") + label
        return body
    mode = normalize_logic(logic)
    if mode == LOGIC_OR:
        return " ∨ ".join(labels)
    if mode == LOGIC_NOT:
        return "¬(" + " ∨ ".join(labels) + ")"
    return " ∧ ".join(labels)
