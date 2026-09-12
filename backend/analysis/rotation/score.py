"""当天轮动软评分：涨幅强度、上涨占比、进攻扩散，按总分排序。

涨幅强度 = 当天加权涨幅 / 近 20 个交易日（不含当天）样本标准差。
缺历史时按市值分档用绝对涨幅。得分大于 SCORE_NAMED 才记入「当天轮到」。
"""

from __future__ import annotations

import math
from typing import Any

from analysis.rotation.config import (
    CAP_MID_YI,
    CAP_WEIGHT_YI,
    SCORE_NAMED,
    SIGMA_FLOOR,
    SIGMA_MIN_DAYS,
    W_BREADTH,
    W_CHANGE,
    W_LIMIT,
)


def _clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _sat(value: float, scale: float) -> float:
    if scale <= 0 or value <= 0:
        return 0.0
    return 100.0 * (1.0 - math.exp(-value / scale))


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def trailing_sigma(prior: list[float]) -> float | None:
    """近 20 日加权涨幅的样本标准差；不足 10 日返回 None。"""
    n = len(prior)
    if n < SIGMA_MIN_DAYS:
        return None
    mean = sum(prior) / n
    var = sum((x - mean) ** 2 for x in prior) / (n - 1)
    return max(math.sqrt(max(var, 0.0)), SIGMA_FLOOR)


def _tier_scale(cap_tier: str) -> float:
    if cap_tier == "权重":
        return 1.0
    if cap_tier == "中盘":
        return 1.8
    return 2.8


def cap_tier_of(median_yi: float | None) -> str:
    yi = float(median_yi or 0.0)
    if yi >= CAP_WEIGHT_YI:
        return "权重"
    if yi >= CAP_MID_YI:
        return "中盘"
    return "题材"


def change_score(
    change_1d: float | None,
    *,
    sigma: float | None = None,
    cap_tier: str = "题材",
) -> float:
    """涨幅强度。有 σ 时用 涨幅/σ；约 1 倍中线，1.5～2 倍高分。"""
    chg = _num(change_1d)
    if chg is None:
        return 0.0
    if sigma is not None and sigma > 0:
        z = chg / sigma
        if z <= 0:
            return _clip(20.0 + z * 15.0)
        return _clip(_sat(z, 1.2))
    if chg <= 0:
        return _clip(20.0 + chg * 8.0)
    return _clip(_sat(chg, _tier_scale(cap_tier)))


def breadth_score(up: int, sample: int) -> float:
    """上涨家数 / 样本。"""
    if sample <= 0:
        return 0.0
    return _clip(100.0 * up / sample)


def thrust_score(strong: int, sample: int) -> float:
    """强势股只数 + 占样本比。权重大票按 2% 计，题材仍接近涨停。"""
    if sample <= 0:
        return 0.0
    n = max(0, strong)
    count_part = _sat(float(n), 1.2)
    ratio_part = _clip(450.0 * n / sample)
    return _clip(0.6 * count_part + 0.4 * ratio_part)


def combine(parts: dict[str, float]) -> float:
    total = (
        W_CHANGE * parts.get("change", 0.0)
        + W_BREADTH * parts.get("breadth", 0.0)
        + W_LIMIT * parts.get("limit", 0.0)
    )
    return round(_clip(total), 1)


def score_row(row: dict[str, Any], *, sigma: float | None = None) -> dict[str, Any]:
    sample = _int(row.get("sample_count"))
    up = _int(row.get("up_1d"))
    strong = _int(row.get("strong_1d"))
    if strong <= 0:
        strong = _int(row.get("limit_up_1d"))
    cap_tier = str(row.get("cap_tier") or "") or cap_tier_of(row.get("cap_median"))
    chg = _num(row.get("change_1d"))
    strength = None
    if chg is not None and sigma is not None and sigma > 0:
        strength = round(chg / sigma, 2)
    parts = {
        "change": round(change_score(chg, sigma=sigma, cap_tier=cap_tier), 1),
        "breadth": round(breadth_score(up, sample), 1),
        "limit": round(thrust_score(strong, sample), 1),
    }
    total = combine(parts)
    chg_text = f"{chg:+.1f}%" if chg is not None else "—"
    if strength is not None and sigma is not None:
        strength_text = f"强度 {chg_text}/σ{sigma:.1f}%={strength:.1f} {parts['change']:.0f}"
    else:
        strength_text = f"涨幅{chg_text} {parts['change']:.0f}"
    reason = (
        f"得分 {total:.0f}（{strength_text}，"
        f"上涨 {up}/{sample} {parts['breadth']:.0f}，"
        f"强势 {strong} {parts['limit']:.0f}）"
    )
    return {
        **row,
        "score": total,
        "scores": parts,
        "breadth": round(100.0 * up / sample, 1) if sample else 0.0,
        "strong_1d": strong,
        "cap_tier": cap_tier,
        "sigma_20": round(sigma, 2) if sigma is not None else None,
        "strength": strength,
        "named": total > SCORE_NAMED,
        "reason": reason,
    }
