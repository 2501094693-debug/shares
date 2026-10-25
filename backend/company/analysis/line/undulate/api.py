"""个股相对基准收盘四价涨跌幅 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.undulate.service import analyze_undulate
from company.analysis.line.undulate.volatility import analyze_volatility

router = APIRouter()


@router.get("/api/stocks/line-undulate")
def stocks_line_undulate(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD 或 YYYYMMDD"),
    end: str = Query("", description="结束日期，默认今天"),
    adjust: str = Query("qfq", description="复权方式：qfq 前复权 / hfq 后复权 / none 不复权"),
):
    """以起始日前一交易日收盘为基准，给出区间内每日四价涨跌幅及范围。"""
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = analyze_undulate(code, beg, end, adjust=adjust)
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/line-undulate/volatility")
def stocks_line_undulate_volatility(
    code: str = Query("", description="股票或指数代码，如 600519 / 000001"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD 或 YYYYMMDD"),
    end: str = Query("", description="结束日期，默认今天"),
    adjust: str = Query("qfq", description="复权方式（仅 kind=stock）：qfq / hfq / none"),
    kind: str = Query("stock", description="stock 个股 | index 指数"),
):
    """四价涨跌幅的波动范围、均值与标准差（基准=起始日前一交易日收盘）。"""
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = analyze_volatility(code, beg, end, adjust=adjust, kind=kind)
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
