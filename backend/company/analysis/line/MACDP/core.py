"""MACDP：成交均价 + 成交量加权快慢线 + 固定信号线。

与标准 MACD 的差异::

    均价_t     = 成交额_t / 成交量_t
    α_fast,t   = V_t / (前 fast 日成交量之和 + V_t)
    α_slow,t   = V_t / (前 slow 日成交量之和 + V_t)
    DIF        = EMA_vol(均价, fast) − EMA_vol(均价, slow)
    α_dea      = 1 / (signal + 1)                 # 固定，不跟量
    DEA        = EMA_fixed(DIF, signal)
    MACD       = 2 × (DIF − DEA)                 # 柱线 ×2（A 股习惯）

成交量均匀时快慢线 α → 1/(N+1)，与 DEA 口径一致；比经典 2/(N+1) 更钝。
纯函数，无网络依赖。
"""

from __future__ import annotations

from typing import Any

from core.fmt import to_float

DEFAULT_FAST = 10
DEFAULT_SLOW = 20
DEFAULT_SIGNAL = 7


def _iso(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 8:
        raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def _bar_date(bar: dict[str, Any]) -> str:
    return str(bar.get("time") or bar.get("date") or "")[:10]


def _typical_price(bar: dict[str, Any]) -> float | None:
    """缺成交额时的兜底：典型价 (H+L+C)/3，再退到收盘价。"""
    high = to_float(bar.get("high"))
    low = to_float(bar.get("low"))
    close = to_float(bar.get("close"))
    if (
        high is not None
        and low is not None
        and close is not None
        and high > 0
        and low > 0
        and close > 0
    ):
        return (float(high) + float(low) + float(close)) / 3.0
    if close is not None and close > 0:
        return float(close)
    return None


def _avg_price(bar: dict[str, Any]) -> float | None:
    """成交均价 = 成交额 / 成交量；单位不对时尝试「手→股」。

    腾讯等源日K常缺 ``amount``（或只有换手率列）时，退回典型价，
    量加权 α 仍可用，避免整段 MACDP 空白。
    """
    amount = to_float(bar.get("amount"))
    volume = to_float(bar.get("volume"))
    low = to_float(bar.get("low"))
    high = to_float(bar.get("high"))

    def _in_band(px: float) -> bool:
        if low is None or high is None or low <= 0 or high <= 0:
            return True
        return low * 0.9 <= px <= high * 1.1

    if amount is not None and volume is not None and amount > 0 and volume > 0:
        price = amount / volume
        if _in_band(price):
            return float(price)
        # volume 常为「手」：再试 ÷(手×100)
        price100 = amount / (volume * 100.0)
        if _in_band(price100):
            return float(price100)

    return _typical_price(bar)


def _volume(bar: dict[str, Any]) -> float | None:
    v = to_float(bar.get("volume"))
    if v is None or v <= 0:
        return None
    return float(v)


def _vol_ema(
    prices: list[float | None],
    volumes: list[float | None],
    period: int,
) -> list[float | None]:
    """成交量加权 EMA。

    - 前 ``period`` 根有效 bar：以成交量加权均价（VWAP）为种子
    - 其后：``α = V_t / (前 period 日成交量之和 + V_t)``，
      ``EMA_t = α·P_t + (1−α)·EMA_{t−1}``
    - 价格或成交量缺失则打断，重新攒满 ``period``
    """
    if period <= 0:
        raise ValueError(f"period 须为正整数，收到 {period!r}")
    n = len(prices)
    out: list[float | None] = [None] * n
    if n == 0:
        return out

    seed_p: list[float] = []
    seed_v: list[float] = []
    prev: float | None = None
    # 已纳入递推链的最近成交量（最多 period 根，供「前 N 日」求和）
    vol_hist: list[float] = []

    for i in range(n):
        p = prices[i]
        v = volumes[i]
        if p is None or v is None:
            seed_p, seed_v = [], []
            prev = None
            vol_hist = []
            continue

        if prev is None:
            seed_p.append(p)
            seed_v.append(v)
            if len(seed_p) < period:
                continue
            sv = sum(seed_v)
            if sv <= 0:
                seed_p, seed_v = [], []
                continue
            prev = sum(pi * vi for pi, vi in zip(seed_p, seed_v)) / sv
            out[i] = prev
            vol_hist = list(seed_v)
            seed_p, seed_v = [], []
            continue

        prior = vol_hist[-period:] if len(vol_hist) >= period else list(vol_hist)
        s = sum(prior)
        denom = s + v
        alpha = (v / denom) if denom > 0 else 0.0
        if alpha > 1.0:
            alpha = 1.0
        elif alpha < 0.0:
            alpha = 0.0
        prev = alpha * p + (1.0 - alpha) * prev
        out[i] = prev
        vol_hist.append(v)
        if len(vol_hist) > period:
            vol_hist = vol_hist[-period:]
    return out


def _fixed_ema(values: list[float | None], period: int) -> list[float | None]:
    """固定系数 EMA：``α = 1/(period+1)``；首值取前 ``period`` 个有效值的 SMA。"""
    if period <= 0:
        raise ValueError(f"period 须为正整数，收到 {period!r}")
    n = len(values)
    out: list[float | None] = [None] * n
    if n == 0:
        return out

    alpha = 1.0 / (period + 1)
    window: list[float] = []
    prev: float | None = None

    for i, raw in enumerate(values):
        if raw is None:
            window = []
            prev = None
            continue
        v = float(raw)
        if prev is None:
            window.append(v)
            if len(window) < period:
                continue
            prev = sum(window) / period
            out[i] = prev
            window = []
        else:
            prev = alpha * v + (1.0 - alpha) * prev
            out[i] = prev
    return out


def compute_macdp(
    bars: list[dict[str, Any]],
    beg: str,
    end: str = "",
    *,
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    signal: int = DEFAULT_SIGNAL,
) -> dict[str, Any]:
    """在已排序日线序列上计算 MACDP，只输出 ``[beg, end]`` 内交易日。

    ``bars`` 宜含 ``beg`` 之前足够暖机数据，且需有 ``amount`` / ``volume``。
    """
    if not bars:
        raise ValueError("无日线数据")
    if fast <= 0 or slow <= 0 or signal <= 0:
        raise ValueError(
            f"fast/slow/signal 须为正整数，收到 fast={fast}, slow={slow}, signal={signal}"
        )
    if fast >= slow:
        raise ValueError(f"快线时长须小于慢线时长: fast={fast} >= slow={slow}")

    beg_iso = _iso(beg)
    end_iso = _iso(end) if end else "9999-12-31"
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")

    ordered = sorted(bars, key=_bar_date)
    prices = [_avg_price(b) for b in ordered]
    volumes = [_volume(b) for b in ordered]

    ema_fast = _vol_ema(prices, volumes, fast)
    ema_slow = _vol_ema(prices, volumes, slow)
    dif_series: list[float | None] = []
    for a, b in zip(ema_fast, ema_slow):
        if a is None or b is None:
            dif_series.append(None)
        else:
            dif_series.append(a - b)
    dea_series = _fixed_ema(dif_series, signal)

    items: list[dict[str, Any]] = []
    for i, bar in enumerate(ordered):
        d = _bar_date(bar)
        if not d or d < beg_iso or d > end_iso:
            continue
        dif = dif_series[i]
        dea = dea_series[i]
        hist = None if dif is None or dea is None else 2.0 * (dif - dea)
        px = prices[i]
        vol = volumes[i]
        items.append(
            {
                "date": d,
                "price": None if px is None else round(px, 6),
                "volume": None if vol is None else round(vol, 4),
                "ema_fast": None if ema_fast[i] is None else round(float(ema_fast[i]), 6),
                "ema_slow": None if ema_slow[i] is None else round(float(ema_slow[i]), 6),
                "dif": None if dif is None else round(dif, 6),
                "dea": None if dea is None else round(dea, 6),
                "macd": None if hist is None else round(hist, 6),
            }
        )

    if not items:
        raise ValueError(f"区间 [{beg_iso}, {end_iso if end else '最新'}] 无交易日")

    used_end = items[-1]["date"]
    return {
        "beg": beg_iso,
        "end": used_end,
        "input_end": _iso(end) if end else None,
        "fast": int(fast),
        "slow": int(slow),
        "signal": int(signal),
        "price": "avg",
        "price_label": "成交均价",
        "alpha": "vol_weighted",
        "dea_alpha": "1/(signal+1)",
        "count": len(items),
        "items": items,
        "latest": dict(items[-1]),
    }
