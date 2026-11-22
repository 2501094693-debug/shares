"""综合分：前低均分 + 股指反向日占比分。"""

from __future__ import annotations

from typing import Any

from analysis.macd.config import DEFAULT_W_DIV, DEFAULT_W_PRIOR


def _clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def composite_score(
    *,
    score_close: float | None,
    score_low: float | None,
    reverse_count: int | None,
    range_days: int | None,
    w_prior: float = DEFAULT_W_PRIOR,
    w_div: float = DEFAULT_W_DIV,
) -> dict[str, Any]:
    """合成总分。

    - ``S_prior = 0.5 * S_close + 0.5 * S_low``（缺一侧则用另一侧）
    - ``S_idx   = reverse_count / range_days * 100``
    - ``S_total = w_prior * clip(S_prior) + w_div * S_idx``
    """
    wp = float(w_prior)
    wd = float(w_div)
    total_w = wp + wd
    if total_w <= 0:
        wp, wd, total_w = DEFAULT_W_PRIOR, DEFAULT_W_DIV, 1.0
    wp, wd = wp / total_w, wd / total_w

    sc = _num(score_close)
    sl = _num(score_low)
    if sc is not None and sl is not None:
        s_prior = 0.5 * sc + 0.5 * sl
    elif sc is not None:
        s_prior = sc
    elif sl is not None:
        s_prior = sl
    else:
        s_prior = None

    days = int(range_days or 0)
    rev = int(reverse_count or 0)
    if days > 0:
        s_idx = rev / days * 100.0
    else:
        s_idx = None

    if s_prior is None and s_idx is None:
        total = None
    elif s_prior is None:
        total = _clip(float(s_idx))
    elif s_idx is None:
        total = _clip(float(s_prior))
    else:
        total = wp * _clip(float(s_prior)) + wd * _clip(float(s_idx))

    return {
        "score_close": None if sc is None else round(sc, 2),
        "score_low": None if sl is None else round(sl, 2),
        "score_prior": None if s_prior is None else round(s_prior, 2),
        "reverse_count": rev if days > 0 else None,
        "range_days": days if days > 0 else None,
        "div_score": None if s_idx is None else round(s_idx, 2),
        "score_total": None if total is None else round(total, 2),
        "w_prior": round(wp, 4),
        "w_div": round(wd, 4),
    }


__all__ = ["composite_score"]
