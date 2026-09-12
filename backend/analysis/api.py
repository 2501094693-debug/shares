"""形态筛选 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from analysis.decline.config import DEFAULT_LOOKBACK_DAYS
from analysis.decline.service import service
from analysis.grind.config import DEFAULT_LOOKBACK_DAYS as GRIND_LOOKBACK_DAYS
from analysis.grind.service import service as grind_service
from analysis.rotation.config import DEFAULT_LOOKBACK_DAYS as ROTATION_LOOKBACK_DAYS
from analysis.rotation.config import MAX_LOOKBACK_DAYS, MIN_LOOKBACK_DAYS
from analysis.rotation.service import service as rotation_service
from core.api import err, ok
from core.codes import normalize_code

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


@router.get("/api/screen/grind")
def get_grind_screen(
    days: int = Query(GRIND_LOOKBACK_DAYS, description="回看窗口（交易日）"),
    top: int = Query(50, description="前 N 名，0=全部"),
    kind: str = Query("all", description="all / decline / consolidation"),
    code: str = Query("", description="只分析一只股票"),
    refresh: str = Query("0", description="1=强制重新分析"),
    workers: int = Query(8, ge=1, le=16, description="并发线程数"),
):
    """阴跌 / 横盘：全市场软评分。无硬门槛，按分排序。"""
    if days < 10 or days > 180:
        return err("days 须在 10–180 之间", 400)
    if top < 0 or top > 500:
        return err("top 须在 0–500 之间", 400)
    kind_l = (kind or "all").strip().lower()
    if kind_l not in {"all", "decline", "consolidation"}:
        return err("kind 须为 all / decline / consolidation", 400)

    try:
        payload = grind_service.run_or_poll(
            days=days,
            top=top,
            kind=kind_l,
            code=normalize_code(code),
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
