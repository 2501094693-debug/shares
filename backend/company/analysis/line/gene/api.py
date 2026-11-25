"""股性（gene）HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.gene.config import (
    ALLOWED_PRESETS,
    DEFAULT_EXTREMA_LAYERS,
    DEFAULT_NEAR_RATIO,
    DEFAULT_PRESET,
)
from company.analysis.line.gene.service import analyze_gene

router = APIRouter()


@router.get("/api/stocks/line-gene")
def stocks_line_gene(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD 或 YYYYMMDD"),
    end: str = Query("", description="结束日期，默认今天"),
    preset: str = Query(
        DEFAULT_PRESET,
        description=f"MACD 预设：{' / '.join(ALLOWED_PRESETS)}，默认 {DEFAULT_PRESET}",
    ),
    near_ratio: float = Query(
        DEFAULT_NEAR_RATIO, ge=0.0, le=1.0, description="即将金叉相对缺口阈值"
    ),
    adjust: str = Query(
        "qfq", description="复权方式：qfq 前复权 / hfq 后复权 / none 不复权"
    ),
    extrema_layers: int = Query(
        DEFAULT_EXTREMA_LAYERS,
        ge=1,
        le=20,
        description="区间峰谷层级数，默认 3（三级峰谷）",
    ),
):
    """区间 MACD 金叉 / 即将金叉：信号日涨跌幅 + 相对此前最近峰/谷贴近度。"""
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = analyze_gene(
            code,
            beg,
            end,
            preset=preset,
            near_ratio=near_ratio,
            adjust=adjust,
            extrema_layers=extrema_layers,
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
