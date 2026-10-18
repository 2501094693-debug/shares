"""横截面统计：逐指标排名、百分位、行业中位数/均值/分位、行业分化度。

输入 ``companies`` = ``[{code, name, metrics:{...}}, ...]``（已算好快照），
输出按 ``registry.INDICATORS`` 组织好的基准与排名，供渲染与前端直接消费。
"""

from __future__ import annotations

from statistics import mean, median
from typing import Any

from company.analysis.competition.registry import INDICATORS, Indicator, get_indicator


def _percentile_sorted(sorted_vals: list[float], q: float) -> float | None:
    """线性插值分位（q∈[0,1]）。"""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _valid_values(companies: list[dict[str, Any]], key: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for c in companies:
        v = (c.get("metrics") or {}).get(key)
        if isinstance(v, (int, float)) and v == v:  # 排除 None / NaN
            out.append((c.get("code") or "", float(v)))
    return out


def rank_metric(
    companies: list[dict[str, Any]], indicator: Indicator
) -> dict[str, dict[str, Any]]:
    """对单个数值型指标算 rank / percentile。

    ``higher``/``neutral`` 按值降序排（大值在前），``lower`` 按升序排（小值在前）。
    neutral 也给出排序位置仅作参考，调用方不应将其当作优劣。
    返回 ``{code: {rank, percentile}}``；缺失样本不入榜。
    """
    valid = _valid_values(companies, indicator.key)
    out: dict[str, dict[str, Any]] = {}
    if len(valid) < 2:
        for code, _ in valid:
            out[code] = {"rank": 1 if valid else None, "percentile": 100.0 if valid else None}
        return out

    reverse = indicator.direction != "lower"
    ordered = sorted(valid, key=lambda kv: kv[1], reverse=reverse)
    n = len(ordered)
    for i, (code, _) in enumerate(ordered):
        rank = i + 1
        percentile = round((n - rank) / (n - 1) * 100, 1)
        out[code] = {"rank": rank, "percentile": percentile}
    return out


def industry_stats(companies: list[dict[str, Any]], indicator: Indicator) -> dict[str, Any]:
    """单个指标的行业基准：中位数/均值/极值/四分位。"""
    values = sorted(v for _, v in _valid_values(companies, indicator.key))
    if not values:
        return {
            "count": 0,
            "median": None,
            "mean": None,
            "min": None,
            "max": None,
            "p25": None,
            "p75": None,
            "iqr": None,
        }
    med = median(values)
    p25 = _percentile_sorted(values, 0.25)
    p75 = _percentile_sorted(values, 0.75)
    iqr = (p75 - p25) if p25 is not None and p75 is not None else None
    return {
        "count": len(values),
        "median": round(med, 4),
        "mean": round(mean(values), 4),
        "min": round(values[0], 4),
        "max": round(values[-1], 4),
        "p25": round(p25, 4) if p25 is not None else None,
        "p75": round(p75, 4) if p75 is not None else None,
        "iqr": round(iqr, 4) if iqr is not None else None,
    }


def _dispersion_level(stats: dict[str, Any]) -> str:
    """用 IQR/|median| 粗判行业分化度。分母过小或样本过少不评。"""
    iqr = stats.get("iqr")
    med = stats.get("median")
    if iqr is None or med is None or stats.get("count", 0) < 3 or abs(med) < 1e-9:
        return "—"
    ratio = abs(iqr / med)
    if ratio >= 1.0:
        return "高"
    if ratio >= 0.4:
        return "中"
    return "低"


def build_benchmark(
    companies: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """返回 ``(benchmark, ranks, dispersion)``。

    - ``benchmark``  ``{key: stats}``；
    - ``ranks``      ``{key: {code: {rank, percentile}}}``（仅数值指标）；
    - ``dispersion`` ``{key: {level, iqr_over_median}}``。
    """
    benchmark: dict[str, Any] = {}
    ranks: dict[str, Any] = {}
    dispersion: dict[str, Any] = {}
    for ind in INDICATORS:
        if ind.unit == "text":
            continue
        stats = industry_stats(companies, ind)
        benchmark[ind.key] = stats
        ranks[ind.key] = rank_metric(companies, ind)
        if ind.unit in {"pct", "x", "day"}:
            level = _dispersion_level(stats)
            ratio = (
                round(abs((stats.get("iqr") or 0) / stats["median"]), 3)
                if stats.get("iqr") is not None and stats.get("median")
                else None
            )
            dispersion[ind.key] = {"level": level, "iqr_over_median": ratio}
    return benchmark, ranks, dispersion


def rank_companies_by_score(companies: list[dict[str, Any]]) -> dict[str, int]:
    """按综合评分降序排名，同分按风险命中数升序；缺分数排在最后。"""
    def _key(item: dict[str, Any]) -> tuple:
        score = item.get("score_total")
        hits = item.get("metrics", {}).get("risk_hits")
        has_score = 0 if isinstance(score, (int, float)) else 1
        score_val = -(score if isinstance(score, (int, float)) else 0)
        hits_val = hits if isinstance(hits, (int, float)) else 999
        return (has_score, score_val, hits_val)

    ordered = sorted(companies, key=_key)
    return {c.get("code") or "": i + 1 for i, c in enumerate(ordered)}


def target_position(
    companies: list[dict[str, Any]],
    target_code: str,
    ranks: dict[str, Any],
) -> dict[str, Any]:
    """目标公司在各维度上的落位：优势指标 / 劣势指标 / 综合排名。"""
    target = next((c for c in companies if c.get("code") == target_code), None)
    if not target:
        return {}
    score_rank_map = rank_companies_by_score(companies)
    n = len(companies)

    strengths: list[str] = []
    weaknesses: list[str] = []
    by_indicator: dict[str, Any] = {}
    for ind in INDICATORS:
        if ind.unit == "text":
            continue
        info = (ranks.get(ind.key) or {}).get(target_code)
        if not info or info.get("percentile") is None:
            continue
        pct = info["percentile"]
        by_indicator[ind.key] = {
            "label": ind.label,
            "value": (target.get("metrics") or {}).get(ind.key),
            "rank": info.get("rank"),
            "percentile": pct,
            "direction": ind.direction,
        }
        if ind.direction == "neutral":
            continue
        rank = info.get("rank")
        if pct >= 70:
            strengths.append(f"{ind.label}（行业第 {rank}/{n}）")
        elif pct <= 30:
            weaknesses.append(f"{ind.label}（行业第 {rank}/{n}）")

    return {
        "code": target_code,
        "name": target.get("name") or target_code,
        "score_total": target.get("score_total"),
        "score_rank": score_rank_map.get(target_code),
        "of": n,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "by_indicator": by_indicator,
    }


def mark_vs_median(
    companies: list[dict[str, Any]], benchmark: dict[str, Any]
) -> dict[str, dict[str, str]]:
    """每个公司每个指标相对行业中位数的标记：高于 / 低于 / 持平 / —。"""
    out: dict[str, dict[str, str]] = {}
    for c in companies:
        code = c.get("code") or ""
        marks: dict[str, str] = {}
        for ind in INDICATORS:
            if ind.unit == "text":
                continue
            v = (c.get("metrics") or {}).get(ind.key)
            med = (benchmark.get(ind.key) or {}).get("median")
            if not isinstance(v, (int, float)) or med is None:
                marks[ind.key] = "—"
            elif abs(v - med) < 1e-9:
                marks[ind.key] = "持平"
            elif v > med:
                marks[ind.key] = "高于"
            else:
                marks[ind.key] = "低于"
        out[code] = marks
    return out


def indicator_meta(key: str) -> Indicator | None:
    return get_indicator(key)
