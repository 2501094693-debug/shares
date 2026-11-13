"""全市场批量「最近最低」：并发调用 analyze_recent_low，产出精简行。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from market.industry.service import service as industry_service

from analysis.evaluate.screen import is_chinext, is_star, is_st
from analysis.recent_low.config import (
    DEFAULT_ADJUST,
    DEFAULT_WORKERS,
    MAX_WORKERS,
    PROGRESS_EVERY,
)
from company.analysis.line.local_extrema.recent_low import analyze_recent_low

logger = logging.getLogger(__name__)


def is_delisted(name: str) -> bool:
    """名称是否含退市标记（退市 / 退）。"""
    text = str(name or "")
    if "退市" in text:
        return True
    # 单字「退」常见于退市整理简称；避免误伤需同时排除纯 ST 已由 is_st 处理
    return "退" in text


def is_eligible_stock(meta: dict[str, Any] | None) -> bool:
    """个股筛选宇宙：排除创业板、科创板、ST、退市。"""
    if not meta:
        return False
    code = str(meta.get("code") or "").strip()
    if not code or is_chinext(code) or is_star(code):
        return False
    name = str(meta.get("name") or "")
    if is_st(name) or is_delisted(name):
        return False
    return True


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _lookback_days(pack: dict[str, Any], factor: str) -> int | None:
    block = (pack.get("lookback") or {}).get(factor) or {}
    days = block.get("days")
    if days is None:
        return None
    try:
        return int(days)
    except (TypeError, ValueError):
        return None


def slim_row(pack: dict[str, Any], *, meta: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """把 analyze_recent_low 压成列表行。"""
    if not pack:
        return None
    code = str(pack.get("code") or (meta or {}).get("code") or "").strip()
    if not code:
        return None

    lookback = pack.get("lookback") or {}
    close_lb = lookback.get("close") or {}
    low_lb = lookback.get("low") or {}
    prices = pack.get("prices") or {}

    close_days = _lookback_days(pack, "close")
    low_days = _lookback_days(pack, "low")
    if close_days is None and low_days is None:
        return None

    gap: int | None = None
    if close_days is not None and low_days is not None:
        gap = abs(close_days - low_days)

    return {
        "code": code,
        "name": str(pack.get("name") or (meta or {}).get("name") or ""),
        "date": str(pack.get("date") or "")[:10],
        "close_price": prices.get("close"),
        "low_price": prices.get("low"),
        "close_days": close_days,
        "low_days": low_days,
        "gap": gap,
        "close_since": str(close_lb.get("since") or "")[:10] or None,
        "low_since": str(low_lb.get("since") or "")[:10] or None,
        "close_all_time": bool(close_lb.get("is_all_time_low"))
        if close_lb.get("is_all_time_low") is not None
        else None,
        "low_all_time": bool(low_lb.get("is_all_time_low"))
        if low_lb.get("is_all_time_low") is not None
        else None,
    }


def _analyze_one(
    meta: dict[str, Any],
    *,
    adjust: str,
) -> tuple[dict[str, Any] | None, str | None]:
    code = str(meta.get("code") or "").strip()
    if not code:
        return None, "缺少代码"
    try:
        pack = analyze_recent_low(code, adjust=adjust)
    except Exception as exc:  # noqa: BLE001
        logger.info("recent_low failed %s: %s", code, exc)
        return None, str(exc)
    row = slim_row(pack, meta=meta)
    if row is None:
        return None, "无有效回溯"
    return row, None


def _assemble(
    *,
    params: dict[str, Any],
    total: int,
    items: list[dict[str, Any]],
    analyzed: int,
    error_count: int,
) -> dict[str, Any]:
    # 默认按两价间隔升序、再按收盘最近最低天数降序
    ordered = sorted(
        items,
        key=lambda r: (
            r.get("gap") if r.get("gap") is not None else 10**9,
            -(r.get("close_days") or 0),
            -(r.get("low_days") or 0),
            str(r.get("code") or ""),
        ),
    )
    return {
        "params": params,
        "candidate_count": total,
        "analyzed_count": analyzed,
        "found_count": len(ordered),
        "error_count": error_count,
        "result_count": len(ordered),
        "items": ordered,
        "updated_at": _now_iso(),
        "note": "主板/中小板等（非创业板、非科创板、非 ST、非退市）；收盘/最低两价最近最低交易日间隔",
    }


def screen_recent_low(
    *,
    adjust: str = DEFAULT_ADJUST,
    workers: int = DEFAULT_WORKERS,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """对符合条件的股票跑 analyze_recent_low，增量推送精简结果。"""
    industry_service.stocks.ensure_populated()
    stocks = [
        meta
        for meta in industry_service.stocks.all_stocks()
        if is_eligible_stock(meta)
    ]
    params = {
        "adjust": str(adjust or DEFAULT_ADJUST).strip().lower() or DEFAULT_ADJUST,
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

    max_workers = min(max(1, workers), int(MAX_WORKERS), max(1, total))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = {
            executor.submit(_analyze_one, meta, adjust=params["adjust"]): meta
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
