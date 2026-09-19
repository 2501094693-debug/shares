"""个股前十大股东 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from company.statistics.owner.holders import fetch_top_holders
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
