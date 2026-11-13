"""相对估值：当前倍数 + 历史分位 + 同业对比。

复用现有能力：
- ``company.profile.get_stock_profile``：当前 PE/PB/PS（盘口）
- ``company.statistics.quote.fetch.fetch_pe_history``：历史每日 PE_TTM/PE静/PB/PS 序列
- 同业倍数由 engine 层用 ``fetch_pe_history`` 逐只取最新值后传入 ``peer_multiples``

结论只看「当前位置 vs 自身历史 / 同业」，不预测涨跌；与 DCF 内在价值互相校验。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.fmt import to_float


# 各倍数分位 → 定性结论（偏低好、偏高差）
def _history_verdict(percentile: float | None) -> str:
    if percentile is None:
        return "数据不足"
    if percentile <= 20:
        return "历史低估区"
    if percentile <= 40:
        return "历史偏低区"
    if percentile <= 60:
        return "历史合理区"
    if percentile <= 80:
        return "历史偏高区"
    return "历史高估区"


def _peer_verdict(discount_pct: float | None) -> str:
    if discount_pct is None:
        return "数据不足"
    if discount_pct <= -30:
        return "显著低于同业"
    if discount_pct <= -10:
        return "低于同业"
    if discount_pct < 10:
        return "与同业相当"
    if discount_pct < 30:
        return "高于同业"
    return "显著高于同业"


def _percentile(values: list[float], current: float | None) -> float | None:
    """current 在历史 values 中的分位（0~100）。"""
    if current is None or not values:
        return None
    below = sum(1 for v in values if v < current)
    equal = sum(1 for v in values if v == current)
    # 用「低于的比例 + 等于的一半」作分位，避免重复值把分位顶到两端
    return (below + 0.5 * equal) / len(values) * 100.0


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _stat_block(values: list[float], current: float | None) -> dict[str, Any]:
    vals = [v for v in values if v is not None]
    if not vals:
        return {
            "current": current,
            "median": None,
            "mean": None,
            "min": None,
            "max": None,
            "p25": None,
            "p75": None,
            "percentile": None,
            "samples": 0,
        }
    ordered = sorted(vals)
    n = len(ordered)

    def _q(p: float) -> float:
        # 线性插值分位数
        if n == 1:
            return ordered[0]
        idx = p * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return ordered[lo] * (1 - frac) + ordered[hi] * frac

    return {
        "current": round(current, 2) if current is not None else None,
        "median": round(_median(vals), 2),
        "mean": round(sum(vals) / n, 2),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
        "p25": round(_q(0.25), 2),
        "p75": round(_q(0.75), 2),
        "percentile": round(_percentile(vals, current), 2) if current is not None else None,
        "samples": n,
    }


@dataclass
class RelativeResult:
    """相对估值结果。倍数单位统一为「倍」。"""

    current: dict[str, Any] = field(default_factory=dict)        # 当前 PE/PB/PS
    history: dict[str, Any] = field(default_factory=dict)        # 各倍数历史统计与分位
    history_span: dict[str, Any] = field(default_factory=dict)   # 历史覆盖区间
    peers: dict[str, Any] = field(default_factory=dict)          # 同业倍数与对比
    history_verdict: str = "数据不足"
    peer_verdict: str = "数据不足"
    overall: str = "数据不足"
    notes: list[str] = field(default_factory=list)


_MULTIPLE_LABELS = {
    "pe_ttm": "市盈率TTM",
    "pe_static": "市盈率(静)",
    "pe_dyn": "市盈率(动)",
    "pb": "市净率",
    "ps_ttm": "市销率TTM",
}
# 只对能反映估值高低的核心倍数做历史定性
_CORE_MULTIPLES = ("pe_ttm", "pb", "ps_ttm")


def _current_from_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {}
    return {
        "pe_ttm": to_float(profile.get("pe_ttm")),
        "pe_static": to_float(profile.get("pe_static") or profile.get("pe")),
        "pe_dyn": to_float(profile.get("pe") or profile.get("pe_dyn")),
        "pb": to_float(profile.get("pb")),
        "ps_ttm": to_float(profile.get("ps_ttm")),
    }


def _history_from_pack(
    pe_history_pack: dict[str, Any] | None,
    current_override: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    items = list((pe_history_pack or {}).get("items") or [])
    # 只保留有效样本（至少有一个倍数）
    rows = [
        it
        for it in items
        if any(to_float(it.get(k)) is not None for k in _MULTIPLE_LABELS)
    ]
    override = current_override or {}
    stats: dict[str, Any] = {}
    for key in _MULTIPLE_LABELS:
        vals = [to_float(it.get(key)) for it in rows]
        vals = [v for v in vals if v is not None and v > 0]  # 负 PE 无经济含义，剔除
        # 当前值优先用盘口实时倍数；缺失才退回历史序列末值（时间升序）
        current = override.get(key)
        if current is None:
            current = vals[-1] if vals else None
        stats[key] = _stat_block(vals, current)
    span = {}
    if rows:
        span = {"start": rows[0].get("time"), "end": rows[-1].get("time"), "points": len(rows)}
    return stats, span


def _peer_block(
    current: dict[str, Any],
    peer_multiples: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """同业倍数中位数与目标公司相对定位。"""
    peers = list(peer_multiples or [])
    if not peers:
        return {}
    block: dict[str, Any] = {"count": len(peers), "multiples": {}}
    for key in ("pe_ttm", "pb", "ps_ttm"):
        peer_vals = [
            to_float(p.get(key)) for p in peers if to_float(p.get(key)) is not None and to_float(p.get(key)) > 0
        ]
        median = _median(peer_vals)
        cur = current.get(key)
        discount = None
        if median and cur is not None:
            discount = (cur - median) / median * 100.0  # 正=溢价，负=折价
        block["multiples"][key] = {
            "label": _MULTIPLE_LABELS[key],
            "peer_median": round(median, 2) if median is not None else None,
            "target": round(cur, 2) if cur is not None else None,
            "premium_pct": round(discount, 2) if discount is not None else None,
            "peer_samples": len(peer_vals),
            "verdict": _peer_verdict(discount),
        }
    # 采样明细（供前端展示）
    block["samples"] = [
        {
            "code": p.get("code"),
            "name": p.get("name"),
            "pe_ttm": to_float(p.get("pe_ttm")),
            "pb": to_float(p.get("pb")),
            "ps_ttm": to_float(p.get("ps_ttm")),
        }
        for p in peers
    ]
    return block


def relative_valuate(
    profile: dict[str, Any] | None,
    pe_history_pack: dict[str, Any] | None,
    *,
    peer_multiples: list[dict[str, Any]] | None = None,
) -> RelativeResult:
    """计算当前倍数、历史分位、同业对比，并给出相对估值定性结论。

    参数
    ----------
    profile: 个股盘口画像（含当前 PE/PB/PS）。
    pe_history_pack: ``fetch_pe_history`` 返回的历史序列包。
    peer_multiples: 同业各公司的当前倍数列表（engine 负责采集），可选。
    """
    notes: list[str] = []
    current = _current_from_profile(profile)
    history, span = _history_from_pack(pe_history_pack, current_override=current)

    # 当前倍数：优先用历史序列最新值（更贴近收盘口径），盘口缺失时回退历史
    for key in _MULTIPLE_LABELS:
        if current.get(key) is None and history.get(key, {}).get("current") is not None:
            current[key] = history[key]["current"]

    # 若缺当前倍数，用历史最新补进统计的 current
    for key in _MULTIPLE_LABELS:
        if history.get(key, {}).get("current") is None and current.get(key) is not None:
            history[key]["current"] = round(current[key], 2)

    peers = _peer_block(current, peer_multiples)

    # 综合历史定性：取核心倍数分位均值
    core_percentiles = [
        history[k]["percentile"]
        for k in _CORE_MULTIPLES
        if history.get(k, {}).get("percentile") is not None
    ]
    avg_percentile = sum(core_percentiles) / len(core_percentiles) if core_percentiles else None
    history_verdict = _history_verdict(avg_percentile)

    # 综合同业定性：取核心倍数溢价均值（负=折价=便宜）
    core_premiums = [
        peers["multiples"][k]["premium_pct"]
        for k in _CORE_MULTIPLES
        if peers.get("multiples", {}).get(k, {}).get("premium_pct") is not None
    ]
    avg_premium = sum(core_premiums) / len(core_premiums) if core_premiums else None
    peer_verdict = _peer_verdict(avg_premium)

    # 总体结论：优先看历史分位，同业作旁证
    if avg_percentile is None:
        overall = "数据不足"
    elif avg_percentile <= 30 and (avg_premium is None or avg_premium <= 10):
        overall = "相对低估"
    elif avg_percentile >= 70 and (avg_premium is None or avg_premium >= -10):
        overall = "相对高估"
    else:
        overall = "相对合理"

    if avg_percentile is None:
        notes.append("历史估值样本不足，历史分位不可靠")
    if not peers:
        notes.append("未采集同业倍数，同业对比为空")

    # 汇总平均分位与溢价，供上层展示
    if avg_percentile is not None:
        history["_summary"] = {
            "avg_percentile": round(avg_percentile, 2),
            "verdict": history_verdict,
        }
    if peers:
        peers["_summary"] = {
            "avg_premium_pct": round(avg_premium, 2) if avg_premium is not None else None,
            "verdict": peer_verdict,
        }

    return RelativeResult(
        current={k: (round(v, 2) if v is not None else None) for k, v in current.items()},
        history=history,
        history_span=span,
        peers=peers,
        history_verdict=history_verdict,
        peer_verdict=peer_verdict,
        overall=overall,
        notes=notes,
    )
