"""形态筛选 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from analysis.config import DEFAULT_LOOKBACK_DAYS
from core.api import err, ok
from screen.service import service

router = APIRouter()


@router.get("/api/screen/yindie")
def get_yindie_screen(
    days: int = Query(DEFAULT_LOOKBACK_DAYS, description="近期涨停窗口（交易日）"),
    top: int = Query(30, description="返回前 N 名，0=全部"),
    refresh: str = Query("0", description="1=强制重新分析"),
    workers: int = Query(8, ge=1, le=16, description="并发线程数"),
):
    """阴跌→横盘→涨停形态筛选。首次或刷新会后台跑任务，前端轮询至完成。"""
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
