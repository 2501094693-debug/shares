"""区间评估 HTTP 路由。

``/api/stocks/line-evaluate``
    最新交易日起的最大 ±band 波动区间 + 区间内最低价日 + 局部极值评分 +
    个股 / 指数 σ 坐标。

- ``code``        股票代码
- ``end``         结束日（默认最新交易日）
- ``factor``      波动测试口径：open/high/low/close/all（默认 close）
- ``low_factor``  找最低价日口径：open/high/low/close（默认 close）
- ``band``        波动带（小数，0.09 = ±9%）
- ``index``       对比指数公开码（默认 000001 上证指数）
- ``lookback``    回溯自然日（默认 900，触到数据头部会自动扩展）
- ``adjust``      复权方式（qfq/hfq/none）
- ``layers`` / ``smooth``  local_extrema 的层级与平滑窗口
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.evaluate.service import analyze_evaluate

router = APIRouter()


@router.get("/api/stocks/line-evaluate")
def stocks_line_evaluate(
    code: str = Query("", description="股票代码，如 600519"),
    end: str = Query("", description="结束日期，默认最新交易日"),
    factor: str = Query("close", description="波动口径：open/high/low/close/all"),
    low_factor: str = Query("close", description="最低价口径：open/high/low/close"),
    band: float = Query(0.09, description="波动带（小数，0.09=±9%）"),
    index: str = Query("000001", description="对比指数公开码，默认上证指数"),
    lookback: int = Query(900, ge=30, le=3650, description="回溯自然日"),
    adjust: str = Query("qfq", description="复权方式：qfq / hfq / none"),
    layers: int = Query(1, ge=1, le=20, description="local_extrema 层级数"),
    smooth: int = Query(1, ge=1, le=15, description="local_extrema 平滑窗口"),
):
    """最新交易日起的最大波动区间、最低价日评分与股 / 指 σ 坐标。"""
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = analyze_evaluate(
            code,
            end=end,
            factor=factor,
            low_factor=low_factor,
            band=band,
            index=index,
            lookback_days=lookback,
            adjust=adjust,
            layers=layers,
            smooth_window=smooth,
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
