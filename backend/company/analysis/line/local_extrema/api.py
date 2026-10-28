"""股票日线局部极值点 HTTP 路由。

- ``/api/stocks/line-local-extrema``  区间内波峰 / 波谷检测
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.local_extrema.service import analyze_local_extrema

router = APIRouter()


@router.get("/api/stocks/line-local-extrema")
def stocks_line_local_extrema(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD 或 YYYYMMDD"),
    end: str = Query("", description="结束日期，默认今天"),
    series: str = Query("close", description="分析序列：open/close/high/low/ohlc4"),
    w: int = Query(5, ge=1, le=30, description="Pivot 窗口半径（交易日）"),
    min_distance: int = Query(3, ge=1, le=30, description="同类极值最小间隔（交易日）"),
    smooth: int = Query(1, ge=1, le=15, description="平滑窗口；1 表示不平滑"),
    prominence: float | None = Query(None, description="突出度绝对阈值（价格单位）"),
    prominence_pct: float | None = Query(None, description="突出度相对阈值（百分比）"),
    adjust: str = Query("qfq", description="复权方式：qfq 前复权 / hfq 后复权 / none 不复权"),
):
    """日线局部极值点：区间内波峰 / 波谷，含 prominence 过滤与波段振幅。"""
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = analyze_local_extrema(
            code,
            beg,
            end,
            series=series,
            w=w,
            prominence=prominence,
            prominence_pct=prominence_pct,
            min_distance=min_distance,
            smooth_window=smooth,
            adjust=adjust,
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
