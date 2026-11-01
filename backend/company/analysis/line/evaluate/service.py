"""区间评估主入口：±band 最大波动区间 + 最低价日评分 + 个股 / 指数 σ 坐标。

流程：

1. 结束日固定为最新交易日；起始日先也设为最新交易日，得到窗口
   ``[起始日, 结束日]``；
2. 用 ``undulate`` 口径（相对起始日前一交易日收盘的四价涨跌幅）判断窗口
   是否落在 ``[-band, band]``（默认 ±9%）。满足则起始日往前推一个交易日，
   继续判断，直到首次不满足，取最后一次满足的区间为「最大起始日期范围」；
3. 在该区间内找出收盘价（``low_factor`` 可切换四价）最低的交易日；
4. 用 ``local_extrema`` 对该区间做极值评分，给出最低价日对应的评分；
5. 用 ``undulate`` 给出个股与指数在该区间的起止日，以及开始日 / 结束日涨跌幅
   以标准差为单位（σ / z）的坐标。

个股日线走 ``company.line.fetcher.fetch_kline``（默认前复权）；指数走 ``exponent``。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.codes import normalize_code

from company.analysis.line.undulate.service import (
    _bar_date,
    _fetch_day_range,
    _iso,
    _today_iso,
)
from company.analysis.line.undulate.volatility import (
    _norm_index_code,
    analyze_volatility,
    compute_volatility,
)

from company.analysis.line.evaluate.core import (
    DEFAULT_BAND,
    LOW_FACTOR_CHOICES,
    TEST_FACTOR_CHOICES,
    find_max_range,
    lowest_day,
    score_low_point,
    slim_window,
    summarize_sigma,
)

# 默认对比指数（上证指数），可传其它宽基公开码
DEFAULT_INDEX = "000001"
# 默认回溯自然日；若窗口触到数据头部仍满足，会自动翻倍向前扩展
DEFAULT_LOOKBACK_DAYS = 900
MAX_LOOKBACK_DAYS = 3650


def _index_sigma(
    index_code: str, beg_iso: str, end_iso: str
) -> dict[str, Any]:
    """指数区间 σ 坐标；失败时降级为带 error 的空块，不影响整体结果。"""
    try:
        vol = analyze_volatility(index_code, beg_iso, end_iso, kind="index")
    except Exception as exc:  # noqa: BLE001
        return {
            "code": index_code,
            "name": "",
            "kind": "index",
            "error": str(exc),
            "stats": {},
        }
    return {
        "code": vol.get("code") or index_code,
        "name": vol.get("name") or "",
        "kind": "index",
        **summarize_sigma(vol),
    }


def analyze_evaluate(
    code: str,
    *,
    end: str = "",
    factor: str = "close",
    low_factor: str = "close",
    band: float = DEFAULT_BAND,
    index: str = DEFAULT_INDEX,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    adjust: str = "qfq",
    layers: int = 1,
    smooth_window: int = 1,
) -> dict[str, Any]:
    """主入口：最新交易日起的最大 ±band 区间 + 最低价日评分 + 股 / 指 σ 坐标。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    if factor not in TEST_FACTOR_CHOICES:
        raise ValueError(
            f"不支持的波动口径 {factor!r}，可选 {TEST_FACTOR_CHOICES}"
        )
    if low_factor not in LOW_FACTOR_CHOICES:
        raise ValueError(
            f"不支持的取价口径 {low_factor!r}，可选 {LOW_FACTOR_CHOICES}"
        )

    end_iso = _iso(end) if end else _today_iso()
    band_abs = abs(float(band))

    # 取数：先按默认回溯拉一段；触到头部仍满足会自动翻倍扩展
    lb = max(60, int(lookback_days))
    max_lb = max(lb, MAX_LOOKBACK_DAYS)
    while True:
        beg_lb = (
            datetime.strptime(end_iso, "%Y-%m-%d") - timedelta(days=lb)
        ).strftime("%Y-%m-%d")
        hist = _fetch_day_range(norm, beg_iso=beg_lb, end_iso=end_iso, adjust=adjust)
        bars = list(hist.get("items") or [])
        if not bars:
            raise ValueError("无日线数据")
        result = find_max_range(bars, end=end_iso, factor=factor, band=band_abs)
        if result.get("found") and result.get("reached_start") and lb < max_lb:
            lb = min(max_lb, lb * 2)
            continue
        break

    meta = {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adjust,
        "factor": factor,
        "low_factor": low_factor,
        "band": band_abs,
    }

    if not result.get("found"):
        return {
            **meta,
            "found": False,
            "message": (
                f"最新交易日单日窗口已超出 ±{band_abs * 100:.2f}% 波动带，"
                "未找到满足条件的区间"
            ),
            "first_fail": slim_window(result.get("first_fail")),
        }

    window = result["window"]
    beg_iso = window["beg"]
    used_end = window["end"]

    low = lowest_day(window, factor=low_factor)
    window_bars = [
        b for b in bars if beg_iso <= _bar_date(b) <= used_end
    ]

    score_block: dict[str, Any] | None = None
    if low is not None:
        scored = score_low_point(
            window_bars,
            low["date"],
            series=low_factor,
            layers=layers,
            smooth_window=smooth_window,
        )
        analysis = scored.get("analysis") or {}
        score_block = {
            "series": scored.get("series"),
            "target": scored.get("match"),
            "extrema_count": analysis.get("extrema_count"),
            "peak_count": analysis.get("peak_count"),
            "trough_count": analysis.get("trough_count"),
            "peak_scores": analysis.get("peak_scores"),
            "trough_scores": analysis.get("trough_scores"),
        }

    # 个股 σ：直接用已拉的日线算，避免二次联网
    stock_sigma = {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "kind": "stock",
        "adjust": adjust,
        **summarize_sigma(compute_volatility(bars, beg_iso, used_end)),
    }

    index_code = _norm_index_code(index) or DEFAULT_INDEX
    index_sigma = _index_sigma(index_code, beg_iso, used_end)

    return {
        **meta,
        "found": True,
        "range": {
            "beg": beg_iso,
            "end": used_end,
            "count": window.get("count"),
            "base": window.get("base"),
            "range": window.get("range"),
        },
        "days": window.get("days"),
        "tested": result.get("tested"),
        "reached_start": result.get("reached_start"),
        "first_fail": slim_window(result.get("first_fail")),
        "low_point": low,
        "score": score_block,
        "stock": stock_sigma,
        "index": index_sigma,
    }
