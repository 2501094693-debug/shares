"""分红 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from company.statistics.dividend.fetcher import get_dividends
from core.api import err, ok

router = APIRouter()


@router.get("/api/stocks/dividend")
def stocks_dividend(
    code: str = Query("", description="股票代码，如 600519"),
    source: str = Query("eastmoney", description="eastmoney（东财）/ ths（同花顺，含特别分红派现总额）"),
    scope: str = Query("all", description="all | detail | history | summary（仅 source=eastmoney 生效）"),
    limit: int = Query(60, ge=1, le=200, description="分红明细最多返回期数"),
    refresh: str = Query("0"),
):
    """个股分红：结构化明细 / 逐次方案 / 历年分红融资。

    - ``source=eastmoney``：东方财富，按报告期 + F10
    - ``source=ths``：同花顺，直接给出每次「AH分红总额」（含特别分红）
    """
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = get_dividends(
            code, scope=scope, limit=limit, force=refresh == "1", source=source
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
