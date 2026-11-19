"""MACD HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.MACD.core import (
    DEFAULT_FAST,
    DEFAULT_SIGNAL,
    DEFAULT_SLOW,
    PRICE_OPTIONS,
)
from company.analysis.line.MACD.service import analyze_macd

router = APIRouter()


@router.get("/api/stocks/line-macd")
def stocks_line_macd(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD 或 YYYYMMDD"),
    end: str = Query("", description="结束日期，默认今天"),
    fast: int = Query(DEFAULT_FAST, ge=1, le=200, description="快线 EMA 时长，默认 10"),
    slow: int = Query(DEFAULT_SLOW, ge=2, le=400, description="慢线 EMA 时长，默认 22"),
    signal: int = Query(
        DEFAULT_SIGNAL, ge=1, le=200, description="DEA 信号线时长，默认 8"
    ),
    price: str = Query(
        "close",
        description=f"价格字段：{' / '.join(PRICE_OPTIONS)}，默认 close",
    ),
    adjust: str = Query(
        "qfq", description="复权方式：qfq 前复权 / hfq 后复权 / none 不复权"
    ),
):
    """区间日线 MACD：返回每日 DIF / DEA / MACD 柱（×2）。"""
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = analyze_macd(
            code,
            beg,
            end,
            fast=fast,
            slow=slow,
            signal=signal,
            price=price,
            adjust=adjust,
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
