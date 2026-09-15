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
) -> dict[str, Any]:
    """``scope=daily|minute|snapshot|big_deal``；``source=eastmoney|tonghuashun``。

    同花顺只提供 HQ 个股大资金动向（``scope=big_deal``）。
    """
    key = (scope or "daily").strip().lower()
    if key in {"big_deal", "bigdeal", "ddzz", "tick"} and _normalize_source(source) != "tonghuashun":
        raise ValueError("逐笔大单仅支持 source=tonghuashun")
    if _normalize_source(source) == "tonghuashun":
        if key not in {"big_deal", "bigdeal", "ddzz", "tick"}:
            raise ValueError("同花顺仅支持 scope=big_deal")
        return get_ths_fund_flow(
            code,
            limit=limit,
            page=page,
            order=order,
            force=force,
        )
    return get_em_fund_flow(
        code,
        scope=scope,
        limit=limit,
        klt=klt,
        force=force,
    )
