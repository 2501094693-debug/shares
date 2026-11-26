"""形态筛选 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from analysis.macd.config import (
    ALLOWED_ADJUSTS as MACD_ALLOWED_ADJUSTS,
    ALLOWED_BANDS as MACD_ALLOWED_BANDS,
    ALLOWED_CROSS_TYPES as MACD_ALLOWED_CROSS_TYPES,
    ALLOWED_FACTORS as MACD_ALLOWED_FACTORS,
    ALLOWED_INDEXES as MACD_ALLOWED_INDEXES,
    DEFAULT_ADJUST as MACD_ADJUST,
    DEFAULT_BAND as MACD_BAND,
    DEFAULT_CROSS_TYPE as MACD_CROSS_TYPE,
    DEFAULT_FACTOR as MACD_FACTOR,
    DEFAULT_FAST as MACD_FAST,
    DEFAULT_INDEX as MACD_INDEX,
    DEFAULT_LOOKBACK_DAYS as MACD_LOOKBACK_DAYS,
    DEFAULT_NEAR_RATIO as MACD_NEAR_RATIO,
    DEFAULT_SIGNAL as MACD_SIGNAL,
    DEFAULT_SLOW as MACD_SLOW,
    DEFAULT_W_DIV as MACD_W_DIV,
    DEFAULT_W_PRIOR as MACD_W_PRIOR,
    DEFAULT_WORKERS as MACD_WORKERS,
    MAX_RANGE_DAYS as MACD_MAX_RANGE_DAYS,
    MAX_WORKERS as MACD_MAX_WORKERS,
    MIN_WORKERS as MACD_MIN_WORKERS,
)
from analysis.macd.range_service import range_service as macd_range_service
from analysis.macd.service import service as macd_service
from analysis.rotation.config import DEFAULT_LOOKBACK_DAYS as ROTATION_LOOKBACK_DAYS
from analysis.rotation.config import MAX_LOOKBACK_DAYS, MIN_LOOKBACK_DAYS
from analysis.rotation.service import service as rotation_service
from company.analysis.line.evaluate.service import MAX_LOOKBACK_DAYS as EVALUATE_MAX_LOOKBACK
from company.analysis.line.undulate.service import _iso
from core.api import err, ok

router = APIRouter()


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


@router.get("/api/screen/macd")
def get_macd_screen(
    band: float = Query(MACD_BAND, description="波动带（小数，0.09=±9%）"),
    index: str = Query(MACD_INDEX, description="对比指数公开码"),
    factor: str = Query(MACD_FACTOR, description="波动口径：open/high/low/close/all"),
    lookback: int = Query(MACD_LOOKBACK_DAYS, description="回溯自然日"),
    end: str = Query("", description="截止交易日 YYYY-MM-DD；空=最新交易日"),
    adjust: str = Query(MACD_ADJUST, description="复权方式：qfq / hfq / none"),
    near_ratio: float = Query(
        MACD_NEAR_RATIO,
        description="相对缺口阈值；与速度外推任一命中即可",
    ),
    fast: int = Query(MACD_FAST, ge=1, le=200, description="MACD 快线"),
    slow: int = Query(MACD_SLOW, ge=2, le=200, description="MACD 慢线"),
    signal: int = Query(MACD_SIGNAL, ge=1, le=200, description="DEA 信号线"),
    w_prior: float = Query(MACD_W_PRIOR, description="前低分权重"),
    w_div: float = Query(MACD_W_DIV, description="股指反向日占比分权重"),
    cross_type: str = Query(
        MACD_CROSS_TYPE,
        description="信号类别：all=全部 / under=水下类 / over=水上类",
    ),
    refresh: str = Query("0", description="1=强制重算"),
    workers: int = Query(
        MACD_WORKERS,
        ge=MACD_MIN_WORKERS,
        le=MACD_MAX_WORKERS,
        description="并发线程数",
    ),
):
    """MACD 水下/水上金叉或即将金叉 + 最大稳定区间综合分。排除创业板、科创板、ST、退市。"""
    band_abs = abs(float(band))
    if band_abs not in MACD_ALLOWED_BANDS:
        return err(f"band 须为 {MACD_ALLOWED_BANDS} 之一", 400)
    factor_key = str(factor or "").strip().lower()
    if factor_key not in MACD_ALLOWED_FACTORS:
        return err(f"factor 须为 {MACD_ALLOWED_FACTORS} 之一", 400)
    index_code = str(index or "").strip() or MACD_INDEX
    if index_code not in MACD_ALLOWED_INDEXES:
        return err(f"index 须为 {MACD_ALLOWED_INDEXES} 之一", 400)
    adjust_key = str(adjust or "").strip().lower() or MACD_ADJUST
    if adjust_key not in MACD_ALLOWED_ADJUSTS:
        return err(f"adjust 须为 {MACD_ALLOWED_ADJUSTS} 之一", 400)
    end_key = str(end or "").strip()
    if end_key:
        try:
            end_key = _iso(end_key)
        except ValueError as exc:
            return err(f"end 格式错误：{exc}", 400)
    if lookback < 60 or lookback > EVALUATE_MAX_LOOKBACK:
        return err(f"lookback 须在 60–{EVALUATE_MAX_LOOKBACK} 之间", 400)
    if fast >= slow:
        return err("fast 须小于 slow", 400)
    if near_ratio <= 0 or near_ratio > 1:
        return err("near_ratio 须在 (0, 1] 之间", 400)
    if w_prior < 0 or w_div < 0 or (w_prior + w_div) <= 0:
        return err("w_prior / w_div 须非负且之和 > 0", 400)
    cross_type_key = str(cross_type or "").strip().lower()
    if cross_type_key not in MACD_ALLOWED_CROSS_TYPES:
        return err(f"cross_type 须为 {MACD_ALLOWED_CROSS_TYPES} 之一", 400)

    try:
        payload = macd_service.run_or_poll(
            band=band_abs,
            index=index_code,
            factor=factor_key,
            lookback=lookback,
            end=end_key,
            adjust=adjust_key,
            near_ratio=float(near_ratio),
            fast=fast,
            slow=slow,
            signal=signal,
            w_prior=float(w_prior),
            w_div=float(w_div),
            cross_type=cross_type_key,
            force=refresh == "1",
            workers=workers,
        )
        return ok(payload)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/screen/macd/range")
def get_macd_range_screen(
    start: str = Query(
        ...,
        description=f"区间起始交易日 YYYY-MM-DD（最多 {MACD_MAX_RANGE_DAYS} 个交易日）",
    ),
    end: str = Query("", description="区间结束交易日；空=最新交易日"),
    band: float = Query(MACD_BAND, description="波动带（小数，0.09=±9%）"),
    index: str = Query(MACD_INDEX, description="对比指数公开码"),
    factor: str = Query(MACD_FACTOR, description="波动口径：open/high/low/close/all"),
    lookback: int = Query(MACD_LOOKBACK_DAYS, description="回溯自然日"),
    adjust: str = Query(MACD_ADJUST, description="复权方式：qfq / hfq / none"),
    near_ratio: float = Query(
        MACD_NEAR_RATIO,
        description="相对缺口阈值；与速度外推任一命中即可",
    ),
    fast: int = Query(MACD_FAST, ge=1, le=200, description="MACD 快线"),
    slow: int = Query(MACD_SLOW, ge=2, le=200, description="MACD 慢线"),
    signal: int = Query(MACD_SIGNAL, ge=1, le=200, description="DEA 信号线"),
    w_prior: float = Query(MACD_W_PRIOR, description="前低分权重"),
    w_div: float = Query(MACD_W_DIV, description="股指反向日占比分权重"),
    cross_type: str = Query(
        MACD_CROSS_TYPE,
        description="信号类别：all=全部 / under=水下类 / over=水上类",
    ),
    refresh: str = Query(
        "0",
        description="0=开始分析（参数未变且有新鲜缓存则直接返回）；1=重新分析（清缓存强制重跑）",
    ),
    workers: int = Query(
        MACD_WORKERS,
        ge=MACD_MIN_WORKERS,
        le=MACD_MAX_WORKERS,
        description="并发线程数",
    ),
):
    """区间内逐日 MACD 金叉筛选，并统计 DIF≥DEA 段事后最大收盘涨/跌幅。

    涨跌基准为信号日收盘；截止日为金叉后首次 DIF<DEA（无则最新日）。
    即将金叉若后续未真正金叉则标无效。``refresh=0`` 复用同参数新鲜结果；
    ``refresh=1`` 清缓存重跑。
    """
    band_abs = abs(float(band))
    if band_abs not in MACD_ALLOWED_BANDS:
        return err(f"band 须为 {MACD_ALLOWED_BANDS} 之一", 400)
    factor_key = str(factor or "").strip().lower()
    if factor_key not in MACD_ALLOWED_FACTORS:
        return err(f"factor 须为 {MACD_ALLOWED_FACTORS} 之一", 400)
    index_code = str(index or "").strip() or MACD_INDEX
    if index_code not in MACD_ALLOWED_INDEXES:
        return err(f"index 须为 {MACD_ALLOWED_INDEXES} 之一", 400)
    adjust_key = str(adjust or "").strip().lower() or MACD_ADJUST
    if adjust_key not in MACD_ALLOWED_ADJUSTS:
        return err(f"adjust 须为 {MACD_ALLOWED_ADJUSTS} 之一", 400)
    try:
        start_key = _iso(str(start or "").strip())
    except ValueError as exc:
        return err(f"start 格式错误：{exc}", 400)
    end_key = str(end or "").strip()
    if end_key:
        try:
            end_key = _iso(end_key)
        except ValueError as exc:
            return err(f"end 格式错误：{exc}", 400)
    if end_key and start_key > end_key:
        return err("start 不能晚于 end", 400)
    if lookback < 60 or lookback > EVALUATE_MAX_LOOKBACK:
        return err(f"lookback 须在 60–{EVALUATE_MAX_LOOKBACK} 之间", 400)
    if fast >= slow:
        return err("fast 须小于 slow", 400)
    if near_ratio <= 0 or near_ratio > 1:
        return err("near_ratio 须在 (0, 1] 之间", 400)
    if w_prior < 0 or w_div < 0 or (w_prior + w_div) <= 0:
        return err("w_prior / w_div 须非负且之和 > 0", 400)
    cross_type_key = str(cross_type or "").strip().lower()
    if cross_type_key not in MACD_ALLOWED_CROSS_TYPES:
        return err(f"cross_type 须为 {MACD_ALLOWED_CROSS_TYPES} 之一", 400)

    try:
        payload = macd_range_service.run_or_poll(
            start=start_key,
            end=end_key,
            band=band_abs,
            index=index_code,
            factor=factor_key,
            lookback=lookback,
            adjust=adjust_key,
            near_ratio=float(near_ratio),
            fast=fast,
            slow=slow,
            signal=signal,
            w_prior=float(w_prior),
            w_div=float(w_div),
            cross_type=cross_type_key,
            force=refresh == "1",
            workers=workers,
        )
        return ok(payload)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
