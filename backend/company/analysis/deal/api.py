"""逐笔成交还原 HTTP 路由（分时成交 × 资金动向）。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.deal.service import run_deal_window_reconstruct
from company.analysis.deal.window import DEFAULT_TRADE_THRESHOLD

router = APIRouter()


@router.get("/api/stocks/deal-window")
def stocks_deal_window(
    code: str = Query("", description="股票代码，如 600519"),
    day: str = Query("", description="交易日 YYYY-MM-DD；留空为当日"),
    threshold: float = Query(
        DEFAULT_TRADE_THRESHOLD,
        gt=0,
        description="资金动向收录门槛（元），同时作为「单笔成交额上限」",
    ),
    view: str = Query(
        "all",
        description="订单视角：all=主/被买卖全部（默认）| aggressor | buy | sell | both(=all)",
    ),
    max_lookback: int = Query(
        0, ge=0, description="订单成交最多回溯多少个窗口，0 表示不限制"
    ),
    rows: str = Query(
        "1",
        description="1=返回逐笔成交序列（time/price/lots/buy_id/sell_id），0=只要统计",
    ),
    windows: str = Query("1", description="1=返回逐窗口约束明细"),
    refresh: str = Query("0"),
):
    """按 3 秒窗口做约束求解，还原逐笔成交并标注订单归属。

    约束：量守恒 + 笔数守恒 + 单笔金额上限 + 订单时序；约束下无解的窗口会
    在 ``reconcile.infeasible`` 里如实列出，不会被悄悄抹平。
    """
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    if view not in {"all", "aggressor", "buy", "sell", "both"}:
        return err("view 须为 all | aggressor | buy | sell | both", 400)
    try:
        data = run_deal_window_reconstruct(
            code,
            day=day.strip(),
            force=refresh == "1",
            threshold=threshold,
            max_lookback=max_lookback,
            view=view,
            with_rows=rows != "0",
            with_windows=windows != "0",
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
