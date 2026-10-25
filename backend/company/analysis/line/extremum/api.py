"""股票四价极值分析 HTTP 路由。

- ``/api/stocks/line-extremum``           某交易日四价前低回溯
- ``/api/stocks/line-extremum/position``  区间四价极值位置百分比
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.extremum.position import analyze_position
from company.analysis.line.extremum.service import analyze_extremum

router = APIRouter()


@router.get("/api/stocks/line-extremum")
def stocks_line_extremum(
    code: str = Query("", description="股票代码，如 600519"),
    date: str = Query(..., description="交易日期 YYYY-MM-DD 或 YYYYMMDD"),
    adjust: str = Query("qfq", description="复权方式：qfq 前复权 / hfq 后复权 / none 不复权"),
):
    """四价前低回溯：个股某交易日的开/收/高/低各自最近一次更低的交易日 + 间隔。"""
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = analyze_extremum(code, date, adjust=adjust)
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/line-extremum/position")
def stocks_line_extremum_position(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD 或 YYYYMMDD"),
    end: str = Query("", description="结束日期，默认今天"),
    adjust: str = Query("qfq", description="复权方式：qfq 前复权 / hfq 后复权 / none 不复权"),
    live: bool = Query(False, description="是否使用最新实时四价作为现价；默认 false，使用结束日价格"),
):
    """区间四价极值位置：(结束日 − 最低) / (最高 − 最低) × 100%，及从小到大排名。"""
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = analyze_position(code, beg, end, adjust=adjust, use_live=live)
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
