"""股票 vs 指数日线四项对比 HTTP 路由。"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.compare.service import (
    available_indices,
    compare_stock_vs_indices,
)

router = APIRouter()

_CODE_RE = re.compile(r"(\d{6})")


def _resolve_code(code: str, company: str) -> str:
    code = str(code or "").strip()
    if code:
        return code
    match = _CODE_RE.search(str(company or ""))
    return match.group(1) if match else ""


@router.get("/api/stocks/line-compare/meta")
def stocks_line_compare_meta():
    """可选指数目录 + 四项对比口径说明。"""
    return ok(available_indices())


@router.get("/api/stocks/line-compare")
def stocks_line_compare(
    code: str = Query("", description="股票代码，如 600519"),
    company: str = Query("", description="公司查询串（含 6 位代码即可）；与 code 二选一"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD 或 YYYYMMDD"),
    end: str = Query("", description="结束日期；空=今天"),
    indices: str = Query(
        "",
        description="逗号分隔指数：000001,399001,000300,000905,000852；空=五只全部",
    ),
):
    """个股日线 vs 所选指数：每日同涨/同跌/股涨指跌/股跌指涨 + 四项差值。"""
    resolved = _resolve_code(code, company)
    if not resolved:
        return err("缺少参数 code", 400)
    try:
        data = compare_stock_vs_indices(
            resolved,
            beg=beg,
            end=end,
            indices=indices or None,
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
