"""聪明投机者 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.T.service import analyze_trader

router = APIRouter()


@router.get("/api/stocks/line-trader")
def stocks_line_trader(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD 或 YYYYMMDD"),
    end: str = Query("", description="结束日期，默认今天"),
    ratio: float = Query(0.01, description="每日买卖量占当日成交量比例"),
    adjust: str = Query("qfq", description="复权方式：qfq / hfq / none"),
    history: bool = Query(False, description="是否返回每日明细"),
):
    """首日低价买入，其后每日高卖低买；返回期末股数与平均成本。"""
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = analyze_trader(
            code, beg, end, ratio=ratio, adjust=adjust, return_history=history
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
