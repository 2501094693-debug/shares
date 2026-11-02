"""区间评估 HTTP 路由。

``/api/stocks/line-evaluate``
    最新交易日起的最大 ±band 波动区间 + 区间内最低价日 + 局部极值评分 +
    区间内个股/指数四价波动走势（上行/下行/冲高回落/探底回升/横盘）+
    股指反向偏离分（反向日数 / 有效日数 × 100）。

- ``code``        股票代码
- ``end``         结束日（默认最新交易日）
- ``factor``      波动测试口径：open/high/low/close/all（默认 close）
- ``low_factor``  找最低价日口径：open/high/low/close（默认 close）
- ``band``        波动带（小数，0.09 = ±9%）
- ``index``       对比指数公开码（默认 000001 上证指数）
- ``lookback``    波动带搜索回溯自然日（默认 900；谷序列另取最近 600 个交易日）
- ``adjust``      复权方式（qfq/hfq/none）
- ``layers`` / ``smooth``  local_extrema 层级与平滑（默认 3 / 1；谷序列用最近 600 交易日）
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.evaluate.service import (
    DEFAULT_LAYERS,
    DEFAULT_SMOOTH_WINDOW,
    analyze_evaluate,
)

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
    layers: int = Query(DEFAULT_LAYERS, ge=1, le=20, description="local_extrema 层级数（谷序列默认 3）"),
    smooth: int = Query(DEFAULT_SMOOTH_WINDOW, ge=1, le=15, description="local_extrema 平滑窗口"),
):
    """最大波动区间、最低价日评分、相对强弱分与股指反向偏离分。"""
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
