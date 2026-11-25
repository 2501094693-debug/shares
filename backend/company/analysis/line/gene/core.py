"""股性（gene）：区间内 MACD 金叉 / 即将金叉扫描 + 后续区间涨跌幅（纯函数）。

流程：

1. 在已算好的 MACD 日序列上，逐日用 ``classify_macd_cross`` 判定四类信号；
2. 对每个信号日确定后续观察区间：
   - 已金叉：从信号日起的连续 ``DIF ≥ DEA`` 段；
   - 即将金叉：看信号日后各日的 ``MACD(=DIF−DEA)``：
     · 仍 ``< 0`` 但 ≥ 信号日 MACD → 继续往后；
     · 仍 ``< 0`` 且 < 信号日 MACD → 判断失败；
     · 一旦 ``≥ 0`` → 成功；先取该段 ``DIF≥DEA`` 连续段；
3. 观察终点 = 连续 ``DIF ≥ DEA`` 结束后**首次** ``DIF < DEA`` 的那天（跌破日）；
   若数据末尾仍未跌破则区间开放、无跌破日。
4. 以信号日收盘为基准，在 ``[信号日, 跌破日]``（含）内算最大收盘涨/跌幅，
   并单独给出跌破日相对信号日收盘的涨跌幅。
"""

from __future__ import annotations

from typing import Any, Sequence

from analysis.macd.signals import (
    SIGNAL_OVER_CROSS,
    SIGNAL_OVER_NEAR,
    SIGNAL_UNDER_CROSS,
    SIGNAL_UNDER_NEAR,
    classify_macd_cross,
)
from core.fmt import to_float

from company.analysis.line.gene.config import (
    ALLOWED_PRESETS,
    DEFAULT_NEAR_RATIO,
    DEFAULT_PRESET,
    MACD_PRESETS,
)

CROSS_SIGNALS = frozenset(
    {SIGNAL_UNDER_CROSS, SIGNAL_OVER_CROSS, SIGNAL_UNDER_NEAR, SIGNAL_OVER_NEAR}
)
NEAR_SIGNALS = frozenset({SIGNAL_UNDER_NEAR, SIGNAL_OVER_NEAR})


def _iso(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 8:
        raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def resolve_preset(preset: str | None = None) -> tuple[str, int, int, int]:
    """解析 MACD 预设，返回 ``(key, fast, slow, signal)``。"""
    key = str(preset or DEFAULT_PRESET).strip().replace(" ", "")
    if key not in MACD_PRESETS:
        raise ValueError(
            f"macd 预设须为 {ALLOWED_PRESETS} 之一，收到 {preset!r}"
        )
    fast, slow, signal = MACD_PRESETS[key]
    return key, int(fast), int(slow), int(signal)


def _num(value: Any) -> float | None:
    v = to_float(value)
    if v is None:
        return None
    return float(v) if v == v else None


def _dif_above(dif: float | None, dea: float | None) -> bool:
    return dif is not None and dea is not None and dif >= dea


def _spread(dif: float | None, dea: float | None) -> float | None:
    """``DIF − DEA``（与柱线 MACD 同号；柱线为 2×spread）。"""
    if dif is None or dea is None:
        return None
    return float(dif) - float(dea)


def _empty_span(*, near_ok: bool | None = None) -> dict[str, Any]:
    return {
        "found": False,
        "beg_idx": None,
        "end_idx": None,
        "beg": None,
        "end": None,
        "count": 0,
        "open_ended": False,
        "break_idx": None,
        "break_date": None,
        "observe_end_idx": None,
        "near_ok": near_ok,
        "cross_date": None,
        "decide_date": None,
        "decide_dif": None,
        "decide_dea": None,
        "decide_macd": None,
        # 兼容旧字段名（决定日）
        "next_date": None,
        "next_dif": None,
        "next_dea": None,
    }


def _pack_span(
    items: Sequence[dict[str, Any]],
    beg_idx: int,
    end_idx: int,
    *,
    open_ended: bool,
    near_ok: bool | None = None,
    cross_date: str | None = None,
    decide_date: str | None = None,
    decide_dif: float | None = None,
    decide_dea: float | None = None,
    decide_macd: float | None = None,
) -> dict[str, Any]:
    """打包区间。

    ``end_idx``：连续 DIF≥DEA 最后一天。
    若已跌破，则 ``break_idx = end_idx + 1``（首次 DIF < DEA），
    ``observe_end_idx`` 取跌破日，供最大涨跌统计使用。
    """
    d_dif = None if decide_dif is None else round(decide_dif, 6)
    d_dea = None if decide_dea is None else round(decide_dea, 6)
    d_macd = None if decide_macd is None else round(decide_macd, 6)
    break_idx: int | None = None
    break_date: str | None = None
    if not open_ended and end_idx + 1 < len(items):
        break_idx = end_idx + 1
        break_date = str(items[break_idx].get("date") or "")[:10] or None
    observe_end_idx = break_idx if break_idx is not None else end_idx
    return {
        "found": True,
        "beg_idx": beg_idx,
        "end_idx": end_idx,
        "beg": str(items[beg_idx].get("date") or "")[:10] or None,
        "end": str(items[end_idx].get("date") or "")[:10] or None,
        "count": end_idx - beg_idx + 1,
        "open_ended": open_ended,
        "break_idx": break_idx,
        "break_date": break_date,
        "observe_end_idx": observe_end_idx,
        "near_ok": near_ok,
        "cross_date": cross_date,
        "decide_date": decide_date,
        "decide_dif": d_dif,
        "decide_dea": d_dea,
        "decide_macd": d_macd,
        "next_date": decide_date,
        "next_dif": d_dif,
        "next_dea": d_dea,
    }


def _extend_above_end(
    items: Sequence[dict[str, Any]],
    start_idx: int,
) -> tuple[int, bool]:
    """从 ``start_idx``（须已 DIF≥DEA）延伸到连续段末，返回 ``(end_idx, open_ended)``。"""
    n = len(items)
    end_idx = start_idx
    for i in range(start_idx + 1, n):
        row = items[i]
        if _dif_above(_num(row.get("dif")), _num(row.get("dea"))):
            end_idx = i
        else:
            return end_idx, False
    return end_idx, True


def find_dif_above_span(
    items: Sequence[dict[str, Any]],
    signal_idx: int,
    *,
    from_next: bool,
) -> dict[str, Any]:
    """确定信号日对应的后续观察区间（闭区间下标）。

    ``from_next=False``（已金叉）：从 ``signal_idx`` 起的连续 DIF≥DEA 段。

    ``from_next=True``（即将金叉）：以信号日 ``MACD_spread = DIF−DEA`` 为基准，
    向后逐日比较：
    - 仍 ``< 0`` 且 ``≥`` 基准 → 继续；
    - 仍 ``< 0`` 且 ``<`` 基准 → ``near_ok=False``；
    - ``≥ 0`` → ``near_ok=True``，先取该段 DIF≥DEA 连续段；
    - 数据用尽仍未分出胜负 → ``near_ok=None``。

    若连续段后出现首次 DIF < DEA，则 ``break_date`` / ``observe_end_idx`` 指向该日。
    """
    n = len(items)
    if signal_idx < 0 or signal_idx >= n:
        return _empty_span()

    if not from_next:
        if not _dif_above(
            _num(items[signal_idx].get("dif")),
            _num(items[signal_idx].get("dea")),
        ):
            return _empty_span()
        end_idx, open_ended = _extend_above_end(items, signal_idx)
        return _pack_span(
            items,
            signal_idx,
            end_idx,
            open_ended=open_ended,
        )

    base_dif = _num(items[signal_idx].get("dif"))
    base_dea = _num(items[signal_idx].get("dea"))
    base = _spread(base_dif, base_dea)
    if base is None:
        return _empty_span(near_ok=None)

    if signal_idx + 1 >= n:
        return _empty_span(near_ok=None)

    for j in range(signal_idx + 1, n):
        row = items[j]
        dif = _num(row.get("dif"))
        dea = _num(row.get("dea"))
        cur = _spread(dif, dea)
        date = str(row.get("date") or "")[:10] or None
        if cur is None:
            out = _empty_span(near_ok=None)
            out["decide_date"] = date
            out["next_date"] = date
            return out

        macd = 2.0 * cur
        if cur >= 0.0:
            end_idx, open_ended = _extend_above_end(items, j)
            return _pack_span(
                items,
                signal_idx,
                end_idx,
                open_ended=open_ended,
                near_ok=True,
                cross_date=date,
                decide_date=date,
                decide_dif=dif,
                decide_dea=dea,
                decide_macd=macd,
            )

        if cur < base:
            out = _empty_span(near_ok=False)
            d_dif = None if dif is None else round(dif, 6)
            d_dea = None if dea is None else round(dea, 6)
            out.update(
                {
                    "decide_date": date,
                    "decide_dif": d_dif,
                    "decide_dea": d_dea,
                    "decide_macd": round(macd, 6),
                    "next_date": date,
                    "next_dif": d_dif,
                    "next_dea": d_dea,
                }
            )
            return out
        # cur < 0 且 cur >= base：继续往后

    return _empty_span(near_ok=None)


def break_day_close_change(
    items: Sequence[dict[str, Any]],
    break_idx: int | None,
    *,
    base_close: float | None,
) -> dict[str, Any]:
    """跌破日（首次 DIF < DEA）相对信号日收盘的涨跌幅。"""
    empty = {
        "break_close": None,
        "break_close_chg": None,
    }
    if break_idx is None or base_close is None or base_close == 0:
        return empty
    if break_idx < 0 or break_idx >= len(items):
        return empty
    row = items[break_idx]
    close = _num(row.get("close"))
    if close is None:
        close = _num(row.get("price"))
    if close is None:
        return empty
    return {
        "break_close": round(float(close), 4),
        "break_close_chg": round(float(close) / float(base_close) - 1.0, 6),
    }


def interval_close_extremes(
    items: Sequence[dict[str, Any]],
    beg_idx: int,
    end_idx: int,
    *,
    base_close: float,
) -> dict[str, Any]:
    """区间内相对 ``base_close`` 的最大收盘涨幅 / 最大收盘跌幅。"""
    empty = {
        "max_close_gain": None,
        "max_close_date": None,
        "max_close_price": None,
        "max_close_drop": None,
        "max_close_drop_date": None,
        "max_close_drop_price": None,
    }
    if base_close is None or base_close == 0:
        return empty
    if beg_idx < 0 or end_idx < beg_idx or end_idx >= len(items):
        return empty

    max_gain: float | None = None
    max_gain_date: str | None = None
    max_gain_price: float | None = None
    max_drop: float | None = None
    max_drop_date: str | None = None
    max_drop_price: float | None = None

    for i in range(beg_idx, end_idx + 1):
        row = items[i]
        close = _num(row.get("close"))
        if close is None:
            close = _num(row.get("price"))
        if close is None:
            continue
        chg = close / float(base_close) - 1.0
        d = str(row.get("date") or "")[:10] or None
        if max_gain is None or chg > max_gain:
            max_gain = chg
            max_gain_date = d
            max_gain_price = close
        if max_drop is None or chg < max_drop:
            max_drop = chg
            max_drop_date = d
            max_drop_price = close

    def _r(v: float | None) -> float | None:
        return None if v is None else round(float(v), 6)

    return {
        "max_close_gain": _r(max_gain),
        "max_close_date": max_gain_date,
        "max_close_price": None if max_gain_price is None else round(max_gain_price, 4),
        "max_close_drop": _r(max_drop),
        "max_close_drop_date": max_drop_date,
        "max_close_drop_price": (
            None if max_drop_price is None else round(max_drop_price, 4)
        ),
    }


def _attach_closes(
    macd_items: Sequence[dict[str, Any]],
    closes_by_date: dict[str, float] | None,
) -> list[dict[str, Any]]:
    """把收盘价挂到 MACD 行上（优先外部 closes，其次 price）。"""
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


def _empty_prior_extrema() -> dict[str, Any]:
    return {
        "peak_date": None,
        "peak_price": None,
        "trough_date": None,
        "trough_price": None,
        "dist_peak": None,
        "dist_trough": None,
        "closer": None,
        "closer_label": None,
        "closer_date": None,
        "closer_price": None,
        "gap": None,
        "gap_pct": None,
        "abs_gap": None,
        "abs_gap_pct": None,
    }


def _pick_nearest_prior(
    extrema: Sequence[dict[str, Any]],
    day: str,
    kind: str,
) -> dict[str, Any] | None:
    """在峰谷序列中取 ``date < day`` 且时间最近的指定类型点。"""
    best: dict[str, Any] | None = None
    for pt in extrema:
        if str(pt.get("type") or "") != kind:
            continue
        d = str(pt.get("date") or "")[:10]
        if not d or d >= day:
            continue
        price = _num(pt.get("price"))
        if price is None:
            continue
        if best is None or d > str(best.get("date") or ""):
            best = {
                "date": d,
                "price": float(price),
                "type": kind,
                "label": "波峰" if kind == "peak" else "波谷",
            }
    return best


def nearest_prior_extrema(
    close: float | None,
    date: str,
    extrema: Sequence[dict[str, Any]] | None,
) -> dict[str, Any]:
    """金叉日收盘相对此前最近峰 / 谷的贴近度。

    - 在三级（或多层）峰谷序列中，取时间上晚于区间起点、严格早于金叉日、
      且离金叉日最近的峰值与谷值各一个；
    - 用绝对价距判断更接近哪一侧；相等时取二者中日期更近者，再相等则记谷；
    - ``gap`` / ``gap_pct`` 为相对更近一侧的有符号差距（收盘 − 参照价）。
    """
    out = _empty_prior_extrema()
    day = str(date or "")[:10]
    base = _num(close)
    if not day or base is None or not extrema:
        return out

    peak = _pick_nearest_prior(extrema, day, "peak")
    trough = _pick_nearest_prior(extrema, day, "trough")
    if peak is not None:
        out["peak_date"] = peak["date"]
        out["peak_price"] = round(float(peak["price"]), 4)
        out["dist_peak"] = round(abs(float(base) - float(peak["price"])), 6)
    if trough is not None:
        out["trough_date"] = trough["date"]
        out["trough_price"] = round(float(trough["price"]), 4)
        out["dist_trough"] = round(abs(float(base) - float(trough["price"])), 6)

    closer: dict[str, Any] | None = None
    if peak is not None and trough is not None:
        dp = float(out["dist_peak"])
        dt = float(out["dist_trough"])
        if dp < dt:
            closer = peak
        elif dt < dp:
            closer = trough
        elif str(peak["date"]) >= str(trough["date"]):
            closer = peak
        else:
            closer = trough
    elif peak is not None:
        closer = peak
    elif trough is not None:
        closer = trough

    if closer is None:
        return out

    ref = float(closer["price"])
    gap = float(base) - ref
    out["closer"] = closer["type"]
    out["closer_label"] = closer["label"]
    out["closer_date"] = closer["date"]
    out["closer_price"] = round(ref, 4)
    out["gap"] = round(gap, 6)
    out["abs_gap"] = round(abs(gap), 6)
    if ref != 0:
        out["gap_pct"] = round(gap / ref, 6)
        out["abs_gap_pct"] = round(abs(gap) / abs(ref), 6)
    return out


def _summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    """按信号类型汇总次数与平均涨/跌幅，便于看股性。"""
    by_type: dict[str, dict[str, Any]] = {}
    for key in (
        SIGNAL_UNDER_NEAR,
        SIGNAL_UNDER_CROSS,
        SIGNAL_OVER_NEAR,
        SIGNAL_OVER_CROSS,
    ):
        by_type[key] = {
            "count": 0,
            "near_ok_count": 0,
            "near_fail_count": 0,
            "near_pending_count": 0,
            "avg_max_close_gain": None,
            "avg_max_close_drop": None,
            "closer_peak_count": 0,
            "closer_trough_count": 0,
            "avg_abs_gap_pct": None,
            "gains": [],
            "drops": [],
            "abs_gaps": [],
        }

    closer_peak = 0
    closer_trough = 0
    abs_gaps_all: list[float] = []

    for ev in events:
        sig = str(ev.get("signal") or "")
        bucket = by_type.get(sig)
        if bucket is None:
            continue
        bucket["count"] += 1
        if sig in NEAR_SIGNALS:
            ok = ev.get("near_ok")
            if ok is True:
                bucket["near_ok_count"] += 1
            elif ok is False:
                bucket["near_fail_count"] += 1
            else:
                bucket["near_pending_count"] += 1
        g = ev.get("max_close_gain")
        d = ev.get("max_close_drop")
        if g is not None:
            bucket["gains"].append(float(g))
        if d is not None:
            bucket["drops"].append(float(d))

        pe = ev.get("prior_extrema") or {}
        closer = pe.get("closer")
        if closer == "peak":
            bucket["closer_peak_count"] += 1
            closer_peak += 1
        elif closer == "trough":
            bucket["closer_trough_count"] += 1
            closer_trough += 1
        ag = pe.get("abs_gap_pct")
        if ag is not None:
            bucket["abs_gaps"].append(float(ag))
            abs_gaps_all.append(float(ag))

    for bucket in by_type.values():
        gains = bucket.pop("gains")
        drops = bucket.pop("drops")
        abs_gaps = bucket.pop("abs_gaps")
        if gains:
            bucket["avg_max_close_gain"] = round(sum(gains) / len(gains), 6)
        if drops:
            bucket["avg_max_close_drop"] = round(sum(drops) / len(drops), 6)
        if abs_gaps:
            bucket["avg_abs_gap_pct"] = round(sum(abs_gaps) / len(abs_gaps), 6)

    return {
        "total": len(events),
        "by_signal": by_type,
        "prior_extrema": {
            "closer_peak_count": closer_peak,
            "closer_trough_count": closer_trough,
            "avg_abs_gap_pct": (
                round(sum(abs_gaps_all) / len(abs_gaps_all), 6)
                if abs_gaps_all
                else None
            ),
        },
    }

_EMPTY_EXTREMES = {
    "max_close_gain": None,
    "max_close_date": None,
    "max_close_price": None,
    "max_close_drop": None,
    "max_close_drop_date": None,
    "max_close_drop_price": None,
}

_EMPTY_BREAK = {
    "break_date": None,
    "break_close": None,
    "break_close_chg": None,
}


def analyze_gene_from_macd(
    macd_items: Sequence[dict[str, Any]],
    beg: str,
    end: str = "",
    *,
    near_ratio: float = DEFAULT_NEAR_RATIO,
    closes_by_date: dict[str, float] | None = None,
    extrema: Sequence[dict[str, Any]] | None = None,
    extrema_layers: int | None = None,
    preset: str = DEFAULT_PRESET,
    fast: int | None = None,
    slow: int | None = None,
    signal: int | None = None,
) -> dict[str, Any]:
    """在 MACD 序列上扫描金叉事件并计算后续观察区间涨跌幅。

    ``macd_items`` 宜覆盖 ``beg`` 前至少 1 根（供首日判定）以及信号后 DIF≥DEA
    段与跌破日可能延伸到的交易日；输出事件的 ``date`` 仅保留 ``[beg, end]`` 内。

    最大涨/跌观察终点为首次 ``DIF < DEA`` 日（跌破日）；未跌破则仍到数据末。
    ``extrema``：区间三级峰谷序列，用于 ``prior_extrema`` 贴近度。
    """
    beg_iso = _iso(beg)
    end_iso = _iso(end) if str(end or "").strip() else "9999-12-31"
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")

    preset_key = str(preset or DEFAULT_PRESET).strip()
    items = _attach_closes(macd_items, closes_by_date)
    extrema_seq = list(extrema or [])
    events: list[dict[str, Any]] = []

    for i in range(1, len(items)):
        date = str(items[i].get("date") or "")[:10]
        if not date or date < beg_iso or date > end_iso:
            continue
        hit = classify_macd_cross(items[: i + 1], near_ratio=near_ratio)
        if not hit.get("matched"):
            continue
        primary = str(hit.get("primary") or "")
        if primary not in CROSS_SIGNALS:
            continue

        base_close = _num(items[i].get("close"))
        is_near = primary in NEAR_SIGNALS
        span = find_dif_above_span(items, i, from_next=is_near)
        near_ok = span.get("near_ok") if is_near else None
        judgment_failed = bool(is_near and near_ok is False)
        if span.get("found") and base_close is not None and not judgment_failed:
            obs_end = span.get("observe_end_idx")
            if obs_end is None:
                obs_end = span["end_idx"]
            extremes = interval_close_extremes(
                items,
                int(span["beg_idx"]),
                int(obs_end),
                base_close=float(base_close),
            )
            break_info = {
                "break_date": span.get("break_date"),
                **break_day_close_change(
                    items,
                    span.get("break_idx"),
                    base_close=float(base_close),
                ),
            }
        else:
            extremes = dict(_EMPTY_EXTREMES)
            break_info = dict(_EMPTY_BREAK)
        prior = nearest_prior_extrema(base_close, date, extrema_seq)

        events.append(
            {
                "date": date,
                "signal": primary,
                "signals": list(hit.get("signals") or []),
                "underwater": hit.get("underwater"),
                "dif": hit.get("dif"),
                "dea": hit.get("dea"),
                "prev_dif": hit.get("prev_dif"),
                "prev_dea": hit.get("prev_dea"),
                "rel_gap": hit.get("rel_gap"),
                "base_close": None if base_close is None else round(base_close, 4),
                "near_ok": near_ok,
                "judgment_failed": judgment_failed,
                "cross_date": span.get("cross_date"),
                "decide_date": span.get("decide_date"),
                "decide_dif": span.get("decide_dif"),
                "decide_dea": span.get("decide_dea"),
                "decide_macd": span.get("decide_macd"),
                "next_date": span.get("next_date"),
                "next_dif": span.get("next_dif"),
                "next_dea": span.get("next_dea"),
                "dif_above_beg": span.get("beg"),
                "dif_above_end": span.get("end"),
                "dif_above_count": span.get("count") or 0,
                "dif_above_open_ended": bool(span.get("open_ended")),
                "dif_above_found": bool(span.get("found")),
                "prior_extrema": prior,
                **break_info,
                **extremes,
            }
        )

    used_end = end_iso if end_iso != "9999-12-31" else (
        str(items[-1].get("date") or "")[:10] if items else beg_iso
    )
    return {
        "beg": beg_iso,
        "end": used_end,
        "preset": preset_key,
        "fast": fast,
        "slow": slow,
        "signal_period": signal,
        "near_ratio": abs(float(near_ratio)),
        "extrema_layers": extrema_layers,
        "extrema_count": len(extrema_seq),
        "macd_count": len(items),
        "event_count": len(events),
        "events": events,
        "summary": _summary(events),
    }


__all__ = [
    "CROSS_SIGNALS",
    "NEAR_SIGNALS",
    "analyze_gene_from_macd",
    "break_day_close_change",
    "find_dif_above_span",
    "interval_close_extremes",
    "nearest_prior_extrema",
    "resolve_preset",
]
