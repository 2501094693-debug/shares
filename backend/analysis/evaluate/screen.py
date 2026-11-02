"""全市场批量区间评估：并发调用 analyze_evaluate，产出精简行。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

from market.industry.service import service as industry_service

from company.analysis.line.evaluate.service import (
    EXTREMA_LOOKBACK_DAYS,
    MAX_LOOKBACK_DAYS,
    analyze_evaluate,
)
from company.analysis.line.undulate.service import _today_iso
from company.analysis.line.undulate.volatility import (
    _fetch_index_day_range,
    _norm_index_code,
)

from analysis.evaluate.config import (
    DEFAULT_BAND,
    DEFAULT_FACTOR,
    DEFAULT_INDEX,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_WORKERS,
    MAX_WORKERS,
    PROGRESS_EVERY,
)

logger = logging.getLogger(__name__)

# 创业板：深市 300 / 301；科创板：沪市 688 / 689
_CHINEXT_PREFIXES = ("300", "301")
_STAR_PREFIXES = ("688", "689")


def _bare6(code: str) -> str:
    text = str(code or "").strip().upper()
    # 兼容 300750 / sz.300001 / 300001.SZ
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else digits


def is_chinext(code: str) -> bool:
    """是否创业板（代码 300/301 开头）。"""
    bare = _bare6(code)
    return bare.startswith(_CHINEXT_PREFIXES)


def is_star(code: str) -> bool:
    """是否科创板（代码 688/689 开头）。"""
    bare = _bare6(code)
    return bare.startswith(_STAR_PREFIXES)


def is_st(name: str) -> bool:
    """名称是否含 ST（含 *ST / S*ST 等）。"""
    return "ST" in str(name or "").upper()


def is_eligible_stock(meta: dict[str, Any] | None) -> bool:
    """个股分析宇宙：排除创业板、科创板与 ST。"""
    if not meta:
        return False
    code = str(meta.get("code") or "").strip()
    if not code or is_chinext(code) or is_star(code):
        return False
    if is_st(str(meta.get("name") or "")):
        return False
    return True


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n == n else None  # NaN guard


def slim_row(pack: dict[str, Any], *, meta: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """把 analyze_evaluate 结果压成列表行；未命中区间返回 None。"""
    if not pack or not pack.get("found"):
        return None

    rng = pack.get("range") or {}
    paths = pack.get("paths") or {}
    divergence = pack.get("divergence") or {}
    score = pack.get("score") or {}
    target = score.get("target") if isinstance(score, dict) else None
    low = pack.get("low_point") or {}
    stock_block = paths.get("stock") if isinstance(paths, dict) else None
    index_block = paths.get("index") if isinstance(paths, dict) else None
    if not isinstance(index_block, dict):
        index_block = (divergence.get("index") if isinstance(divergence, dict) else None) or {}
    if not isinstance(stock_block, dict):
        stock_block = {}

    code = str(pack.get("code") or (meta or {}).get("code") or "").strip()
    if not code:
        return None

    low_score = None
    if isinstance(target, dict):
        low_score = _num(target.get("score"))

    stock_paths = stock_block.get("paths") if isinstance(stock_block.get("paths"), dict) else {}
    index_paths = index_block.get("paths") if isinstance(index_block.get("paths"), dict) else {}

    return {
        "code": code,
        "name": str(pack.get("name") or (meta or {}).get("name") or ""),
        "beg": str(rng.get("beg") or "")[:10],
        "end": str(rng.get("end") or "")[:10],
        "count": int(rng.get("count") or 0),
        "stock_path": {
            "open": str(stock_paths.get("open") or "unknown"),
            "high": str(stock_paths.get("high") or "unknown"),
            "low": str(stock_paths.get("low") or "unknown"),
            "close": str(stock_paths.get("close") or "unknown"),
        },
        "index_path": {
            "open": str(index_paths.get("open") or "unknown"),
            "high": str(index_paths.get("high") or "unknown"),
            "low": str(index_paths.get("low") or "unknown"),
            "close": str(index_paths.get("close") or "unknown"),
        },
        "stock_path_close": str(stock_paths.get("close") or "unknown"),
        "index_path_close": str(index_paths.get("close") or "unknown"),
        "divergence": _num(divergence.get("score")),
        "low_score": low_score,
        "low_date": str(low.get("date") or "")[:10],
        "low_price": _num(low.get("price")),
        "index_name": str(index_block.get("name") or ""),
    }


def _prefetch_index_hist(
    index: str,
    *,
    lookback_days: int,
) -> dict[str, Any] | None:
    """预取足够宽的指数日线，供全市场路径/偏离复用。失败返回 None。"""
    index_code = _norm_index_code(index) or str(index or "").strip()
    if not index_code:
        return None
    end_iso = _today_iso()
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
    index_hist: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """返回 (精简行|None, 错误信息|None)。未命中区间不算错误。"""
    code = str(meta.get("code") or "").strip()
    if not code:
        return None, "缺少代码"
    try:
        pack = analyze_evaluate(
            code,
            factor=factor,
            low_factor=factor,
            band=band,
            index=index,
            lookback_days=lookback_days,
            adjust="qfq",
            index_hist=index_hist,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("evaluate failed %s: %s", code, exc)
        return None, str(exc)

    if not pack.get("found"):
        return None, None
    row = slim_row(pack, meta=meta)
    return row, None


def _assemble(
    *,
    params: dict[str, Any],
    total: int,
    items: list[dict[str, Any]],
    analyzed: int,
    error_count: int,
) -> dict[str, Any]:
    return {
        "params": params,
        "candidate_count": total,
        "analyzed_count": analyzed,
        "found_count": len(items),
        "error_count": error_count,
        "result_count": len(items),
        "items": list(items),
        "updated_at": _now_iso(),
        "note": "主板/中小板等（非创业板、非科创板、非 ST）；±band 最大波动区间评估；仅展示命中区间",
    }


def screen_evaluate(
    *,
    band: float = DEFAULT_BAND,
    index: str = DEFAULT_INDEX,
    factor: str = DEFAULT_FACTOR,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    workers: int = DEFAULT_WORKERS,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """对符合条件的股票跑 analyze_evaluate，增量推送精简结果。

    宇宙：全市场剔除创业板（300/301）、科创板（688/689）与 ST。
    """
    industry_service.stocks.ensure_populated()
    stocks = [
        meta
        for meta in industry_service.stocks.all_stocks()
        if is_eligible_stock(meta)
    ]
    params = {
        "band": float(band),
        "index": str(index or DEFAULT_INDEX).strip() or DEFAULT_INDEX,
        "factor": str(factor or DEFAULT_FACTOR).strip().lower() or DEFAULT_FACTOR,
        "lookback": int(lookback_days),
        "exclude": "chinext+star+st",
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
        params["index"], lookback_days=params["lookback"]
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
