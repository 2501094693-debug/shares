"""龙虎榜 HTTP 路由：每日上榜、个股历史。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from .service import service

router = APIRouter()


@router.get("/api/list/daily")
def list_daily(
    date: str = Query("", description="交易日 YYYY-MM-DD / YYYYMMDD，空则最近有数据的一天"),
    refresh: str = Query("0"),
):
    """某日上榜股票，附买入 / 卖出席位。"""
    try:
        data = service.daily(date=date.strip(), force=refresh == "1")
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/list/stock")
def list_stock(
    code: str = Query("", description="股票代码，如 000001"),
    refresh: str = Query("0"),
):
    """一只股票的历史上榜记录，每条附买卖席位。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = service.stock(code, force=refresh == "1")
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
