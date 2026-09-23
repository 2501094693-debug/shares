"""形态筛选 HTTP 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query

from analysis.decline.config import DEFAULT_LOOKBACK_DAYS
from analysis.decline.service import service
from analysis.rotation.config import DEFAULT_LOOKBACK_DAYS as ROTATION_LOOKBACK_DAYS
from analysis.rotation.config import MAX_LOOKBACK_DAYS, MIN_LOOKBACK_DAYS
from analysis.rotation.service import service as rotation_service
from analysis.shares.config import DEFAULT_LOOKBACK_DAYS as SHARES_LOOKBACK_DAYS
from analysis.shares.config import MAX_LOOKBACK_DAYS as SHARES_MAX_LOOKBACK_DAYS
from analysis.shares.days import list_trade_days
from analysis.shares.service import service as shares_service
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


@router.get("/api/screen/shares/days")
def get_shares_trade_days(
    days: int = Query(SHARES_LOOKBACK_DAYS, description="近 N 个交易日（约一个月=22）"),
):
    """近一个月交易日列表 + 可选条件字段说明，供按日勾选筛选条件。"""
    if days < 1 or days > SHARES_MAX_LOOKBACK_DAYS:
        return err(f"days 须在 1–{SHARES_MAX_LOOKBACK_DAYS} 之间", 400)
    try:
        return ok(list_trade_days(days))
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.post("/api/screen/shares")
def post_shares_screen(payload: dict[str, Any] = Body(...)):
    """按多日日线条件筛选股票。

    Body 示例::

        {
          "days": [
            {"date": "2026-09-23", "pct_chg_min": 2, "lower_ratio_min": 0.4},
            {"date": "2026-09-22", "amplitude_min": 3, "amplitude_max": 8}
          ],
          "top": 50,
          "code": "",
          "refresh": "0",
          "workers": 8
        }

    单日可选字段：pct_chg / max_gain / max_drop / body_pct / body_ratio /
    lower_ratio / upper_ratio 的 ``*_min`` / ``*_max``。未填字段表示不限；多日之间为 AND。
    """
    raw_days = payload.get("days") if isinstance(payload, dict) else None
    if not isinstance(raw_days, list) or not raw_days:
        return err("days 须为非空数组", 400)

    try:
        top = int(payload.get("top") if payload.get("top") is not None else 50)
    except (TypeError, ValueError):
        return err("top 无效", 400)
    if top < 0 or top > 500:
        return err("top 须在 0–500 之间", 400)

    try:
        workers = int(payload.get("workers") if payload.get("workers") is not None else 8)
    except (TypeError, ValueError):
        return err("workers 无效", 400)
    if workers < 1 or workers > 16:
        return err("workers 须在 1–16 之间", 400)

    refresh = str(payload.get("refresh") or "0").strip()
    code = normalize_code(str(payload.get("code") or ""))

    try:
        result = shares_service.run_or_poll(
            day_specs=raw_days,
            top=top,
            code=code,
            force=refresh == "1",
            workers=workers,
        )
        if result.get("status") == "error" and "data" not in result:
            return err(str(result.get("error") or "筛选失败"), 400)
        return ok(result)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
