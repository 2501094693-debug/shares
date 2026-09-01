"""申万行业行情 HTTP 路由：树、涨跌、资金流向、涨跌停日历。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok
from market.steep.service import DEFAULT_DAYS, service as steep_service
from market.sw.service import service

router = APIRouter()


def _level(raw: str) -> int:
    return int(raw)


@router.get("/api/market/tree")
def market_tree(
    period: str = Query("today", description="today | 5d | 10d"),
    refresh: str = Query("0"),
    live: str = Query("0", description="1=只刷新申万指数点位，树结构不动"),
):
    try:
        data = service.tree(
            period=period,
            force=refresh == "1",
            live=live == "1",
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/market/overview")
def market_overview(
    period: str = Query("today"),
    refresh: str = Query("0"),
    level: str = Query("1"),
):
    """兼容旧路径，返回整棵行业树。``level`` 已忽略。"""
    _ = level
    return market_tree(period=period, refresh=refresh)


@router.get("/api/market/quotes")
def market_quotes(
    level: str = Query("1", description="1=一级 2=二级 3=三级"),
    refresh: str = Query("0"),
):
    try:
        data = service.quotes(_level(level), force=refresh == "1")
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/market/fund-flow")
def market_fund_flow(
    level: str = Query("1"),
    period: str = Query("today", description="today | 5d | 10d"),
    refresh: str = Query("0"),
):
    try:
        data = service.fund_flow(_level(level), period=period, force=refresh == "1")
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/market/steep")
def market_steep(
    days: int = Query(DEFAULT_DAYS, description="最近几个交易日，默认 15，最大 30"),
    refresh: str = Query("0"),
):
    """最近几个交易日的涨停 / 跌停名单，按天分组。"""
    try:
        data = steep_service.recent(days=days, force=refresh == "1")
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
