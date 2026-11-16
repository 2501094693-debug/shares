"""个股资金流向统一入口（东财 / 同花顺路由 + 缓存）。"""

from __future__ import annotations

from typing import Any

from company.statistics.fundflow.eastmoney.fetcher import get_fund_flow as get_em_fund_flow
from company.statistics.fundflow.tonghuashun.fetcher import get_fund_flow as get_ths_fund_flow


def _normalize_source(source: str) -> str:
    text = (source or "eastmoney").strip().lower()
    if text in {"ths", "tonghuashun", "10jqka", "thsh"}:
        return "tonghuashun"
    return "eastmoney"


def get_fund_flow(
    code: str,
    *,
    scope: str = "daily",
    limit: int = 120,
    klt: int = 1,
    page: int = 1,
    order: str = "desc",
    force: bool = False,
    source: str = "eastmoney",
    min_amount: float = 10_000_000,
    day: str = "",
) -> dict[str, Any]:
    """``scope=daily|minute|snapshot|big_deal|daily_capital``；``source=eastmoney|tonghuashun``。

    同花顺：``big_deal``（HQ 大单）或 ``daily_capital``（thsdk 当日资金流拆分）。
    """
    key = (scope or "daily").strip().lower()
    ths_scopes = {
        "big_deal",
        "bigdeal",
        "ddzz",
        "tick",
        "daily_capital",
        "capital",
        "capital_flow",
        "capital_flows",
        "ths_capital",
    }
    if key in {"big_deal", "bigdeal", "ddzz", "tick"} and _normalize_source(source) != "tonghuashun":
        raise ValueError("逐笔大单仅支持 source=tonghuashun")
    if key in {
        "daily_capital",
        "capital",
        "capital_flow",
        "capital_flows",
        "ths_capital",
    } and _normalize_source(source) != "tonghuashun":
        raise ValueError("当日资金流拆分仅支持 source=tonghuashun")
    if _normalize_source(source) == "tonghuashun":
        if key not in ths_scopes:
            raise ValueError("同花顺仅支持 scope=big_deal | daily_capital")
        return get_ths_fund_flow(
            code,
            scope=key,
            limit=limit,
            page=page,
            order=order,
            force=force,
            min_amount=min_amount,
            day=day,
        )
    return get_em_fund_flow(
        code,
        scope=scope,
        limit=limit,
        klt=klt,
        force=force,
    )
