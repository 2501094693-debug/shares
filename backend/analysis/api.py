"""形态筛选 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from analysis.decline.config import DEFAULT_LOOKBACK_DAYS
from analysis.decline.service import service
from analysis.evaluate.config import (
    ALLOWED_BANDS,
    ALLOWED_FACTORS,
    ALLOWED_INDEXES,
    DEFAULT_BAND,
    DEFAULT_FACTOR,
    DEFAULT_INDEX,
    DEFAULT_LOOKBACK_DAYS as EVALUATE_LOOKBACK_DAYS,
    DEFAULT_WORKERS,
    MAX_WORKERS,
    MIN_WORKERS,
)
from analysis.evaluate.service import service as evaluate_service
from analysis.recent_low.config import (
    ALLOWED_ADJUSTS,
    DEFAULT_ADJUST as RECENT_LOW_ADJUST,
    DEFAULT_WORKERS as RECENT_LOW_WORKERS,
    MAX_WORKERS as RECENT_LOW_MAX_WORKERS,
    MIN_WORKERS as RECENT_LOW_MIN_WORKERS,
)
from analysis.recent_low.service import service as recent_low_service
from analysis.rotation.config import DEFAULT_LOOKBACK_DAYS as ROTATION_LOOKBACK_DAYS
from analysis.rotation.config import MAX_LOOKBACK_DAYS, MIN_LOOKBACK_DAYS
from analysis.rotation.service import service as rotation_service
from company.analysis.line.evaluate.service import MAX_LOOKBACK_DAYS as EVALUATE_MAX_LOOKBACK
from core.api import err, ok

router = APIRouter()


@router.get("/api/screen/decline")
def get_decline_screen(
    days: int = Query(DEFAULT_LOOKBACK_DAYS, description="近期涨停窗口（交易日）"),
    top: int = Query(30, description="每个交易日前 N 名，0=全部"),
    refresh: str = Query("0", description="1=强制重新分析"),
    workers: int = Query(8, ge=1, le=16, description="并发线程数"),
):
    """阴跌→横盘→涨停：按交易日涨停池分批排名。首次或刷新会后台跑任务。"""
    if days < 1 or days > 30:
        return err("days 须在 1–30 之间", 400)
    if top < 0 or top > 500:
        return err("top 须在 0–500 之间", 400)

    try:
        payload = service.run_or_poll(
            days=days,
            top=top,
            force=refresh == "1",
            workers=workers,
        )
        return ok(payload)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/screen/rotation")
def get_rotation_screen(
    days: int = Query(
        ROTATION_LOOKBACK_DAYS,
        description="回看窗口（交易日，20=近一个月 / 60=近三个月 / 120=近半年 / 245=一年 / 490=两年）",
    ),
    refresh: str = Query("0", description="1=强制重算"),
):
    """申万三级：按日上榜，分为首次/上涨；待涨按距上次上榜最久排序。"""
    if days < MIN_LOOKBACK_DAYS or days > MAX_LOOKBACK_DAYS:
        return err(f"days 须在 {MIN_LOOKBACK_DAYS}–{MAX_LOOKBACK_DAYS} 之间", 400)
    try:
        payload = rotation_service.run_or_poll(days=days, top=0, force=refresh == "1")
        return ok(payload)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/screen/evaluate")
def get_evaluate_screen(
    band: float = Query(DEFAULT_BAND, description="波动带（小数，0.09=±9%）"),
    index: str = Query(DEFAULT_INDEX, description="对比指数公开码"),
    factor: str = Query(DEFAULT_FACTOR, description="波动/最低价口径：open/high/low/close"),
    lookback: int = Query(EVALUATE_LOOKBACK_DAYS, description="回溯自然日"),
    refresh: str = Query("0", description="1=强制重算"),
    workers: int = Query(DEFAULT_WORKERS, ge=MIN_WORKERS, le=MAX_WORKERS, description="并发线程数"),
):
    """全市场 ±band 区间评估：相对强弱 / 股指偏离 / 低点评分。首次或刷新会后台跑任务。"""
    band_abs = abs(float(band))
    if band_abs not in ALLOWED_BANDS:
        return err(f"band 须为 {ALLOWED_BANDS} 之一", 400)
    factor_key = str(factor or "").strip().lower()
    if factor_key not in ALLOWED_FACTORS:
        return err(f"factor 须为 {ALLOWED_FACTORS} 之一", 400)
    index_code = str(index or "").strip() or DEFAULT_INDEX
    if index_code not in ALLOWED_INDEXES:
        return err(f"index 须为 {ALLOWED_INDEXES} 之一", 400)
    if lookback < 60 or lookback > EVALUATE_MAX_LOOKBACK:
        return err(f"lookback 须在 60–{EVALUATE_MAX_LOOKBACK} 之间", 400)

    try:
        payload = evaluate_service.run_or_poll(
            band=band_abs,
            index=index_code,
            factor=factor_key,
            lookback=lookback,
            force=refresh == "1",
            workers=workers,
        )
        return ok(payload)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/screen/recent-low")
def get_recent_low_screen(
    adjust: str = Query(RECENT_LOW_ADJUST, description="复权方式：qfq / hfq / none"),
    refresh: str = Query("0", description="1=强制重算"),
    workers: int = Query(
        RECENT_LOW_WORKERS,
        ge=RECENT_LOW_MIN_WORKERS,
        le=RECENT_LOW_MAX_WORKERS,
        description="并发线程数",
    ),
):
    """全市场两价最近最低：收盘/最低各自回溯交易日数与间隔。排除创业板、科创板、ST、退市。"""
    adjust_key = str(adjust or "").strip().lower() or RECENT_LOW_ADJUST
    if adjust_key not in ALLOWED_ADJUSTS:
        return err(f"adjust 须为 {ALLOWED_ADJUSTS} 之一", 400)

    try:
        payload = recent_low_service.run_or_poll(
            adjust=adjust_key,
            force=refresh == "1",
            workers=workers,
        )
        return ok(payload)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)

