"""日线段划分 HTTP 路由。

``/api/stocks/line-section``：把一只股票的区间日线划分为最小段 → 同向段 →
涨 / 跌 / 横盘段（每段带 ``children`` 子段树）。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.section.service import analyze_sections

router = APIRouter()


@router.get("/api/stocks/line-section")
def stocks_line_section(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD 或 YYYYMMDD"),
    end: str = Query("", description="结束日期，默认今天"),
    series: str = Query("close", description="分析序列：open/close/high/low/ohlc4"),
    band_pct: float = Query(
        0.05, description="横盘带宽阈值（占起始价比例，0.05=5%）"
    ),
    min_runs: int = Query(3, ge=2, le=100, description="横盘至少包含的交替段数"),
    adjust: str = Query(
        "qfq", description="复权方式：qfq 前复权 / hfq 后复权 / none 不复权"
    ),
):
    """日线段划分：返回 level 2 的涨 / 跌 / 横盘段，children 为同向合并段与最小段。"""
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = analyze_sections(
            code,
            beg,
            end,
            series=series,
            band_pct=band_pct,
            min_runs=min_runs,
            adjust=adjust,
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
