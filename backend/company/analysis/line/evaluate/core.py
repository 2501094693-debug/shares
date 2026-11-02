"""区间评估的纯函数：波动筛选、最低价日、极值评分、标准差坐标。

无网络、无 IO，输入已排序 / 未排序的日线序列即可，便于单测。

口径与 ``undulate`` 完全一致：以「起始日前一交易日收盘」为基准，区间内每个
交易日的四价相对该基准算涨跌幅。波动筛选要求区间内指定价格（或四价）的
涨跌幅都落在 ``[-band, band]``，``band=0.09`` 即 ±9%。
"""

from __future__ import annotations

from typing import Any

from core.fmt import to_float

from company.analysis.line.undulate.service import (
    FACTORS,
    FACTOR_LABELS,
    _bar_date,
    _iso,
    compute_undulate,
)

# 波动带默认 ±9%（涨跌幅用小数，0.09 = 9%，与 undulate 口径一致）
DEFAULT_BAND = 0.09

# 「波动测试」可选口径：四价任一，或 all = 四价同时满足
TEST_FACTOR_CHOICES: tuple[str, ...] = ("open", "high", "low", "close", "all")

# 找最低价日可选口径：只支持单一价格
LOW_FACTOR_CHOICES: tuple[str, ...] = ("open", "high", "low", "close")


def _factor_bounds(
    pack: dict[str, Any], factor: str
) -> tuple[float | None, float | None]:
    """从 ``compute_undulate`` 结果的 ``range`` 里取某价格的 (min, max)。"""
    row = (pack.get("range") or {}).get(factor) or {}
    mn = row.get("min")
    mx = row.get("max")
    return (
        None if mn is None else float(mn),
        None if mx is None else float(mx),
    )


def window_within(
    pack: dict[str, Any],
    *,
    factor: str = "close",
    band: float = DEFAULT_BAND,
) -> bool:
    """判断一个 ``compute_undulate`` 结果是否落在 ``[-band, band]`` 波动带内。

    ``factor="all"`` 时要求四价的涨跌幅上下界都满足；否则只看单一价格。
    区间没有有效样本时视为不满足。
    """
    lo = -abs(float(band))
    hi = abs(float(band))

    if factor == "all":
        any_present = False
        for f in FACTORS:
            mn, mx = _factor_bounds(pack, f)
            if mn is None or mx is None:
                continue
            any_present = True
            if mn < lo or mx > hi:
                return False
        return any_present

    mn, mx = _factor_bounds(pack, factor)
    if mn is None or mx is None:
        return False
    return mn >= lo and mx <= hi


def _prices_within_band(
    run_min: dict[str, float],
    run_max: dict[str, float],
    *,
    base_close: float,
    band_abs: float,
    factors: tuple[str, ...] | list[str],
) -> bool:
    """用窗口内价格 min/max + 基准收盘，判断是否落在 ±band（与 ``_pct`` 六位小数一致）。"""
    lo = -band_abs
    hi = band_abs
    any_present = False
    for f in factors:
        mn = run_min.get(f)
        mx = run_max.get(f)
        if mn is None or mx is None:
            continue
        any_present = True
        pct_lo = round(float(mn) / base_close - 1.0, 6)
        pct_hi = round(float(mx) / base_close - 1.0, 6)
        if pct_lo < lo or pct_hi > hi:
            return False
    return any_present


def find_max_range(
    bars: list[dict[str, Any]],
    *,
    end: str = "",
    factor: str = "close",
    band: float = DEFAULT_BAND,
) -> dict[str, Any]:
    """从最新交易日逐日往前推，找出仍满足 ``[-band, band]`` 的最大区间。

    起始日先取区间最后一个交易日；满足条件就把起始日前推一个交易日再测，
    直到首次不满足即停，返回最后一次满足的区间（即最大起始日期范围）。

    实现：向后扩展时增量维护价格 min/max（O(n)），仅对最终窗口调用一次
    ``compute_undulate`` 生成完整结果，避免原先每个候选起点整段重算。

    返回：
    - ``found``         是否找到（最新交易日单日窗口即不满足时为 ``False``）
    - ``window``        最后一次满足的 ``compute_undulate`` 结果（含 beg/end/days/range）
    - ``first_fail``    首次不满足的窗口（用于说明为何停止），无则为 ``None``
    - ``reached_start`` 是否因「起始日之前已无基准交易日」而停止（触到数据头部）
    - ``tested``        实际测试的窗口数
    """
    if not bars:
        raise ValueError("无日线数据")
    if factor not in TEST_FACTOR_CHOICES:
        raise ValueError(
            f"不支持的波动口径 {factor!r}，可选 {TEST_FACTOR_CHOICES}"
        )

    ordered = [b for b in sorted(bars, key=_bar_date) if _bar_date(b)]
    if not ordered:
        raise ValueError("无日线数据")

    dates = [_bar_date(b) for b in ordered]
    end_iso = _iso(end) if end else dates[-1]
    end_idx = -1
    for i, d in enumerate(dates):
        if d <= end_iso:
            end_idx = i
    if end_idx < 0:
        raise ValueError(f"{end_iso} 之前无交易日")

    track: tuple[str, ...] = FACTORS if factor == "all" else (factor,)
    band_abs = abs(float(band))
    run_min: dict[str, float] = {}
    run_max: dict[str, float] = {}

    last_good_i: int | None = None
    first_fail_i: int | None = None
    reached_start = False
    tested = 0

    for i in range(end_idx, -1, -1):
        if i == 0:
            # 起始日是序列首根时没有基准前收，与 compute_undulate 行为一致
            reached_start = True
            break

        bar = ordered[i]
        for f in track:
            val = to_float(bar.get(f))
            if val is None:
                continue
            prev_min = run_min.get(f)
            prev_max = run_max.get(f)
            run_min[f] = val if prev_min is None else min(prev_min, val)
            run_max[f] = val if prev_max is None else max(prev_max, val)

        base_close = to_float(ordered[i - 1].get("close"))
        if base_close is None or base_close == 0:
            reached_start = True
            break

        tested += 1
        if _prices_within_band(
            run_min,
            run_max,
            base_close=float(base_close),
            band_abs=band_abs,
            factors=track,
        ):
            last_good_i = i
        else:
            first_fail_i = i
            break

    last_good: dict[str, Any] | None = None
    first_fail: dict[str, Any] | None = None
    if last_good_i is not None:
        last_good = compute_undulate(ordered, dates[last_good_i], end_iso)
        last_good["factor"] = factor
        last_good["band"] = band_abs
    if first_fail_i is not None:
        try:
            first_fail = compute_undulate(ordered, dates[first_fail_i], end_iso)
            first_fail["factor"] = factor
            first_fail["band"] = band_abs
        except ValueError:
            first_fail = None

    return {
        "found": last_good is not None,
        "factor": factor,
        "band": band_abs,
        "end": last_good["end"] if last_good else (
            first_fail["end"] if first_fail else end_iso
        ),
        "tested": tested,
        "reached_start": reached_start,
        "window": last_good,
        "first_fail": first_fail,
    }


def lowest_day(
    window: dict[str, Any],
    *,
    factor: str = "close",
) -> dict[str, Any] | None:
    """在 ``compute_undulate`` 结果的区间内，找指定价格最低的交易日。

    返回 ``{date, factor, label, price, prices}``；区间无有效价格时返回 ``None``。
    """
    if factor not in LOW_FACTOR_CHOICES:
        raise ValueError(
            f"不支持的取价口径 {factor!r}，可选 {LOW_FACTOR_CHOICES}"
        )
    best: dict[str, Any] | None = None
    for day in window.get("days") or []:
        prices = day.get("prices") or {}
        price = prices.get(factor)
        if price is None:
            continue
        if best is None or float(price) < float(best["price"]):
            best = {
                "date": day.get("date"),
                "factor": factor,
                "label": FACTOR_LABELS.get(factor, factor),
                "price": float(price),
                "prices": dict(prices),
            }
    return best


def score_low_point(
    bars: list[dict[str, Any]],
    low_date: str,
    *,
    series: str = "close",
    layers: int = 3,
    smooth_window: int = 1,
    match_beg: str = "",
    match_end: str = "",
) -> dict[str, Any]:
    """在给定日线跑 local_extrema 评分，返回整体结果与最低价日对应评分行。

    调用方通常传入最近约 600 个交易日（层级默认 3），以便谷序列在更长语境下相对打分；
    ``match_beg`` / ``match_end`` 用于在最低价日未命中极值时，仅在该窗口内回退
    取价格最低波谷（避免误取回溯窗口外的全局最低谷）。

    ``series`` 不在可选序列内时回退到 ``close``。
    """
    from company.analysis.line.local_extrema.service import (
        SERIES_OPTIONS,
        compute_alternating_extrema,
    )

    key = series if series in SERIES_OPTIONS else "close"
    analysis = compute_alternating_extrema(
        bars,
        layers=layers,
        series=key,
        smooth_window=smooth_window,
    )

    rows: list[dict[str, Any]] = []
    rows.extend(analysis.get("trough_scores") or [])
    rows.extend(analysis.get("peak_scores") or [])

    match = next((r for r in rows if r.get("date") == low_date), None)
    if match is None:
        troughs = list(analysis.get("trough_scores") or [])
        beg = str(match_beg or "")[:10]
        end = str(match_end or "")[:10]
        if beg and end:
            troughs = [
                r
                for r in troughs
                if beg <= str(r.get("date") or "")[:10] <= end
            ]
        if troughs:
            match = min(
                troughs, key=lambda r: float(r.get("price") or float("inf"))
            )

    return {"series": key, "match": match, "analysis": analysis}


def summarize_sigma(
    vol: dict[str, Any],
    *,
    factors: tuple[str, ...] = FACTORS,
) -> dict[str, Any]:
    """把 ``compute_volatility`` / ``analyze_volatility`` 结果收成 σ / z 汇总。

    输出区间起止日，以及四价在「开始日 / 结束日」的涨跌幅及其以标准差为单位
    的坐标：``sigma = pct / σ``、``z = (pct - mean) / σ``。
    """
    stats = vol.get("stats") or {}
    out: dict[str, Any] = {
        "beg": vol.get("beg"),
        "end": vol.get("end"),
        "base": vol.get("base"),
        "stats": {},
    }
    for f in factors:
        row = stats.get(f) or {}
        out["stats"][f] = {
            "label": row.get("label", FACTOR_LABELS.get(f, f)),
            "beg_date": row.get("beg_date"),
            "beg_pct": row.get("beg_pct"),
            "beg_sigma": row.get("beg_sigma"),
            "beg_z": row.get("beg_z"),
            "end_date": row.get("end_date"),
            "end_pct": row.get("end_pct"),
            "end_sigma": row.get("end_sigma"),
            "end_z": row.get("end_z"),
            "mean": row.get("mean"),
            "std": row.get("std"),
        }
    return out


def slim_window(pack: dict[str, Any] | None) -> dict[str, Any] | None:
    """只保留窗口的起止日期、样本数与四价范围，便于把「失败窗口」放进结果。"""
    if not pack:
        return None
    return {
        "beg": pack.get("beg"),
        "end": pack.get("end"),
        "count": pack.get("count"),
        "range": pack.get("range"),
    }
