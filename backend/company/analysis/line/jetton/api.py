"""筹码分布 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.jetton.service import run_symbol, to_chart_payload

router = APIRouter()


@router.get("/api/stocks/line-jetton")
def stocks_line_jetton(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD 或 YYYYMMDD"),
    end: str = Query("", description="结束日期，默认取 beg 当日或数据末日"),
    f_mode: str = Query("triangle", description="成交分布形态"),
    k_kind: str = Query("flat", description="卖出比例形态"),
    base: float = Query(0.05, description="基准卖出比例"),
    bins: int | None = Query(None, description="价格分箱数，空则按 tick 自动"),
):
    """按日线迭代筹码分布，返回价格轴 centers 与筹码量 H（供右侧筹码峰）。"""
    if not code:
        return err("缺少参数 code", 400)
    end_s = (end or beg or "").strip()
    if not end_s:
        return err("缺少参数 end", 400)
    try:
        kw: dict = {
            "f_mode": f_mode,
            "k_kind": k_kind,
            "base": base,
            "seed": f_mode,
        }
        if bins is not None and bins > 0:
            kw["bins"] = int(bins)
        raw = run_symbol(code, beg, end_s, **kw)
        return ok(to_chart_payload(raw, beg=beg, end=end_s))
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
