"""MACD 金叉 / 即将金叉判定（纯函数）。

四类信号（任一命中即可入选）：

- 水下金叉 / 即将水下金叉：``DEA < 0``
- 水上金叉 / 即将水上金叉：``DEA ≥ 0``

已金叉：昨 ``DIF < DEA``，今 ``DIF ≥ DEA``。
即将金叉：今仍 ``DIF < DEA`` 且缺口收窄，并满足以下任一：
按最近两日速度外推下一交易日会金叉（``pred_next_gap <= 0``），
或相对缺口 ``(DEA-DIF)/(|DEA|+ε) <= near_ratio``。
"""

from __future__ import annotations

from typing import Any, Sequence

from analysis.macd.config import DEFAULT_NEAR_RATIO

SIGNAL_UNDER_CROSS = "水下金叉"
SIGNAL_UNDER_NEAR = "即将水下金叉"
SIGNAL_OVER_CROSS = "水上金叉"
SIGNAL_OVER_NEAR = "即将水上金叉"

# 展示优先级：已金叉 > 即将；同级水下优先（任意固定序即可）
SIGNAL_PRIORITY: tuple[str, ...] = (
    SIGNAL_UNDER_CROSS,
    SIGNAL_OVER_CROSS,
    SIGNAL_UNDER_NEAR,
    SIGNAL_OVER_NEAR,
)

_EPS = 1e-8


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n == n else None  # NaN guard


def gap_velocity(
    dif: float,
    dea: float,
    prev_dif: float,
    prev_dea: float,
) -> tuple[float, float, float]:
    """返回 ``(当前缺口, 上一缺口, 收窄速度)``。

    缺口为 ``DEA - DIF``；速度 = 上一缺口 - 当前缺口，正数代表收窄。
    """
    gap_t = float(dea) - float(dif)
    gap_prev = float(prev_dea) - float(prev_dif)
    return gap_t, gap_prev, gap_prev - gap_t


def relative_gap(dif: float, dea: float) -> float:
    """相对缺口 ``(DEA − DIF) / (|DEA| + ε)``；仅在 DIF < DEA 时有意义。"""
    return (float(dea) - float(dif)) / (abs(float(dea)) + _EPS)


def classify_macd_cross(
    items: Sequence[dict[str, Any]],
    *,
    near_ratio: float = DEFAULT_NEAR_RATIO,
) -> dict[str, Any]:
    """根据 MACD 日序列最新两根判定金叉 / 即将金叉。

    ``items`` 为 ``compute_macd`` 的输出（按日期升序，含 ``dif`` / ``dea``）。
    无有效信号时 ``matched=False``、``signals=[]``。
    """
    theta = abs(float(near_ratio))
    empty = {
        "matched": False,
        "signals": [],
        "primary": None,
        "date": None,
        "prev_date": None,
        "dif": None,
        "dea": None,
        "prev_dif": None,
        "prev_dea": None,
        "rel_gap": None,
        "gap_narrowing": None,
        "gap_velocity": None,
        "pred_next_gap": None,
        "pred_next_cross": None,
        "near_by_prediction": None,
        "near_by_relative_gap": None,
        "near_ratio": theta,
        "underwater": None,
    }
    if len(items) < 2:
        return empty

    cur = items[-1]
    prev = items[-2]
    dif = _num(cur.get("dif"))
    dea = _num(cur.get("dea"))
    prev_dif = _num(prev.get("dif"))
    prev_dea = _num(prev.get("dea"))
    if None in (dif, dea, prev_dif, prev_dea):
        return empty

    date = str(cur.get("date") or "")[:10] or None
    prev_date = str(prev.get("date") or "")[:10] or None
    underwater = dea < 0.0
    gap_t, gap_prev, velocity = gap_velocity(dif, dea, prev_dif, prev_dea)
    narrowing = velocity > 0.0
    rel = relative_gap(dif, dea) if dif < dea else 0.0
    pred_next_gap = gap_t - velocity
    pred_next_cross = pred_next_gap <= 0.0
    near_by_prediction = pred_next_cross
    near_by_relative_gap = rel <= theta

    signals: list[str] = []
    # 已金叉优先
    if prev_dif < prev_dea and dif >= dea:
        signals.append(SIGNAL_UNDER_CROSS if underwater else SIGNAL_OVER_CROSS)
    elif dif < dea and narrowing and (near_by_prediction or near_by_relative_gap):
        signals.append(SIGNAL_UNDER_NEAR if underwater else SIGNAL_OVER_NEAR)

    primary = None
    if signals:
        for key in SIGNAL_PRIORITY:
            if key in signals:
                primary = key
                break

    return {
        "matched": bool(signals),
        "signals": signals,
        "primary": primary,
        "date": date,
        "prev_date": prev_date,
        "dif": round(dif, 6),
        "dea": round(dea, 6),
        "prev_dif": round(prev_dif, 6),
        "prev_dea": round(prev_dea, 6),
        "rel_gap": round(rel, 6) if dif < dea else None,
        "gap_narrowing": narrowing if dif < dea else None,
        "gap_velocity": round(velocity, 6) if dif < dea else None,
        "pred_next_gap": round(pred_next_gap, 6) if dif < dea else None,
        "pred_next_cross": pred_next_cross if dif < dea else None,
        "near_by_prediction": near_by_prediction if dif < dea else None,
        "near_by_relative_gap": near_by_relative_gap if dif < dea else None,
        "near_ratio": theta,
        "underwater": underwater,
    }


__all__ = [
    "SIGNAL_OVER_CROSS",
    "SIGNAL_OVER_NEAR",
    "SIGNAL_PRIORITY",
    "SIGNAL_UNDER_CROSS",
    "SIGNAL_UNDER_NEAR",
    "classify_macd_cross",
    "gap_velocity",
    "relative_gap",
]
