"""区间评估的纯函数：波动筛选、最低价日、极值评分、标准差坐标。

无网络、无 IO，输入已排序 / 未排序的日线序列即可，便于单测。

口径与 ``undulate`` 完全一致：以「起始日前一交易日收盘」为基准，区间内每个
交易日的四价相对该基准算涨跌幅。波动筛选要求区间内指定价格（或四价）的
涨跌幅都落在 ``[-band, band]``，``band=0.09`` 即 ±9%。
"""

from __future__ import annotations

from typing import Any

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

    ordered = sorted(bars, key=_bar_date)
    dates = [d for d in (_bar_date(b) for b in ordered) if d]
    if not dates:
        raise ValueError("无日线数据")

    end_iso = _iso(end) if end else dates[-1]
    cand = [d for d in dates if d <= end_iso]
    if not cand:
        raise ValueError(f"{end_iso} 之前无交易日")

    last_good: dict[str, Any] | None = None
    first_fail: dict[str, Any] | None = None
    reached_start = False
    tested = 0

    for k in range(len(cand) - 1, -1, -1):
        beg = cand[k]
        try:
            pack = compute_undulate(ordered, beg, end_iso)
        except ValueError:
            # 起始日之前没有基准交易日，无法再往前推
            reached_start = True
            break
        pack["factor"] = factor
        pack["band"] = abs(float(band))
        tested += 1
        if window_within(pack, factor=factor, band=band):
            last_good = pack
        else:
            first_fail = pack
            break

    return {
        "found": last_good is not None,
        "factor": factor,
        "band": abs(float(band)),
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
    window_bars: list[dict[str, Any]],
    low_date: str,
    *,
    series: str = "close",
    layers: int = 1,
    smooth_window: int = 1,
) -> dict[str, Any]:
    """在区间日线跑 local_extrema 评分，返回整体结果与最低价日对应评分行。

    ``series`` 不在可选序列内时回退到 ``close``。若最低价日不是检测到的极值点，
    退而取区间内价格最低的波谷评分行（仍无则 ``match=None``）。
    """
    from company.analysis.line.local_extrema.service import (
        SERIES_OPTIONS,
        compute_alternating_extrema,
    )

    key = series if series in SERIES_OPTIONS else "close"
    analysis = compute_alternating_extrema(
        window_bars,
        layers=layers,
        series=key,
        smooth_window=smooth_window,
    )

    rows: list[dict[str, Any]] = []
    rows.extend(analysis.get("trough_scores") or [])
    rows.extend(analysis.get("peak_scores") or [])

    match = next((r for r in rows if r.get("date") == low_date), None)
    if match is None:
        troughs = analysis.get("trough_scores") or []
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
