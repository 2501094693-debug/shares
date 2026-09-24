"""融资融券 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from company.statistics.margintrading.history import fetch_margin_trading
from core.api import err, ok

router = APIRouter()


@router.get("/api/stocks/margin-trading")
def stocks_margin_trading(
    code: str = Query("", description="股票代码，如 600519"),
    limit: int = Query(1500, ge=1, le=3000, description="最近交易日数量"),
    refresh: str = Query("0"),
):
    """融资融券走势：东财个股两融日序列（余额 / 净买入 / 占流通市值比）。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = fetch_margin_trading(code, limit=limit, force=refresh == "1")
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
