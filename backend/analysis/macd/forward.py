"""信号日后最大收盘涨幅 / 最高价涨幅（纯函数 + 拉数）。

基准：信号日收盘价。
区间：信号日（含）→ 最新交易日（或指定 asof）。
"""

from __future__ import annotations

from typing import Any

from core.codes import normalize_code
from core.fmt import to_float
from company.analysis.line.undulate.service import _bar_date, _fetch_day_range, _iso, _today_iso


def max_forward_gains_from_bars(
    bars: list[dict[str, Any]],
    *,
    signal_date: str,
    asof: str = "",
) -> dict[str, Any]:
    """在已排序日线上算最大收盘/最高价涨幅。

    - ``max_close_gain`` = max(close / base − 1)
    - ``max_high_gain``  = max(high / base − 1)
    - ``base`` = 信号日收盘
    """
    sig = _iso(signal_date)
    end_iso = _iso(asof) if str(asof or "").strip() else "9999-12-31"

    empty = {
        "signal_date": sig,
        "base_date": None,
        "base_close": None,
        "asof": None,
        "hold_days": 0,
        "max_close_gain": None,
        "max_close_date": None,
        "max_close_price": None,
        "max_high_gain": None,
        "max_high_date": None,
        "max_high_price": None,
        "last_close": None,
        "last_close_gain": None,
        "last_date": None,
    }
    if not bars:
        return empty

    ordered = sorted(bars, key=_bar_date)
    base_bar: dict[str, Any] | None = None
    window: list[dict[str, Any]] = []
    for bar in ordered:
        d = _bar_date(bar)
        if not d:
            continue
        if d == sig:
            base_bar = bar
        if sig <= d <= end_iso:
            window.append(bar)

    if base_bar is None or not window:
        return empty

    base = to_float(base_bar.get("close"))
    if base is None or base == 0:
        return empty

    max_close_gain: float | None = None
    max_close_date: str | None = None
    max_close_price: float | None = None
    max_high_gain: float | None = None
    max_high_date: str | None = None
    max_high_price: float | None = None

    for bar in window:
        d = _bar_date(bar)
        close = to_float(bar.get("close"))
        high = to_float(bar.get("high"))
        if close is not None:
            g = close / base - 1.0
            if max_close_gain is None or g > max_close_gain:
                max_close_gain = g
                max_close_date = d
                max_close_price = close
        if high is not None:
            g = high / base - 1.0
            if max_high_gain is None or g > max_high_gain:
                max_high_gain = g
                max_high_date = d
                max_high_price = high

    last = window[-1]
    last_close = to_float(last.get("close"))
    last_date = _bar_date(last)
    last_gain = None if last_close is None else last_close / base - 1.0

    def _r(v: float | None) -> float | None:
        return None if v is None else round(float(v), 6)

    return {
        "signal_date": sig,
        "base_date": sig,
        "base_close": round(base, 4),
        "asof": last_date,
        "hold_days": len(window),
        "max_close_gain": _r(max_close_gain),
        "max_close_date": max_close_date,
        "max_close_price": None if max_close_price is None else round(max_close_price, 4),
        "max_high_gain": _r(max_high_gain),
        "max_high_date": max_high_date,
        "max_high_price": None if max_high_price is None else round(max_high_price, 4),
        "last_close": None if last_close is None else round(last_close, 4),
        "last_close_gain": _r(last_gain),
        "last_date": last_date,
    }


def max_forward_gains(
    code: str,
    *,
    signal_date: str,
    adjust: str = "qfq",
    asof: str = "",
) -> dict[str, Any]:
    """拉日线后计算；失败时返回空涨幅字段。"""
    norm = normalize_code(code)
    sig = _iso(signal_date)
    end_iso = _iso(asof) if str(asof or "").strip() else _today_iso()
    if not norm:
        return max_forward_gains_from_bars([], signal_date=sig, asof=end_iso)
    try:
        pack = _fetch_day_range(norm, beg_iso=sig, end_iso=end_iso, adjust=adjust)
    except Exception:  # noqa: BLE001
        return max_forward_gains_from_bars([], signal_date=sig, asof=end_iso)
    items = list(pack.get("items") or [])
    return max_forward_gains_from_bars(items, signal_date=sig, asof=end_iso)


__all__ = ["max_forward_gains", "max_forward_gains_from_bars"]
