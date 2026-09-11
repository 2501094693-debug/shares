"""财务报表 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from company.news.financialreport.fetcher import get_financial_report
from core.api import err, ok

router = APIRouter()


@router.get("/api/stocks/financial-report")
def stocks_financial_report(
    code: str = Query("", description="股票代码，如 600519"),
    scope: str = Query(
        "merged",
        description="all 全量 | merged 合并 | main 主要指标 | income 利润表 | balance 资产负债表 | cashflow 现金流量表 | lico 业绩报表",
    ),
    limit: int = Query(24, ge=1, le=60, description="每类报表拉取期数"),
    refresh: str = Query("0"),
):
    """东方财富 F10 财务报表：主要指标、利润表、资产负债表、现金流量表、业绩报表。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = get_financial_report(
            code,
            scope=scope.strip() or "merged",
            limit=limit,
            force=refresh == "1",
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
