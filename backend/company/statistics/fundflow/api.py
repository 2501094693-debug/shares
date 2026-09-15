"""个股资金流向 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from company.statistics.fundflow.fetcher import get_fund_flow
from core.api import err, ok

router = APIRouter()


@router.get("/api/stocks/fund-flow")
def stocks_fund_flow(
    code: str = Query("", description="股票代码，如 600519"),
    scope: str = Query(
        "daily",
        description="daily 历史日线 | minute 当日分钟 | snapshot 当日快照 | big_deal 大资金动向（同花顺 HQ）",
    ),
    limit: int = Query(120, ge=1, le=200, description="日线根数（东财最多约 120）或 big_deal 条数（最多 200）"),
    klt: int = Query(1, description="分钟粒度：1|5|15|30|60，仅 scope=minute 时有效"),
    page: int = Query(1, ge=1, le=100, description="页码，仅 scope=big_deal 时有效"),
    order: str = Query("desc", description="排序：desc|asc，仅 scope=big_deal 时有效"),
    source: str = Query("eastmoney", description="eastmoney 东方财富 | tonghuashun 同花顺 HQ 大单"),
    refresh: str = Query("0"),
):
    """个股资金流向：小单 / 中单 / 大单 / 超大单净流入及净占比。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = get_fund_flow(
            code,
            scope=scope.strip() or "daily",
            limit=limit,
            klt=klt,
            page=page,
            order=order.strip() or "desc",
            source=source.strip() or "eastmoney",
            force=refresh == "1",
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
