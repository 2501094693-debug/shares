"""大单资金动向统计 HTTP 路由。

``GET /api/stocks/deal-stats`` 为独立入口；同花顺资金流路由上的
``scope=big_deal_stats`` 也转到这里（见 ``company.statistics.fundflow.api``）。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.deal.fundflow.core import BIN_BY_MODES
from company.analysis.deal.fundflow.service import DEFAULT_MIN_AMOUNT, fetch_big_deal_stats

router = APIRouter()

_BIN_BY_HINT = "|".join(BIN_BY_MODES)


@router.get("/api/stocks/deal-stats")
def stocks_deal_stats(
    code: str = Query("", description="股票代码，如 002384"),
    min_amount: float = Query(
        DEFAULT_MIN_AMOUNT,
        ge=0,
        description="大单金额门槛（元），默认 1000 万，与列表接口同口径",
    ),
    bin_by: str = Query(
        "amount",
        description=f"分箱口径：amount 金额（默认）| lots 手数 | both 两套；{_BIN_BY_HINT}",
    ),
    day: str = Query("", description="交易日 YYYY-MM-DD；历史日只读缓存"),
    refresh: str = Query("0"),
):
    """四象限（主动/被动 x 买/卖）笔数、金额、手数 + 定步长分箱 + 净值。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = fetch_big_deal_stats(
            code,
            min_amount=min_amount,
            bin_by=bin_by,
            force=refresh == "1",
            day=day.strip(),
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)