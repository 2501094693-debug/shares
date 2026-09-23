"""日线条件：规范化与匹配。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from analysis.decline.bars import normalize_date
from analysis.shares.config import RANGE_FIELDS
from core.fmt import to_float


def _bound(raw: Any) -> float | None:
    return to_float(raw)


def normalize_day_spec(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """把前端/CLI 传来的单日条件收成标准结构；无有效约束则返回 None。"""
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
        if lo is not None:
            spec[f"{field}_min"] = lo
            has_rule = True
        if hi is not None:
            spec[f"{field}_max"] = hi
            has_rule = True

    if not has_rule:
        return None
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
    return sorted(by_date.values(), key=lambda s: s["date"])


def has_active_rules(spec: dict[str, Any]) -> bool:
    for field in RANGE_FIELDS:
        if spec.get(f"{field}_min") is not None or spec.get(f"{field}_max") is not None:
            return True
    return False


def match_metrics(metrics: dict[str, Any] | None, spec: dict[str, Any]) -> bool:
    """单日指标是否满足该日全部约束。"""
    if metrics is None:
        return False

    for field in RANGE_FIELDS:
        lo = spec.get(f"{field}_min")
        hi = spec.get(f"{field}_max")
        if lo is None and hi is None:
            continue
        value = metrics.get(field)
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


def specs_fingerprint(specs: list[dict[str, Any]]) -> str:
    """条件指纹，用作任务 / 缓存 key。"""
    payload = json.dumps(specs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def describe_spec(spec: dict[str, Any]) -> str:
    """人类可读的单日条件摘要。"""
    parts: list[str] = []
    for field in RANGE_FIELDS:
        lo = spec.get(f"{field}_min")
        hi = spec.get(f"{field}_max")
        if lo is None and hi is None:
            continue
        if lo is not None and hi is not None:
            parts.append(f"{field}[{lo},{hi}]")
        elif lo is not None:
            parts.append(f"{field}>={lo}")
        else:
            parts.append(f"{field}<={hi}")
    return ", ".join(parts) or "(空)"
