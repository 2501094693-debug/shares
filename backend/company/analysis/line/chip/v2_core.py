"""筹码 V2：双池（未知 U + 已知 K）+ 分时分价注入 + 三种衰减。

- U：beg 之前筹码，形状未知，只记剩余股数；初始 = 自由流通股 F
- K：beg 起由分钟成交构建的价位分布（绝对股数）
- 每日：分时得 new（合计 V）→ 按存量比拆 V_u/V_k → U 减标量、K 按衰减扣量 → K += new
- 展示只基于 K；守恒 U + sum(K) = F
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import numpy as np

from company.analysis.line.chip.core import (
    DEFAULT_BINS,
    MAX_BINS,
    MIN_BINS,
    prepare_rows,
    summarize_chips,
)

SHARES_PER_LOT = 100.0
DEFAULT_DECAY_MODE = "uniform"
DECAY_MODES = ("uniform", "profit", "cut")
_EPS = 1e-9


def normalize_decay_mode(value: Any) -> str:
    key = str(value or "").strip().lower()
    aliases = {
        "": DEFAULT_DECAY_MODE,
        "auto": DEFAULT_DECAY_MODE,
        "even": "uniform",
        "avg": "uniform",
        "平均": "uniform",
        "均匀": "uniform",
        "profit_first": "profit",
        "获利": "profit",
        "获利优先": "profit",
        "cut_first": "cut",
        "loss": "cut",
        "割肉": "cut",
        "割肉优先": "cut",
    }
    if key in DECAY_MODES:
        return key
    return aliases.get(key, DEFAULT_DECAY_MODE)


def make_grid_range(
    lo: float,
    hi: float,
    bins: int = DEFAULT_BINS,
) -> tuple[np.ndarray, np.ndarray]:
    """按价格区间建网格。"""
    if not np.isfinite(lo) or not np.isfinite(hi):
        raise ValueError("价格区间无效")
    if hi <= lo:
        hi = lo + max(0.01, abs(lo) * 0.001)
    try:
        n = int(bins)
    except (TypeError, ValueError):
        n = DEFAULT_BINS
    n = max(MIN_BINS, min(MAX_BINS, n))
    edges = np.linspace(float(lo), float(hi), n + 1, dtype=float)
    centers = (edges[:-1] + edges[1:]) / 2.0
    return edges, centers


def _shares_of(row: Mapping[str, Any]) -> float:
    """分钟行 → 股数。``volume`` / ``volume_lots`` 为手；若有 cum 差分痕迹也按手×100。"""
    for key in ("volume_shares", "shares"):
        raw = row.get(key)
        if raw is not None:
            try:
                number = float(raw)
            except (TypeError, ValueError):
                number = 0.0
            if number > 0:
                return number
    lots = row.get("volume_lots")
    if lots is None:
        lots = row.get("volume")
    try:
        number = float(lots or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if number <= 0:
        return 0.0
    # 分时接口对外 volume 已是「手」
    return number * SHARES_PER_LOT


def intraday_volume_hist(
    trends: Iterable[Mapping[str, Any]],
    edges: np.ndarray,
) -> np.ndarray:
    """分钟价量落入价格网格，返回各箱绝对股数；合计为 0 报错。"""
    edges_arr = np.asarray(edges, dtype=float)
    if len(edges_arr) < 2:
        raise ValueError("价格网格无效")
    hist = np.zeros(len(edges_arr) - 1, dtype=float)
    for row in trends or []:
        if not isinstance(row, Mapping):
            continue
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            continue
        if not np.isfinite(price):
            continue
        shares = _shares_of(row)
        if shares <= 0:
            continue
        idx = int(np.searchsorted(edges_arr, price, side="right") - 1)
        idx = max(0, min(len(hist) - 1, idx))
        hist[idx] += shares
    total = float(hist.sum())
    if total <= 0:
        raise ValueError("分时成交量为 0，无法构建当日筹码")
    return hist


def take_from_known(
    chips: np.ndarray,
    centers: np.ndarray,
    close: float,
    volume: float,
    mode: Any = DEFAULT_DECAY_MODE,
) -> np.ndarray:
    """从已知池 K 按衰减模式扣掉 ``volume`` 股，返回扣后的副本。"""
    out = np.asarray(chips, dtype=float).copy()
    need = float(volume)
    if need <= 0:
        return out
    total = float(out.sum())
    if total <= 0:
        return out
    if need >= total - _EPS:
        out[:] = 0.0
        return out

    key = normalize_decay_mode(mode)
    if key == "uniform":
        out *= 1.0 - need / total
        out[out < 0] = 0.0
        return out

    close_n = float(close)
    tick = float(centers[1] - centers[0]) if len(centers) > 1 else 0.0
    eps = max(tick * 0.5, abs(close_n) * 1e-8, 1e-9)
    profit = centers < close_n - eps
    loss = centers > close_n + eps
    neutral = ~(profit | loss)

    if key == "profit":
        order = (profit, loss, neutral)
    else:  # cut
        order = (loss, profit, neutral)

    for mask in order:
        if need <= _EPS:
            break
        if not bool(mask.any()):
            continue
        pool = float(out[mask].sum())
        if pool <= _EPS:
            continue
        take = min(need, pool)
        out[mask] *= 1.0 - take / pool
        need -= take

    out[out < 0] = 0.0
    return out


def split_volume(v: float, unknown: float, known: float) -> tuple[float, float]:
    """按存量比例拆 V → (V_u, V_k)；K=0 时全从 U。"""
    volume = max(0.0, float(v))
    u = max(0.0, float(unknown))
    k = max(0.0, float(known))
    pool = u + k
    if volume <= 0 or pool <= _EPS:
        return 0.0, 0.0
    if volume > pool:
        volume = pool
    if k <= _EPS:
        return volume, 0.0
    if u <= _EPS:
        return 0.0, volume
    v_u = volume * u / pool
    v_k = volume - v_u
    return v_u, v_k


def run_chip_v2(
    rows: Iterable[dict[str, Any]],
    day_trends: Mapping[str, Iterable[Mapping[str, Any]]],
    *,
    float_shares: float,
    bins: int = DEFAULT_BINS,
    decay_mode: Any = DEFAULT_DECAY_MODE,
    with_history: bool = True,
    price_lo: float | None = None,
    price_hi: float | None = None,
) -> dict[str, Any]:
    """双池推演。

    Parameters
    ----------
    rows
        窗口内日线（需 date/close/low/high）。
    day_trends
        ``date -> 分钟行列表``；缺日或量为 0 时由 ``intraday_volume_hist`` 报错。
    float_shares
        自由流通股 F，初始 U。
    """
    data = prepare_rows(rows)
    if not data:
        raise ValueError("无有效日线（缺少 open/high/low/close）")
    try:
        f_shares = float(float_shares)
    except (TypeError, ValueError) as exc:
        raise ValueError("自由流通股无效") from exc
    if not np.isfinite(f_shares) or f_shares <= 0:
        raise ValueError("自由流通股须 > 0")

    mode = normalize_decay_mode(decay_mode)
    lo = min(float(r["low"]) for r in data)
    hi = max(float(r["high"]) for r in data)
    if price_lo is not None and np.isfinite(price_lo):
        lo = min(lo, float(price_lo))
    if price_hi is not None and np.isfinite(price_hi):
        hi = max(hi, float(price_hi))
    # 分时价也可能越出日线高低
    for day, trends in (day_trends or {}).items():
        for row in trends or []:
            if not isinstance(row, Mapping):
                continue
            try:
                price = float(row.get("price"))
            except (TypeError, ValueError):
                continue
            if np.isfinite(price):
                lo = min(lo, price)
                hi = max(hi, price)

    edges, centers = make_grid_range(lo, hi, bins)
    unknown = f_shares
    known = np.zeros_like(centers, dtype=float)
    history: list[dict[str, Any]] = []

    for row in data:
        date = row["date"]
        trends = day_trends.get(date) if day_trends else None
        if not trends:
            raise ValueError(f"{date} 缺少分时成交")
        try:
            new_hist = intraday_volume_hist(trends, edges)
        except ValueError as exc:
            raise ValueError(f"{date} {exc}") from exc

        v = float(new_hist.sum())
        pool = unknown + float(known.sum())
        if v > pool + _EPS:
            # 成交超过存量：钳到存量并同比缩放 new，保证加回=扣出
            scale = pool / v if v > 0 else 0.0
            new_hist = new_hist * scale
            v = float(new_hist.sum())

        v_u, v_k = split_volume(v, unknown, float(known.sum()))
        unknown = max(0.0, unknown - v_u)
        known = take_from_known(known, centers, float(row["close"]), v_k, mode)
        known = known + new_hist

        # 数值漂移：把总量拉回 F（优先微调 U）
        known_sum = float(known.sum())
        drift = f_shares - (unknown + known_sum)
        if abs(drift) > 1e-3:
            unknown = max(0.0, unknown + drift)

        if not with_history:
            continue
        if known_sum <= _EPS:
            # 首日若 V 全来自 U，加回后 known 应 > 0；仍空则跳过统计
            continue
        stats = summarize_chips(known, centers, float(row["close"]), with_peaks=False)
        stats.update(
            date=date,
            turnover=row.get("turnover"),
            volume=v,
            volume_from_unknown=v_u,
            volume_from_known=v_k,
            unknown_shares=unknown,
            known_shares=float(known.sum()),
            low=float(row["low"]),
            high=float(row["high"]),
        )
        history.append(stats)

    known_sum = float(known.sum())
    if known_sum <= _EPS:
        raise ValueError("已知筹码为空（窗口内无有效成交注入）")
    final = summarize_chips(known, centers, float(data[-1]["close"]), with_peaks=True)
    final.update(
        date=data[-1]["date"],
        turnover=data[-1].get("turnover"),
        unknown_shares=unknown,
        known_shares=known_sum,
    )
    return {
        "centers": centers,
        "edges": edges,
        "chips": known.copy(),
        "chips_share": known / known_sum,
        "tick": float(edges[1] - edges[0]),
        "stats": final,
        "peaks": final.get("peaks") or [],
        "history": history,
        "rows": len(data),
        "decay_mode": mode,
        "unknown_shares": unknown,
        "known_shares": known_sum,
        "float_shares": f_shares,
    }
