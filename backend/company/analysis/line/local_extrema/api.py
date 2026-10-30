"""股票日线局部极值点 HTTP 路由。

- ``/api/stocks/line-local-extrema``             自起始日起的波峰 / 波谷检测
- ``/api/stocks/line-local-extrema-alternating`` 峰谷交替序列（过滤小峰小谷）

输入：一只股票（code）+ 起始日期（beg）。

输出：

- 极值接口：按交易日从远到近排列的单一峰谷序列（extrema）；
- 交替接口：单一序列（extrema），峰谷严格交替；
- 两者均附带 ``peak_scores`` / ``trough_scores`` 两条评分序列
  （价格排名倒数×30 + (1−e^(−天数))×30 + 最大侧差距×40）。

规则：相邻比较——大于等于左右即波峰，小于等于左右即波谷；相同值运行前合并；
并输出每个极值点左右各延续多少个交易日（left_span / right_span）。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.local_extrema.service import (
    analyze_alternating_extrema,
    analyze_local_extrema,
)

router = APIRouter()


@router.get("/api/stocks/line-local-extrema")
def stocks_line_local_extrema(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD 或 YYYYMMDD"),
    end: str = Query("", description="结束日期，默认今天"),
    series: str = Query("close", description="分析序列：open/close/high/low/ohlc4"),
    smooth: int = Query(1, ge=1, le=15, description="平滑窗口；1 表示不平滑"),
    layers: int = Query(1, ge=1, le=20, description="层级数"),
    adjust: str = Query("qfq", description="复权方式：qfq 前复权 / hfq 后复权 / none 不复权"),
):
    """日线局部极值点：返回按交易日从远到近排列的峰谷序列 extrema。"""
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = analyze_local_extrema(
            code,
            beg,
            end,
            series=series,
            smooth_window=smooth,
            adjust=adjust,
            layers=layers,
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/line-local-extrema-alternating")
def stocks_line_local_extrema_alternating(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD 或 YYYYMMDD"),
    end: str = Query("", description="结束日期，默认今天"),
    series: str = Query("close", description="分析序列：open/close/high/low/ohlc4"),
    smooth: int = Query(1, ge=1, le=15, description="平滑窗口；1 表示不平滑"),
    layers: int = Query(1, ge=1, le=20, description="层级数"),
    adjust: str = Query("qfq", description="复权方式：qfq 前复权 / hfq 后复权 / none 不复权"),
):
    """峰谷交替序列：返回严格交替的 extrema。"""
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = analyze_alternating_extrema(
            code,
            beg,
            end,
            series=series,
            smooth_window=smooth,
            adjust=adjust,
            layers=layers,
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
