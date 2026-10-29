"""筹码参数标定：用同花顺客户端读数反解 decay 与三角峰口径。

同花顺没有公开筹码分布接口，所以「和客户端尽量一致」只能拿客户端上肉眼可见
的几个读数当基准——平均成本、获利比例、70% / 90% 成本区间、筹码峰——再对
``decay``（换手衰减系数）× ``peak``（三角峰位置口径）做网格搜索，取加权误差
最小的组合。

用法（CLI）::

    python -m company.analysis.line.chip 001216 --end 2026-10-29 \
        --target-avg-cost 21.5 --target-profit-ratio 62 \
        --target-cost90-low 15.2 --target-cost90-high 27.8

用法（HTTP）::

    GET /api/stocks/line-chip/calibrate?code=001216&end=2026-10-29&avg_cost=21.5
"""

from __future__ import annotations

from typing import Any, Iterable

from company.analysis.line.chip.core import (
    DEFAULT_BINS,
    DEFAULT_PEAK,
    PEAK_MODES,
    normalize_peak,
    run_chip,
)
from company.analysis.line.chip.service import _resolve_day, _today, load_daily

# 通达信 / 同花顺的「历史换手衰减系数」常见档位；1.0 是客户端默认
DEFAULT_DECAYS = (0.6, 0.8, 1.0, 1.2, 1.5, 1.8, 2.0)

# 基准字段：(权重, 是否按相对误差)。比例类用绝对误差，价格类用相对误差。
_TARGETS: dict[str, tuple[float, bool]] = {
    "avg_cost": (3.0, True),
    "profit_ratio": (2.0, False),
    "median": (1.5, True),
    "peak": (1.5, True),
    "cost70_low": (1.0, True),
    "cost70_high": (1.0, True),
    "cost90_low": (0.8, True),
    "cost90_high": (0.8, True),
    "concentration70": (1.0, False),
    "concentration90": (1.0, False),
}

TARGET_KEYS = tuple(_TARGETS)
STAT_KEYS = (
    "close",
    "profit_ratio",
    "avg_cost",
    "median",
    "peak",
    "cost70_low",
    "cost70_high",
    "cost90_low",
    "cost90_high",
    "concentration70",
    "concentration90",
)


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _ratio(value: Any) -> float | None:
    """获利比例 / 集中度可能是 0~1，也可能是百分数。"""
    number = _num(value)
    if number is None:
        return None
    if abs(number) > 1.5:
        number /= 100.0
    return number


def normalize_targets(targets: dict[str, Any] | None) -> dict[str, float]:
    """过滤并归一化基准读数；未知字段、空值、非数字一律丢弃。"""
    out: dict[str, float] = {}
    for key, value in (targets or {}).items():
        spec = _TARGETS.get(key)
        if spec is None or value is None or value == "":
            continue
        number = _num(value) if spec[1] else _ratio(value)
        if number is None:
            continue
        out[key] = float(number)
    return out


def _error(stats: dict[str, Any], targets: dict[str, float]) -> float:
    """加权均方根误差：价格类按相对误差，比例类按绝对误差。"""
    acc = 0.0
    weight_sum = 0.0
    for key, target in targets.items():
        weight, relative = _TARGETS[key]
        actual = _num(stats.get(key))
        if actual is None:
            continue
        if relative:
            err = abs(actual - target) / max(abs(target), 1e-9)
        else:
            err = abs(actual - target)
        acc += weight * err * err
        weight_sum += weight
    if weight_sum <= 0:
        return float("inf")
    return (acc / weight_sum) ** 0.5


def _decay_list(decays: Iterable[Any] | None) -> list[float]:
    out: list[float] = []
    for item in decays or ():
        number = _num(item)
        if number is not None and number > 0:
            out.append(round(float(number), 4))
    return list(dict.fromkeys(out))


def _peak_list(peaks: Iterable[Any] | None) -> list[str]:
    out = [normalize_peak(item) for item in (peaks or PEAK_MODES)]
    return list(dict.fromkeys(out))


def _stats_snapshot(stats: dict[str, Any]) -> dict[str, float | None]:
    return {key: (round(float(stats[key]), 6) if _num(stats.get(key)) is not None else None)
            for key in STAT_KEYS}


def _diff(stats: dict[str, Any], targets: dict[str, float]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for key, target in targets.items():
        actual = _num(stats.get(key))
        out[key] = None if actual is None else round(actual - target, 6)
    return out


def fit_rows(
    rows: list[dict[str, Any]],
    *,
    targets: dict[str, Any] | None = None,
    decays: Iterable[Any] | None = None,
    peaks: Iterable[Any] | None = None,
    bins: int = DEFAULT_BINS,
    top: int = 8,
) -> dict[str, Any]:
    """纯计算版标定：给定日线行做网格搜索，不碰网络（单测 / 复用）。"""
    goal = normalize_targets(targets)
    if not goal:
        raise ValueError("至少给一个基准读数：" + " / ".join(TARGET_KEYS))
    if not rows:
        raise ValueError("无日线数据")
    decay_list = _decay_list(decays) or list(DEFAULT_DECAYS)
    peak_list = _peak_list(peaks)

    results: list[dict[str, Any]] = []
    for peak in peak_list:
        for decay in decay_list:
            out = run_chip(
                rows,
                bins=bins,
                decay=decay,
                peak=peak,
                with_history=False,
            )
            stats = out["stats"]
            results.append({
                "peak": peak,
                "decay": round(float(decay), 4),
                "score": round(_error(stats, goal), 6),
                "stats": _stats_snapshot(stats),
                "diff": _diff(stats, goal),
            })
    results.sort(key=lambda item: item["score"])
    return {
        "targets": goal,
        "best": results[0],
        "candidates": results[: max(1, int(top or 1))],
        "grid": {"bins": int(bins), "decays": decay_list, "peaks": peak_list},
    }


def calibrate(
    code: str,
    *,
    end: str = "",
    targets: dict[str, Any] | None = None,
    decays: Iterable[Any] | None = None,
    peaks: Iterable[Any] | None = None,
    bins: int = DEFAULT_BINS,
    source: str = "auto",
    top: int = 8,
) -> dict[str, Any]:
    """网格搜索 (decay, peak)，返回按误差升序的候选表与最优组合。"""
    end_iso = _resolve_day(end) or _today()
    pack = load_daily(code, end=end_iso, source=source)
    rows = [row for row in pack["items"] if row["date"] <= end_iso]
    if not rows:
        raise ValueError(f"{code} 在 {end_iso} 之前无日线")

    fitted = fit_rows(
        rows,
        targets=targets,
        decays=decays,
        peaks=peaks,
        bins=bins,
        top=top,
    )
    return {
        "symbol": str(pack.get("code") or code),
        "name": str(pack.get("name") or ""),
        "source": str(pack.get("source") or ""),
        "adjust": "none",
        "date": str(rows[-1]["date"]),
        "end": end_iso,
        "start": str(pack.get("start") or rows[0]["date"]),
        "rows": len(rows),
        "defaults": {"decay": 1.0, "peak": DEFAULT_PEAK},
        **fitted,
    }
