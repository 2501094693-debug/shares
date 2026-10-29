"""筹码分布（CYQ）推演引擎。

同花顺手机端在个股日线上看到的筹码分布，本质是用日线 OHLC + 换手率滚动
推演：

1. 首日：全部流通筹码按当日三角分布落在 ``[low, high]`` 上；
2. 之后每天：旧筹码按换手率 ``t`` 衰减为 ``chips * (1 - t)``，
   当日成交筹码按三角分布注入 ``chips * t``；
3. 三角分布的峰值口径由 ``peak`` 决定（见 ``PEAK_MODES``）：``avg`` 取
   成交额/成交量，即通达信 / 同花顺客户端口径，也是默认值；``ohlc4`` 取
   ``(O+H+L+C)/4``；``typical`` 取 ``(H+L+C)/3``；``close`` 取收盘价；
4. 对分布做分位数统计：获利比例、平均成本、70% / 90% 成本区间、
   集中度与筹码峰。

输入行的 ``turnover`` 为百分数（0.31 表示 0.31%），``volume`` 为股。
换手率缺失时由调用方先补齐；这里只做纯计算，不访问网络。
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np

DEFAULT_BINS = 200
DEFAULT_DECAY = 1.0
# 三角峰位置口径：avg=成交额/成交量（通达信、同花顺客户端口径）
DEFAULT_PEAK = "avg"
PEAK_MODES = ("avg", "ohlc4", "typical", "close")
MIN_BINS = 20
MAX_BINS = 2000
# 筹码峰合并阈值：价格相差 0.2% 以内视为同一个峰
_PEAK_MERGE = 0.002


def _f(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """把外部行收成引擎要的字段；价格缺失或区间异常返回 None。"""
    close = _f(row.get("close"))
    high = _f(row.get("high"))
    low = _f(row.get("low"))
    open_ = _f(row.get("open"))
    if close is None or high is None or low is None or close <= 0:
        return None
    if low > high:
        low, high = high, low
    if high <= 0:
        return None
    date = str(row.get("date") or "").strip()[:10]
    if not date:
        return None
    if open_ is None or open_ <= 0:
        open_ = close
    turnover = _f(row.get("turnover"))
    volume = _f(row.get("volume")) or 0.0
    return {
        "date": date,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": max(0.0, volume),
        "amount": _f(row.get("amount")),
        "turnover": turnover,
    }


def prepare_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        row = normalize_row(raw)
        if row is not None:
            out.append(row)
    out.sort(key=lambda r: r["date"])
    return out


def make_grid(
    rows: list[dict[str, Any]],
    bins: int = DEFAULT_BINS,
) -> tuple[np.ndarray, np.ndarray]:
    """价格网格：区间覆盖全部日线的 ``[min low, max high]``。"""
    if not rows:
        raise ValueError("无日线数据")
    lo = min(float(r["low"]) for r in rows)
    hi = max(float(r["high"]) for r in rows)
    if not np.isfinite(lo) or not np.isfinite(hi):
        raise ValueError("日线价格无效")
    if hi <= lo:
        hi = lo + max(0.01, abs(lo) * 0.001)
    try:
        n = int(bins)
    except (TypeError, ValueError):
        n = DEFAULT_BINS
    n = max(MIN_BINS, min(MAX_BINS, n))
    edges = np.linspace(lo, hi, n + 1, dtype=float)
    centers = (edges[:-1] + edges[1:]) / 2.0
    return edges, centers


def normalize_peak(value: Any) -> str:
    """把外部传入的峰值口径收成 ``PEAK_MODES`` 之一；未知值回落到默认。"""
    mode = str(value or "").strip().lower()
    if mode in ("", "auto", "none"):
        return DEFAULT_PEAK
    if mode in ("amount", "vwap", "mean", "average"):
        return "avg"
    if mode in ("ohlc", "ohlc4", "mean4"):
        return "ohlc4"
    if mode in ("tp", "typical", "hlc3"):
        return "typical"
    if mode in ("close", "last"):
        return "close"
    return DEFAULT_PEAK


def _avg_price(row: dict[str, Any]) -> float | None:
    """成交均价 = 成交额 / 成交量；单位不一致或越界时返回 None。"""
    amount = _f(row.get("amount"))
    volume = _f(row.get("volume"))
    if amount is None or volume is None or amount <= 0 or volume <= 0:
        return None
    price = amount / volume
    low = float(row["low"])
    high = float(row["high"])
    # 成交额/成交量单位对不上（如「手」当「股」）会差一个数量级，直接弃用
    if price < low * 0.9 or price > high * 1.1:
        return None
    return price


def peak_price(row: dict[str, Any], mode: Any = DEFAULT_PEAK) -> float:
    """当日成交分布三角峰的位置（元），并夹在 ``[low, high]`` 内。"""
    low = float(row["low"])
    high = float(row["high"])
    close = float(row["close"])
    open_ = float(row.get("open") or close)
    key = normalize_peak(mode)
    if key == "close":
        price = close
    elif key == "typical":
        price = (high + low + close) / 3.0
    elif key == "ohlc4":
        price = (open_ + high + low + close) / 4.0
    else:  # avg：成交均价，通达信 / 同花顺客户端口径
        price = _avg_price(row)
        if price is None:
            price = (open_ + high + low + close) / 4.0
    return min(max(price, low), high)


def triangle_weights(
    row: dict[str, Any],
    centers: np.ndarray,
    *,
    peak: Any = DEFAULT_PEAK,
) -> np.ndarray:
    """当日成交在价格轴上的三角分布权重（已归一，和为 1）。"""
    low = float(row["low"])
    high = float(row["high"])
    close = float(row["close"])
    apex = peak_price(row, peak)

    weights = np.zeros_like(centers, dtype=float)
    inside = (centers >= low) & (centers <= high)
    if not bool(inside.any()):
        nearest = int(np.argmin(np.abs(centers - close)))
        weights[nearest] = 1.0
        return weights

    left = inside & (centers <= apex)
    right = inside & (centers >= apex)
    if apex > low:
        weights[left] = np.clip(1.0 - (apex - centers[left]) / (apex - low), 0.0, 1.0)
    else:
        weights[left] = 1.0
    if high > apex:
        weights[right] = np.clip(1.0 - (centers[right] - apex) / (high - apex), 0.0, 1.0)
    else:
        weights[right] = 1.0

    total = float(weights.sum())
    if total <= 0:
        nearest = int(np.argmin(np.abs(centers - close)))
        weights[:] = 0.0
        weights[nearest] = 1.0
        return weights
    return weights / total


def _turnover_fraction(row: dict[str, Any], decay: float) -> float:
    turn = _f(row.get("turnover"))
    if turn is None or turn <= 0:
        return 0.0
    return min(1.0, max(0.0, turn / 100.0 * decay))


def _quantile(cum: np.ndarray, centers: np.ndarray, q: float) -> float:
    if not len(cum) or float(cum[-1]) <= 0:
        return 0.0
    return float(np.interp(float(q), cum, centers))


def _peaks(
    chips: np.ndarray,
    centers: np.ndarray,
    cum: np.ndarray,
    *,
    top: int = 5,
    min_share: float = 0.02,
) -> list[dict[str, float]]:
    """找出筹码峰：局部极大且占比 ≥ ``min_share``，按筹码量降序。"""
    if not len(chips):
        return []
    peak_value = float(chips.max())
    if peak_value <= 0:
        return []
    picks: list[int] = []
    for i in range(len(chips)):
        if chips[i] < peak_value * min_share:
            continue
        left = max(0, i - 2)
        right = min(len(chips), i + 3)
        if chips[i] >= float(chips[left:right].max()):
            picks.append(i)
    picks.sort(key=lambda i: -float(chips[i]))
    out: list[dict[str, float]] = []
    for i in picks:
        price = float(centers[i])
        if any(abs(price - item["price"]) <= max(0.01, price * _PEAK_MERGE) for item in out):
            continue
        out.append({
            "price": price,
            "weight": float(chips[i]),
            "cum": float(cum[i]),
        })
        if len(out) >= top:
            break
    return out


def summarize_chips(
    chips: np.ndarray,
    centers: np.ndarray,
    close: float,
    *,
    with_peaks: bool = True,
) -> dict[str, Any]:
    """对某一天的筹码分布做统计。``chips`` 可以是未归一化的量。"""
    values = np.asarray(chips, dtype=float)
    total = float(values.sum())
    if not len(values) or total <= 0:
        raise ValueError("筹码总量为 0")
    weights = values / total
    cum = np.cumsum(weights)
    # 分箱中心落在收盘价上方半格以内时，该箱仍覆盖收盘价（一字板 high=low=close 常见）
    tick = float(centers[1] - centers[0]) if len(centers) > 1 else 0.0
    profit_limit = float(close) + tick * 0.5 + 1e-9
    cost70_low = _quantile(cum, centers, 0.15)
    cost70_high = _quantile(cum, centers, 0.85)
    cost90_low = _quantile(cum, centers, 0.05)
    cost90_high = _quantile(cum, centers, 0.95)
    denom70 = cost70_low + cost70_high
    denom90 = cost90_low + cost90_high
    stats: dict[str, Any] = {
        "close": float(close),
        "profit_ratio": float(weights[centers <= profit_limit].sum()),
        "avg_cost": float((centers * weights).sum()),
        "median": _quantile(cum, centers, 0.5),
        "cost70_low": cost70_low,
        "cost70_high": cost70_high,
        "cost90_low": cost90_low,
        "cost90_high": cost90_high,
        "concentration70": (cost70_high - cost70_low) / denom70 if denom70 else 0.0,
        "concentration90": (cost90_high - cost90_low) / denom90 if denom90 else 0.0,
        "peak": float(centers[int(np.argmax(weights))]),
    }
    if with_peaks:
        stats["peaks"] = _peaks(weights, centers, cum)
    return stats


def run_chip(
    rows: Iterable[dict[str, Any]],
    *,
    bins: int = DEFAULT_BINS,
    decay: float = DEFAULT_DECAY,
    peak: Any = DEFAULT_PEAK,
    with_history: bool = True,
) -> dict[str, Any]:
    """按日线迭代筹码分布。

    Parameters
    ----------
    bins
        价格分箱数。
    decay
        换手衰减系数：当日有效换手 = ``min(1, 换手率/100 × decay)``。
        通达信 / 同花顺默认 1.0，调大后历史筹码消散更快。
    peak
        三角峰位置口径，见 ``PEAK_MODES``；默认 ``avg``（成交均价）。
    with_history
        False 时只推演末日分布、跳过逐日统计（快照 / 标定用）。

    Returns
    -------
    dict
        ``centers`` 价格轴、``chips`` 末日筹码（和为 1）、``stats`` 末日统计、
        ``history`` 每个交易日的统计序列、``peaks`` 末日筹码峰、
        ``tick`` 网格步长、``peak`` 实际使用的峰值口径。
    """
    data = prepare_rows(rows)
    if not data:
        raise ValueError("无有效日线（缺少 open/high/low/close）")
    try:
        decay_n = float(decay)
    except (TypeError, ValueError):
        decay_n = DEFAULT_DECAY
    if decay_n <= 0:
        raise ValueError("decay 须 > 0")
    peak_key = normalize_peak(peak)

    edges, centers = make_grid(data, bins)
    chips = np.zeros_like(centers, dtype=float)
    history: list[dict[str, Any]] = []

    for index, row in enumerate(data):
        weights = triangle_weights(row, centers, peak=peak_key)
        if index == 0:
            chips = weights
        else:
            t = _turnover_fraction(row, decay_n)
            if row["volume"] > 0 and t > 0:
                chips = chips * (1.0 - t) + weights * t
        if not with_history:
            continue
        total = float(chips.sum())
        if total <= 0:
            continue
        weights_n = chips / total
        cum = np.cumsum(weights_n)
        stats = summarize_chips(weights_n, centers, float(row["close"]), with_peaks=False)
        stats.update(
            date=row["date"],
            turnover=row.get("turnover"),
            volume=row.get("volume") or 0.0,
            low=float(row["low"]),
            high=float(row["high"]),
        )
        history.append(stats)

    if float(chips.sum()) <= 0:
        raise ValueError("筹码分布为空")
    if with_history and not history:
        raise ValueError("筹码分布为空")
    final = summarize_chips(chips, centers, float(data[-1]["close"]), with_peaks=True)
    final.update(date=data[-1]["date"], turnover=data[-1].get("turnover"))
    return {
        "centers": centers,
        "edges": edges,
        "chips": chips / float(chips.sum()),
        "tick": float(edges[1] - edges[0]),
        "stats": final,
        "peaks": final.get("peaks") or [],
        "history": history,
        "rows": len(data),
        "peak": peak_key,
    }
