"""当日分价表 HTTP 路由。

``GET /api/stocks/price-levels`` → ``fetch_price_levels_pack``。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.deal.price_levels.service import fetch_price_levels_pack

router = APIRouter()


@router.get("/api/stocks/price-levels")
def stocks_price_levels(
    code: str = Query("", description="股票代码，如 600519"),
    around: float | None = Query(None, description="只看某价附近（元）"),
    span: float | None = Query(
        None,
        description="配合 around 的半宽（元）；省略时 around 默认半宽 5",
    ),
    limit: int = Query(0, ge=0, description="截断条数，0=全部"),
    refresh: str = Query("0", description="1=绕过前端缓存（后端本身实时拉取）"),
):
    """当日各价位已成交汇总（价位直方图，非买卖队列）。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    _ = refresh  # 仅供前端 OrbitHttp 绕过缓存
    try:
        data = fetch_price_levels_pack(
            code,
            around=around,
            span=span,
            limit=limit,
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
