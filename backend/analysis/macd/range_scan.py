"""区间内逐交易日 MACD 筛选 + 事后最大涨幅。

股票池 / 日线 / 指数 / MACD 序列在区间内共用：每只股票只拉一次 K 线、
只算一次 MACD，再按交易日切片判定金叉与稳定区间。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

from analysis.macd.analyze import analyze_macd_stable_on_bars
from analysis.macd.config import (
    DEFAULT_ADJUST,
    DEFAULT_BAND,
    DEFAULT_CROSS_TYPE,
    DEFAULT_FACTOR,
    DEFAULT_FAST,
    DEFAULT_INDEX,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_NEAR_RATIO,
    DEFAULT_SIGNAL,
    DEFAULT_SLOW,
    DEFAULT_W_DIV,
    DEFAULT_W_PRIOR,
    DEFAULT_WORKERS,
    MAX_RANGE_DAYS,
    MAX_WORKERS,
    PROGRESS_EVERY,
)
from analysis.macd.forward import max_forward_gains_from_bars
from analysis.macd.screen import cross_type_matches, slim_row
from analysis.universe import is_eligible_stock
from company.analysis.line.evaluate.service import EXTREMA_LOOKBACK_DAYS
from company.analysis.line.MACD.core import compute_macd
from company.analysis.line.undulate.service import (
    _bar_date,
    _fetch_day_range,
    _iso,
    _today_iso,
)
from company.analysis.line.undulate.volatility import (
    _fetch_index_day_range,
    _norm_index_code,
)
from core.codes import normalize_code
from market.industry.service import service as industry_service
from market.steep.calendar import recent_trade_dates

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _ymd_to_iso(ymd: str) -> str:
    text = str(ymd or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return _iso(text)


def trade_dates_in_range(start: str, end: str) -> list[str]:
    """``[start, end]`` 内交易日，升序 YYYY-MM-DD。"""
    beg_iso = _iso(start)
    end_iso = _iso(end)
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")

    today = _today_iso()
    span = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(beg_iso, "%Y-%m-%d")).days
    need = max(80, int(span * 0.8) + 40, MAX_RANGE_DAYS + 10)
    raws = recent_trade_dates(need)
    dates = sorted(
        d
        for d in (_ymd_to_iso(r) for r in raws)
        if beg_iso <= d <= end_iso
    )
    seen: set[str] = set()
    out: list[str] = []
    for d in dates:
        if d in seen:
            continue
        seen.add(d)
        out.append(d)
    return out


def _gain_fields(gain: dict[str, Any]) -> dict[str, Any]:
    return {
        "base_close": gain.get("base_close"),
        "hold_days": gain.get("hold_days"),
        "max_close_gain": gain.get("max_close_gain"),
        "max_close_date": gain.get("max_close_date"),
        "max_close_price": gain.get("max_close_price"),
        "max_high_gain": gain.get("max_high_gain"),
        "max_high_date": gain.get("max_high_date"),
        "max_high_price": gain.get("max_high_price"),
        "last_close": gain.get("last_close"),
        "last_close_gain": gain.get("last_close_gain"),
        "last_date": gain.get("last_date"),
    }


def _hist_span(
    *,
    start: str,
    asof: str,
    lookback_days: int,
) -> tuple[str, str]:
    """区间扫描共用日线窗口：[start−lookback/extrema, asof]。"""
    pad = max(int(lookback_days), int(EXTREMA_LOOKBACK_DAYS), 60)
    beg = (
        datetime.strptime(_iso(start), "%Y-%m-%d") - timedelta(days=pad)
    ).strftime("%Y-%m-%d")
    return beg, _iso(asof)


def _prefetch_index(
    index: str,
    *,
    beg_iso: str,
    end_iso: str,
) -> dict[str, Any] | None:
    index_code = _norm_index_code(index) or str(index or "").strip()
    if not index_code:
        return None
    try:
        return _fetch_index_day_range(index_code, beg_iso=beg_iso, end_iso=end_iso)
    except Exception as exc:  # noqa: BLE001
        logger.info("index prefetch failed %s: %s", index_code, exc)
        return None


def _sort_key(row: dict[str, Any]) -> tuple:
    close_g = row.get("max_close_gain")
    high_g = row.get("max_high_gain")
    total = row.get("score_total")
    return (
        -(close_g if close_g is not None else -1.0),
        -(high_g if high_g is not None else -1.0),
        -(total if total is not None else -1.0),
        str(row.get("signal_day") or ""),
        str(row.get("code") or ""),
    )


def _scan_one_stock(
    meta: dict[str, Any],
    *,
    days: list[str],
    hist_beg: str,
    hist_end: str,
    asof: str,
    band: float,
    index: str,
    factor: str,
    adjust: str,
    near_ratio: float,
    fast: int,
    slow: int,
    signal: int,
    w_prior: float,
    w_div: float,
    cross_type: str,
    index_hist: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None, str | None]:
    """返回 ``(命中行, 日线bars或None, 错误)``。

    命中行在扫描阶段就用地已拉到的日线算好事后涨幅，running 推送即完整。
    """
    code = normalize_code(str(meta.get("code") or ""))
    if not code:
        return [], None, "缺少代码"
    try:
        pack = _fetch_day_range(code, beg_iso=hist_beg, end_iso=hist_end, adjust=adjust)
    except Exception as exc:  # noqa: BLE001
        return [], None, str(exc)

    bars = list(pack.get("items") or [])
    if not bars:
        return [], None, None

    name = str(pack.get("name") or meta.get("name") or "")
    source = str(pack.get("source") or "")
    bar_dates = [d for d in (_bar_date(b) for b in bars) if d]
    if not bar_dates:
        return [], bars, None

    try:
        macd_pack = compute_macd(
            bars,
            bar_dates[0],
            bar_dates[-1],
            fast=fast,
            slow=slow,
            signal=signal,
            price="close",
        )
    except ValueError:
        return [], bars, None

    macd_items = list(macd_pack.get("items") or [])
    hits: list[dict[str, Any]] = []
    for day in days:
        try:
            analyzed = analyze_macd_stable_on_bars(
                code,
                bars,
                end=day,
                name=name,
                source=source,
                factor=factor,
                band=band,
                index=index,
                adjust=adjust,
                near_ratio=near_ratio,
                fast=fast,
                slow=slow,
                signal=signal,
                w_prior=w_prior,
                w_div=w_div,
                index_hist=index_hist,
                macd_items=macd_items,
                allow_fetch_more=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("range day analyze failed %s %s: %s", code, day, exc)
            continue

        if not analyzed.get("found"):
            continue
        cross = ((analyzed.get("macd") or {}).get("cross") or {})
        if not cross_type_matches(cross, cross_type):
            continue
        row = slim_row(analyzed, meta=meta)
        if not row:
            continue
        row["signal_day"] = day
        gain = max_forward_gains_from_bars(bars, signal_date=day, asof=asof)
        row.update(_gain_fields(gain))
        hits.append(row)
    return hits, bars, None


def screen_macd_range(
    *,
    start: str,
    end: str = "",
    band: float = DEFAULT_BAND,
    index: str = DEFAULT_INDEX,
    factor: str = DEFAULT_FACTOR,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    adjust: str = DEFAULT_ADJUST,
    near_ratio: float = DEFAULT_NEAR_RATIO,
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    signal: int = DEFAULT_SIGNAL,
    w_prior: float = DEFAULT_W_PRIOR,
    w_div: float = DEFAULT_W_DIV,
    cross_type: str = DEFAULT_CROSS_TYPE,
    workers: int = DEFAULT_WORKERS,
    force: bool = False,
    asof: str = "",
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """对 ``[start, end]`` 每个交易日筛金叉，并附带事后最大涨幅。

    ``force`` 保留兼容（区间结果由 range_service 缓存）；本函数每次现算。
    """
    _ = force
    beg_iso = _iso(start)
    end_iso = _iso(end) if str(end or "").strip() else _today_iso()
    asof_iso = _iso(asof) if str(asof or "").strip() else _today_iso()
    days = trade_dates_in_range(beg_iso, end_iso)
    if not days:
        raise ValueError(f"区间 [{beg_iso}, {end_iso}] 内无交易日")
    if len(days) > MAX_RANGE_DAYS:
        raise ValueError(
            f"区间交易日过多（{len(days)}），最多 {MAX_RANGE_DAYS} 天；"
            "请缩小 start/end"
        )

    cross_type_key = str(cross_type or "").strip().lower() or DEFAULT_CROSS_TYPE
    params = {
        "start": beg_iso,
        "end": end_iso,
        "asof": asof_iso,
        "band": float(band),
        "index": str(index or DEFAULT_INDEX).strip() or DEFAULT_INDEX,
        "factor": str(factor or DEFAULT_FACTOR).strip().lower() or DEFAULT_FACTOR,
        "lookback": int(lookback_days),
        "adjust": str(adjust or DEFAULT_ADJUST).strip().lower() or DEFAULT_ADJUST,
        "near_ratio": abs(float(near_ratio)),
        "fast": int(fast),
        "slow": int(slow),
        "signal": int(signal),
        "w_prior": float(w_prior),
        "w_div": float(w_div),
        "cross_type": cross_type_key,
        "day_count": len(days),
        "shared_bars": True,
    }

    industry_service.stocks.ensure_populated()
    stocks = [
        meta
        for meta in industry_service.stocks.all_stocks()
        if is_eligible_stock(meta)
    ]
    total = len(stocks)
    hist_beg, hist_end = _hist_span(
        start=beg_iso, asof=asof_iso, lookback_days=params["lookback"]
    )
    # 指数覆盖：历史窗起点 → 区间末日（稳定区间/反向日）+ asof
    index_end = max(end_iso, asof_iso)
    index_hist = _prefetch_index(
        params["index"], beg_iso=hist_beg, end_iso=index_end
    )

    def _assemble(
        *,
        analyzed: int,
        flat: list[dict[str, Any]],
        day_rows: list[dict[str, Any]],
        phase: str,
        error_count: int = 0,
    ) -> dict[str, Any]:
        return {
            "params": params,
            "phase": phase,
            "candidate_count": total,
            "analyzed_count": analyzed,
            "error_count": error_count,
            "days_total": len(days),
            "days_done": len(days) if phase in ("gains", "done") else 0,
            "current_day": None,
            "day_progress": {"done": analyzed, "total": total},
            "day_count": len(day_rows),
            "result_count": len(flat),
            "days": day_rows,
            "items": sorted(flat, key=_sort_key),
            "updated_at": _now_iso(),
            "note": (
                f"区间 [{beg_iso}, {end_iso}] 共 {len(days)} 个交易日；"
                "股票池/日线/指数/MACD 共用，按日切片判金叉；"
                f"涨幅基准=信号日收盘，统计至 {asof_iso}"
            ),
        }

    flat: list[dict[str, Any]] = []
    analyzed = 0
    error_count = 0

    empty_days = [{"date": d, "found_count": 0, "items": []} for d in days]
    if on_update:
        on_update(
            _assemble(
                analyzed=0,
                flat=flat,
                day_rows=empty_days,
                phase="screening",
            )
        )

    if not stocks:
        return {
            **_assemble(
                analyzed=0,
                flat=[],
                day_rows=empty_days,
                phase="done",
            ),
            "note": "股票索引为空",
        }

    max_workers = min(max(1, workers), int(MAX_WORKERS), max(1, total))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {
            executor.submit(
                _scan_one_stock,
                meta,
                days=days,
                hist_beg=hist_beg,
                hist_end=hist_end,
                asof=asof_iso,
                band=params["band"],
                index=params["index"],
                factor=params["factor"],
                adjust=params["adjust"],
                near_ratio=params["near_ratio"],
                fast=params["fast"],
                slow=params["slow"],
                signal=params["signal"],
                w_prior=params["w_prior"],
                w_div=params["w_div"],
                cross_type=params["cross_type"],
                index_hist=index_hist,
            ): meta
            for meta in stocks
        }
        for fut in as_completed(futs):
            hits, _bars, err = fut.result()
            analyzed += 1
            if err:
                error_count += 1
            if hits:
                flat.extend(hits)
            if on_update and (
                analyzed == total
                or analyzed % PROGRESS_EVERY == 0
                or analyzed == 1
            ):
                by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for row in flat:
                    by_day[str(row.get("signal_day") or "")].append(row)
                day_rows = [
                    {
                        "date": d,
                        "found_count": len(by_day.get(d) or []),
                        "items": list(by_day.get(d) or []),
                    }
                    for d in days
                ]
                on_update(
                    _assemble(
                        analyzed=analyzed,
                        flat=flat,
                        day_rows=day_rows,
                        phase="screening",
                        error_count=error_count,
                    )
                )

    # 命中行在扫描阶段已带上事后涨幅，这里按日分组收尾即可。
    by_day_final: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in flat:
        by_day_final[str(row.get("signal_day") or "")].append(row)
    final_days = [
        {
            "date": d,
            "found_count": len(by_day_final.get(d) or []),
            "items": sorted(by_day_final.get(d) or [], key=_sort_key),
        }
        for d in days
    ]

    return _assemble(
        analyzed=analyzed,
        flat=flat,
        day_rows=final_days,
        phase="done",
        error_count=error_count,
    )


__all__ = ["screen_macd_range", "trade_dates_in_range"]
