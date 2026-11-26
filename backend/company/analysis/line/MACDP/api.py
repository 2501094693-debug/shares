"""MACDP HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.MACDP.core import (
    DEFAULT_FAST,
    DEFAULT_SIGNAL,
    DEFAULT_SLOW,
)
from company.analysis.line.MACDP.service import analyze_macdp

router = APIRouter()


@router.get("/api/stocks/line-macdp")
def stocks_line_macdp(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD 或 YYYYMMDD"),
    end: str = Query("", description="结束日期，默认今天"),
    fast: int = Query(DEFAULT_FAST, ge=1, le=200, description="快线时长，默认 10"),
    slow: int = Query(DEFAULT_SLOW, ge=2, le=400, description="慢线时长，默认 20"),
    signal: int = Query(
        DEFAULT_SIGNAL, ge=1, le=200, description="DEA 信号线时长，默认 7"
    ),
    adjust: str = Query(
        "qfq", description="复权方式：qfq 前复权 / hfq 后复权 / none 不复权"
    ),
):
    """区间日线 MACDP：均价 + 量加权快慢线 + 固定 1/(signal+1) DEA。"""
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = analyze_macdp(
            code,
            beg,
            end,
            fast=fast,
            slow=slow,
            signal=signal,
            adjust=adjust,
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
