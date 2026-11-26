"""信号日后涨跌：截止于 DIF≥DEA 后首个 DIF<DEA（纯函数）。

基准：信号日收盘价。
截止日：金叉确立后连续 ``DIF ≥ DEA`` 段之后**首次** ``DIF < DEA``；
若数据末尾仍未跌破，则截止日取序列最新交易日。

即将金叉：先判定后续是否真正金叉（``near_ok``）；不成立则 ``valid=False``，不给涨跌。
"""

from __future__ import annotations

from typing import Any, Sequence

from core.codes import normalize_code
from core.fmt import to_float
from company.analysis.line.gene.core import (
    break_day_close_change,
    find_dif_above_span,
    interval_close_extremes,
)
from company.analysis.line.undulate.service import _bar_date, _fetch_day_range, _iso, _today_iso
from company.analysis.line.MACD.core import compute_macd
from analysis.macd.config import DEFAULT_FAST, DEFAULT_SIGNAL, DEFAULT_SLOW


def _num(value: Any) -> float | None:
    v = to_float(value)
    if v is None:
        return None
    return float(v) if v == v else None


def _closes_by_date(bars: Sequence[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for bar in bars:
        d = _bar_date(bar)
        if not d:
            continue
        close = _num(bar.get("close"))
        if close is not None:
            out[d] = close
    return out


def _attach_closes(
    macd_items: Sequence[dict[str, Any]],
    closes_by_date: dict[str, float] | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in macd_items:
        d = str(row.get("date") or "")[:10]
        item = dict(row)
        close = None
        if closes_by_date and d in closes_by_date:
            close = closes_by_date[d]
        if close is None:
            close = _num(row.get("close"))
        if close is None:
            close = _num(row.get("price"))
        item["close"] = None if close is None else float(close)
        out.append(item)
    return out


def _empty(
    *,
    signal_date: str,
    valid: bool = False,
    near_ok: bool | None = None,
    judgment_failed: bool = False,
) -> dict[str, Any]:
    return {
        "signal_date": signal_date,
        "base_date": None,
        "base_close": None,
        "valid": valid,
        "near_ok": near_ok,
        "judgment_failed": judgment_failed,
        "end_date": None,
        "end_source": None,
        "hold_days": 0,
        "open_ended": False,
        "break_date": None,
        "cross_date": None,
        "max_close_gain": None,
        "max_close_date": None,
        "max_close_price": None,
        "max_close_drop": None,
        "max_close_drop_date": None,
        "max_close_drop_price": None,
        "end_close": None,
        "end_close_gain": None,
        # 兼容旧字段名（前端曾用 last_*）
        "last_close": None,
        "last_close_gain": None,
        "last_date": None,
        "asof": None,
    }


def forward_gains_after_signal(
    macd_items: Sequence[dict[str, Any]],
    *,
    signal_date: str,
    is_near: bool = False,
    closes_by_date: dict[str, float] | None = None,
) -> dict[str, Any]:
    """以信号日收盘为基准，统计至 DIF≥DEA 后首个 DIF<DEA（或最新日）的涨跌。

    - 已金叉：从信号日起连续 ``DIF≥DEA``，截止日=首次 ``DIF<DEA``（无则最新日）。
    - 即将金叉：先看后续是否真正金叉；``near_ok is not True`` → ``valid=False``。
    """
    sig = _iso(signal_date)
    items = _attach_closes(macd_items, closes_by_date)
    if not items:
        return _empty(signal_date=sig)

    sig_idx: int | None = None
    for i, row in enumerate(items):
        if str(row.get("date") or "")[:10] == sig:
            sig_idx = i
            break
    if sig_idx is None:
        return _empty(signal_date=sig)

    base_close = _num(items[sig_idx].get("close"))
    span = find_dif_above_span(items, sig_idx, from_next=bool(is_near))
    near_ok = span.get("near_ok") if is_near else None
    judgment_failed = bool(is_near and near_ok is not True)

    if judgment_failed or not span.get("found") or base_close is None or base_close == 0:
        return _empty(
            signal_date=sig,
            valid=False,
            near_ok=near_ok if is_near else None,
            judgment_failed=judgment_failed or (is_near and near_ok is not True),
        )

    break_idx = span.get("break_idx")
    if break_idx is not None:
        end_idx = int(break_idx)
        end_source = "break"
        open_ended = False
    else:
        # 未跌破：默认最新交易日
        end_idx = len(items) - 1
        end_source = "latest"
        open_ended = True

    beg_idx = int(span["beg_idx"])
    if end_idx < beg_idx:
        end_idx = beg_idx

    extremes = interval_close_extremes(
        items, beg_idx, end_idx, base_close=float(base_close)
    )
    end_row = items[end_idx]
    end_date = str(end_row.get("date") or "")[:10] or None
    end_close = _num(end_row.get("close"))
    end_gain = None if end_close is None else end_close / float(base_close) - 1.0
    break_info = break_day_close_change(
        items, break_idx, base_close=float(base_close)
    )

    def _r(v: float | None) -> float | None:
        return None if v is None else round(float(v), 6)

    return {
        "signal_date": sig,
        "base_date": sig,
        "base_close": round(float(base_close), 4),
        "valid": True,
        "near_ok": near_ok,
        "judgment_failed": False,
        "end_date": end_date,
        "end_source": end_source,
        "hold_days": end_idx - beg_idx + 1,
        "open_ended": open_ended,
        "break_date": span.get("break_date"),
        "cross_date": span.get("cross_date"),
        "max_close_gain": extremes.get("max_close_gain"),
        "max_close_date": extremes.get("max_close_date"),
        "max_close_price": extremes.get("max_close_price"),
        "max_close_drop": extremes.get("max_close_drop"),
        "max_close_drop_date": extremes.get("max_close_drop_date"),
        "max_close_drop_price": extremes.get("max_close_drop_price"),
        "end_close": None if end_close is None else round(float(end_close), 4),
        "end_close_gain": _r(end_gain),
        "break_close": break_info.get("break_close"),
        "break_close_chg": break_info.get("break_close_chg"),
        "last_close": None if end_close is None else round(float(end_close), 4),
        "last_close_gain": _r(end_gain),
        "last_date": end_date,
        "asof": end_date,
    }


def max_forward_gains_from_bars(
    bars: list[dict[str, Any]],
    *,
    signal_date: str,
    is_near: bool = False,
    macd_items: Sequence[dict[str, Any]] | None = None,
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    signal: int = DEFAULT_SIGNAL,
) -> dict[str, Any]:
    """从日线（及可选已算 MACD）计算信号后涨跌；无 MACD 时现场计算。"""
    sig = _iso(signal_date)
    closes = _closes_by_date(bars)
    items = list(macd_items or [])
    if not items:
        if not bars:
            return _empty(signal_date=sig)
        ordered = sorted(bars, key=_bar_date)
        dates = [d for d in (_bar_date(b) for b in ordered) if d]
        if not dates:
            return _empty(signal_date=sig)
        try:
            pack = compute_macd(
                ordered,
                dates[0],
                dates[-1],
                fast=fast,
                slow=slow,
                signal=signal,
                price="close",
            )
        except ValueError:
            return _empty(signal_date=sig)
        items = list(pack.get("items") or [])
    return forward_gains_after_signal(
        items,
        signal_date=sig,
        is_near=is_near,
        closes_by_date=closes,
    )


def max_forward_gains(
    code: str,
    *,
    signal_date: str,
    adjust: str = "qfq",
    is_near: bool = False,
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    signal: int = DEFAULT_SIGNAL,
) -> dict[str, Any]:
    """拉日线后计算；失败时返回空涨幅字段。"""
    norm = normalize_code(code)
    sig = _iso(signal_date)
    if not norm:
        return _empty(signal_date=sig)
    try:
        pack = _fetch_day_range(
            norm, beg_iso=sig, end_iso=_today_iso(), adjust=adjust
        )
    except Exception:  # noqa: BLE001
        return _empty(signal_date=sig)
    items = list(pack.get("items") or [])
    return max_forward_gains_from_bars(
        items,
        signal_date=sig,
        is_near=is_near,
        fast=fast,
        slow=slow,
        signal=signal,
    )


__all__ = [
    "forward_gains_after_signal",
    "max_forward_gains",
    "max_forward_gains_from_bars",
]
