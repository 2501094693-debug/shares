"""区间内逐交易日 MACD 筛选 + 事后最大涨幅。

股票池 / 日线 / MACD 序列在区间内共用：每只股票只拉一次 K 线、
只算一次 MACD，再按交易日切片判定金叉；命中后对金叉前 DIF<DEA 段
做对数匀速偏离加速度（``prior_below``），并统计事后涨跌。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

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
from analysis.macd.forward import forward_gains_after_signal
from analysis.macd.screen import cross_type_matches
from analysis.macd.signals import (
    SIGNAL_OVER_NEAR,
    SIGNAL_UNDER_NEAR,
    classify_macd_cross,
)
from analysis.universe import is_eligible_stock
from company.analysis.line.MACD.core import compute_macd
from company.analysis.line.MACD.prior_below import analyze_prior_below
from company.analysis.line.undulate.service import (
    _bar_date,
    _fetch_day_range,
    _iso,
    _today_iso,
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
        "valid": gain.get("valid"),
        "near_ok": gain.get("near_ok"),
        "judgment_failed": gain.get("judgment_failed"),
        "end_date": gain.get("end_date"),
        "end_source": gain.get("end_source"),
        "open_ended": gain.get("open_ended"),
        "break_date": gain.get("break_date"),
        "cross_date": gain.get("cross_date"),
        "max_close_gain": gain.get("max_close_gain"),
        "max_close_date": gain.get("max_close_date"),
        "max_close_price": gain.get("max_close_price"),
        "max_close_drop": gain.get("max_close_drop"),
        "max_close_drop_date": gain.get("max_close_drop_date"),
        "max_close_drop_price": gain.get("max_close_drop_price"),
        "end_close": gain.get("end_close"),
        "end_close_gain": gain.get("end_close_gain"),
        "last_close": gain.get("last_close"),
        "last_close_gain": gain.get("last_close_gain"),
        "last_date": gain.get("last_date"),
    }


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def _hist_span(
    *,
    start: str,
    end: str,
    lookback_days: int,
) -> tuple[str, str]:
    """区间扫描共用日线窗口：[start−lookback, max(end, 今日)]。

    终点取到最新，以便信号日后能找到 DIF≥DEA 段的跌破日。
    """
    pad = max(int(lookback_days), 60)
    beg = (
        datetime.strptime(_iso(start), "%Y-%m-%d") - timedelta(days=pad)
    ).strftime("%Y-%m-%d")
    end_iso = _iso(end) if str(end or "").strip() else _today_iso()
    return beg, max(end_iso, _today_iso())


def _sort_key(row: dict[str, Any]) -> tuple:
    close_g = row.get("max_close_gain")
    end_g = row.get("end_close_gain")
    down = row.get("down_accel")
    up = row.get("up_accel")
    valid = 0 if row.get("valid") is False else 1
    return (
        -valid,
        -(close_g if close_g is not None else -1.0),
        -(end_g if end_g is not None else -1.0),
        -(down if down is not None else -1e9),
        -(up if up is not None else -1e9),
        str(row.get("signal_day") or ""),
        str(row.get("code") or ""),
    )


def _build_hit_row(
    *,
    code: str,
    name: str,
    day: str,
    cross: dict[str, Any],
    prior: dict[str, Any],
    gain: dict[str, Any],
) -> dict[str, Any]:
    primary = str(cross.get("primary") or "")
    latest_dif = _num(cross.get("dif"))
    latest_dea = _num(cross.get("dea"))
    return {
        "code": code,
        "name": name,
        "signal_day": day,
        "macd_signal": primary,
        "macd_signals": list(cross.get("signals") or []),
        "macd_date": str(cross.get("date") or "")[:10] or None,
        "gap_velocity": _num(cross.get("gap_velocity")),
        "pred_next_gap": _num(cross.get("pred_next_gap")),
        "pred_next_cross": cross.get("pred_next_cross"),
        "near_by_prediction": cross.get("near_by_prediction"),
        "near_by_relative_gap": cross.get("near_by_relative_gap"),
        "dif": latest_dif,
        "dea": latest_dea,
        "underwater": cross.get("underwater"),
        # 金叉前 DIF<DEA 段（prior_below）
        "beg": str(prior.get("beg") or "")[:10] or None,
        "end": str(prior.get("end") or "")[:10] or None,
        "count": int(prior.get("count") or 0),
        "include_signal": prior.get("include_signal"),
        "trough_date": str(prior.get("trough_date") or "")[:10] or None,
        "trough_close": _num(prior.get("trough_close")),
        "down_accel": _num(prior.get("down_accel")),
        "up_accel": _num(prior.get("up_accel")),
        **_gain_fields(gain),
    }


def _scan_one_stock(
    meta: dict[str, Any],
    *,
    days: list[str],
    hist_beg: str,
    hist_end: str,
    adjust: str,
    near_ratio: float,
    fast: int,
    slow: int,
    signal: int,
    cross_type: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None, str | None]:
    """返回 ``(命中行, 日线bars或None, 错误)``。

    命中行在扫描阶段就用已拉到的日线/MACD 算好 prior_below 与事后涨跌。
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
    closes_by_date: dict[str, float] = {}
    for bar in bars:
        d = _bar_date(bar)
        if not d:
            continue
        try:
            closes_by_date[d] = float(bar.get("close"))
        except (TypeError, ValueError):
            continue

    # prior_below / 事后涨跌都需要收盘价；compute_macd 已有 price，再补 close
    for row in macd_items:
        d = str(row.get("date") or "")[:10]
        if d in closes_by_date:
            row["close"] = closes_by_date[d]

    hits: list[dict[str, Any]] = []
    # days 升序：单指针推进，O(n) 完成逐日 MACD 前缀
    macd_i = 0
    n_macd = len(macd_items)
    for day in days:
        while macd_i < n_macd and str(macd_items[macd_i].get("date") or "")[:10] <= day:
            macd_i += 1
        if macd_i <= 0:
            continue
        macd_prefix = macd_items[:macd_i]
        try:
            cross = classify_macd_cross(macd_prefix, near_ratio=near_ratio)
        except Exception as exc:  # noqa: BLE001
            logger.info("range day classify failed %s %s: %s", code, day, exc)
            continue
        if not cross.get("matched"):
            continue
        if not cross_type_matches(cross, cross_type):
            continue

        primary = str(cross.get("primary") or "")
        signal_idx = len(macd_prefix) - 1
        try:
            prior = analyze_prior_below(
                macd_prefix,
                signal_idx,
                signal=primary,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("range day prior_below failed %s %s: %s", code, day, exc)
            continue
        if not prior.get("found"):
            continue

        is_near = primary in (SIGNAL_UNDER_NEAR, SIGNAL_OVER_NEAR)
        gain = forward_gains_after_signal(
            macd_items,
            signal_date=day,
            is_near=is_near,
            closes_by_date=closes_by_date,
        )
        hits.append(
            _build_hit_row(
                code=code,
                name=name,
                day=day,
                cross=cross,
                prior=prior,
                gain=gain,
            )
        )
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
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """对 ``[start, end]`` 每个交易日筛金叉，并附带 DIF≥DEA 段事后涨跌。

    命中后对金叉前连续 ``DIF < DEA`` 段计算 ``prior_below`` 加速度；
    涨跌截止日 = 金叉后首次 ``DIF < DEA``；找不到则用最新交易日。
    即将金叉若后续未真正金叉，则标 ``valid=False``。

    ``band`` / ``index`` / ``factor`` / ``w_prior`` / ``w_div`` 保留入参以兼容
    API 缓存键，区间回测路径不再使用稳定区间与股指反向打分。
    ``force`` 保留兼容（区间结果由 range_service 缓存）；本函数每次现算。
    """
    _ = force, band, index, factor, w_prior, w_div
    beg_iso = _iso(start)
    end_iso = _iso(end) if str(end or "").strip() else _today_iso()
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
        "score": "prior_below",
        "gain_until": "first_dif_below",
    }

    industry_service.stocks.ensure_populated()
    stocks = [
        meta
        for meta in industry_service.stocks.all_stocks()
        if is_eligible_stock(meta)
    ]
    total = len(stocks)
    hist_beg, hist_end = _hist_span(
        start=beg_iso, end=end_iso, lookback_days=params["lookback"]
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
                "股票池/日线/MACD 共用，按日切片判金叉；"
                "得分=金叉前 DIF<DEA 段对数匀速偏离加速度（prior_below）；"
                "涨跌基准=信号日收盘，截止=DIF≥DEA 后首个 DIF<DEA（无则最新日）；"
                "即将金叉未真正金叉则标无效"
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
                adjust=params["adjust"],
                near_ratio=params["near_ratio"],
                fast=params["fast"],
                slow=params["slow"],
                signal=params["signal"],
                cross_type=params["cross_type"],
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
