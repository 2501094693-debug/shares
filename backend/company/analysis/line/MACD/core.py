"""MACD 纯函数计算。

标准公式（A 股常用柱线 ×2）::

    EMA_fast = EMA(price, fast)
    EMA_slow = EMA(price, slow)
    DIF      = EMA_fast - EMA_slow          # 快线 / 差离值
    DEA      = EMA(DIF, signal)             # 慢线 / 信号线
    MACD     = 2 * (DIF - DEA)              # 柱线

默认参数：fast=10, slow=20, signal=7；价格序列默认收盘价。
纯函数，无网络依赖，便于单测。
"""

from __future__ import annotations

from typing import Any

from core.fmt import to_float

DEFAULT_FAST = 10
DEFAULT_SLOW = 20
DEFAULT_SIGNAL = 7

PRICE_OPTIONS: tuple[str, ...] = ("close", "open", "high", "low")
PRICE_LABELS: dict[str, str] = {
    "close": "收盘价",
    "open": "开盘价",
    "high": "最高价",
    "low": "最低价",
}


def _iso(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 8:
        raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def _bar_date(bar: dict[str, Any]) -> str:
    return str(bar.get("time") or bar.get("date") or "")[:10]


def _ema(values: list[float | None], period: int) -> list[float | None]:
    """指数移动平均：首值取前 ``period`` 个有效价的 SMA，其后按标准 EMA 递推。

    无效价（None）位置输出 None，且打断递推（需重新攒满 period）。
    """
    if period <= 0:
        raise ValueError(f"period 须为正整数，收到 {period!r}")
    n = len(values)
    out: list[float | None] = [None] * n
    if n == 0:
        return out

    alpha = 2.0 / (period + 1)
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


def _extract_prices(
    bars: list[dict[str, Any]],
    price: str,
) -> list[float | None]:
    out: list[float | None] = []
    for bar in bars:
        v = to_float(bar.get(price))
        out.append(float(v) if v is not None and v > 0 else None)
    return out


def compute_macd(
    bars: list[dict[str, Any]],
    beg: str,
    end: str = "",
    *,
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    signal: int = DEFAULT_SIGNAL,
    price: str = "close",
) -> dict[str, Any]:
    """在已排序日线序列上计算 MACD，只输出 ``[beg, end]`` 内交易日。

    - ``bars`` 宜包含 ``beg`` 之前足够的暖机数据（至少约 ``slow + signal`` 根）
    - ``beg`` / ``end``：``YYYY-MM-DD`` 或 ``YYYYMMDD``；``end`` 空则用序列最后一根
    - ``price``：``close`` / ``open`` / ``high`` / ``low``
    """
    if not bars:
        raise ValueError("无日线数据")
    if fast <= 0 or slow <= 0 or signal <= 0:
        raise ValueError(
            f"fast/slow/signal 须为正整数，收到 fast={fast}, slow={slow}, signal={signal}"
        )
    if fast >= slow:
        raise ValueError(f"快线时长须小于慢线时长: fast={fast} >= slow={slow}")
    price_key = str(price or "close").strip().lower()
    if price_key not in PRICE_OPTIONS:
        raise ValueError(
            f"price 须为 {PRICE_OPTIONS} 之一，收到 {price!r}"
        )

    beg_iso = _iso(beg)
    end_iso = _iso(end) if end else "9999-12-31"
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")

    ordered = sorted(bars, key=_bar_date)
    prices = _extract_prices(ordered, price_key)

    ema_fast = _ema(prices, fast)
    ema_slow = _ema(prices, slow)
    dif_series: list[float | None] = []
    for a, b in zip(ema_fast, ema_slow):
        if a is None or b is None:
            dif_series.append(None)
        else:
            dif_series.append(a - b)
    dea_series = _ema(dif_series, signal)

    items: list[dict[str, Any]] = []
    for i, bar in enumerate(ordered):
        d = _bar_date(bar)
        if not d or d < beg_iso or d > end_iso:
            continue
        dif = dif_series[i]
        dea = dea_series[i]
        hist = None if dif is None or dea is None else 2.0 * (dif - dea)
        px = prices[i]
        items.append(
            {
                "date": d,
                "price": None if px is None else round(px, 6),
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
        "price": price_key,
        "price_label": PRICE_LABELS[price_key],
        "count": len(items),
        "items": items,
        # 最新一根摘要，便于 CLI / 前端一眼看结果
        "latest": dict(items[-1]),
    }
