"""全市场 MACD 金叉 + 稳定区间综合分筛选。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

from market.industry.service import service as industry_service

from analysis.macd.analyze import analyze_macd_stable
from analysis.macd.config import (
    ALLOWED_CROSS_TYPES,
    CROSS_TYPE_ALL,
    CROSS_TYPE_OVER,
    CROSS_TYPE_UNDER,
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
    MAX_WORKERS,
    PROGRESS_EVERY,
)
from analysis.recent_low.screen import is_eligible_stock
from company.analysis.line.evaluate.service import (
    EXTREMA_LOOKBACK_DAYS,
    MAX_LOOKBACK_DAYS,
)
from company.analysis.line.undulate.service import _iso, _today_iso
from company.analysis.line.undulate.volatility import (
    _fetch_index_day_range,
    _norm_index_code,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def cross_type_matches(cross: dict[str, Any], cross_type: str) -> bool:
    """判断信号是否属于指定类别。

    ``under`` 命中水下金叉 / 即将水下金叉，``over`` 命中水上金叉 /
    即将水上金叉，``all`` 不做过滤。无信号或非法类别均不命中。
    """
    key = str(cross_type or "").strip().lower()
    if key not in ALLOWED_CROSS_TYPES:
        key = CROSS_TYPE_ALL
    if key == CROSS_TYPE_ALL:
        return True
    underwater = cross.get("underwater") if isinstance(cross, dict) else None
    if underwater is None:
        return False
    if key == CROSS_TYPE_UNDER:
        return bool(underwater)
    if key == CROSS_TYPE_OVER:
        return not bool(underwater)
    return False


def slim_row(
    pack: dict[str, Any], *, meta: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """把 analyze_macd_stable 结果压成列表行；未命中返回 None。"""
    if not pack or not pack.get("found"):
        return None

    code = str(pack.get("code") or (meta or {}).get("code") or "").strip()
    if not code:
        return None

    rng = pack.get("range") or {}
    macd = pack.get("macd") or {}
    cross = macd.get("cross") if isinstance(macd, dict) else None
    cross = cross if isinstance(cross, dict) else {}
    scored = pack.get("score") if isinstance(pack.get("score"), dict) else {}
    divergence = pack.get("divergence") if isinstance(pack.get("divergence"), dict) else {}
    low_close = pack.get("low_point_close") if isinstance(pack.get("low_point_close"), dict) else {}
    low_low = pack.get("low_point_low") if isinstance(pack.get("low_point_low"), dict) else {}
    latest = macd.get("latest") if isinstance(macd.get("latest"), dict) else {}

    reverse_count = divergence.get("reverse_count")
    try:
        rev_i = int(reverse_count) if reverse_count is not None else None
    except (TypeError, ValueError):
        rev_i = None

    return {
        "code": code,
        "name": str(pack.get("name") or (meta or {}).get("name") or ""),
        "macd_signal": cross.get("primary"),
        "macd_signals": list(cross.get("signals") or []),
        "macd_date": str(cross.get("date") or "")[:10] or None,
        "gap_velocity": _num(cross.get("gap_velocity")),
        "pred_next_gap": _num(cross.get("pred_next_gap")),
        "pred_next_cross": cross.get("pred_next_cross"),
        "near_by_prediction": cross.get("near_by_prediction"),
        "near_by_relative_gap": cross.get("near_by_relative_gap"),
        "dif": _num(cross.get("dif") if cross.get("dif") is not None else latest.get("dif")),
        "dea": _num(cross.get("dea") if cross.get("dea") is not None else latest.get("dea")),
        "underwater": cross.get("underwater"),
        "beg": str(rng.get("beg") or "")[:10],
        "end": str(rng.get("end") or "")[:10],
        "count": int(rng.get("count") or 0),
        "score_close": _num(scored.get("score_close")),
        "score_low": _num(scored.get("score_low")),
        "score_prior": _num(scored.get("score_prior")),
        "reverse_count": rev_i,
        "div_score": _num(scored.get("div_score")),
        "score_total": _num(scored.get("score_total")),
        "low_close_date": str(low_close.get("date") or "")[:10] or None,
        "low_close_price": _num(low_close.get("price")),
        "low_low_date": str(low_low.get("date") or "")[:10] or None,
        "low_low_price": _num(low_low.get("price")),
        "index": str(pack.get("index") or ""),
        "index_name": str((divergence.get("index") or {}).get("name") or ""),
    }


def _prefetch_index_hist(
    index: str,
    *,
    lookback_days: int,
    end: str = "",
) -> dict[str, Any] | None:
    index_code = _norm_index_code(index) or str(index or "").strip()
    if not index_code:
        return None
    end_iso = _iso(end) if end else _today_iso()
    span = max(int(lookback_days), int(EXTREMA_LOOKBACK_DAYS), int(MAX_LOOKBACK_DAYS))
    beg_iso = (
        datetime.strptime(end_iso, "%Y-%m-%d") - timedelta(days=span)
    ).strftime("%Y-%m-%d")
    try:
        return _fetch_index_day_range(index_code, beg_iso=beg_iso, end_iso=end_iso)
    except Exception as exc:  # noqa: BLE001
        logger.info("index prefetch failed %s: %s", index_code, exc)
        return None


def _analyze_one(
    meta: dict[str, Any],
    *,
    band: float,
    index: str,
    factor: str,
    lookback_days: int,
    adjust: str,
    near_ratio: float,
    fast: int,
    slow: int,
    signal: int,
    w_prior: float,
    w_div: float,
    cross_type: str = DEFAULT_CROSS_TYPE,
    end: str = "",
    index_hist: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    code = str(meta.get("code") or "").strip()
    if not code:
        return None, "缺少代码"
    try:
        pack = analyze_macd_stable(
            code,
            factor=factor,
            band=band,
            index=index,
            lookback_days=lookback_days,
            adjust=adjust,
            near_ratio=near_ratio,
            fast=fast,
            slow=slow,
            signal=signal,
            w_prior=w_prior,
            w_div=w_div,
            end=end,
            index_hist=index_hist,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("macd_stable failed %s: %s", code, exc)
        return None, str(exc)

    if not pack.get("found"):
        return None, None
    macd = pack.get("macd") if isinstance(pack.get("macd"), dict) else {}
    cross = macd.get("cross") if isinstance(macd.get("cross"), dict) else {}
    if not cross_type_matches(cross, cross_type):
        return None, None
    row = slim_row(pack, meta=meta)
    return row, None


def _sort_key(row: dict[str, Any]) -> tuple:
    total = row.get("score_total")
    prior = row.get("score_prior")
    count = row.get("count") or 0
    return (
        -(total if total is not None else -1.0),
        -(prior if prior is not None else -1.0),
        -int(count),
        str(row.get("code") or ""),
    )


def _assemble(
    *,
    params: dict[str, Any],
    total: int,
    items: list[dict[str, Any]],
    analyzed: int,
    error_count: int,
) -> dict[str, Any]:
    ordered = sorted(items, key=_sort_key)
    return {
        "params": params,
        "candidate_count": total,
        "analyzed_count": analyzed,
        "found_count": len(ordered),
        "error_count": error_count,
        "result_count": len(ordered),
        "items": ordered,
        "updated_at": _now_iso(),
        "note": (
            "主板/中小板等（非创业板、非科创板、非 ST、非退市）；"
            f"MACD 信号类别={params.get('cross_type') or 'all'}（all/under/over） + 最大稳定区间；"
            "收盘/最低前低分与股指反向日占比合成总分"
        ),
    }


def screen_macd_stable(
    *,
    band: float = DEFAULT_BAND,
    index: str = DEFAULT_INDEX,
    factor: str = DEFAULT_FACTOR,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    end: str = "",
    adjust: str = DEFAULT_ADJUST,
    near_ratio: float = DEFAULT_NEAR_RATIO,
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    signal: int = DEFAULT_SIGNAL,
    w_prior: float = DEFAULT_W_PRIOR,
    w_div: float = DEFAULT_W_DIV,
    cross_type: str = DEFAULT_CROSS_TYPE,
    workers: int = DEFAULT_WORKERS,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """全市场并发筛选；增量推送精简结果。"""
    industry_service.stocks.ensure_populated()
    stocks = [
        meta
        for meta in industry_service.stocks.all_stocks()
        if is_eligible_stock(meta)
    ]
    end_iso = _iso(end) if end else _today_iso()
    cross_type_key = str(cross_type or "").strip().lower()
    if cross_type_key not in ALLOWED_CROSS_TYPES:
        cross_type_key = DEFAULT_CROSS_TYPE
    params = {
        "band": float(band),
        "index": str(index or DEFAULT_INDEX).strip() or DEFAULT_INDEX,
        "factor": str(factor or DEFAULT_FACTOR).strip().lower() or DEFAULT_FACTOR,
        "lookback": int(lookback_days),
        "end": end_iso,
        "adjust": str(adjust or DEFAULT_ADJUST).strip().lower() or DEFAULT_ADJUST,
        "near_ratio": abs(float(near_ratio)),
        "fast": int(fast),
        "slow": int(slow),
        "signal": int(signal),
        "w_prior": float(w_prior),
        "w_div": float(w_div),
        "cross_type": cross_type_key,
        "exclude": "chinext+star+st+delisted",
    }
    total = len(stocks)
    items: list[dict[str, Any]] = []
    analyzed = 0
    error_count = 0

    empty = _assemble(
        params=params,
        total=total,
        items=items,
        analyzed=0,
        error_count=0,
    )
    if on_update:
        on_update(empty)
    if not stocks:
        return {**empty, "note": "股票索引为空"}

    index_hist = _prefetch_index_hist(
        params["index"], lookback_days=params["lookback"], end=end_iso
    )

    max_workers = min(max(1, workers), int(MAX_WORKERS), max(1, total))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {
            executor.submit(
                _analyze_one,
                meta,
                band=params["band"],
                index=params["index"],
                factor=params["factor"],
                lookback_days=params["lookback"],
                adjust=params["adjust"],
                near_ratio=params["near_ratio"],
                fast=params["fast"],
                slow=params["slow"],
                signal=params["signal"],
                w_prior=params["w_prior"],
                w_div=params["w_div"],
                cross_type=params["cross_type"],
                end=end_iso,
                index_hist=index_hist,
            ): meta
            for meta in stocks
        }
        for fut in as_completed(futs):
            row, err = fut.result()
            analyzed += 1
            if err:
                error_count += 1
            if row:
                items.append(row)
            if on_update and (
                analyzed == total
                or analyzed % PROGRESS_EVERY == 0
                or analyzed == 1
            ):
                on_update(
                    _assemble(
                        params=params,
                        total=total,
                        items=items,
                        analyzed=analyzed,
                        error_count=error_count,
                    )
                )

    return _assemble(
        params=params,
        total=total,
        items=items,
        analyzed=analyzed,
        error_count=error_count,
    )


__all__ = [
    "cross_type_matches",
    "is_eligible_stock",
    "screen_macd_stable",
    "slim_row",
]
