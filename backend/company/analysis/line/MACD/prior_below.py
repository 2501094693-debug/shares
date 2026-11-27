"""金叉前 DIF<DEA 段：相对对数匀速路径的偏离累加（纯函数）。

对水下金叉 / 即将水下金叉信号日前一段连续 ``DIF < DEA``：

1. 以收盘最低日为谷底，劈成下跌腿、上涨腿；
2. 每腿按对数直线做「按比例匀速」参考价；
3. 主指标 ``s = Σ(ln P − ln P_匀)``（不除以天数）；
4. ``down_accel = −s_down``（正数=前程更急 / 先砸后磨），
   ``up_accel = −s_up``（正数=后程更急 / 先磨后拉）。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from core.fmt import to_float

# 与 analysis.macd.signals 文案一致；此处自持常量，避免 company→analysis 循环导入
SIGNAL_UNDER_CROSS = "水下金叉"
SIGNAL_UNDER_NEAR = "即将水下金叉"

# 每腿至少若干根 K 线才估加速度（含端点）
DEFAULT_MIN_BARS = 3
# 总变动过小（对数空间）则视为噪声
DEFAULT_MIN_LOG_MOVE = 1e-4

UNDER_SIGNALS = frozenset({SIGNAL_UNDER_CROSS, SIGNAL_UNDER_NEAR})


def _num(value: Any) -> float | None:
    v = to_float(value)
    if v is None:
        return None
    return float(v) if v == v else None


def _bar_close(row: dict[str, Any]) -> float | None:
    """优先 close，其次 MACD 输出的 price。"""
    for key in ("close", "price"):
        v = _num(row.get(key))
        if v is not None and v > 0:
            return v
    return None


def _dif_below(dif: float | None, dea: float | None) -> bool:
    return dif is not None and dea is not None and dif < dea


def _empty_leg(*, reason: str = "") -> dict[str, Any]:
    return {
        "found": False,
        "beg_idx": None,
        "end_idx": None,
        "beg": None,
        "end": None,
        "count": 0,
        "days": 0,
        "beg_close": None,
        "end_close": None,
        "log_move": None,
        "sum_dev": None,
        "accel": None,
        "reason": reason or None,
    }


def _empty_prior(*, reason: str = "") -> dict[str, Any]:
    return {
        "found": False,
        "signal": None,
        "include_signal": None,
        "beg_idx": None,
        "end_idx": None,
        "beg": None,
        "end": None,
        "count": 0,
        "trough_idx": None,
        "trough_date": None,
        "trough_close": None,
        "down": _empty_leg(reason=reason),
        "up": _empty_leg(reason=reason),
        "down_accel": None,
        "up_accel": None,
        "reason": reason or None,
    }


def find_dif_below_span(
    items: Sequence[dict[str, Any]],
    signal_idx: int,
    *,
    include_signal: bool,
) -> dict[str, Any]:
    """定位信号对应的前序连续 ``DIF < DEA`` 段。

    - ``include_signal=False``（已金叉）：终点为 ``signal_idx - 1``
    - ``include_signal=True``（即将金叉）：终点为 ``signal_idx``（当天仍 DIF<DEA）
    """
    n = len(items)
    if signal_idx < 0 or signal_idx >= n:
        return {
            "found": False,
            "beg_idx": None,
            "end_idx": None,
            "beg": None,
            "end": None,
            "count": 0,
            "include_signal": include_signal,
            "reason": "信号下标越界",
        }

    end_idx = signal_idx if include_signal else signal_idx - 1
    if end_idx < 0:
        return {
            "found": False,
            "beg_idx": None,
            "end_idx": None,
            "beg": None,
            "end": None,
            "count": 0,
            "include_signal": include_signal,
            "reason": "金叉日前无交易日",
        }

    end_row = items[end_idx]
    if not _dif_below(_num(end_row.get("dif")), _num(end_row.get("dea"))):
        return {
            "found": False,
            "beg_idx": None,
            "end_idx": end_idx,
            "beg": None,
            "end": str(end_row.get("date") or "")[:10] or None,
            "count": 0,
            "include_signal": include_signal,
            "reason": "终点日非 DIF<DEA",
        }

    beg_idx = end_idx
    for i in range(end_idx - 1, -1, -1):
        row = items[i]
        dif = _num(row.get("dif"))
        dea = _num(row.get("dea"))
        if dif is None or dea is None:
            break
        if not _dif_below(dif, dea):
            break
        beg_idx = i

    return {
        "found": True,
        "beg_idx": beg_idx,
        "end_idx": end_idx,
        "beg": str(items[beg_idx].get("date") or "")[:10] or None,
        "end": str(items[end_idx].get("date") or "")[:10] or None,
        "count": end_idx - beg_idx + 1,
        "include_signal": include_signal,
        "reason": None,
    }


def log_uniform_sum_dev(
    closes: Sequence[float],
    *,
    min_bars: int = DEFAULT_MIN_BARS,
    min_log_move: float = DEFAULT_MIN_LOG_MOVE,
) -> dict[str, Any]:
    """对一段收盘价序列：对数匀速参考线下的偏离累加 ``Σ(lnP − lnP_匀)``。

    端点偏离为 0；``accel`` 字段不在此函数内取负，由调用方按腿决定符号。
    """
    n = len(closes)
    if n < int(min_bars):
        return {
            "ok": False,
            "days": max(0, n - 1),
            "count": n,
            "beg_close": closes[0] if n else None,
            "end_close": closes[-1] if n else None,
            "log_move": None,
            "sum_dev": None,
            "devs": [],
            "reason": f"样本不足（需≥{min_bars}根，实际{n}）",
        }

    for px in closes:
        if px is None or float(px) <= 0:
            return {
                "ok": False,
                "days": n - 1,
                "count": n,
                "beg_close": None,
                "end_close": None,
                "log_move": None,
                "sum_dev": None,
                "devs": [],
                "reason": "收盘价无效",
            }

    p0 = float(closes[0])
    p1 = float(closes[-1])
    ln0 = math.log(p0)
    ln1 = math.log(p1)
    log_move = ln1 - ln0
    if abs(log_move) < float(min_log_move):
        return {
            "ok": False,
            "days": n - 1,
            "count": n,
            "beg_close": round(p0, 6),
            "end_close": round(p1, 6),
            "log_move": round(log_move, 8),
            "sum_dev": None,
            "devs": [],
            "reason": "总变动过小",
        }

    t_span = n - 1
    devs: list[float] = []
    total = 0.0
    for t, px in enumerate(closes):
        ln_u = ln0 + (ln1 - ln0) * (t / t_span)
        e = math.log(float(px)) - ln_u
        devs.append(e)
        total += e

    return {
        "ok": True,
        "days": t_span,
        "count": n,
        "beg_close": round(p0, 6),
        "end_close": round(p1, 6),
        "log_move": round(log_move, 8),
        "sum_dev": round(total, 8),
        "devs": [round(x, 8) for x in devs],
        "reason": None,
    }


def _pack_leg(
    items: Sequence[dict[str, Any]],
    beg_idx: int,
    end_idx: int,
    *,
    accel_sign: float,
    min_bars: int,
    min_log_move: float,
) -> dict[str, Any]:
    if end_idx < beg_idx:
        return _empty_leg(reason="腿区间无效")

    closes: list[float] = []
    for i in range(beg_idx, end_idx + 1):
        px = _bar_close(items[i])
        if px is None:
            return _empty_leg(reason="收盘价缺失")
        closes.append(px)

    raw = log_uniform_sum_dev(
        closes, min_bars=min_bars, min_log_move=min_log_move
    )
    sum_dev = raw.get("sum_dev")
    accel = None if sum_dev is None else round(float(accel_sign) * float(sum_dev), 8)
    return {
        "found": bool(raw.get("ok")),
        "beg_idx": beg_idx,
        "end_idx": end_idx,
        "beg": str(items[beg_idx].get("date") or "")[:10] or None,
        "end": str(items[end_idx].get("date") or "")[:10] or None,
        "count": int(raw.get("count") or 0),
        "days": int(raw.get("days") or 0),
        "beg_close": raw.get("beg_close"),
        "end_close": raw.get("end_close"),
        "log_move": raw.get("log_move"),
        "sum_dev": sum_dev,
        "accel": accel,
        "devs": list(raw.get("devs") or []),
        "reason": raw.get("reason"),
    }


def analyze_prior_below(
    items: Sequence[dict[str, Any]],
    signal_idx: int,
    *,
    signal: str | None = None,
    include_signal: bool | None = None,
    min_bars: int = DEFAULT_MIN_BARS,
    min_log_move: float = DEFAULT_MIN_LOG_MOVE,
) -> dict[str, Any]:
    """分析信号日前序 DIF<DEA 段的对数匀速偏离加速度。

    ``include_signal`` 可显式传入；若省略则按 ``signal`` 推断：
    即将水下金叉含信号日，水下金叉不含。
    """
    sig = str(signal or "").strip() or None
    if include_signal is None:
        if sig == SIGNAL_UNDER_NEAR:
            include_signal = True
        elif sig == SIGNAL_UNDER_CROSS:
            include_signal = False
        else:
            # 未标明信号时：若信号日仍 DIF<DEA 则含当日，否则不含
            if 0 <= signal_idx < len(items):
                row = items[signal_idx]
                include_signal = _dif_below(
                    _num(row.get("dif")), _num(row.get("dea"))
                )
            else:
                include_signal = False

    span = find_dif_below_span(
        items, signal_idx, include_signal=bool(include_signal)
    )
    if not span.get("found"):
        out = _empty_prior(reason=str(span.get("reason") or "无 DIF<DEA 段"))
        out["signal"] = sig
        out["include_signal"] = bool(include_signal)
        return out

    beg_idx = int(span["beg_idx"])
    end_idx = int(span["end_idx"])

    trough_idx = beg_idx
    trough_px = _bar_close(items[beg_idx])
    if trough_px is None:
        out = _empty_prior(reason="谷底收盘价缺失")
        out["signal"] = sig
        out["include_signal"] = bool(include_signal)
        out.update(
            {
                "beg_idx": beg_idx,
                "end_idx": end_idx,
                "beg": span.get("beg"),
                "end": span.get("end"),
                "count": span.get("count") or 0,
            }
        )
        return out

    for i in range(beg_idx + 1, end_idx + 1):
        px = _bar_close(items[i])
        if px is None:
            out = _empty_prior(reason="收盘价缺失")
            out["signal"] = sig
            out["include_signal"] = bool(include_signal)
            out.update(
                {
                    "beg_idx": beg_idx,
                    "end_idx": end_idx,
                    "beg": span.get("beg"),
                    "end": span.get("end"),
                    "count": span.get("count") or 0,
                }
            )
            return out
        # 并列最低取最早一根，避免虚抬上涨腿
        if px < trough_px:
            trough_px = px
            trough_idx = i

    down = _pack_leg(
        items,
        beg_idx,
        trough_idx,
        accel_sign=-1.0,  # down_accel = −s_down：正=先砸后磨
        min_bars=min_bars,
        min_log_move=min_log_move,
    )
    up = _pack_leg(
        items,
        trough_idx,
        end_idx,
        accel_sign=-1.0,  # up_accel = −s_up：正=先磨后拉
        min_bars=min_bars,
        min_log_move=min_log_move,
    )

    return {
        "found": True,
        "signal": sig,
        "include_signal": bool(include_signal),
        "beg_idx": beg_idx,
        "end_idx": end_idx,
        "beg": span.get("beg"),
        "end": span.get("end"),
        "count": int(span.get("count") or 0),
        "trough_idx": trough_idx,
        "trough_date": str(items[trough_idx].get("date") or "")[:10] or None,
        "trough_close": round(float(trough_px), 6),
        "down": down,
        "up": up,
        "down_accel": down.get("accel"),
        "up_accel": up.get("accel"),
        "reason": None,
    }


__all__ = [
    "DEFAULT_MIN_BARS",
    "DEFAULT_MIN_LOG_MOVE",
    "UNDER_SIGNALS",
    "analyze_prior_below",
    "find_dif_below_span",
    "log_uniform_sum_dev",
]
