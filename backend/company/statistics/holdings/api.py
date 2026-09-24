"""持股信息 HTTP 路由：前十大股东、股东户数、基金持股。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from company.statistics.holdings.fund_holders import fetch_fund_holders
from company.statistics.holdings.holder_num import fetch_holder_num
from company.statistics.holdings.holders import fetch_top_holders
from core.api import err, ok

router = APIRouter()


@router.get("/api/stocks/holders")
def stocks_holders(
    code: str = Query("", description="股票代码，如 600519"),
    date: str = Query("", description="报告期 YYYY-MM-DD；留空取最新"),
    scope: str = Query(
        "holders",
        description="holders 十大股东 | free 十大流通股东",
    ),
    refresh: str = Query("0"),
):
    """一家公司某一报告期的前十大股东（东财 F10）。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = fetch_top_holders(
            code,
            report_date=date.strip() or None,
            scope=scope.strip() or "holders",
            force=refresh == "1",
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/holder-num")
def stocks_holder_num(
    code: str = Query("", description="股票代码，如 600519"),
    limit: int = Query(80, ge=1, le=500, description="最近报告期数量"),
    refresh: str = Query("0"),
):
    """股东户数走势：东财报告期序列（户数 / 环比 / 户均持股）。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = fetch_holder_num(code, limit=limit, force=refresh == "1")
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/fund-holders")
def stocks_fund_holders(
    code: str = Query("", description="股票代码，如 600519"),
    date: str = Query("", description="报告期 YYYY-MM-DD；留空取最新"),
    refresh: str = Query("0"),
):
    """持有该股票的基金列表及持仓比例（东财基金持股明细）。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = fetch_fund_holders(
            code,
            report_date=date.strip() or None,
            force=refresh == "1",
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
