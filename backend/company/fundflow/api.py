"""个股资金流向 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from company.fundflow.fetcher import get_fund_flow
from core.api import err, ok

router = APIRouter()


@router.get("/api/stocks/fund-flow")
def stocks_fund_flow(
    code: str = Query("", description="股票代码，如 600519"),
    scope: str = Query("daily", description="daily 历史日线 | minute 当日分钟 | snapshot 当日快照"),
    limit: int = Query(120, ge=1, le=120, description="历史根数（东财日线最多约 120）"),
    klt: int = Query(1, description="分钟粒度：1|5|15|30|60，仅 scope=minute 时有效"),
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
            force=refresh == "1",
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
